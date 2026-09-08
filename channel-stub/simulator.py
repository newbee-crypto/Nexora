# channel-stub/simulator.py
# --------------------------
# The core simulation engine for the Channel Stub microservice.
#
# SYSTEM DESIGN CONTEXT — Read this first:
# ==========================================
# Real messaging providers (WhatsApp Business API, Twilio, MSG91) work like this:
#   1. You POST a message to their API → they return 202 immediately
#   2. They deliver the message asynchronously (network, device state, etc.)
#   3. They POST back to YOUR webhook URL with delivery events (delivered, opened, etc.)
#
# This simulator mirrors that exact pattern. The Channel Stub:
#   - Accepts POST /send → returns 202 immediately (non-blocking)
#   - Spawns an asyncio coroutine that "simulates" delivery with realistic delays
#   - POSTs callbacks back to the CRM's /receipts endpoint for each event
#   - Retries with exponential backoff if the CRM is unreachable
#
# WHY asyncio.create_task() instead of FastAPI's BackgroundTasks?
# → BackgroundTasks runs AFTER the response is sent, but still within the
#   same request lifecycle. It's not truly fire-and-forget.
# → asyncio.create_task() schedules the coroutine on the event loop IMMEDIATELY,
#   completely decoupled from the HTTP request. Even if the request context is
#   gone, the task keeps running. This is exactly what we need for a simulation
#   that waits 1-8 seconds after the request completes.
# → asyncio.create_task() is appropriate here because we're inside an async
#   FastAPI application — we have a running event loop available.

import asyncio
import logging
import os
import random
from datetime import datetime, timezone

import httpx
from dotenv import load_dotenv

# Load .env file so CRM_RECEIPT_URL is available
load_dotenv()

# ── Logging ───────────────────────────────────────────────────────────────────
# We use Python's built-in logging instead of print() because:
# → Logging is thread-safe and asyncio-safe
# → Log levels (DEBUG, INFO, WARNING, ERROR) let you control verbosity
# → In production (Railway), logs are captured and searchable
# → Format includes timestamp + logger name for easy debugging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("channel-stub.simulator")


# ── Environment Configuration ─────────────────────────────────────────────────
# The only external dependency this service has is knowing WHERE to send callbacks.
# Everything else is self-contained simulation logic.
CRM_RECEIPT_URL = os.getenv("CRM_RECEIPT_URL", "http://localhost:8000").rstrip("/")

# ── Per-Channel Delivery Simulation Config ────────────────────────────────────
# These configs encode the different delivery characteristics of each channel.
# Based on the product spec, these probabilities mirror real-world engagement rates
# for Indian e-commerce customers.
#
# Structure per channel:
#   fail_rate:        Probability (0.0–1.0) that delivery fails outright
#   open_rate:        Probability that a DELIVERED message is opened
#   click_rate:       Probability that an OPENED message is clicked
#   delivery_delay:   (min_seconds, max_seconds) — how long "delivery" takes
#   open_delay:       (min_seconds, max_seconds) — delay after delivery before open
#   click_delay:      (min_seconds, max_seconds) — delay after open before click
#
# Why separate delays per stage?
# → WhatsApp is instant (phone notification) — delivery is fast, open is fast
# → Email is slow (users check email less frequently) — larger delays
# → SMS is middle ground — delivered quickly, but engagement takes time
CHANNEL_CONFIGS = {
    "whatsapp": {
        "fail_rate": 0.05,          # 5% of WhatsApp messages fail to deliver
        "open_rate": 0.55,          # 55% of delivered WhatsApp messages are opened
        "click_rate": 0.20,         # 20% of opened WhatsApp messages get a link click
        "conversion_rate": 0.35,     # 35% of clicks result in a purchase
        "delivery_delay": (1, 2),   # Delivered within 1–2 seconds (very fast)
        "open_delay": (1.5, 3.5),   # User opens within 1.5–3.5 seconds after delivery
        "click_delay": (1, 2.5),    # User clicks within 1–2.5 seconds after opening
        "purchase_delay": (2, 4),    # purchase within 2-4 seconds after click
    },
    "sms": {
        "fail_rate": 0.08,          # 8% fail rate (slightly higher — telco issues)
        "open_rate": 0.35,          # 35% open rate (lower than WhatsApp)
        "click_rate": 0.10,         # 10% click rate (SMS has no rich UI, harder to click)
        "conversion_rate": 0.20,     # 20% of clicks result in a purchase
        "delivery_delay": (1, 3),   # 1–3 seconds
        "open_delay": (2, 4),       # 2-4 seconds delay
        "click_delay": (1.5, 3),
        "purchase_delay": (2.5, 4.5),
    },
    "email": {
        "fail_rate": 0.10,          # 10% fail rate (bounce rate — invalid emails, spam)
        "open_rate": 0.25,          # 25% open rate (email has lowest open rate)
        "click_rate": 0.12,         # 12% click rate (slightly better than SMS for links)
        "conversion_rate": 0.15,     # 15% of clicks result in a purchase
        "delivery_delay": (1.5, 4), # 1.5–4 seconds
        "open_delay": (2.5, 5),     # 2.5–5 seconds delay
        "click_delay": (2, 4),
        "purchase_delay": (3, 5),
    },
}

