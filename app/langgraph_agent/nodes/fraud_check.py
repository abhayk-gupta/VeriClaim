"""
Node: fraud_check

Computes a weighted fraud score in [0.0, 1.0] from independent signals, using the
weights configured in the store policy. Signals:

  - reused_image            : Gemini flagged the photo as stock/screenshot/reused
  - obscured_label          : label missing/obscured or didn't match a real shipment
  - repeat_claimant         : customer filed more than N prior claims in the window
  - too_soon_after_delivery : claim filed within N hours of delivery
  - high_value_new_customer : high-value order from a first-time claimant

Each firing signal adds its weight; the total is capped at 1.0. The per-signal
breakdown is stored on the claim (`fraud_signals`) for the audit trail.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone, timedelta

from sqlalchemy import select, func

from app.database import AsyncSessionLocal
from app.models.claim import Claim
from app.langgraph_agent.tools.policy_loader import load_policy
from app.langgraph_agent.state import ClaimState

logger = logging.getLogger(__name__)

_REUSED_HINTS = ("stock", "marketing", "screenshot", "reused", "screen shot", "downloaded")
_OBSCURED_HINTS = ("obscured", "blurry", "blurred", "label", "cropped", "cut off", "unreadable")


def _parse_iso(value):
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


async def fraud_check(state: ClaimState) -> dict:
    policy = load_policy(state.get("policy_id", "default"))
    fraud_cfg = policy.get("fraud", {})
    weights = fraud_cfg.get("weights", {})

    anomalies = [a.lower() for a in state.get("gemini_anomalies", [])]
    signals: dict[str, dict] = {}

    # ── reused / fake image ────────────────────────────────────────────────────
    if any(any(h in a for h in _REUSED_HINTS) for a in anomalies):
        signals["reused_image"] = {"weight": weights.get("reused_image", 0.40),
                                   "detail": "Vision model flagged image as stock/reused/screenshot."}

    # ── obscured / mismatched label ────────────────────────────────────────────
    label_match = state.get("gemini_label_match")
    label_obscured = label_match is False or any(
        any(h in a for h in _OBSCURED_HINTS) for a in anomalies
    )
    if label_obscured:
        signals["obscured_label"] = {"weight": weights.get("obscured_label", 0.15),
                                     "detail": "Shipping label missing, obscured, or unverifiable."}

    # ── DB-derived signals (repeat claimant, new high-value customer) ──────────
    repeat_count, total_claims = await _claim_history(
        state.get("customer_id"),
        state.get("claim_id"),
        fraud_cfg.get("repeat_claim_window_days", 90),
    )
    trigger = fraud_cfg.get("repeat_claim_count_trigger", 2)
    if repeat_count > trigger:
        signals["repeat_claimant"] = {"weight": weights.get("repeat_claimant", 0.25),
                                      "detail": f"{repeat_count} prior claims in the policy window."}

    # ── claim filed suspiciously soon after delivery ───────────────────────────
    delivered = _parse_iso(state.get("delivered_at"))
    filed = _parse_iso(state.get("claim_created_at")) or datetime.now(timezone.utc)
    too_soon_hours = fraud_cfg.get("too_soon_hours", 24)
    if delivered:
        # Ensure both sides are stripped of timezone attachments
        filed_naive = filed.replace(tzinfo=None) if filed.tzinfo else filed
        delivered_naive = delivered.replace(tzinfo=None) if delivered.tzinfo else delivered
        
        if (filed_naive - delivered_naive) < timedelta(hours=too_soon_hours):
            signals["too_soon_after_delivery"] = {
                "weight": weights.get("too_soon_after_delivery", 0.10),
                "detail": f"Claim filed within {too_soon_hours}h of delivery.",
            }

    # ── high-value order from a first-time claimant ────────────────────────────
    high_value_threshold = fraud_cfg.get("high_value_threshold_usd", 200)
    order_value = state.get("order_value_usd", 0.0) or 0.0
    if order_value >= high_value_threshold and total_claims <= 1:
        signals["high_value_new_customer"] = {
            "weight": weights.get("high_value_new_customer", 0.10),
            "detail": f"High-value order (${order_value:.2f}) from a first-time claimant.",
        }

    score = min(1.0, round(sum(s["weight"] for s in signals.values()), 4))
    logger.info("Fraud score for claim %s: %.2f (%d signals)",
                state.get("claim_id"), score, len(signals))
    return {"fraud_score": score, "fraud_signals": signals}


async def _claim_history(customer_id: str | None, current_claim_id: str | None, window_days: int):
    """Return (claims_in_window_excluding_current, total_claims_for_customer)."""
    if not customer_id:
        return 0, 0
    cid = uuid.UUID(customer_id)
    cutoff = (datetime.now(timezone.utc) - timedelta(days=window_days)).replace(tzinfo=None)
    async with AsyncSessionLocal() as session:
        total = await session.scalar(
            select(func.count()).select_from(Claim).where(Claim.customer_id == cid)
        )
        window_stmt = select(func.count()).select_from(Claim).where(
            Claim.customer_id == cid, Claim.created_at >= cutoff
        )
        if current_claim_id:
            window_stmt = window_stmt.where(Claim.id != uuid.UUID(current_claim_id))
        in_window = await session.scalar(window_stmt)

    return int(in_window or 0), int(total or 0)
