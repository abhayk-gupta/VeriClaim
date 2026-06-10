import uuid
from datetime import datetime
from enum import Enum
from typing import Optional, TYPE_CHECKING

from sqlalchemy import String, Text, Float, Boolean, ForeignKey, func
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.customer import Customer
    from app.models.order import Order


class ClaimType(str, Enum):
    DAMAGED = "damaged"
    NOT_RECEIVED = "not_received"
    WRONG_ITEM = "wrong_item"
    MISSING_PARTS = "missing_parts"


class ClaimStatus(str, Enum):
    PENDING_MEDIA = "pending_media"
    MEDIA_RECEIVED = "media_received"
    ANALYZING = "analyzing"
    PENDING_CLARIFICATION = "pending_clarification"
    APPROVED = "approved"
    REJECTED = "rejected"
    ESCALATED = "escalated"
    REFUNDED = "refunded"
    REPLACED = "replaced"


class ClaimOutcome(str, Enum):
    REPLACEMENT = "replacement"
    REFUND = "refund"
    REJECTION = "rejection"
    MANUAL_REVIEW = "manual_review"


class Claim(Base):
    __tablename__ = "claims"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    order_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orders.id"), index=True)
    customer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("customers.id"), index=True)
    claim_type: Mapped[Optional[ClaimType]] = mapped_column(SQLEnum(ClaimType), nullable=True)
    status: Mapped[ClaimStatus] = mapped_column(SQLEnum(ClaimStatus), default=ClaimStatus.PENDING_MEDIA)
    outcome: Mapped[Optional[ClaimOutcome]] = mapped_column(SQLEnum(ClaimOutcome), nullable=True)

    # Voice bot data
    call_sid: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    verbal_description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    transcript_raw: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # WhatsApp media — original Meta media IDs (for audit)
    media_url_item: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    media_url_label: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    media_received_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)

    # Cloudflare R2 keys (permanent storage — never expire)
    media_r2_key_item: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    media_r2_key_label: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Gemini analysis results
    gemini_item_description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    gemini_damage_assessment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    gemini_damage_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    gemini_damage_severity: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    gemini_label_match: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    gemini_confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Fraud analysis
    fraud_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    fraud_signals: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    # Policy and reasoning
    policy_verdict: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    agent_reasoning: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Clarification loop guard
    clarification_count: Mapped[int] = mapped_column(default=0)

    # Resolution
    resolution_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    resolved_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # Channel that originated this claim
    intake_channel: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)  # "whatsapp" | "voice"

    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[Optional[datetime]] = mapped_column(onupdate=func.now(), nullable=True)

    order: Mapped["Order"] = relationship("Order", back_populates="claims")
    customer: Mapped["Customer"] = relationship("Customer", back_populates="claims")

    def __repr__(self) -> str:
        return f"<Claim id={self.id} status={self.status} outcome={self.outcome}>"
