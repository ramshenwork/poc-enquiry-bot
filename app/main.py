from fastapi import FastAPI
from app.api.health import router as health_router
from app.api.webhook_whatsapp import router as whatsapp_router
from app.core.logger import setup_logger
from app.core.config import settings

logger = setup_logger()

app = FastAPI(title=settings.APP_NAME)

app.include_router(health_router)
app.include_router(whatsapp_router)

@app.on_event("startup")
def startup_event():
    logger.info("Application starting...")
    logger.info(f"Environment: {settings.ENV}")

@app.on_event("shutdown")
def shutdown_event():
    logger.info("Application shutting down...")