# Fallback config if an unknown channel is sent — be graceful, don't crash
DEFAULT_CONFIG = {
    "fail_rate": 0.10,
    "open_rate": 0.30,
    "click_rate": 0.10,
    "conversion_rate": 0.15,
    "delivery_delay": (1, 3),
    "open_delay": (2, 4),
    "click_delay": (1.5, 3),
    "purchase_delay": (2, 4),
}

# ── Exponential Backoff Retry Config ─────────────────────────────────────────
# If the CRM's /receipts endpoint is down or returns non-200, we retry.
# The delays form an exponential series: 0s, 1s, 2s, 4s (4 total attempts).
#
# Why exponential backoff?
# → If the CRM is temporarily overloaded, hammering it with immediate retries
#   makes the overload WORSE (thundering herd problem).
# → Exponential backoff gives the CRM time to recover between retries.
# → This pattern is used by every real webhook provider: Stripe, Twilio, etc.
# → After 4 attempts (max ~7 seconds of retries), we give up and log the failure.
#   In production, you'd put the failed event on a dead-letter queue for manual review.
RETRY_DELAYS_SECONDS = [0, 1, 2, 4]  # Attempt 1 is immediate (0s wait)
MAX_RETRY_ATTEMPTS = len(RETRY_DELAYS_SECONDS)  # = 4


