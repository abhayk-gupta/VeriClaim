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
from sqlalchemy import select, desc, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_session
from app.models.claim import Claim, ClaimStatus, ClaimOutcome
from app.models.audit_log import AuditLog
from app.models.interaction_log import (
    InteractionLog, InteractionChannel, InteractionDirection,
)
from app.models.order import Order
from app.models.customer import Customer
from app.models.agent import Agent
from app.schemas.claim import ClaimRead, ClaimOverride
from app.schemas.interaction import ClaimDetail, AuditLogRead, InteractionLogRead
from app.services.interaction_log_service import log_event
from app.auth_deps import get_current_agent

router = APIRouter(prefix="/claims", tags=["claims"])


@router.get("", response_model=dict)
async def list_claims(
    status: Optional[ClaimStatus] = None,
    customer_id: Optional[uuid.UUID] = None,
    intake_channel: Optional[str] = None,
    fraud_score_min: Optional[float] = None,
    fraud_score_max: Optional[float] = None,
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_session),
    current_agent: Agent = Depends(get_current_agent),
):
    stmt = select(Claim)
    if status is not None:
        stmt = stmt.where(Claim.status == status)
    if customer_id is not None:
        stmt = stmt.where(Claim.customer_id == customer_id)
    if intake_channel is not None:
        stmt = stmt.where(Claim.intake_channel == intake_channel)
    if fraud_score_min is not None:
        stmt = stmt.where(Claim.fraud_score >= fraud_score_min)
    if fraud_score_max is not None:
        stmt = stmt.where(Claim.fraud_score <= fraud_score_max)
    
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total_count = await db.scalar(count_stmt)

    stmt = stmt.order_by(desc(Claim.created_at)).limit(limit).offset(offset)
    result = await db.execute(stmt)
    claims = list(result.scalars().all())

    return {
        "items": [ClaimRead.model_validate(c) for c in claims],
        "total": total_count
    }


@router.get("/{claim_id}", response_model=ClaimDetail)
async def get_claim_detail(
    claim_id: uuid.UUID,
    db: AsyncSession = Depends(get_session),
    current_agent: Agent = Depends(get_current_agent)
):
    stmt = select(Claim).where(Claim.id == claim_id).options(
        selectinload(Claim.order),
        selectinload(Claim.customer)
    )
    result = await db.execute(stmt)
    claim = result.scalar_one_or_none()
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
    current_agent: Agent = Depends(get_current_agent)
):
    claim = await db.get(Claim, claim_id)
    if claim is None:
        raise HTTPException(status_code=404, detail="Claim not found")

    customer = await db.get(Customer, claim.customer_id)

    claim.outcome = payload.outcome
    claim.resolution_notes = payload.resolution_notes
    claim.resolved_by = current_agent.email
    claim.resolved_at = datetime.now(timezone.utc).replace(tzinfo=None)
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
        metadata={"outcome": payload.outcome.value, "by": current_agent.email},
        commit=False,
    )
    await db.commit()
    
    # Send automated WhatsApp notification
    if payload.outcome in [ClaimOutcome.REFUND, ClaimOutcome.REPLACEMENT, ClaimOutcome.REJECTION]:
        from app.routers.dashboard_whatsapp import load_templates
        templates_dict = load_templates()
        templates_list = templates_dict.get("templates", [])
        
        target_id = "approval_notice" if payload.outcome in [ClaimOutcome.REFUND, ClaimOutcome.REPLACEMENT] else "rejection_notice"
        message_text = next((t["text"] for t in templates_list if t["id"] == target_id), None)
        
        if message_text and customer and customer.phone_e164:
            from worker.tasks.send_whatsapp import send_text as celery_send_text
            celery_send_text.delay(customer.phone_e164, message_text)
            
            await log_event(
                db,
                channel=InteractionChannel.WHATSAPP,
                direction=InteractionDirection.OUTBOUND,
                event_type="text_sent",
                order_id=claim.order_id,
                claim_id=claim.id,
                customer_id=claim.customer_id,
                content_text=message_text,
                metadata={"sent_by": "system_auto_resolution", "is_template": True},
                commit=False
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
