import logging
import os

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("crm.main")

from routers import campaigns, chat, customers, opportunities, receipts

from sqlalchemy import text
from database import engine, Base
try:
    Base.metadata.create_all(bind=engine)
    if not engine.url.drivername.startswith("sqlite"):
        with engine.connect() as conn:
            conn.execute(text("ALTER TABLE communications ADD COLUMN IF NOT EXISTS purchased_at TIMESTAMP NULL;"))
            conn.commit()
        logger.info("Database migrations complete.")
    else:
        logger.info("SQLite database verified.")
except Exception as e:
    logger.error(f"Failed to execute startup migrations: {e}")

tags_metadata = [
    {
        "name": "Campaigns",
        "description": "Create, launch, retrieve and analyze campaign details, live funnel stats, and ROI metrics.",
    },
    {
        "name": "Customers",
        "description": "Retrieve customer details, filter segments, analyze channel preferences, and fetch aggregate database statistics.",
    },
    {
        "name": "Receipts",
        "description": "Inbound webhook called by the Channel Stub simulator to report message delivery events.",
    },
    {
        "name": "AI Copilot",
        "description": "Copilot chat loop. Translates plain English marketing goals into customer segments, channels, and message copy.",
    },
    {
        "name": "Opportunities",
        "description": "Identify and recommend campaign opportunities based on customer purchase recency and average order value.",
    },
    {
        "name": "System",
        "description": "Diagnostic and service health check endpoints.",
    },
]

app = FastAPI(
    title="Nexora — AI-Native Campaign Copilot",
    description=(
        "Core backend for the Nexora CRM system. Handles segmentation, "
        "AI copywriting, delivery receipt tracking, and campaign ROI analytics."
    ),
    version="1.0.0",
    openapi_tags=tags_metadata,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(customers.router)
app.include_router(campaigns.router)
app.include_router(receipts.router)
app.include_router(chat.router)
app.include_router(opportunities.router)


@app.api_route("/health", methods=["GET", "HEAD"], tags=["System"])
def health_check():
    """Health check endpoint — returns service status and config summary."""
    channel_stub = os.getenv("CHANNEL_STUB_URL", "NOT CONFIGURED")
    db_url = os.getenv("DATABASE_URL", "NOT CONFIGURED")
    if "@" in db_url:
        parts = db_url.split("@")
        auth = parts[0].split(":")
        masked_db_url = f"{auth[0]}:{auth[1]}:***@{parts[1]}"
    else:
        masked_db_url = "configured"

    return {
        "status": "healthy",
        "service": "nexora-crm-backend",
        "version": "1.0.0",
        "channel_stub_url": channel_stub,
        "database": masked_db_url,
    }


@app.get("/", tags=["System"])
def root():
    """Root endpoint — shows available API sections."""
    return {
        "message": "Nexora CRM API",
        "docs": "/docs",
        "health": "/health",
        "endpoints": {
            "customers": "/customers",
            "campaigns": "/campaigns",
            "receipts": "/receipts",
            "chat": "/chat",
            "opportunities": "/opportunities",
        },
    }