async def send_callback_with_retry(
    communication_id: str,
    event_type: str,
    extra_metadata: dict = None,
) -> bool:
    """
    Send a single delivery event callback to the CRM's /receipts endpoint.
    Implements exponential backoff retry if the CRM is unavailable.

    WHY this function is `async`:
    → httpx.AsyncClient makes HTTP calls WITHOUT blocking the event loop.
    → If we used synchronous `requests.post()`, the entire asyncio event loop
      would FREEZE for the duration of the HTTP call — other simulations couldn't
      progress. async httpx lets 87 concurrent simulations all make progress.

    Args:
        communication_id: UUID of the Communication record in the CRM DB
        event_type: One of 'delivered' | 'failed' | 'opened' | 'clicked'
        extra_metadata: Optional dict of additional event data

    Returns:
        True if callback was delivered successfully, False after all retries exhausted
    """
    # Build the callback payload — matches what the CRM's POST /receipts expects
    payload = {
        "communication_id": communication_id,
        "event_type": event_type,
        # ISO 8601 UTC timestamp — consistent format across services
        "event_time": datetime.now(timezone.utc).isoformat(),
        "event_metadata": extra_metadata or {},
    }

    callback_url = f"{CRM_RECEIPT_URL}/receipts"

    # ── Retry Loop with Exponential Backoff ───────────────────────────────────
    # RETRY_DELAYS_SECONDS = [0, 1, 2, 4]
    # attempt 0: delay 0s  (immediate)
    # attempt 1: delay 1s  (wait 1s then retry)
    # attempt 2: delay 2s  (wait 2s then retry)
    # attempt 3: delay 4s  (wait 4s then retry)
    # After attempt 3 fails: log and give up
    for attempt_num, wait_seconds in enumerate(RETRY_DELAYS_SECONDS):
        if wait_seconds > 0:
            # Wait before this retry attempt (not before the first attempt)
            logger.info(
                f"[{communication_id[:8]}] Retrying callback in {wait_seconds}s "
                f"(attempt {attempt_num + 1}/{MAX_RETRY_ATTEMPTS})..."
            )
            await asyncio.sleep(wait_seconds)

        try:
            # Use httpx.AsyncClient as a context manager for proper resource cleanup.
            # timeout=10.0 prevents hanging forever if CRM is completely unreachable.
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(callback_url, json=payload)

                if response.status_code in (200, 201, 202):
                    # Success — callback delivered
                    logger.info(
                        f"[{communication_id[:8]}] Callback '{event_type}' delivered "
                        f"→ {response.status_code} (attempt {attempt_num + 1})"
                    )
                    return True
                else:
                    # CRM returned an error status — treat as failure, will retry
                    logger.warning(
                        f"[{communication_id[:8]}] Callback '{event_type}' got "
                        f"HTTP {response.status_code} from CRM (attempt {attempt_num + 1})"
                    )

        except httpx.ConnectError:
            # CRM is not reachable at all (connection refused, DNS failure, etc.)
            logger.warning(
                f"[{communication_id[:8]}] Cannot reach CRM at {callback_url} "
                f"(attempt {attempt_num + 1}/{MAX_RETRY_ATTEMPTS})"
            )
        except httpx.TimeoutException:
            # CRM took too long to respond
            logger.warning(
                f"[{communication_id[:8]}] Timeout waiting for CRM response "
                f"(attempt {attempt_num + 1}/{MAX_RETRY_ATTEMPTS})"
            )
        except Exception as e:
            # Catch-all for unexpected errors (SSL issues, malformed response, etc.)
            logger.error(
                f"[{communication_id[:8]}] Unexpected error sending callback: {e} "
                f"(attempt {attempt_num + 1}/{MAX_RETRY_ATTEMPTS})"
            )

    # ── All retries exhausted ─────────────────────────────────────────────────
    # In production: push to a dead-letter queue (Redis, SQS) for manual replay.
    # For this demo: log the failure and move on.
    logger.error(
        f"[{communication_id[:8]}] GAVE UP sending '{event_type}' callback "
        f"after {MAX_RETRY_ATTEMPTS} attempts. Event lost."
    )
    return False


