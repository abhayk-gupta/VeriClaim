"""
Node: decide_outcome

Combines the policy verdict, fraud score, and vision confidence into a final
decision. Decision values:

  rejection    -> policy-ineligible
  escalate     -> fraud score at/above the escalate threshold (manual review)
  clarify      -> borderline fraud, low confidence, or a claim/photo mismatch
                  (Phase 4 turns this into an outbound clarification call)
  replacement  -> eligible, low fraud, confident -> per policy preference
  refund       -> as above, but a refund is the appropriate resolution

Sets `decision`, `outcome` (ClaimOutcome value or None), `final_status`
(ClaimStatus value), and a human-readable `agent_reasoning` summary.
"""
from __future__ import annotations

import logging

from app.models.claim import ClaimStatus, ClaimOutcome
from app.langgraph_agent.tools.policy_loader import load_policy
from app.langgraph_agent.state import ClaimState

logger = logging.getLogger(__name__)

_NO_DAMAGE = {"none", "not_applicable", "unknown", ""}


async def decide_outcome(state: ClaimState) -> dict:
    policy = load_policy(state.get("policy_id", "default"))
    fraud_cfg = policy.get("fraud", {})
    escalate_threshold = fraud_cfg.get("escalate_threshold", 0.60)
    auto_approve_threshold = fraud_cfg.get("auto_approve_threshold", 0.30)
    min_confidence = policy.get("min_confidence", 0.70)
    preferred = policy.get("preferred_resolution", "replacement")

    max_clarifications = policy.get("max_clarifications", 2)

    verdict = state.get("policy_verdict", "ELIGIBLE")
    fraud_score = state.get("fraud_score", 0.0)
    confidence = state.get("gemini_confidence", 0.0)
    claim_type = state.get("claim_type")
    severity = (state.get("gemini_damage_severity") or "none").lower()
    damage_type = (state.get("gemini_damage_type") or "none").lower()
    clarification_count = state.get("clarification_count", 0)

    def clarify(reasoning: str) -> dict:
        # Loop guard: once we've already asked the customer enough times, stop
        # clarifying and escalate to a human instead of calling again.
        if clarification_count >= max_clarifications:
            return _result("escalate", ClaimOutcome.MANUAL_REVIEW, ClaimStatus.ESCALATED, state,
                           f"{reasoning} Clarification limit ({max_clarifications}) reached — "
                           "escalating for manual review.")
        return _result("clarify", None, ClaimStatus.PENDING_CLARIFICATION, state, reasoning)

    # 1. Policy ineligible → reject outright.
    if verdict == "INELIGIBLE":
        return _result("rejection", ClaimOutcome.REJECTION, ClaimStatus.REJECTED, state,
                       "Claim rejected: " + "; ".join(state.get("policy_reasons", [])))

    # 2. High fraud → escalate to a human.
    if fraud_score >= escalate_threshold:
        return _result("escalate", ClaimOutcome.MANUAL_REVIEW, ClaimStatus.ESCALATED, state,
                       f"Escalated for manual review: fraud score {fraud_score:.2f} "
                       f">= {escalate_threshold:.2f}.")

    # 3. Photo doesn't support a damage-type claim → need a clearer/proper photo.
    damage_claim = claim_type in {"damaged", "wrong_item", "missing_parts"}
    if damage_claim and severity in _NO_DAMAGE and damage_type in _NO_DAMAGE:
        return clarify("No damage is clearly visible in the photo for a damage claim.")

    # 4. Low vision confidence → clarify.
    if confidence < min_confidence:
        return clarify(f"Vision confidence {confidence:.2f} below threshold {min_confidence:.2f}.")

    # 5. Borderline fraud (between auto-approve and escalate) → clarify.
    if fraud_score >= auto_approve_threshold:
        return clarify(f"Borderline fraud score {fraud_score:.2f} needs confirmation.")

    # 6. Eligible, low fraud, confident → approve.
    if claim_type == "not_received":
        decision, outcome = "refund", ClaimOutcome.REFUND
    elif preferred == "refund":
        decision, outcome = "refund", ClaimOutcome.REFUND
    else:
        decision, outcome = "replacement", ClaimOutcome.REPLACEMENT

    return _result(decision, outcome, ClaimStatus.APPROVED, state,
                   f"Approved for {decision}: eligible, fraud {fraud_score:.2f} < "
                   f"{auto_approve_threshold:.2f}, confidence {confidence:.2f}.")


def _result(decision: str, outcome, status: ClaimStatus, state: ClaimState, reasoning: str) -> dict:
    logger.info("Decision for claim %s: %s (%s)", state.get("claim_id"), decision, status.value)
    return {
        "decision": decision,
        "outcome": outcome.value if outcome is not None else None,
        "final_status": status.value,
        "agent_reasoning": reasoning,
    }
