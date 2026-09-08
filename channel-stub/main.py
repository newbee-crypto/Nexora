# channel-stub/main.py
# ---------------------
# The Channel Stub is a completely SEPARATE FastAPI microservice.
# It runs on port 8001 and has ZERO knowledge of the CRM database.
#
# Its entire job:
#   1. Accept POST /send → validate payload → return 202 immediately
#   2. Fire an asyncio background task to simulate message delivery
#   3. That background task POSTs callbacks back to the CRM's /receipts endpoint
#
# SEPARATION OF CONCERNS:
# → This service could be deployed by a different team, in a different language,
#   on a different cloud provider — the CRM doesn't care. It only cares about
#   receiving callbacks at /receipts with the right payload format.
# → This mirrors real-world microservice design: Twilio is a separate company from
#   your backend, but they communicate via the same webhook pattern.
#
# IMPORTANT: This file is STANDALONE — do NOT import from the backend/ directory.
# It has its own venv, requirements.txt, and .env file.

import asyncio
import logging
import os
from datetime import datetime, timezone

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# Import the simulation engine from simulator.py (same directory)
from simulator import simulate_delivery, CHANNEL_CONFIGS

# Load .env before anything else
load_dotenv()

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("channel-stub.main")


# ── FastAPI Application ───────────────────────────────────────────────────────
app = FastAPI(
    title="Nexora Channel Stub",
    description=(
        "Simulates async message delivery for WhatsApp, SMS, and Email. "
        "Accepts POST /send → returns 202 immediately → fires async callbacks "
        "to the CRM /receipts endpoint with delivery events."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# ── CORS Middleware ────────────────────────────────────────────────────────────
# The Channel Stub is called by the CRM backend (server-to-server), not by a browser.
# CORS doesn't technically matter here, but we add it for completeness and
# so the Swagger UI (/docs) works if opened in a browser.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Request Schema ────────────────────────────────────────────────────────────
class SendRequest(BaseModel):
    """
    Payload sent by the CRM dispatcher to POST /send.

    Pydantic validates this automatically — if any required field is missing
    or has the wrong type, FastAPI returns 422 Unprocessable Entity before
    our code even runs. This means our handler always receives a valid object.

    Field descriptions explain the contract between CRM and Channel Stub.
    """

    communication_id: str = Field(
        ...,
        description="UUID of the Communication record in the CRM database. "
                    "Used in callbacks so the CRM can identify which record to update.",
        example="550e8400-e29b-41d4-a716-446655440000",
    )
    customer_id: str = Field(
        ...,
        description="UUID of the Customer. Used for logging and tracing only — "
                    "the Channel Stub has no access to the CRM database.",
        example="7c9e6679-7425-40de-944b-e07fc1f90ae7",
    )
    channel: str = Field(
        ...,
        description="Delivery channel: 'whatsapp' | 'sms' | 'email'",
        example="whatsapp",
    )
    message: str = Field(
        ...,
        description="The fully resolved message text (tokens already replaced). "
                    "Used for logging only.",
        example="Hi Priya, we miss you! Come back and shop.",
    )
    recipient: str = Field(
        ...,
        description="Phone number (for WhatsApp/SMS) or email address (for Email). "
                    "Used for logging only — we don't actually send anything.",
        example="+919876543210",
    )


# ── Response Schema ───────────────────────────────────────────────────────────
class SendResponse(BaseModel):
    """
    Immediate response returned by POST /send.

    status='accepted' signals that the message has been QUEUED for delivery,
    not that it has been delivered. This is the 202 Accepted pattern.
    """

    status: str = Field("accepted", description="Always 'accepted' for a 202 response")
    communication_id: str = Field(..., description="Echoes back the communication_id for confirmation")
    message: str = Field(..., description="Human-readable confirmation message")
    channel: str = Field(..., description="The channel the message will be sent on")


# ── POST /send — The Core Endpoint ────────────────────────────────────────────
@app.post(
    "/send",
    status_code=202,    # 202 Accepted — "I received your request and will process it asynchronously"
    response_model=SendResponse,
    summary="Accept a message for async delivery simulation",
    tags=["Delivery"],
)
async def send_message(request: SendRequest):
    """
    Accept a message and immediately return 202, then simulate delivery asynchronously.

    THE CRITICAL DESIGN: WHY 202 AND NOT 200?
    ─────────────────────────────────────────
    HTTP 200 OK means "I processed your request and here is the result."
    HTTP 202 Accepted means "I received your request and will process it eventually."

    202 is the CORRECT status for async operations because:
    → The CRM dispatcher doesn't need to wait for delivery to complete
    → Delivery can take 1–60+ seconds (real WhatsApp/Email is even slower)
    → If we blocked waiting for delivery, the CRM request would time out
    → The CRM will receive delivery status via the /receipts callback instead

    THE asyncio.create_task() PATTERN:
    ───────────────────────────────────
    asyncio.create_task(coroutine) schedules the coroutine to run on the event loop
    immediately, but the current function continues running without waiting for it.
    When we hit `return SendResponse(...)`, the HTTP response is sent to the caller.
    The simulate_delivery task keeps running in the background independently.

    Compare to alternatives:
    ✗ `await simulate_delivery(...)` → BLOCKS the response. Caller waits 1–60s. Bad.
    ✗ `threading.Thread(target=...)` → Works but spawns OS threads. asyncio is better
      for I/O-bound work (HTTP callbacks, sleeps).
    ✗ `BackgroundTasks.add_task()` → Runs AFTER the response, but within the request
      context. Fine for short tasks. For our multi-stage simulation (3 callbacks,
      each with retries and delays), create_task is more appropriate.
    ✓ `asyncio.create_task(...)` → Fire-and-forget. Response sent immediately.
      Task runs independently on the event loop. Perfect for this use case.
    """

    # Validate that the channel is one we know how to simulate
    # (We'll still simulate unknown channels using DEFAULT_CONFIG, but warn)
    channel_lower = request.channel.lower()
    if channel_lower not in CHANNEL_CONFIGS:
        logger.warning(
            f"Unknown channel '{request.channel}' — using default simulation config. "
            f"Valid channels: {list(CHANNEL_CONFIGS.keys())}"
        )

    logger.info(
        f"[{request.communication_id[:8]}] POST /send received: "
        f"channel={request.channel}, recipient={request.recipient}"
    )

    # ── Fire and forget the simulation task ────────────────────────────────────
    # This line is the KEY to the non-blocking design.
    # create_task() registers the coroutine with the event loop and returns
    # a Task object immediately — we don't await it.
    #
    # The task will run concurrently with everything else on the event loop.
    # When simulate_delivery awaits asyncio.sleep(), it yields control and
    # OTHER tasks (other simulate_delivery calls, other HTTP requests) can run.
    task = asyncio.create_task(
        simulate_delivery(
            communication_id=request.communication_id,
            customer_id=request.customer_id,
            channel=channel_lower,
            message=request.message,
            recipient=request.recipient,
        )
    )

    # Add a done-callback to log if the task crashes with an unhandled exception.
    # Without this, exceptions in create_task() are silently swallowed.
    def _on_task_done(t: asyncio.Task):
        if t.cancelled():
            logger.warning(f"[{request.communication_id[:8]}] Simulation task was cancelled")
        elif t.exception():
            logger.error(
                f"[{request.communication_id[:8]}] Simulation task raised exception: "
                f"{t.exception()}"
            )

    task.add_done_callback(_on_task_done)

    # ── Return 202 immediately ─────────────────────────────────────────────────
    # This response is sent to the CRM dispatcher RIGHT NOW, before any delivery
    # simulation happens. The simulation is running in the background.
    return SendResponse(
        status="accepted",
        communication_id=request.communication_id,
        message=f"Message queued for {request.channel} delivery. "
                f"Callbacks will be sent to CRM as delivery events occur.",
        channel=request.channel,
    )


# ── GET /health ────────────────────────────────────────────────────────────────
@app.api_route(
    "/health",
    methods=["GET", "HEAD"],
    summary="Health check",
    tags=["System"],
)
def health_check():
    """
    Health check endpoint for Docker, Railway, and the CRM's connectivity tests.

    Returns the current CRM_RECEIPT_URL so operators can verify the callback
    target is correctly configured without needing to inspect the .env file.
    """
    crm_url = os.getenv("CRM_RECEIPT_URL", "NOT CONFIGURED")
    return {
        "status": "healthy",
        "service": "nexora-channel-stub",
        "version": "1.0.0",
        "crm_receipt_url": crm_url,      # Shows operators where callbacks go
        "supported_channels": list(CHANNEL_CONFIGS.keys()),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ── GET / (root) ───────────────────────────────────────────────────────────────
@app.get("/", tags=["System"])
def root():
    """Root endpoint — confirms service is running and shows API docs link."""
    return {
        "message": "Nexora Channel Stub is running",
        "docs": "/docs",
        "health": "/health",
        "send_endpoint": "POST /send",
    }
