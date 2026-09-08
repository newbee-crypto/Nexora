# backend/schemas.py
# -------------------
# Pydantic v2 request and response schemas for the API layer.
#
# WHY Pydantic schemas separate from SQLAlchemy models?
# ─────────────────────────────────────────────────────
# SQLAlchemy models (models.py) define the DATABASE structure.
# Pydantic schemas (this file) define the API CONTRACT — what the
# frontend sends and what it receives.
#
# Keeping them separate gives us:
# 1. SECURITY: We control exactly what fields are exposed.
#    (e.g., we never expose internal DB timestamps to the client unless needed)
# 2. FLEXIBILITY: The DB shape can differ from the API shape.
#    (e.g., segment_filters stored as JSON dict but returned with computed fields)
# 3. VALIDATION: Pydantic validates incoming data before it touches the DB.
#    A bad request returns 422 with a clear error message — not a DB exception.
# 4. DOCUMENTATION: FastAPI auto-generates OpenAPI docs from these schemas.
#
# Pydantic v2 note: We use `model_config = ConfigDict(from_attributes=True)`
# (replaces Pydantic v1's `orm_mode = True`) to allow creating schemas from
# SQLAlchemy ORM objects directly: CampaignResponse.model_validate(campaign_orm).

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


# ── Customer Schemas ──────────────────────────────────────────────────────────

class CustomerResponse(BaseModel):
    """
    API representation of a customer record.
    Used in list endpoints and communication detail responses.
    """
    model_config = ConfigDict(from_attributes=True)  # Allow ORM object → schema

    id: str
    name: str
    phone: str
    email: str
    channel_preference: str
    total_orders: int
    total_spent: float
    last_order_date: Optional[datetime]
    first_order_date: Optional[datetime]
    tags: list
    created_at: datetime


class CustomerStats(BaseModel):
    """Aggregate stats about the customer base — used by /customers/stats."""
    total_customers: int
    avg_spend: float
    channel_breakdown: dict[str, int]   # {"whatsapp": 200, "sms": 100, "email": 100}
    inactive_45_days: int               # Count inactive 45+ days (main win-back segment)
    inactive_60_days: int               # Count inactive 60+ days (deep churn)
    vip_count: int                      # total_spent > 5000


# ── Campaign Schemas ──────────────────────────────────────────────────────────

class CampaignCreate(BaseModel):
    """
    Payload for POST /campaigns — creates a campaign in 'draft' status.
    The AI copilot calls this implicitly via the launch_campaign tool.
    """
    name: str = Field(..., description="Human-readable campaign name", example="Win-back June 2026")
    goal: str = Field(..., description="Natural language goal from the marketer's chat", example="Win back customers inactive 45+ days")
    segment_filters: dict[str, Any] = Field(
        default_factory=dict,
        description="JSON filters: {inactive_days, min_orders, min_spent, tags}",
        example={"inactive_days": 45, "min_orders": 1},
    )
    message_template: Optional[str] = Field(
        None,
        description="Message with {{name}}, {{last_order_date}} tokens",
        example="Hi {{name}}, we miss you! Your last order was on {{last_order_date}}.",
    )
    channel: Optional[str] = Field(
        None,
        description="Delivery channel: whatsapp | sms | email",
        example="whatsapp",
    )


class CampaignResponse(BaseModel):
    """Full campaign record returned from DB."""
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    goal: str
    segment_filters: dict
    segment_size: int
    message_template: Optional[str]
    channel: Optional[str]
    status: str
    created_at: datetime
    launched_at: Optional[datetime]


class CampaignLaunchResponse(BaseModel):
    """
    Response from POST /campaigns/{id}/launch.
    Confirms the campaign was launched and shows how many messages were queued.
    """
    campaign_id: str
    status: str                 # 'launched'
    segment_size: int           # How many customers matched the filters
    communications_queued: int  # How many Communication records were created
    message: str                # Human-readable confirmation


class CampaignStats(BaseModel):
    """
    Funnel statistics for GET /campaigns/{id}/stats.
    This endpoint is polled every 3 seconds by the frontend.

    The funnel is CUMULATIVE:
    - sent:      All messages dispatched to Channel Stub (excludes still-queued)
    - delivered: Messages confirmed delivered by Channel Stub callback
    - opened:    Messages the recipient opened
    - clicked:   Messages where recipient clicked a link
    - purchased: Messages where recipient converted to a sale
    - failed:    Messages that could not be delivered

    open_rate, click_rate, and conversion_rate are computed percentages.
    estimated_cost, estimated_revenue, and roi_percentage are used for ROI estimation.
    """
    campaign_id: str
    campaign_name: str
    total: int          # Total communications for this campaign
    queued: int         # Still waiting to be dispatched
    sent: int           # Dispatched (but not yet delivered)
    delivered: int
    opened: int
    clicked: int
    purchased: int
    failed: int
    open_rate: float    # opened / delivered × 100 (%)
    click_rate: float   # clicked / opened × 100 (%)
    conversion_rate: float  # purchased / clicked × 100 (%)
    estimated_cost: float
    estimated_revenue: float
    roi_percentage: float


# ── Communication Schemas ─────────────────────────────────────────────────────

class CommunicationResponse(BaseModel):
    """Single communication record with customer name for display in the UI table."""
    model_config = ConfigDict(from_attributes=True)

    id: str
    campaign_id: str
    customer_id: str
    channel: str
    message: str
    status: str
    sent_at: Optional[datetime]
    delivered_at: Optional[datetime]
    opened_at: Optional[datetime]

    # Joined from Customer — populated manually in the router (not from ORM directly)
    customer_name: Optional[str] = None
    customer_phone: Optional[str] = None
    customer_email: Optional[str] = None


# ── Receipt (Webhook) Schemas ─────────────────────────────────────────────────

class ReceiptCreate(BaseModel):
    """
    Payload posted by the Channel Stub to POST /receipts.

    This is the INBOUND webhook payload — the Channel Stub sends this to us.
    The field names must match exactly what simulator.py sends.

    Validation here protects us from malformed callbacks:
    - If communication_id is missing → 422, not a DB crash
    - If event_type is invalid → we validate it in the router
    """
    communication_id: str = Field(..., description="UUID of the Communication record to update")
    event_type: str = Field(..., description="Event: delivered | failed | opened | clicked | read")
    event_time: Optional[datetime] = Field(None, description="When the event occurred (ISO 8601 UTC)")
    event_metadata: Optional[dict] = Field(default_factory=dict, description="Optional extra event data")


class ReceiptResponse(BaseModel):
    """Confirmation returned to the Channel Stub after processing a callback."""
    model_config = ConfigDict(from_attributes=True)

    id: str
    communication_id: str
    event_type: str
    event_time: datetime
    message: str = "Receipt processed"
