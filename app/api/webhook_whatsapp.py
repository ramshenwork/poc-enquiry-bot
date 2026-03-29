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
# 🤖 LLM SYSTEM PROMPT (MARKDOWN)
# =========================
SYSTEM_PROMPT = """
# Role
You are a professional WhatsApp assistant for **BV Textiles & Stitchers**, Hyderabad.

# Business Context
- Premium men's formal wear and custom tailoring
- Specializes in suits, tuxedos, blazers, formal shirts
- Uses brands like Raymond and Park Avenue
- Customers visit store for measurement and fitting

# Objectives
- Convert user into:
  1. Store visit
  2. WhatsApp lead
- Assist with outfit selection
- Provide a premium experience

# Rules (STRICT)
- DO NOT ask user's name if already known
- DO NOT repeat greetings
- DO NOT start every message with the user's name
- Use name naturally and sparingly
- DO NOT provide exact pricing
- Encourage store visit for measurements
- Suggest outfits based on occasion
- Ask for size OR suggest in-store measurement

# Inventory Handling
If asked about stock:
Say:
"I’m currently in queue for live inventory access, but I’ve noted your preference."

# Conversation Style
- Natural, human, professional
- Concise (no long paragraphs)
- Helpful, not robotic

# Fallback Behavior
- If unsure → guide user to visit store or connect with team
"""

# =========================
# 🤖 LLM CALL
# =========================
def generate_ai_reply(message, session):
    try:
        context = f"""
User Name: {session.get("name", "unknown")}
Intent: {session.get("intent")}
Recent Messages: {session.get("history")[-5:]}
User Message: {message}
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

    # SESSION INIT
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

    # INTENT UPDATE
    session["intent"] = detect_intent(body)

    name_prefix = get_name_prefix(session)

    # =========================
    # 📋 MENU
    # =========================
    if user_message in ["hi", "hello", "hey", "start"]:
        response.message(
            "Hi 👋 Welcome to BV Textiles & Stitchers.\n\n"
            "How can I assist you today?\n\n"
            "1️⃣ Book Appointment / Visit Store\n"
            "2️⃣ Explore Services & Products\n"
            "3️⃣ Outfit Suggestions\n"
            "4️⃣ Store Location & Timings\n"
            "5️⃣ Talk to a Specialist\n\n"
            "Reply with a number or type your requirement."
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
    # 📲 HUMAN ESCALATION
    # =========================
    elif any(word in user_message for word in ["human", "talk", "call", "contact"]):
        link = generate_whatsapp_link("919966283131", session)

        response.message(
            f"{name_prefix}Got it 👍\n\n"
            "I’ve shared your requirement with our team so you don’t have to repeat anything.\n\n"
            "Continue here:\n\n"
            f"👉 {link}"
        )

    # =========================
    # 🤖 AI FALLBACK
    # =========================
    else:
        ai_reply = generate_ai_reply(body, session)
        response.message(name_prefix + ai_reply)

    return Response(content=str(response), media_type="application/xml")