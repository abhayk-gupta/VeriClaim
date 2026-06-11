"""
Response schemas for cross-channel timeline + audit data.
"""
import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from app.schemas.claim import ClaimRead
from app.schemas.order import OrderRead


class InteractionLogRead(BaseModel):
    id: int
    order_id: Optional[uuid.UUID]
    claim_id: Optional[uuid.UUID]
    customer_id: Optional[uuid.UUID]
    channel: str
    direction: str
    event_type: str
    content_text: Optional[str]
    media_url: Optional[str]
    metadata: Optional[dict] = Field(default=None, validation_alias="metadata_")
    created_at: datetime

    model_config = {"from_attributes": True, "populate_by_name": True}


class AuditLogRead(BaseModel):
    id: int
    claim_id: Optional[uuid.UUID]
    event_type: str
    payload: Optional[dict]
    created_at: datetime

    model_config = {"from_attributes": True}


class OrderTimeline(BaseModel):
    """Full cross-channel history for an order, sorted chronologically."""
    order: OrderRead
    events: list[InteractionLogRead]
    claim_count: int


class ClaimDetail(ClaimRead):
    """Claim detail enriched with its audit trail and interaction events."""
    verbal_description: Optional[str] = None
    gemini_item_description: Optional[str] = None
    gemini_damage_assessment: Optional[str] = None
    gemini_label_match: Optional[bool] = None
    clarification_count: int = 0
    audit_logs: list[AuditLogRead] = []
    interactions: list[InteractionLogRead] = []

    model_config = {"from_attributes": True}
