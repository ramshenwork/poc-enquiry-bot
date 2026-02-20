from fastapi import APIRouter, Request, Response, status
from twilio.request_validator import RequestValidator
from twilio.twiml.messaging_response import MessagingResponse
from app.core.config import settings
import os
import logging

router = APIRouter()
logger = logging.getLogger(settings.APP_NAME)

def validate_twilio_request(request: Request, body: dict) -> bool:
    validator = RequestValidator(os.getenv("TWILIO_AUTH_TOKEN"))
    signature = request.headers.get("X-Twilio-Signature", "")
    url = str(request.url)
    return validator.validate(url, body, signature)

@router.post("/webhook/whatsapp")
async def whatsapp_webhook(request: Request):
    form = await request.form()
    form_dict = dict(form)

    # 1️⃣ Validate signature FIRST
    if not validate_twilio_request(request, form_dict):
        logger.warning("Invalid Twilio signature")
        return Response(status_code=status.HTTP_403_FORBIDDEN)

    # 2️⃣ Now safely extract fields
    from_number = form_dict.get("From")
#   to_number = form_dict.get("To")
    body = form_dict.get("Body")

    logger.info(f"Message from {from_number}: {body}")

    # 3️⃣ Create reply
    response = MessagingResponse()
    response.message("Hello! This is your AI assistant. How can I help you today?")

    return Response(
        content=str(response),
        media_type="application/xml"
    )
