"""
Claims REST API (`/api/v1/claims`).

  GET  /claims                list claims with filters
  GET  /claims/{id}           full detail + audit trail + interaction events
  POST /claims/{id}/override  manual agent override of the outcome
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.models.claim import Claim, ClaimStatus, ClaimOutcome
from app.models.audit_log import AuditLog
from app.models.interaction_log import (
    InteractionLog, InteractionChannel, InteractionDirection,
)
from app.schemas.claim import ClaimRead, ClaimOverride
from app.schemas.interaction import ClaimDetail, AuditLogRead, InteractionLogRead
from app.services.interaction_log_service import log_event

router = APIRouter(prefix="/claims", tags=["claims"])


@router.get("", response_model=list[ClaimRead])
async def list_claims(
    status: Optional[ClaimStatus] = None,
    customer_id: Optional[uuid.UUID] = None,
    intake_channel: Optional[str] = None,
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_session),
):
    stmt = select(Claim)
    if status is not None:
        stmt = stmt.where(Claim.status == status)
    if customer_id is not None:
        stmt = stmt.where(Claim.customer_id == customer_id)
    if intake_channel is not None:
        stmt = stmt.where(Claim.intake_channel == intake_channel)
    stmt = stmt.order_by(desc(Claim.created_at)).limit(limit).offset(offset)

    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.get("/{claim_id}", response_model=ClaimDetail)
async def get_claim_detail(claim_id: uuid.UUID, db: AsyncSession = Depends(get_session)):
    claim = await db.get(Claim, claim_id)
    if claim is None:
        raise HTTPException(status_code=404, detail="Claim not found")

    audit_rows = (await db.execute(
        select(AuditLog).where(AuditLog.claim_id == claim_id).order_by(AuditLog.created_at)
    )).scalars().all()
    interaction_rows = (await db.execute(
        select(InteractionLog).where(InteractionLog.claim_id == claim_id)
        .order_by(InteractionLog.created_at)
    )).scalars().all()

    detail = ClaimDetail.model_validate(claim)
    detail.audit_logs = [AuditLogRead.model_validate(a) for a in audit_rows]
    detail.interactions = [InteractionLogRead.model_validate(i) for i in interaction_rows]
    return detail


@router.post("/{claim_id}/override", response_model=ClaimRead)
async def override_claim(
    claim_id: uuid.UUID,
    payload: ClaimOverride,
    db: AsyncSession = Depends(get_session),
):
    claim = await db.get(Claim, claim_id)
    if claim is None:
        raise HTTPException(status_code=404, detail="Claim not found")

    claim.outcome = payload.outcome
    claim.resolution_notes = payload.resolution_notes
    claim.resolved_by = payload.resolved_by
    claim.resolved_at = datetime.now(timezone.utc)
    claim.status = _status_for_outcome(payload.outcome)

    await log_event(
        db,
        channel=InteractionChannel.API,
        direction=InteractionDirection.INTERNAL,
        event_type="manual_override",
        order_id=claim.order_id,
        claim_id=claim.id,
        customer_id=claim.customer_id,
        content_text=payload.resolution_notes,
        metadata={"outcome": payload.outcome.value, "by": payload.resolved_by},
        commit=False,
    )
    await db.commit()
    await db.refresh(claim)
    return claim


def _status_for_outcome(outcome: ClaimOutcome) -> ClaimStatus:
    return {
        ClaimOutcome.REPLACEMENT: ClaimStatus.APPROVED,
        ClaimOutcome.REFUND: ClaimStatus.APPROVED,
        ClaimOutcome.REJECTION: ClaimStatus.REJECTED,
        ClaimOutcome.MANUAL_REVIEW: ClaimStatus.ESCALATED,
    }.get(outcome, ClaimStatus.ESCALATED)
