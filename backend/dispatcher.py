import asyncio
import json
import logging
import os
from datetime import datetime, timezone

import httpx
from dotenv import load_dotenv
from sqlalchemy import text

from database import SessionLocal
from models import Campaign, Communication, Customer

load_dotenv()

logger = logging.getLogger("crm.dispatcher")

CHANNEL_STUB_URL = os.getenv("CHANNEL_STUB_URL", "http://localhost:8001").rstrip("/")
MAX_CONCURRENT_SENDS = int(os.getenv("MAX_CONCURRENT_SENDS", "20"))


def resolve_message_tokens(template: str, customer: Customer, campaign_name: str = "WINBACK", campaign_id: str = "") -> str:
    """Replace {{token}} placeholders in message template with actual customer values."""
    if customer.last_order_date:
        day = customer.last_order_date.strftime("%d").lstrip("0") or "0"
        month = customer.last_order_date.strftime("%B")
        order_date_str = f"{day} {month}"
    else:
        order_date_str = "a while ago"

    first_name = customer.name.split()[0] if customer.name else ""
    total_spent_str = f"₹{int(round(customer.total_spent or 0)):,}"
    clean_tags = [t for t in (customer.tags or []) if not t.startswith("rfm_")]
    customer_tags_str = ", ".join(clean_tags) if clean_tags else "valued customer"

    name_lower = campaign_name.lower() if campaign_name else ""
    if "win-back" in name_lower or "winback" in name_lower:
        prefix = "WINBACK"
    elif "vip" in name_lower:
        prefix = "VIP"
    elif "gift" in name_lower:
        prefix = "GIFT"
    elif "reward" in name_lower:
        prefix = "REWARD"
    else:
        import re
        words = re.sub(r'[^a-zA-Z0-9\s]', '', campaign_name).upper().split() if campaign_name else []
        prefix = words[0][:6] if words else "CONV"

    camp_suffix = campaign_id[:4].upper() if campaign_id else "TEMP"
    cust_suffix = customer.id[:4].upper() if customer.id else "CUST"
    discount_code = f"{prefix}{camp_suffix}{cust_suffix}"

    resolved = (
        template
        .replace("{{name}}", customer.name or "")
        .replace("{{first_name}}", first_name)
        .replace("{{last_order_date}}", order_date_str)
        .replace("{{discount_code}}", discount_code)
        .replace("{{total_spent}}", total_spent_str)
        .replace("{{total_orders}}", str(customer.total_orders or 0))
        .replace("{{customer_tags}}", customer_tags_str)
    )
    return resolved


def build_segment_query(db, filters: dict):
    """
    Translate segment_filters JSON dict into a SQLAlchemy query.

    Supported filters (all optional, combined with AND):
        inactive_days  — last_order_date < NOW() - N days
        active_days    — last_order_date >= NOW() - N days
        min_orders     — total_orders >= N
        max_orders     — total_orders <= N
        min_spent      — total_spent >= N
        max_spent      — total_spent <= N
        tags           — customer must have ALL specified tags
        customer_ids   — target specific customer IDs (bypasses other filters)
        retarget_campaign_id — non-responders from a previous campaign
    """
    query = db.query(Customer)

    if "customer_ids" in filters and filters["customer_ids"]:
        query = query.filter(Customer.id.in_(filters["customer_ids"]))
        return query

    if "inactive_days" in filters:
        cutoff_date = datetime.now(timezone.utc) - __import__("datetime").timedelta(
            days=int(filters["inactive_days"])
        )
        cutoff_naive = cutoff_date.replace(tzinfo=None)
        query = query.filter(Customer.last_order_date < cutoff_naive)

    if "active_days" in filters:
        cutoff_date = datetime.now(timezone.utc) - __import__("datetime").timedelta(
            days=int(filters["active_days"])
        )
        cutoff_naive = cutoff_date.replace(tzinfo=None)
        query = query.filter(Customer.last_order_date >= cutoff_naive)

    if "min_orders" in filters:
        query = query.filter(Customer.total_orders >= int(filters["min_orders"]))

    if "max_orders" in filters:
        query = query.filter(Customer.total_orders <= int(filters["max_orders"]))

    if "min_spent" in filters:
        query = query.filter(Customer.total_spent >= float(filters["min_spent"]))

    if "max_spent" in filters:
        query = query.filter(Customer.total_spent <= float(filters["max_spent"]))

    if "tags" in filters and filters["tags"]:
        for tag in filters["tags"]:
            if db.bind.dialect.name == "sqlite":
                query = query.filter(
                    text("exists (select 1 from json_each(customers.tags) where value = :tag_val)").bindparams(
                        tag_val=tag
                    )
                )
            else:
                query = query.filter(
                    text("tags::jsonb @> :tag_val").bindparams(
                        tag_val=json.dumps([tag])
                    )
                )

    if "retarget_campaign_id" in filters:
        campaign_id = filters["retarget_campaign_id"]
        target_subquery = (
            db.query(Communication.customer_id)
            .filter(Communication.campaign_id == campaign_id)
        )
        exclude_subquery = (
            db.query(Communication.customer_id)
            .filter(
                Communication.campaign_id == campaign_id,
                Communication.status.in_(["opened", "clicked", "read"])
            )
        )
        query = query.filter(Customer.id.in_(target_subquery)).filter(Customer.id.not_in(exclude_subquery))

    return query


