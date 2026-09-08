import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from database import get_db
from dispatcher import dispatch_campaign
from models import Campaign, Communication, Customer
from schemas import (
    CampaignCreate,
    CampaignLaunchResponse,
    CampaignResponse,
    CampaignStats,
    CommunicationResponse,
)

logger = logging.getLogger("crm.campaigns")

router = APIRouter(prefix="/campaigns", tags=["Campaigns"])


@router.post("", response_model=CampaignResponse, status_code=201)
def create_campaign(payload: CampaignCreate, db: Session = Depends(get_db)):
    """Create a new campaign in 'draft' status."""
    campaign = Campaign(
        name=payload.name,
        goal=payload.goal,
        segment_filters=payload.segment_filters,
        message_template=payload.message_template,
        channel=payload.channel,
        status="draft",
    )
    db.add(campaign)
    db.commit()
    db.refresh(campaign)
    logger.info(f"Campaign created: '{campaign.name}' (id={campaign.id[:8]})")
    return campaign


@router.get("", response_model=list[CampaignResponse])
def list_campaigns(
    skip: int = Query(0, description="Pagination offset"),
    limit: int = Query(50, description="Max records to return"),
    db: Session = Depends(get_db),
):
    """List all campaigns ordered by creation time (newest first)."""
    campaigns = (
        db.query(Campaign)
        .order_by(Campaign.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return campaigns


@router.get("/{campaign_id}/stats", response_model=CampaignStats)
def get_campaign_stats(campaign_id: str, db: Session = Depends(get_db)):
    """
    Aggregate funnel statistics for a campaign.
    Uses cumulative counts: opened includes clicked & purchased, etc.
    """
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail=f"Campaign {campaign_id} not found")

    status_rows = (
        db.query(
            Communication.status,
            func.count(Communication.id).label("count"),
        )
        .filter(Communication.campaign_id == campaign_id)
        .group_by(Communication.status)
        .all()
    )

    status_counts: dict[str, int] = {row.status: row.count for row in status_rows}

    total = sum(status_counts.values())
    queued = status_counts.get("queued", 0)
    sent = status_counts.get("sent", 0)
    delivered = status_counts.get("delivered", 0)
    opened = status_counts.get("opened", 0)
    clicked = status_counts.get("clicked", 0)
    purchased = status_counts.get("purchased", 0)
    failed = status_counts.get("failed", 0)

    sent_cumulative = total - queued
    delivered_cumulative = delivered + opened + clicked + purchased
    opened_cumulative = opened + clicked + purchased
    clicked_cumulative = clicked + purchased

    open_rate = round((opened_cumulative / delivered_cumulative * 100), 1) if delivered_cumulative > 0 else 0.0
    click_rate = round((clicked_cumulative / opened_cumulative * 100), 1) if opened_cumulative > 0 else 0.0
    conversion_rate = round((purchased / clicked_cumulative * 100), 1) if clicked_cumulative > 0 else 0.0

    estimated_cost = 0.0
    for comm in campaign.communications:
        if comm.status != "queued":
            c_cost = 0.80
            if comm.channel == "sms":
                c_cost = 0.20
            elif comm.channel == "email":
                c_cost = 0.05
            estimated_cost += c_cost
    estimated_cost = round(estimated_cost, 2)

    purchased_customers = (
        db.query(Customer.total_spent, Customer.total_orders)
        .join(Communication, Communication.customer_id == Customer.id)
        .filter(Communication.campaign_id == campaign_id)
        .filter(Communication.status == "purchased")
        .all()
    )

    estimated_revenue = sum(
        round(c.total_spent / max(c.total_orders, 1), 2)
        for c in purchased_customers
    )
    estimated_revenue = round(estimated_revenue, 2)

    if estimated_cost > 0:
        roi_percentage = round(((estimated_revenue - estimated_cost) / estimated_cost) * 100, 1)
    else:
        roi_percentage = 0.0

    return CampaignStats(
        campaign_id=campaign.id,
        campaign_name=campaign.name,
        total=total,
        queued=queued,
        sent=sent_cumulative,
        delivered=delivered_cumulative,
        opened=opened_cumulative,
        clicked=clicked_cumulative,
        purchased=purchased,
        failed=failed,
        open_rate=open_rate,
        click_rate=click_rate,
        conversion_rate=conversion_rate,
        estimated_cost=estimated_cost,
        estimated_revenue=estimated_revenue,
        roi_percentage=roi_percentage,
    )


@router.get("/{campaign_id}/communications", response_model=list[CommunicationResponse])
def get_campaign_communications(
    campaign_id: str,
    skip: int = Query(0),
    limit: int = Query(50),
    db: Session = Depends(get_db),
):
    """List all individual message records for a campaign with customer details."""
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail=f"Campaign {campaign_id} not found")

    rows = (
        db.query(Communication, Customer)
        .join(Customer, Communication.customer_id == Customer.id)
        .filter(Communication.campaign_id == campaign_id)
        .order_by(Communication.sent_at.desc().nullslast())
        .offset(skip)
        .limit(limit)
        .all()
    )

    result = []
    for comm, customer in rows:
        response = CommunicationResponse(
            id=comm.id,
            campaign_id=comm.campaign_id,
            customer_id=comm.customer_id,
            channel=comm.channel,
            message=comm.message,
            status=comm.status,
            sent_at=comm.sent_at,
            delivered_at=comm.delivered_at,
            opened_at=comm.opened_at,
            customer_name=customer.name,
            customer_phone=customer.phone,
            customer_email=customer.email,
        )
        result.append(response)

    return result


