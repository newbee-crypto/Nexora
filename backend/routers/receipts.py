import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models import Communication, Receipt
from schemas import ReceiptCreate, ReceiptResponse

logger = logging.getLogger("crm.receipts")

router = APIRouter(prefix="/receipts", tags=["Receipts"])

# Status priority — only upgrade, never downgrade communication status
STATUS_PRIORITY: dict[str, int] = {
    "queued": 0,
    "sent": 1,
    "failed": 2,
    "delivered": 3,
    "opened": 4,
    "read": 4,
    "clicked": 5,
    "purchased": 6,
}

VALID_EVENT_TYPES = frozenset({"delivered", "failed", "opened", "read", "clicked", "purchased"})


@router.post("", response_model=ReceiptResponse, status_code=200)
def ingest_receipt(payload: ReceiptCreate, db: Session = Depends(get_db)):
    """Accept a delivery event callback from the Channel Stub."""
    if payload.event_type not in VALID_EVENT_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown event_type '{payload.event_type}'. Valid types: {sorted(VALID_EVENT_TYPES)}",
        )

    comm = (
        db.query(Communication)
        .filter(Communication.id == payload.communication_id)
        .first()
    )
    if not comm:
        logger.warning(
            f"[receipts] Received event '{payload.event_type}' for unknown "
            f"communication_id='{payload.communication_id}'"
        )
        raise HTTPException(
            status_code=404,
            detail=f"Communication {payload.communication_id} not found.",
        )

    event_time = payload.event_time or datetime.now(timezone.utc)

    current_priority = STATUS_PRIORITY.get(comm.status, 0)
    incoming_priority = STATUS_PRIORITY.get(payload.event_type, 0)

    status_was_updated = False

    if incoming_priority > current_priority:
        old_status = comm.status
        comm.status = payload.event_type
        status_was_updated = True

        logger.info(
            f"[receipts] comm={comm.id[:8]} "
            f"status: '{old_status}' → '{payload.event_type}'"
        )

        if payload.event_type == "delivered" and comm.delivered_at is None:
            comm.delivered_at = event_time.replace(tzinfo=None) if event_time.tzinfo else event_time

        elif payload.event_type in ("opened", "read") and comm.opened_at is None:
            comm.opened_at = event_time.replace(tzinfo=None) if event_time.tzinfo else event_time

        elif payload.event_type == "purchased" and comm.purchased_at is None:
            comm.purchased_at = event_time.replace(tzinfo=None) if event_time.tzinfo else event_time

            try:
                from models import Order
                import random

                customer = comm.customer
                if customer:
                    products_list = [
                        "Kurta", "Saree", "Dupatta", "Lehenga", "Salwar Kameez",
                        "Dhoti", "Sherwani", "Anarkali", "Palazzo Pants", "Chikankari Kurti",
                        "Bandhani Dupatta", "Phulkari Dupatta", "Kanjivaram Silk Saree",
                        "Banarasi Silk Saree", "Ikat Kurta", "Linen Shirt", "Cotton Kurta",
                        "Ethnic Jacket", "Waistcoat", "Formal Trousers",
                    ]
                    items_bought = random.sample(products_list, k=random.randint(1, 3))

                    avg_spent = customer.total_spent / max(customer.total_orders, 1)
                    min_amt = max(200.0, avg_spent * 0.7)
                    max_amt = min(10000.0, avg_spent * 1.3)
                    new_amount = round(random.uniform(min_amt, max_amt), 2)

                    new_order = Order(
                        customer_id=customer.id,
                        amount=new_amount,
                        items=items_bought,
                        status="completed",
                        created_at=event_time.replace(tzinfo=None) if event_time.tzinfo else event_time
                    )
                    db.add(new_order)

                    customer.total_orders += 1
                    customer.total_spent = round(customer.total_spent + new_amount, 2)
                    customer.last_order_date = event_time.replace(tzinfo=None) if event_time.tzinfo else event_time

                    logger.info(
                        f"[receipts] Auto-created Order for customer={customer.id[:8]} "
                        f"amount=₹{new_amount}"
                    )
            except Exception as order_err:
                logger.error(f"[receipts] Failed to auto-create order on purchase event: {order_err}")

    else:
        logger.debug(
            f"[receipts] comm={comm.id[:8]} skipping status update "
            f"(current='{comm.status}' >= incoming='{payload.event_type}')"
        )

    receipt = Receipt(
        communication_id=comm.id,
        event_type=payload.event_type,
        event_time=event_time.replace(tzinfo=None) if event_time.tzinfo else event_time,
        event_metadata=payload.event_metadata or {},
    )
    db.add(receipt)

    try:
        db.commit()
        db.refresh(receipt)
    except Exception as e:
        db.rollback()
        logger.error(f"[receipts] DB commit failed for event '{payload.event_type}': {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to persist receipt — Channel Stub should retry",
        )

    logger.info(
        f"[receipts] Processed: event='{payload.event_type}' "
        f"comm={comm.id[:8]} "
        f"status_updated={status_was_updated} "
        f"receipt_id={receipt.id[:8]}"
    )

    return ReceiptResponse(
        id=receipt.id,
        communication_id=receipt.communication_id,
        event_type=receipt.event_type,
        event_time=receipt.event_time,
        message=f"Receipt processed. Communication status: {comm.status}",
    )
