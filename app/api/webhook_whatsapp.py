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

# 🧠 In-memory session store (POC)
sessions = {}

# 🔐 Twilio validation
def validate_twilio_request(request: Request, body: dict) -> bool:
    validator = RequestValidator(os.getenv("TWILIO_AUTH_TOKEN"))
    signature = request.headers.get("X-Twilio-Signature", "")
    return validator.validate(str(request.url), body, signature)

# 👤 Name extraction
def extract_name(message):
    patterns = ["i am", "i'm", "my name is"]
    for p in patterns:
        if p in message.lower():
            return message.lower().split(p)[-1].strip().title()
    return None

# 📲 WhatsApp escalation link
def generate_whatsapp_link(phone, session):
    summary = f"""
Customer Name: {session.get('name', 'Not provided')}
Requirement: {session.get('intent', 'General inquiry')}
"""
    return f"https://wa.me/{phone}?text={urllib.parse.quote(summary)}"

# 🤖 LLM
def generate_ai_reply(message, session):
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are an assistant for BV Textiles & Stitchers.\n"
                        "- Capture user's name and use it naturally\n"
                        "- Do NOT give exact pricing\n"
                        "- Suggest store visit\n"
                        "- Ask for size or fitting preference\n"
                        "- Recommend outfits\n"
                        "- If inventory asked: say you are still in queue for inventory access\n"
                        "- Be human and conversational\n"
                    )
                },
                {"role": "user", "content": message}
            ],
            max_tokens=120
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"LLM Error: {e}")
        return "I’m here to help! Could you please tell me a bit more about what you're looking for?"

# 📲 MAIN ENDPOINT
@router.post("/webhook/whatsapp")
async def whatsapp_webhook(request: Request):
    form = await request.form()
    data = dict(form)

    if not validate_twilio_request(request, data):
        return Response(status_code=status.HTTP_403_FORBIDDEN)

    from_number = data.get("From")
    body = data.get("Body", "")

    # 🧠 INIT SESSION
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

    # 👤 Name detection
    name = extract_name(body)
    if name:
        session["name"] = name

    name_prefix = f"{session['name']}, " if session["name"] else ""

    # 📍 Location intent
    if any(word in user_message for word in ["location", "where", "address"]):
        response.message(
            f"{name_prefix}📍 We are located at Basheer Bagh, Hyderabad.\n\n"
            "Here’s our Google Maps location:\n"
            "https://www.google.com/maps/search/?api=1&query=BV+Textiles+Basheer+Bagh+Hyderabad\n\n"
            "You can visit us between 11 AM and 9:30 PM."
        )

    # 📲 Human help
    elif any(word in user_message for word in ["human", "call", "contact", "talk"]):
        link = generate_whatsapp_link("9966283131", session)  # 🔁 replace with real number

        response.message(
            f"{name_prefix}I’ll connect you with our team for personalized assistance.\n\n"
            f"👉 {link}"
        )

    # 👔 Appointment / fitting flow
    elif "appointment" in user_message or "visit" in user_message:
        response.message(
            f"{name_prefix}We’d love to help you get the perfect fit!\n\n"
            "Would you like to visit for measurements, or do you already know your size?\n\n"
            "We recommend visiting for best results."
        )

    # 🧵 Inventory placeholder
    elif "fabric" in user_message or "collection" in user_message:
        response.message(
            f"{name_prefix}We have a wide range of premium fabrics including Raymond and Park Avenue.\n\n"
            "I’m currently in queue for live inventory access.\n"
            "But I’ve noted your preference.\n\n"
            "Would you like help choosing a style?"
        )

    # 💰 Pricing (controlled)
    elif "price" in user_message or "cost" in user_message:
        response.message(
            f"{name_prefix}Pricing depends on fabric and customization.\n\n"
            "We recommend visiting our store or connecting with our team for accurate details.\n\n"
            "Would you like me to connect you?"
        )

    # 🧠 LLM fallback
    else:
        ai_reply = generate_ai_reply(body, session)
        response.message(name_prefix + ai_reply)

    return Response(content=str(response), media_type="application/xml")