async def send_to_channel_stub(
    semaphore: asyncio.Semaphore,
    comm: Communication,
    customer: Customer,
) -> bool:
    """POST a single message to the Channel Stub. Returns True on 202 acceptance."""
    async with semaphore:
        payload = {
            "communication_id": comm.id,
            "customer_id": customer.id,
            "channel": comm.channel,
            "message": comm.message,
            "recipient": customer.phone if comm.channel in ("whatsapp", "sms") else customer.email,
        }
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.post(
                    f"{CHANNEL_STUB_URL}/send",
                    json=payload,
                )
                return response.status_code == 202
        except Exception as e:
            logger.error(f"[dispatcher] Failed to POST to Channel Stub for comm {comm.id[:8]}: {e}")
            return False


def allocate_channels_for_budget(customers, budget_limit: float) -> dict[str, str | None]:
    """
    Greedy channel allocation under a budget constraint.
    Sorts customers by total_spent descending, upgrades to WhatsApp/SMS where budget allows.
    Returns: dict mapping customer_id -> channel (or None if dropped due to budget).
    """
    sorted_customers = sorted(customers, key=lambda c: c.total_spent, reverse=True)
    total_count = len(sorted_customers)

    budget_paise = int(round(budget_limit * 100))
    email_cost_paise = 5
    base_cost_paise = total_count * email_cost_paise

    allocation = {}

    if base_cost_paise > budget_paise:
        affordable_emails = budget_paise // email_cost_paise
        for idx, c in enumerate(sorted_customers):
            allocation[c.id] = "email" if idx < affordable_emails else None
    else:
        leftover_paise = budget_paise - base_cost_paise
        whatsapp_upgrades = int(min(total_count, leftover_paise // 75))
        leftover_paise -= whatsapp_upgrades * 75
        sms_upgrades = int(min(total_count - whatsapp_upgrades, leftover_paise // 15))

        for idx, c in enumerate(sorted_customers):
            if idx < whatsapp_upgrades:
                allocation[c.id] = "whatsapp"
            elif idx < whatsapp_upgrades + sms_upgrades:
                allocation[c.id] = "sms"
            else:
                allocation[c.id] = "email"

    return allocation


async def dispatch_campaign(campaign_id: str) -> None:
    """
    Main campaign dispatch coroutine — runs as a BackgroundTask after launch.

    Flow:
        1. Load campaign and segment_filters
        2. Query matching customers
        3. Create Communication records (batch commit before any HTTP calls)
        4. Concurrently dispatch messages to Channel Stub via semaphore
        5. Update statuses based on Channel Stub responses
    """
    logger.info(f"[dispatcher] Starting dispatch for campaign {campaign_id[:8]}")

    db = SessionLocal()

    try:
        campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
        if not campaign:
            logger.error(f"[dispatcher] Campaign {campaign_id[:8]} not found — aborting")
            return

        if campaign.status != "launched":
            logger.warning(
                f"[dispatcher] Campaign {campaign_id[:8]} is not in 'launched' state "
                f"(got '{campaign.status}') — aborting"
            )
            return

        logger.info(
            f"[dispatcher] Campaign: '{campaign.name}' | "
            f"channel: {campaign.channel} | "
            f"filters: {campaign.segment_filters}"
        )

        customer_query = build_segment_query(db, campaign.segment_filters)
        customers = customer_query.all()

        logger.info(f"[dispatcher] Segment matched {len(customers)} customers")

        if not customers:
            logger.warning(f"[dispatcher] No customers matched the segment — nothing to dispatch")
            campaign.status = "completed"
            db.commit()
            return

        campaign.segment_size = len(customers)

        budget_limit = campaign.segment_filters.get("budget_limit") if campaign.segment_filters else None
        allocation = None
        if budget_limit is not None:
            logger.info(f"[dispatcher] Budget constraint ₹{budget_limit} found. Running channel allocation...")
            allocation = allocate_channels_for_budget(customers, float(budget_limit))
            affordable_customers = [c for c in customers if allocation.get(c.id) is not None]
            campaign.segment_size = len(affordable_customers)
            logger.info(f"[dispatcher] Budget limits target size to {campaign.segment_size} customers.")

        # Phase 1: Create all Communication records before making any HTTP calls
        communications = []
        for customer in customers:
            assigned_channel = campaign.channel
            if allocation is not None:
                assigned_channel = allocation.get(customer.id)
                if assigned_channel is None:
                    continue

            template = campaign.message_template or "Hi {{name}}, we have a message for you!"
            if template.strip().startswith("{"):
                try:
                    templates = json.loads(template)
                    template = templates.get(assigned_channel, template)
                except Exception:
                    pass

            resolved_message = resolve_message_tokens(
                template=template,
                customer=customer,
                campaign_name=campaign.name,
                campaign_id=campaign.id,
            )

            comm = Communication(
                campaign_id=campaign.id,
                customer_id=customer.id,
                channel=assigned_channel,
                message=resolved_message,
                status="queued",
            )
            db.add(comm)
            communications.append((comm, customer))

        db.flush()
        db.commit()
        logger.info(f"[dispatcher] Created {len(communications)} Communication records")

        # Phase 2: Dispatch concurrently with semaphore
        semaphore = asyncio.Semaphore(MAX_CONCURRENT_SENDS)
        send_tasks = [
            send_to_channel_stub(semaphore, comm, customer)
            for comm, customer in communications
        ]
        results = await asyncio.gather(*send_tasks, return_exceptions=True)

        # Phase 3: Update statuses
        now = datetime.now(timezone.utc)
        sent_count = 0
        failed_count = 0

        for (comm, _customer), result in zip(communications, results):
            if isinstance(result, Exception):
                logger.error(f"[dispatcher] Send task exception for comm {comm.id[:8]}: {result}")
                failed_count += 1
                continue

            if result is True:
                db.refresh(comm)
                if comm.status == "queued":
                    comm.status = "sent"
                    comm.sent_at = now
                sent_count += 1
            else:
                db.refresh(comm)
                if comm.status == "queued":
                    comm.status = "failed"
                    comm.sent_at = now
                failed_count += 1

        db.commit()
        logger.info(
            f"[dispatcher] Dispatch complete: "
            f"{sent_count} sent, {failed_count} failed "
            f"(out of {len(communications)} total)"
        )

        journey = campaign.segment_filters.get("journey") if campaign.segment_filters else None
        if journey:
            logger.info(f"[dispatcher] Journey fallback detected. Spawning journey task...")
            asyncio.create_task(run_journey_followup(campaign.id, journey))

    except Exception as e:
        db.rollback()
        logger.exception(f"[dispatcher] CRITICAL ERROR dispatching campaign {campaign_id}: {e}")
        raise
    finally:
        db.close()
        logger.info(f"[dispatcher] DB session closed for campaign {campaign_id[:8]}")


async def run_journey_followup(campaign_id: str, journey: dict) -> None:
    """Send fallback messages to recipients who did not open the initial message."""
    duration = journey.get("duration_seconds", 15)
    logger.info(f"[journey] Waiting {duration} seconds before retargeting check...")
    await asyncio.sleep(duration)

    db = SessionLocal()
    try:
        campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
        if not campaign:
            logger.error(f"[journey] Campaign {campaign_id[:8]} not found for journey fallback.")
            return

        unopened_comms = (
            db.query(Communication)
            .filter(
                Communication.campaign_id == campaign_id,
                ~Communication.status.in_(["opened", "read", "clicked", "purchased"])
            )
            .all()
        )

        if not unopened_comms:
            logger.info(f"[journey] All communications opened — no fallback needed.")
            return

        fallback_channel = journey.get("fallback_channel", "sms")
        logger.info(f"[journey] Sending fallback to {len(unopened_comms)} recipients via {fallback_channel}...")

        fallback_template = journey.get("fallback_template")
        if not fallback_template:
            if fallback_channel == "sms":
                fallback_template = "Nexora: We noticed you missed our offer! Use {{discount_code}} for a discount. Reply STOP to opt out"
            elif fallback_channel == "email":
                fallback_template = "SUBJECT: Special offer just for you! | BODY: Hi {{name}},\nWe sent you an offer on WhatsApp but didn't want you to miss out. Use coupon {{discount_code}} at checkout!\nCheers!"
            else:
                fallback_template = "Hi {{name}}, we miss you! Don't forget to use coupon {{discount_code}}."

        fallback_comms = []
        for old_comm in unopened_comms:
            customer = old_comm.customer
            resolved_message = resolve_message_tokens(
                template=fallback_template,
                customer=customer,
                campaign_name=campaign.name,
                campaign_id=campaign.id
            )

            fallback_comm = Communication(
                campaign_id=campaign.id,
                customer_id=customer.id,
                channel=fallback_channel,
                message=resolved_message,
                status="queued"
            )
            db.add(fallback_comm)
            fallback_comms.append((fallback_comm, customer))

        db.flush()
        db.commit()
        logger.info(f"[journey] Created {len(fallback_comms)} fallback communication records.")

        semaphore = asyncio.Semaphore(MAX_CONCURRENT_SENDS)
        send_tasks = [
            send_to_channel_stub(semaphore, comm, customer)
            for comm, customer in fallback_comms
        ]
        results = await asyncio.gather(*send_tasks, return_exceptions=True)

        now = datetime.now(timezone.utc)
        for (comm, _customer), result in zip(fallback_comms, results):
            db.refresh(comm)
            if result is True:
                if comm.status == "queued":
                    comm.status = "sent"
                    comm.sent_at = now
            else:
                comm.status = "failed"

        db.commit()
        logger.info(f"[journey] Retargeting fallback dispatch complete.")

    except Exception as e:
        logger.error(f"[journey] Journey execution failed: {e}")
        db.rollback()
    finally:
        db.close()
