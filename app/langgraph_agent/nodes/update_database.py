"""
Node: update_database (terminal)

Persists the full analysis outcome to the claim, writes the audit trail
(AuditLog) and the customer-facing event (InteractionLog), and enqueues the
WhatsApp resolution message — except for `clarify`, where Phase 4's
clarification flow takes over instead of sending a resolution.

If an upstream node set `state["error"]`, the claim is parked in ESCALATED for
manual review rather than receiving an automated verdict.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from app.database import AsyncSessionLocal
from app.models.claim import Claim, ClaimStatus, ClaimOutcome
from app.models.customer import Customer
from app.models.audit_log import AuditLog
from app.services.interaction_log_service import log_event
from app.models.interaction_log import InteractionChannel, InteractionDirection
from app.langgraph_agent.state import ClaimState

logger = logging.getLogger(__name__)

_TERMINAL_STATUSES = {
    ClaimStatus.APPROVED.value,
    ClaimStatus.REJECTED.value,
    ClaimStatus.ESCALATED.value,
    ClaimStatus.REFUNDED.value,
    ClaimStatus.REPLACED.value,
}


async def update_database(state: ClaimState) -> dict:
    claim_id = uuid.UUID(state["claim_id"])

    async with AsyncSessionLocal() as session:
        claim = await session.get(Claim, claim_id)
        if claim is None:
            logger.error("update_database: claim %s not found", claim_id)
            return {}

        if state.get("error"):
            _apply_error(claim, state)
        else:
            _apply_analysis(claim, state)

        # Audit trail (internal reasoning).
        session.add(AuditLog(
            claim_id=claim.id,
            event_type="outcome_decided",
            payload=_audit_payload(state),
        ))

        # Customer-facing timeline event.
        await log_event(
            session,
            channel=InteractionChannel.SYSTEM,
            direction=InteractionDirection.INTERNAL,
            event_type="verdict_issued",
            order_id=claim.order_id,
            claim_id=claim.id,
            customer_id=claim.customer_id,
            content_text=claim.agent_reasoning,
            metadata={
                "decision": state.get("decision"),
                "outcome": state.get("outcome"),
                "fraud_score": state.get("fraud_score"),
                "confidence": state.get("gemini_confidence"),
            },
            commit=False,
        )

        # Need the phone for the outbound message before the session closes.
        customer = await session.get(Customer, claim.customer_id)
        phone = customer.phone_e164 if customer else None
        order_external = state.get("order_external", "")

        await session.commit()

    # Enqueue the resolution message (skip for clarify / error-escalation).
    decision = state.get("decision")
    if phone and decision and decision != "clarify" and not state.get("error"):
        _enqueue_resolution(phone, decision, order_external)

    return {}


def _apply_analysis(claim: Claim, state: ClaimState) -> None:
    claim.gemini_item_description = state.get("gemini_item_description")
    claim.gemini_damage_assessment = state.get("gemini_assessment")
    claim.gemini_damage_type = state.get("gemini_damage_type")
    claim.gemini_damage_severity = state.get("gemini_damage_severity")
    claim.gemini_label_match = state.get("gemini_label_match")
    claim.gemini_confidence = state.get("gemini_confidence")

    claim.fraud_score = state.get("fraud_score")
    claim.fraud_signals = state.get("fraud_signals")
    claim.policy_verdict = state.get("policy_verdict")
    claim.agent_reasoning = state.get("agent_reasoning")

    outcome = state.get("outcome")
    claim.outcome = ClaimOutcome(outcome) if outcome else None

    status_value = state.get("final_status", ClaimStatus.ANALYZING.value)
    claim.status = ClaimStatus(status_value)
    if status_value in _TERMINAL_STATUSES:
        claim.resolved_at = datetime.now(timezone.utc)
        claim.resolved_by = "ai_agent"


def _apply_error(claim: Claim, state: ClaimState) -> None:
    claim.status = ClaimStatus.ESCALATED
    claim.outcome = ClaimOutcome.MANUAL_REVIEW
    claim.agent_reasoning = f"Automated analysis failed: {state.get('error')}. Escalated for review."
    claim.resolved_by = "ai_agent_error"


def _audit_payload(state: ClaimState) -> dict:
    return {
        "decision": state.get("decision"),
        "outcome": state.get("outcome"),
        "final_status": state.get("final_status"),
        "policy_verdict": state.get("policy_verdict"),
        "policy_reasons": state.get("policy_reasons"),
        "fraud_score": state.get("fraud_score"),
        "fraud_signals": state.get("fraud_signals"),
        "gemini": {
            "damage_type": state.get("gemini_damage_type"),
            "damage_severity": state.get("gemini_damage_severity"),
            "label_match": state.get("gemini_label_match"),
            "confidence": state.get("gemini_confidence"),
            "anomalies": state.get("gemini_anomalies"),
        },
        "error": state.get("error"),
    }


# ── Resolution message ──────────────────────────────────────────────────────────

def _resolution_message(decision: str, order_external: str) -> str:
    ext = f" for order *{order_external}*" if order_external else ""
    if decision == "replacement":
        return (f"Good news! ✅ Your claim{ext} has been approved and a *replacement* "
                "is being arranged. You'll receive tracking details soon.")
    if decision == "refund":
        return (f"Good news! ✅ Your claim{ext} has been approved and a *refund* has been "
                "issued. It should appear on your original payment method within a few business days.")
    if decision == "rejection":
        return (f"We've reviewed your claim{ext}. Unfortunately we're unable to approve it "
                "based on our policy. Reply here if you'd like to discuss it further.")
    if decision == "escalate":
        return (f"Thanks for your patience. Your claim{ext} needs a closer look by our team "
                "and is now under manual review. We'll be in touch shortly.")
    return f"Your claim{ext} has been updated."


def _enqueue_resolution(phone: str, decision: str, order_external: str) -> None:
    from worker.tasks.send_whatsapp import send_text
    send_text.delay(phone, _resolution_message(decision, order_external))