@router.get("/{campaign_id}", response_model=CampaignResponse)
def get_campaign(campaign_id: str, db: Session = Depends(get_db)):
    """Single campaign record."""
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail=f"Campaign {campaign_id} not found")
    return campaign


@router.post("/{campaign_id}/launch", response_model=CampaignLaunchResponse)
async def launch_campaign(
    campaign_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """
    Launch a campaign: set status to 'launched', then trigger async dispatch.
    Returns immediately — dispatch runs in background after the response is sent.
    """
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail=f"Campaign {campaign_id} not found")

    if campaign.status == "launched":
        raise HTTPException(
            status_code=409,
            detail=f"Campaign {campaign_id} is already launched.",
        )
    if campaign.status == "completed":
        raise HTTPException(
            status_code=409,
            detail=f"Campaign {campaign_id} is already completed.",
        )

    from dispatcher import build_segment_query
    preview_count = build_segment_query(db, campaign.segment_filters).count()

    if preview_count == 0:
        raise HTTPException(
            status_code=400,
            detail=f"No customers match the segment filters: {campaign.segment_filters}.",
        )

    campaign.status = "launched"
    campaign.launched_at = datetime.now(timezone.utc)
    campaign.segment_size = preview_count
    db.commit()

    logger.info(
        f"Campaign '{campaign.name}' (id={campaign_id[:8]}) launched. "
        f"Audience: {preview_count} customers."
    )

    background_tasks.add_task(dispatch_campaign, campaign_id)

    return CampaignLaunchResponse(
        campaign_id=campaign.id,
        status="launched",
        segment_size=preview_count,
        communications_queued=preview_count,
        message=(
            f"Campaign '{campaign.name}' is now live! "
            f"Dispatching to {preview_count} customers via {campaign.channel}. "
            f"Check /campaigns/{campaign_id}/stats for live delivery updates."
        ),
    )


@router.post("/reset", status_code=200)
def reset_campaigns(db: Session = Depends(get_db)):
    """Wipe all campaigns, communications, and receipts. Preserves customers and orders."""
    try:
        from sqlalchemy import text
        from routers.opportunities import clear_opportunities_cache

        db.execute(text("TRUNCATE campaigns, communications, receipts CASCADE;"))
        db.commit()
        clear_opportunities_cache()
        logger.info("All campaign history reset.")
        return {"status": "success", "message": "Campaign history reset to zero successfully."}
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to reset campaigns: {e}")
        raise HTTPException(status_code=500, detail=f"Database reset error: {str(e)}")


@router.post("/reset-db", status_code=200)
def reset_database(db: Session = Depends(get_db)):
    """Wipe all tables and re-seed with 400 Indian customer profiles."""
    try:
        from sqlalchemy import text
        from seed import seed_database
        from routers.opportunities import clear_opportunities_cache

        db.execute(text("TRUNCATE customers, orders, campaigns, communications, receipts CASCADE;"))
        db.commit()
        seed_database()
        clear_opportunities_cache()
        logger.info("Database re-seeded with 400 customers.")
        return {"status": "success", "message": "Database successfully re-seeded with 400 clean profiles."}
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to re-seed database: {e}")
        raise HTTPException(status_code=500, detail=f"Database re-seed error: {str(e)}")
