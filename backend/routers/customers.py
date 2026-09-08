import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from database import get_db
from models import Customer
from schemas import CustomerResponse, CustomerStats

logger = logging.getLogger("crm.customers")

# NOTE: /customers/stats must be defined before /{customer_id} to avoid
# "stats" being matched as an ID parameter.
router = APIRouter(prefix="/customers", tags=["Customers"])


@router.get("/stats", response_model=CustomerStats)
def get_customer_stats(db: Session = Depends(get_db)):
    """Aggregate statistics about the customer base for the dashboard KPIs."""
    total = db.query(func.count(Customer.id)).scalar() or 0
    avg_spend = db.query(func.avg(Customer.total_spent)).scalar() or 0.0

    channel_rows = (
        db.query(Customer.channel_preference, func.count(Customer.id))
        .group_by(Customer.channel_preference)
        .all()
    )
    channel_breakdown = {channel: count for channel, count in channel_rows}

    now = datetime.now(timezone.utc)
    cutoff_45 = (now - timedelta(days=45)).replace(tzinfo=None)
    cutoff_60 = (now - timedelta(days=60)).replace(tzinfo=None)

    inactive_45 = (
        db.query(func.count(Customer.id))
        .filter(Customer.last_order_date < cutoff_45)
        .scalar() or 0
    )
    inactive_60 = (
        db.query(func.count(Customer.id))
        .filter(Customer.last_order_date < cutoff_60)
        .scalar() or 0
    )

    vip_count = (
        db.query(func.count(Customer.id))
        .filter(Customer.total_spent > 5000)
        .scalar() or 0
    )

    return CustomerStats(
        total_customers=total,
        avg_spend=round(float(avg_spend), 2),
        channel_breakdown=channel_breakdown,
        inactive_45_days=inactive_45,
        inactive_60_days=inactive_60,
        vip_count=vip_count,
    )


@router.get("", response_model=list[CustomerResponse])
def list_customers(
    skip: int = Query(0, ge=0, description="Pagination offset"),
    limit: int = Query(50, ge=1, le=200, description="Max records (max 200)"),
    channel: str = Query(None, description="Filter by channel: whatsapp | sms | email"),
    tag: str = Query(None, description="Filter by tag: vip | new | at-risk"),
    db: Session = Depends(get_db),
):
    """List customers with optional channel/tag filtering and pagination."""
    import json
    from sqlalchemy import text

    query = db.query(Customer).order_by(Customer.created_at.desc())

    if channel:
        query = query.filter(Customer.channel_preference == channel.lower())

    if tag:
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

    customers = query.offset(skip).limit(limit).all()
    return customers


@router.get("/{customer_id}/activity")
def get_customer_activity(customer_id: str, db: Session = Depends(get_db)):
    """Retrieve a customer's purchase orders and communication logs."""
    customer = db.query(Customer).filter(Customer.id == customer_id).first()
    if not customer:
        raise HTTPException(
            status_code=404,
            detail=f"Customer {customer_id} not found",
        )

    from models import Order, Communication, Campaign
    orders = db.query(Order).filter(Order.customer_id == customer_id).order_by(Order.created_at.desc()).all()

    comms = (
        db.query(Communication, Campaign.name.label("campaign_name"))
        .join(Campaign, Communication.campaign_id == Campaign.id)
        .filter(Communication.customer_id == customer_id)
        .order_by(Communication.sent_at.desc().nullslast(), Communication.id.desc())
        .all()
    )

    orders_list = [
        {
            "id": o.id,
            "amount": o.amount,
            "items": o.items,
            "status": o.status,
            "created_at": o.created_at
        }
        for o in orders
    ]

    comms_list = [
        {
            "id": c.id,
            "campaign_id": c.campaign_id,
            "campaign_name": campaign_name,
            "channel": c.channel,
            "message": c.message,
            "status": c.status,
            "sent_at": c.sent_at,
            "delivered_at": c.delivered_at,
            "opened_at": c.opened_at,
            "purchased_at": c.purchased_at
        }
        for c, campaign_name in comms
    ]

    return {
        "customer": {
            "id": customer.id,
            "name": customer.name,
            "email": customer.email,
            "phone": customer.phone,
            "channel_preference": customer.channel_preference,
            "total_orders": customer.total_orders,
            "total_spent": customer.total_spent,
            "tags": customer.tags,
            "last_order_date": customer.last_order_date,
            "created_at": customer.created_at
        },
        "orders": orders_list,
        "communications": comms_list
    }


@router.get("/{customer_id}", response_model=CustomerResponse)
def get_customer(customer_id: str, db: Session = Depends(get_db)):
    """Retrieve a single customer's full profile."""
    customer = db.query(Customer).filter(Customer.id == customer_id).first()
    if not customer:
        raise HTTPException(
            status_code=404,
            detail=f"Customer {customer_id} not found",
        )
    return customer


@router.post("/refresh-rfm")
def refresh_rfm_segments(db: Session = Depends(get_db)):
    """Recalculate RFM categories and write them as tags for all customers."""
    from rfm import recalculate_rfm_tags
    try:
        counts = recalculate_rfm_tags(db)
        db.commit()
        return {
            "success": True,
            "message": "RFM segments recalculated and saved successfully.",
            "counts": counts
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to refresh RFM tags: {str(e)}"
        )
