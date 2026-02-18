from fastapi import APIRouter, Request, Response, status
import twilio
from twilio.request_validator import RequestValidator
from app.core.config import settings
import os
import logging

router = APIRouter()
logger = logging.getLogger(settings.APP_NAME)

def validate_twilio_request(request: Request, body: dict) -> bool:
    validator = RequestValidator(os.getenv("TWILIO_AUTH_TOKEN"))
    signature = request.headers.get("X-Twilio-Signature", "")

    # Twilio signs the full URL
    url = str(request.url)

    return validator.validate(url, body, signature)

@router.post("/webhook/whatsapp")
async def whatsapp_webhook(request: Request):
    # Twilio sends application/x-www-form-urlencoded
    form = await request.form()
    form_dict = dict(form)

    # 1) Verify signature
    if not validate_twilio_request(request, form_dict):
        logger.warning("Invalid Twilio signature")
        return Response(status_code=status.HTTP_403_FORBIDDEN)

    # 2) Extract minimal fields safely
    from_number = form_dict.get("From")
    to_number = form_dict.get("To")
    body = form_dict.get("Body")

    logger.info(
        "Incoming WhatsApp message",
        extra={
            "from": from_number,
            "to": to_number,
            "body": body,
        },
    )

    # 3) ACK immediately (VERY IMPORTANT)
    return Response(status_code=status.HTTP_200_OK)
