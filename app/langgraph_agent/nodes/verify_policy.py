"""
Node: verify_policy

Applies the store policy (loaded from YAML by policy_id) to decide structural
eligibility — independent of fraud. Checks:
  - claim type is covered by the policy
  - the claim was filed within the policy's delivery window

Sets `policy_verdict` (ELIGIBLE | INELIGIBLE) and human-readable `policy_reasons`.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from app.langgraph_agent.tools.policy_loader import load_policy
from app.langgraph_agent.state import ClaimState

logger = logging.getLogger(__name__)


def _parse_iso(value) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


async def verify_policy(state: ClaimState) -> dict:
    policy = load_policy(state.get("policy_id", "default"))
    reasons: list[str] = []
    verdict = "ELIGIBLE"

    claim_type = state.get("claim_type")
    eligible_types = policy.get("eligible_claim_types", [])
    if claim_type and eligible_types and claim_type not in eligible_types:
        verdict = "INELIGIBLE"
        reasons.append(f"Claim type '{claim_type}' is not covered by this policy.")

    # Delivery window
    delivered = _parse_iso(state.get("delivered_at"))
    filed = _parse_iso(state.get("claim_created_at")) or datetime.now(timezone.utc)
    max_days = policy.get("max_claim_days")
    if delivered and max_days is not None:
        age_days = (filed - delivered).days
        if age_days > max_days:
            verdict = "INELIGIBLE"
            reasons.append(
                f"Claim filed {age_days} days after delivery, exceeds the "
                f"{max_days}-day window."
            )
        else:
            reasons.append(f"Filed {age_days} days after delivery (within {max_days}-day window).")
    elif state.get("claim_type") == "not_received":
        reasons.append("No delivery date on record — consistent with a 'not received' claim.")

    logger.info("Policy verdict for claim %s: %s", state.get("claim_id"), verdict)
    return {"policy_verdict": verdict, "policy_reasons": reasons}
