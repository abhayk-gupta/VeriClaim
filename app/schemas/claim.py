import uuid
from datetime import datetime
from typing import Optional, Any
from pydantic import BaseModel

from app.models.claim import ClaimType, ClaimStatus, ClaimOutcome


class ClaimCreate(BaseModel):
    order_id: uuid.UUID
    customer_id: uuid.UUID
    claim_type: Optional[ClaimType] = None
    call_sid: Optional[str] = None
    verbal_description: Optional[str] = None
    intake_channel: Optional[str] = None


class ClaimRead(BaseModel):
    id: uuid.UUID
    order_id: uuid.UUID
    customer_id: uuid.UUID
    claim_type: Optional[ClaimType]
    status: ClaimStatus
    outcome: Optional[ClaimOutcome]
    intake_channel: Optional[str]
    fraud_score: Optional[float]
    fraud_signals: Optional[dict]
    policy_verdict: Optional[str]
    gemini_damage_severity: Optional[str]
    gemini_damage_type: Optional[str]
    gemini_confidence: Optional[float]
    agent_reasoning: Optional[str]
    resolution_notes: Optional[str]
    resolved_at: Optional[datetime]
    media_r2_key_item: Optional[str]
    media_r2_key_label: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}


class ClaimOverride(BaseModel):
    outcome: ClaimOutcome
    resolution_notes: str


class ClaimListFilter(BaseModel):
    status: Optional[ClaimStatus] = None
    customer_id: Optional[uuid.UUID] = None
    intake_channel: Optional[str] = None
    limit: int = 50
    offset: int = 0
