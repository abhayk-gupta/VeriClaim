"""
Claim-engine pipeline tests with a mocked Gemini (no live API, no image files).

These drive the real analysis nodes (analyze_image -> verify_policy -> fraud_check
-> decide_outcome) with canned vision results and a stubbed claim-history lookup,
so the full verdict logic is exercised deterministically and offline.

DB note: the DB-touching pieces (history query, update_database) are stubbed /
omitted here; end-to-end DB runs are covered by the docker-based verification in
the plan. Requires the test Postgres only because conftest's session-scoped
fixture connects — the assertions themselves are DB-free.
"""
from datetime import datetime, timezone, timedelta

import pytest

from app.langgraph_agent.nodes.analyze_image import analyze_image
from app.langgraph_agent.nodes.verify_policy import verify_policy
from app.langgraph_agent.nodes import fraud_check as fc_module
from app.langgraph_agent.nodes.fraud_check import fraud_check
from app.langgraph_agent.nodes.decide_outcome import decide_outcome
from app.langgraph_agent.tools import gemini_client


def _iso(days_ago: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()


# ── Canned Gemini vision results ──────────────────────────────────────────────

CLEAN_DAMAGE = {
    "item_description": "Black wireless headphones with a cracked ear cup",
    "damage_type": "cracked", "damage_severity": "moderate",
    "label_match": True, "anomalies": [], "confidence": 0.92,
    "assessment": "Visible crack consistent with a damage claim.",
}
REUSED_IMAGE = {
    "item_description": "Product photo",
    "damage_type": "cracked", "damage_severity": "moderate",
    "label_match": True, "anomalies": ["appears to be a stock/marketing image"],
    "confidence": 0.8, "assessment": "Image looks like stock photography.",
}
BLURRY_LABEL = {
    "item_description": "Headphones",
    "damage_type": "cracked", "damage_severity": "moderate",
    "label_match": False, "anomalies": ["label is blurry or obscured"],
    "confidence": 0.6, "assessment": "Damage visible but label unreadable.",
}
NO_DAMAGE = {
    "item_description": "Intact headphones, no visible damage",
    "damage_type": "none", "damage_severity": "none",
    "label_match": True, "anomalies": [], "confidence": 0.9,
    "assessment": "No damage visible.",
}


async def _run_pipeline(monkeypatch, *, vision, state, history=(0, 1)):
    async def fake_analyze(**kwargs):
        return vision

    async def fake_history(customer_id, current_claim_id, window_days):
        return history  # (claims_in_window, total_claims)

    monkeypatch.setattr(gemini_client, "analyze_damage", fake_analyze)
    monkeypatch.setattr(fc_module, "_claim_history", fake_history)

    s = dict(state)
    s["item_image"] = b"fake-image-bytes"
    s.update(await analyze_image(s))
    s.update(await verify_policy(s))
    s.update(await fraud_check(s))
    s.update(await decide_outcome(s))
    return s


def _state(**overrides) -> dict:
    base = {
        "claim_id": "11111111-1111-1111-1111-111111111111",
        "customer_id": "22222222-2222-2222-2222-222222222222",
        "policy_id": "default",
        "claim_type": "damaged",
        "product_description": "Sony WH-1000XM5 headphones",
        "order_value_usd": 50.0,
        "delivered_at": _iso(5),
        "claim_created_at": _iso(0),
        "clarification_count": 0,
    }
    base.update(overrides)
    return base


@pytest.mark.asyncio
async def test_clean_damage_is_approved(monkeypatch):
    out = await _run_pipeline(monkeypatch, vision=CLEAN_DAMAGE, state=_state())
    assert out["policy_verdict"] == "ELIGIBLE"
    assert out["fraud_score"] == 0.0
    assert out["decision"] == "replacement"
    assert out["final_status"] == "approved"


@pytest.mark.asyncio
async def test_reused_image_plus_repeat_claimant_escalates(monkeypatch):
    # reused_image (0.40) + repeat_claimant (0.25) = 0.65 >= escalate threshold 0.60
    out = await _run_pipeline(monkeypatch, vision=REUSED_IMAGE, state=_state(), history=(3, 5))
    assert "reused_image" in out["fraud_signals"]
    assert "repeat_claimant" in out["fraud_signals"]
    assert out["fraud_score"] >= 0.60
    assert out["decision"] == "escalate"
    assert out["outcome"] == "manual_review"


@pytest.mark.asyncio
async def test_blurry_label_low_confidence_clarifies(monkeypatch):
    out = await _run_pipeline(monkeypatch, vision=BLURRY_LABEL, state=_state())
    assert "obscured_label" in out["fraud_signals"]
    assert out["decision"] == "clarify"
    assert out["final_status"] == "pending_clarification"


@pytest.mark.asyncio
async def test_no_visible_damage_clarifies(monkeypatch):
    out = await _run_pipeline(monkeypatch, vision=NO_DAMAGE, state=_state())
    assert out["decision"] == "clarify"


@pytest.mark.asyncio
async def test_past_delivery_window_is_rejected(monkeypatch):
    out = await _run_pipeline(monkeypatch, vision=CLEAN_DAMAGE,
                              state=_state(delivered_at=_iso(45)))
    assert out["policy_verdict"] == "INELIGIBLE"
    assert out["decision"] == "rejection"
    assert out["final_status"] == "rejected"


@pytest.mark.asyncio
async def test_clarify_becomes_escalate_after_limit(monkeypatch):
    out = await _run_pipeline(monkeypatch, vision=BLURRY_LABEL,
                              state=_state(clarification_count=2))
    # Same low-confidence input, but the loop guard escalates instead of looping.
    assert out["decision"] == "escalate"
    assert out["final_status"] == "escalated"
