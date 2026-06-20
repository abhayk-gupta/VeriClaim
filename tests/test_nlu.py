"""
Unit tests for the heuristic NLU fallback (no Gemini key, no DB required).

These guard the natural-language understanding the WhatsApp-only flow depends
on: simple human phrasing must map to the right intent and claim_type, and an
order number — when present — must be extracted regardless of surrounding words.
"""
import pytest

from app.services import nlu


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "text,intent,claim_type",
    [
        ("hi my package came broken", "file_claim", "damaged"),
        ("the screen is cracked", "file_claim", "damaged"),
        ("wrong product was sent", "file_claim", "wrong_item"),
        ("this isn't what I ordered", "file_claim", "wrong_item"),
        ("my order never arrived", "file_claim", "not_received"),
        ("where is my package", "file_claim", "not_received"),
        ("parts are missing from the box", "file_claim", "missing_parts"),
        ("my order is incomplete", "file_claim", "missing_parts"),
        ("where is my refund", "check_status", None),
        ("any update on my claim", "check_status", None),
        ("hello", "greeting", None),
        ("i have a problem", "unknown", None),
    ],
)
async def test_intent_and_claim_type(text, intent, claim_type):
    result = await nlu.extract_intent([text])
    assert result.intent == intent, f"{text!r} -> {result.intent}"
    assert result.claim_type == claim_type, f"{text!r} -> {result.claim_type}"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "text,expected_core",
    [
        ("its 98765", "98765"),
        ("order ORD-10002 is damaged", "10002"),
        ("ord 10001", "10001"),
        ("my number is 123456", "123456"),
    ],
)
async def test_order_id_extraction(text, expected_core):
    result = await nlu.extract_intent([text])
    assert result.order_id is not None
    assert expected_core in "".join(c for c in result.order_id if c.isdigit())


@pytest.mark.asyncio
async def test_no_order_id_when_absent():
    result = await nlu.extract_intent(["my package is broken"])
    assert result.order_id is None
