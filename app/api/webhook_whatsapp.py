from fastapi import APIRouter, Request, Response, status
from twilio.request_validator import RequestValidator
from twilio.twiml.messaging_response import MessagingResponse
from openai import OpenAI
from app.core.config import settings
import os
import logging

router = APIRouter()
logger = logging.getLogger(settings.APP_NAME)

# Initialize OpenAI client
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# 🔐 Validate Twilio Request
def validate_twilio_request(request: Request, body: dict) -> bool:
    validator = RequestValidator(os.getenv("TWILIO_AUTH_TOKEN"))
    signature = request.headers.get("X-Twilio-Signature", "")
    url = str(request.url)
    return validator.validate(url, body, signature)

# 🤖 LLM fallback
def generate_ai_reply(user_message: str) -> str:
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a WhatsApp assistant for ABC Services. "
                        "Be polite, concise, and helpful. "
                        "Only answer business-related queries. "
                        "If unsure, ask the user to be more specific."
                        "If user is doesnt find the appointment he is looking ask him if he wants to schedule by service, least traffic service or specific timings"
                        "pricing discounts are available on code = AI10"
                        "location is banjara hills and mention once you have access you would send a live location / route to the place"
                    )
                },
                {"role": "user", "content": user_message}
            ],
            max_tokens=100
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"LLM Error: {e}")
        return "Sorry, something went wrong. Please try again later."

# 📲 Webhook Endpoint
@router.post("/webhook/whatsapp")
async def whatsapp_webhook(request: Request):
    form = await request.form()
    form_dict = dict(form)

    # 1️⃣ Validate signature
    if not validate_twilio_request(request, form_dict):
        logger.warning("Invalid Twilio signature")
        return Response(status_code=status.HTTP_403_FORBIDDEN)

    # 2️⃣ Extract message
    from_number = form_dict.get("From")
    body = form_dict.get("Body")

    logger.info(f"Message from {from_number}: {body}")

    # 3️⃣ Normalize input
    user_message = (body or "").strip().lower()

    # 4️⃣ Create response
    response = MessagingResponse()

    # 🟢 Menu Logic
    if user_message in ["hi", "hello", "menu", "start"]:
        response.message(
            "Hi 👋 Welcome to ABC Services.\n\n"
            "1️⃣ Book appointment\n"
            "2️⃣ Pricing info\n"
            "3️⃣ Talk to human\n"
            "4️⃣ Location\n\n"
            "Reply with a number."
        )

    elif user_message == "1":
        response.message(
            "📅 Great! Please share your preferred date and time.\n\n"
            "Example: 25 Feb at 4 PM"
        )

    elif user_message == "2":
        response.message(
            "💰 Our pricing starts from ₹999 depending on the service.\n"
            "Would you like to book an appointment?"
        )

    elif user_message == "3":
        response.message(
            "👨‍💼 A team member will contact you shortly.\n"
            "Please share your name."
        )

    elif user_message == "4":
        response.message(
            "📍 We are located at:\n"
            "ABC Services\n"
            "Banjara Hills, Hyderabad\n\n"
            "Open: 10 AM – 7 PM"
        )

    # 🤖 LLM Fallback
    else:
        ai_reply = generate_ai_reply(body)
        response.message(ai_reply)

    return Response(
        content=str(response),
        media_type="application/xml"
    )