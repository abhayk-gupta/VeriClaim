"""
Unit tests for the policy + decision nodes (no DB, no Gemini required).

Covers the verdict matrix that determines auto-resolution vs. escalation vs.
clarification — the core business logic of the claim engine.
"""
from datetime import datetime, timezone, timedelta

import pytest

from app.langgraph_agent.nodes.verify_policy import verify_policy
from app.langgraph_agent.nodes.decide_outcome import decide_outcome


def _iso(days_ago: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()


# ── verify_policy ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_policy_eligible_within_window():
    state = {"policy_id": "default", "claim_type": "damaged",
             "delivered_at": _iso(5), "claim_created_at": _iso(0)}
    out = await verify_policy(state)
    assert out["policy_verdict"] == "ELIGIBLE"


@pytest.mark.asyncio
async def test_policy_ineligible_past_window():
    state = {"policy_id": "default", "claim_type": "damaged",
             "delivered_at": _iso(45), "claim_created_at": _iso(0)}
    out = await verify_policy(state)
    assert out["policy_verdict"] == "INELIGIBLE"


@pytest.mark.asyncio
async def test_policy_electronics_stricter_window():
    # 20 days is fine for default (30) but not electronics (14).
    state = {"policy_id": "electronics", "claim_type": "damaged",
             "delivered_at": _iso(20), "claim_created_at": _iso(0)}
    out = await verify_policy(state)
    assert out["policy_verdict"] == "INELIGIBLE"


# ── decide_outcome ───────────────────────────────────────────────────────────

def _base(**overrides) -> dict:
    state = {
        "policy_id": "default",
        "policy_verdict": "ELIGIBLE",
        "fraud_score": 0.0,
        "gemini_confidence": 0.9,
        "claim_type": "damaged",
        "gemini_damage_severity": "moderate",
        "gemini_damage_type": "cracked",
    }
    state.update(overrides)
    return state


@pytest.mark.asyncio
async def test_decision_reject_when_ineligible():
    out = await decide_outcome(_base(policy_verdict="INELIGIBLE", policy_reasons=["too old"]))
    assert out["decision"] == "rejection"
    assert out["final_status"] == "rejected"


@pytest.mark.asyncio
async def test_decision_escalate_on_high_fraud():
    out = await decide_outcome(_base(fraud_score=0.7))
    assert out["decision"] == "escalate"
    assert out["outcome"] == "manual_review"


@pytest.mark.asyncio
async def test_decision_clarify_on_low_confidence():
    out = await decide_outcome(_base(gemini_confidence=0.4))
    assert out["decision"] == "clarify"
    assert out["final_status"] == "pending_clarification"


@pytest.mark.asyncio
async def test_decision_clarify_on_borderline_fraud():
    out = await decide_outcome(_base(fraud_score=0.4))
    assert out["decision"] == "clarify"


@pytest.mark.asyncio
async def test_decision_clarify_when_no_visible_damage():
    out = await decide_outcome(_base(gemini_damage_severity="none", gemini_damage_type="none"))
    assert out["decision"] == "clarify"


@pytest.mark.asyncio
async def test_decision_approve_replacement_when_clean():
    out = await decide_outcome(_base())
    assert out["decision"] == "replacement"
    assert out["outcome"] == "replacement"
    assert out["final_status"] == "approved"


@pytest.mark.asyncio
async def test_decision_refund_for_not_received():
    out = await decide_outcome(_base(claim_type="not_received",
                                     gemini_damage_severity="none",
                                     gemini_damage_type="not_applicable"))
    assert out["decision"] == "refund"
    assert out["outcome"] == "refund"
