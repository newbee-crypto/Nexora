import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


def generate_uuid() -> str:
    return str(uuid.uuid4())


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=generate_uuid)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[str] = mapped_column(String(15), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    channel_preference: Mapped[str] = mapped_column(String(20), nullable=False)

    total_orders: Mapped[int] = mapped_column(Integer, default=0)
    total_spent: Mapped[float] = mapped_column(Float, default=0.0)
    last_order_date: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    first_order_date: Mapped[datetime] = mapped_column(DateTime, nullable=True)

    tags: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    orders: Mapped[list["Order"]] = relationship(
        "Order", back_populates="customer", lazy="select"
    )
    communications: Mapped[list["Communication"]] = relationship(
        "Communication", back_populates="customer", lazy="select"
    )

    def __repr__(self) -> str:
        return f"<Customer id={self.id} name={self.name} channel={self.channel_preference}>"


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=generate_uuid)
    customer_id: Mapped[str] = mapped_column(
        String, ForeignKey("customers.id", ondelete="CASCADE"), nullable=False
    )
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    items: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(50), default="completed")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    customer: Mapped["Customer"] = relationship("Customer", back_populates="orders")

    def __repr__(self) -> str:
        return f"<Order id={self.id} customer_id={self.customer_id} amount=₹{self.amount}>"


class Campaign(Base):
    """
    Lifecycle: draft → launched → completed
    segment_filters is a JSON dict used to re-run the audience query.
    message_template supports {{token}} placeholders resolved at dispatch time.
    """

    __tablename__ = "campaigns"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=generate_uuid)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    goal: Mapped[str] = mapped_column(Text, nullable=False)
    segment_filters: Mapped[dict] = mapped_column(JSON, default=dict)
    segment_size: Mapped[int] = mapped_column(Integer, default=0)
    message_template: Mapped[str] = mapped_column(Text, nullable=True)
    channel: Mapped[str] = mapped_column(String(20), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="draft")
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    launched_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)

    communications: Mapped[list["Communication"]] = relationship(
        "Communication", back_populates="campaign", lazy="select"
    )

    def __repr__(self) -> str:
        return f"<Campaign id={self.id} name={self.name} status={self.status}>"


class Communication(Base):
    """
    One record per customer per campaign message.
    Status lifecycle: queued → sent → delivered → opened → clicked
    """

    __tablename__ = "communications"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=generate_uuid)
    campaign_id: Mapped[str] = mapped_column(
        String, ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False
    )
    customer_id: Mapped[str] = mapped_column(
        String, ForeignKey("customers.id", ondelete="CASCADE"), nullable=False
    )
    channel: Mapped[str] = mapped_column(String(20), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="queued")
    sent_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    delivered_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    opened_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    purchased_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)

    campaign: Mapped["Campaign"] = relationship(
        "Campaign", back_populates="communications"
    )
    customer: Mapped["Customer"] = relationship(
        "Customer", back_populates="communications"
    )
    receipts: Mapped[list["Receipt"]] = relationship(
        "Receipt", back_populates="communication", lazy="select"
    )

    def __repr__(self) -> str:
        return (
            f"<Communication id={self.id} campaign_id={self.campaign_id} "
            f"customer_id={self.customer_id} status={self.status}>"
        )


class Receipt(Base):
    """
    Immutable event log for every delivery event on a Communication.
    Receipts are never updated — only created (append-only).
    """

    __tablename__ = "receipts"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=generate_uuid)
    communication_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("communications.id", ondelete="CASCADE"),
        nullable=False,
    )
    event_type: Mapped[str] = mapped_column(String(20), nullable=False)
    event_time: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    # Cannot be named `metadata` — reserved by SQLAlchemy's DeclarativeBase
    event_metadata: Mapped[dict] = mapped_column(JSON, default=dict)

    communication: Mapped["Communication"] = relationship(
        "Communication", back_populates="receipts"
    )

    def __repr__(self) -> str:
        return (
            f"<Receipt id={self.id} communication_id={self.communication_id} "
            f"event_type={self.event_type}>"
        )