async def simulate_delivery(
    communication_id: str,
    customer_id: str,
    channel: str,
    message: str,
    recipient: str,
) -> None:
    """
    The core asynchronous delivery simulation coroutine.

    This function is the heart of the Channel Stub. It mimics the async
    lifecycle of a real message provider:
        1. Wait for simulated "delivery" time
        2. Roll the dice on fail vs. delivered
        3. If delivered, wait then roll the dice on "opened"
        4. If opened, wait then roll the dice on "clicked"
        5. Send a callback to the CRM for each event

    CONCURRENCY NOTE:
        This coroutine runs as an asyncio Task — completely independently
        of the HTTP request that spawned it. `await asyncio.sleep(n)` yields
        control back to the event loop during the wait, allowing OTHER
        simulate_delivery tasks (for other messages) to make progress
        simultaneously. This is cooperative multitasking — no threads needed.

    The event loop can handle hundreds of concurrent simulate_delivery tasks
    because each task only consumes CPU during its tiny execution windows —
    the majority of time is spent "sleeping" (yielded to the loop).

    Args:
        communication_id: UUID to reference in CRM callbacks
        customer_id: For logging context only
        channel: 'whatsapp' | 'sms' | 'email'
        message: The resolved message text (for logging only)
        recipient: Phone number or email address (for logging only)
    """
    # Get channel-specific config — fall back to default for unknown channels
    config = CHANNEL_CONFIGS.get(channel.lower(), DEFAULT_CONFIG)

    logger.info(
        f"[{communication_id[:8]}] Starting {channel.upper()} simulation "
        f"for recipient={recipient}"
    )

    # ── Phase 1: Delivery Simulation ──────────────────────────────────────────
    # Simulate the time it takes for the message to reach the recipient's device.
    # asyncio.sleep() is non-blocking — the event loop continues running other tasks.
    delivery_min, delivery_max = config["delivery_delay"]
    delivery_wait = random.uniform(delivery_min, delivery_max)
    await asyncio.sleep(delivery_wait)

    # Roll the dice: does this message fail to deliver?
    if random.random() < config["fail_rate"]:
        # Message failed — send 'failed' callback and STOP. No further events.
        logger.info(
            f"[{communication_id[:8]}] Simulated FAILURE "
            f"(fail_rate={config['fail_rate']*100:.0f}%)"
        )
        await send_callback_with_retry(
            communication_id=communication_id,
            event_type="failed",
            extra_metadata={"reason": "simulated_delivery_failure", "channel": channel},
        )
        return  # Early exit — failed messages don't get opened or clicked

    # Message delivered successfully — send 'delivered' callback
    logger.info(
        f"[{communication_id[:8]}] Simulated DELIVERED "
        f"after {delivery_wait:.1f}s"
    )
    await send_callback_with_retry(
        communication_id=communication_id,
        event_type="delivered",
        extra_metadata={"channel": channel, "delivery_seconds": round(delivery_wait, 2)},
    )

    # ── Phase 2: Open Simulation ──────────────────────────────────────────────
    # After delivery, wait a bit — then simulate whether the recipient opens it.
    # Only DELIVERED messages can be opened.
    open_min, open_max = config["open_delay"]
    open_wait = random.uniform(open_min, open_max)
    await asyncio.sleep(open_wait)

    if random.random() >= config["open_rate"]:
        # Recipient didn't open the message — simulation ends here
        logger.info(
            f"[{communication_id[:8]}] Not opened "
            f"(open_rate={config['open_rate']*100:.0f}%)"
        )
        return

    # Recipient opened the message — send 'opened' callback
    logger.info(f"[{communication_id[:8]}] Simulated OPENED")
    await send_callback_with_retry(
        communication_id=communication_id,
        event_type="opened",
        extra_metadata={"channel": channel},
    )

    # ── Phase 3: Click Simulation ─────────────────────────────────────────────
    # After opening, simulate whether the recipient clicks a link in the message.
    # Only OPENED messages can be clicked.
    click_min, click_max = config["click_delay"]
    click_wait = random.uniform(click_min, click_max)
    await asyncio.sleep(click_wait)

    if random.random() >= config["click_rate"]:
        # Recipient didn't click — simulation ends
        logger.info(
            f"[{communication_id[:8]}] Not clicked "
            f"(click_rate={config['click_rate']*100:.0f}%)"
        )
        return

    # Recipient clicked a link — send 'clicked' callback
    logger.info(f"[{communication_id[:8]}] Simulated CLICKED")
    await send_callback_with_retry(
        communication_id=communication_id,
        event_type="clicked",
        extra_metadata={"channel": channel},
    )

    # ── Phase 4: Purchase Simulation ──────────────────────────────────────────
    # After clicking, simulate whether the recipient actually completes a purchase.
    # Only CLICKED messages can lead to a purchase.
    purchase_min, purchase_max = config.get("purchase_delay", (2, 4))
    purchase_wait = random.uniform(purchase_min, purchase_max)
    await asyncio.sleep(purchase_wait)

    if random.random() >= config.get("conversion_rate", 0.15):
        # Recipient didn't purchase — simulation ends
        logger.info(
            f"[{communication_id[:8]}] Not converted to purchase "
            f"(conversion_rate={config.get('conversion_rate', 0.15)*100:.0f}%)"
        )
        return

    # Recipient purchased — send 'purchased' callback
    logger.info(f"[{communication_id[:8]}] Simulated PURCHASED (Converted!)")
    await send_callback_with_retry(
        communication_id=communication_id,
        event_type="purchased",
        extra_metadata={"channel": channel, "conversion": True},
    )

    logger.info(
        f"[{communication_id[:8]}] Simulation complete: delivered → opened → clicked → purchased"
    )
