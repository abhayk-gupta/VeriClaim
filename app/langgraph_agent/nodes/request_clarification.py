"""
Node: request_clarification (CLARIFY branch, terminal for this graph run)

When `decide_outcome` returns `clarify`, this node — instead of escalating to a
human — places a targeted outbound voice call to collect the one missing piece of
evidence. It:

  1. increments the claim's clarification_count and sets PENDING_CLARIFICATION
  2. writes audit + interaction-log entries
  3. enqueues the outbound_call Celery task with a question tailored to why the
     verdict was uncertain

The customer's spoken answer comes back via /webhooks/voice/clarification-response,
which re-enqueues process_claim. The decide_outcome guard escalates instead of
looping once clarification_count reaches the policy maximum.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from app.database import AsyncSessionLocal
from app.models.claim import Claim, ClaimStatus
from app.models.audit_log import AuditLog
from app.services.interaction_log_service import log_event
from app.models.interaction_log import InteractionChannel, InteractionDirection
from app.langgraph_agent.state import ClaimState

logger = logging.getLogger(__name__)


def _build_question(state: ClaimState) -> str:
    anomalies = [a.lower() for a in state.get("gemini_anomalies", [])]
    label_match = state.get("gemini_label_match")

    if label_match is False or any("label" in a for a in anomalies):
        return ("We couldn't clearly read the shipping label in your photo. "
                "Can you describe the carrier and tracking number, or tell us what "
                "the label looks like?")
    severity = (state.get("gemini_damage_severity") or "none").lower()
    if severity in {"none", "not_applicable", ""}:
        return ("We had trouble seeing the damage in your photo. "
                "Can you describe exactly where the item is damaged and what happened?")
    return ("We need a little more detail to finish your claim. "
            "Can you describe the problem with your order in your own words?")


async def request_clarification(state: ClaimState) -> dict:
    claim_id = uuid.UUID(state["claim_id"])
    question = _build_question(state)

    async with AsyncSessionLocal() as session:
        claim = await session.get(Claim, claim_id)
        if claim is None:
            logger.error("request_clarification: claim %s not found", claim_id)
            return {}

        claim.clarification_count = (claim.clarification_count or 0) + 1
        claim.status = ClaimStatus.PENDING_CLARIFICATION
        claim.updated_at = datetime.now(timezone.utc)

        session.add(AuditLog(
            claim_id=claim.id,
            event_type="clarification_triggered",
            payload={
                "attempt": claim.clarification_count,
                "question": question,
                "fraud_score": state.get("fraud_score"),
                "confidence": state.get("gemini_confidence"),
            },
        ))
        await log_event(
            session,
            channel=InteractionChannel.SYSTEM,
            direction=InteractionDirection.INTERNAL,
            event_type="clarification_requested",
            order_id=claim.order_id,
            claim_id=claim.id,
            customer_id=claim.customer_id,
            content_text=question,
            metadata={"attempt": claim.clarification_count},
            commit=False,
        )
        await session.commit()

    phone = state.get("customer_phone")
    if phone:
        _enqueue_outbound_call(str(claim_id), question, phone)
    else:
        logger.warning("No customer phone for claim %s; cannot place clarification call", claim_id)

    logger.info("Clarification requested for claim %s (attempt %s)",
                claim_id, state.get("clarification_count", 0) + 1)
    return {"final_status": ClaimStatus.PENDING_CLARIFICATION.value}


def _enqueue_outbound_call(claim_id: str, question: str, phone: str) -> None:
    from worker.celery_app import celery_app
    celery_app.send_task(
        "worker.tasks.outbound_call.place_clarification_call",
        args=[claim_id, question, phone],
        queue="calls",
    )
