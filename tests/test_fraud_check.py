"""
Fraud-scoring unit tests. Claim history is stubbed so no DB is required for the
assertions; weights come from the real default policy YAML.
"""
from datetime import datetime, timezone, timedelta

import pytest

from app.langgraph_agent.nodes import fraud_check as fc_module
from app.langgraph_agent.nodes.fraud_check import fraud_check


def _iso(days_ago: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()


def _state(**overrides) -> dict:
    base = {
        "claim_id": "11111111-1111-1111-1111-111111111111",
        "customer_id": "22222222-2222-2222-2222-222222222222",
        "policy_id": "default",
        "claim_type": "damaged",
        "order_value_usd": 50.0,
        "delivered_at": _iso(10),
        "claim_created_at": _iso(0),
        "gemini_label_match": True,
        "gemini_anomalies": [],
    }
    base.update(overrides)
    return base


def _stub_history(monkeypatch, history):
    async def fake_history(customer_id, current_claim_id, window_days):
        return history

    monkeypatch.setattr(fc_module, "_claim_history", fake_history)


@pytest.mark.asyncio
async def test_no_signals_zero_score(monkeypatch):
    _stub_history(monkeypatch, (0, 1))
    out = await fraud_check(_state())
    assert out["fraud_score"] == 0.0
    assert out["fraud_signals"] == {}


@pytest.mark.asyncio
async def test_reused_image_signal(monkeypatch):
    _stub_history(monkeypatch, (0, 1))
    out = await fraud_check(_state(gemini_anomalies=["appears to be a stock image"]))
    assert "reused_image" in out["fraud_signals"]
    assert out["fraud_score"] == pytest.approx(0.40)


@pytest.mark.asyncio
async def test_obscured_label_signal(monkeypatch):
    _stub_history(monkeypatch, (0, 1))
    out = await fraud_check(_state(gemini_label_match=False))
    assert "obscured_label" in out["fraud_signals"]
    assert out["fraud_score"] == pytest.approx(0.15)


@pytest.mark.asyncio
async def test_repeat_claimant_signal(monkeypatch):
    _stub_history(monkeypatch, (3, 5))  # > trigger of 2
    out = await fraud_check(_state())
    assert "repeat_claimant" in out["fraud_signals"]
    assert out["fraud_score"] == pytest.approx(0.25)


@pytest.mark.asyncio
async def test_too_soon_after_delivery_signal(monkeypatch):
    _stub_history(monkeypatch, (0, 1))
    out = await fraud_check(_state(delivered_at=_iso(0)))  # delivered today
    assert "too_soon_after_delivery" in out["fraud_signals"]


@pytest.mark.asyncio
async def test_high_value_new_customer_signal(monkeypatch):
    _stub_history(monkeypatch, (0, 1))  # total_claims <= 1
    out = await fraud_check(_state(order_value_usd=300.0))
    assert "high_value_new_customer" in out["fraud_signals"]


@pytest.mark.asyncio
async def test_multiple_signals_accumulate_and_stay_bounded(monkeypatch):
    # repeat_claimant (0.25) requires many prior claims, so high_value_new_customer
    # (needs a first-time claimant) cannot also fire — they're mutually exclusive.
    # reused 0.40 + obscured 0.15 + repeat 0.25 + too_soon 0.10 = 0.90.
    _stub_history(monkeypatch, (5, 9))
    out = await fraud_check(_state(
        order_value_usd=500.0,
        delivered_at=_iso(0),
        gemini_label_match=False,
        gemini_anomalies=["stock image", "label obscured"],
    ))
    assert out["fraud_score"] == pytest.approx(0.90)
    assert out["fraud_score"] <= 1.0
    assert "high_value_new_customer" not in out["fraud_signals"]
