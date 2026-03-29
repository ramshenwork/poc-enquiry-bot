from fastapi import APIRouter, Request, Response, status
from twilio.request_validator import RequestValidator
from twilio.twiml.messaging_response import MessagingResponse
from openai import OpenAI
from app.core.config import settings
import os
import logging
import urllib.parse

router = APIRouter()
logger = logging.getLogger(settings.APP_NAME)

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# =========================
# 🧠 SESSION STORE (POC)
# =========================
sessions = {}

# =========================
# 🔐 SECURITY
# =========================
def validate_twilio_request(request: Request, body: dict) -> bool:
    validator = RequestValidator(os.getenv("TWILIO_AUTH_TOKEN"))
    signature = request.headers.get("X-Twilio-Signature", "")
    return validator.validate(str(request.url), body, signature)

# =========================
# 👤 NAME EXTRACTION
# =========================
def extract_name(message):
    patterns = ["i am", "i'm", "my name is"]
    for p in patterns:
        if p in message.lower():
            return message.lower().split(p)[-1].strip().title()
    return None

# =========================
# 🎯 INTENT DETECTION
# =========================
def detect_intent(message):
    msg = message.lower()

    if "wedding" in msg:
        return "Wedding outfit"
    elif "office" in msg:
        return "Office formal wear"
    elif "suit" in msg:
        return "Suit requirement"
    elif "tuxedo" in msg:
        return "Tuxedo"
    elif "alteration" in msg:
        return "Alteration"
    elif "fabric" in msg:
        return "Fabric inquiry"

    return "General inquiry"

# =========================
# 🧾 SUMMARY GENERATION
# =========================
def generate_summary(session):
    history = session.get("history", [])[-5:]

    summary = f"""
🧵 BV Textiles Lead

👤 Name: {session.get("name", "Not provided")}
🎯 Requirement: {session.get("intent", "General inquiry")}

💬 Recent Conversation:
"""

    for msg in history:
        summary += f"- {msg}\n"

    summary += "\nPlease assist the customer further."

    return summary

# =========================
# 📲 WHATSAPP ESCALATION LINK
# =========================
def generate_whatsapp_link(phone, session):
    summary = generate_summary(session)
    encoded = urllib.parse.quote(summary)
    return f"https://wa.me/{phone}?text={encoded}"

# =========================
# 🤖 SYSTEM PROMPT (CLEAN + GUARDED)
# =========================
SYSTEM_PROMPT = """
# Role
You are a professional WhatsApp assistant for BV Textiles & Stitchers (Hyderabad).

# Objective
Convert users into:
- Store visits
- Qualified leads

# Business Context
- Premium men's formal wear
- Custom tailoring (suits, tuxedos, blazers)
- Raymond & Park Avenue fabrics
- In-store measurement preferred

# Rules (STRICT)
- Do NOT ask name if already known
- Do NOT repeat greetings
- Do NOT overuse the name
- Do NOT give exact pricing
- Encourage store visit
- Ask about occasion, style, or size
- Keep replies concise

# Inventory Handling
If asked about stock:
Say:
"I’m currently in queue for live inventory access, but I’ve noted your preference."

# Conversation Style
- Natural
- Helpful
- Slightly premium tone
- Ask 1–2 smart follow-up questions

# Behavior
- Guide conversation (not passive)
- Suggest next step
"""

# =========================
# 🤖 LLM CALL
# =========================
def generate_ai_reply(message, session):
    try:
        context = f"""
Customer Name: {session.get("name", "unknown")}
Detected Intent: {session.get("intent")}
Conversation So Far: {session.get("history")[-5:]}

Latest User Message: {message}

Your task:
- Understand requirement
- Suggest outfit or next step
- Ask relevant follow-up (size / visit / occasion)
"""

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": context}
            ],
            max_tokens=120
        )

        return response.choices[0].message.content.strip()

    except Exception as e:
        logger.error(f"LLM Error: {e}")
        return "I’m here to help! Could you tell me a bit more about your requirement?"

# =========================
# 🧠 NAME USAGE CONTROL
# =========================
def get_name_prefix(session):
    if session["name"] and len(session["history"]) > 2:
        return f"{session['name']}, "
    return ""

# =========================
# 📲 MAIN WEBHOOK
# =========================
@router.post("/webhook/whatsapp")
async def whatsapp_webhook(request: Request):
    form = await request.form()
    data = dict(form)

    if not validate_twilio_request(request, data):
        return Response(status_code=status.HTTP_403_FORBIDDEN)

    from_number = data.get("From")
    body = data.get("Body", "")

    # INIT SESSION
    if from_number not in sessions:
        sessions[from_number] = {
            "name": None,
            "intent": None,
            "history": []
        }

    session = sessions[from_number]
    session["history"].append(body)

    user_message = body.strip().lower()
    response = MessagingResponse()

    # NAME DETECTION
    name = extract_name(body)
    if name and not session["name"]:
        session["name"] = name

    # INTENT FIX (NO OVERWRITE BUG)
    detected_intent = detect_intent(body)
    if session["intent"] is None or session["intent"] == "General inquiry":
        session["intent"] = detected_intent

    name_prefix = get_name_prefix(session)

    # =========================
    # 👋 GREETING (NO MENU)
    # =========================
    if user_message in ["hi", "hello", "hey", "start"]:
        response.message(
            "Hi 👋 Welcome to BV Textiles & Stitchers.\n\n"
            "I can help you with:\n"
            "• Outfit suggestions (weddings, office, occasions)\n"
            "• Custom tailoring & fittings\n"
            "• Fabric selection guidance\n"
            "• Store location & visit planning\n"
            "• Connecting you with our team\n\n"
            "Tell me what you're looking for 🙂"
        )
        return Response(content=str(response), media_type="application/xml")

    # =========================
    # 📍 LOCATION
    # =========================
    elif any(word in user_message for word in ["location", "where", "address"]):
        response.message(
            f"{name_prefix}📍 Basheer Bagh, Hyderabad\n\n"
            "https://www.google.com/maps/search/?api=1&query=BV+Textiles+Basheer+Bagh+Hyderabad\n\n"
            "🕒 11 AM – 9:30 PM"
        )

    # =========================
    # 👔 GUIDED SELLING
    # =========================
    elif "wedding" in user_message or "suit" in user_message:
        response.message(
            f"{name_prefix}That sounds great — we can help you with that.\n\n"
            "Are you looking for a classic formal look or something more modern?\n\n"
            "Also, would you prefer visiting for measurements or do you already know your size?"
        )

    # =========================
    # 📲 HUMAN ESCALATION
    # =========================
    elif any(word in user_message for word in ["human", "talk", "call", "contact"]):
        link = generate_whatsapp_link("919966283131", session)

        response.message(
            f"{name_prefix}Got it 👍\n\n"
            "I’ve shared your requirement with our team so you don’t have to repeat anything.\n\n"
            "They’ll take over from here:\n\n"
            f"👉 {link}"
        )

    # =========================
    # 🤖 AI FALLBACK
    # =========================
    else:
        ai_reply = generate_ai_reply(body, session)
        response.message(name_prefix + ai_reply)

    return Response(content=str(response), media_type="application/xml")