"""
Voice TwiML builder tests (DB-free, no Twilio account needed).

Confirms each IVR step emits valid TwiML with the expected verbs and that the
outbound clarification call records the answer to the right callback URL.
"""
import pytest

from app.voice import twiml_responses as twiml


def test_greeting_menu_has_gather_and_options(mocker):
    mocker.patch("app.voice.twiml_responses.tts.is_available", return_value=False)
    xml = twiml.greeting_menu()
    assert xml.startswith("<?xml")
    assert "<Gather" in xml
    assert "press 1" in xml.lower()
    assert "/webhooks/voice/menu" in xml


def test_ask_order_id_gathers_input(mocker):
    mocker.patch("app.voice.twiml_responses.tts.is_available", return_value=False)
    xml = twiml.ask_order_id()
    assert "<Gather" in xml
    assert "/webhooks/voice/collect-order-id" in xml


def test_ask_claim_type_lists_options(mocker):
    mocker.patch("app.voice.twiml_responses.tts.is_available", return_value=False)
    xml = twiml.ask_claim_type().lower()
    assert "damaged" in xml
    assert "wrong item" in xml
    assert "missing parts" in xml


def test_say_status_hangs_up(mocker):
    mocker.patch("app.voice.twiml_responses.tts.is_available", return_value=False)
    xml = twiml.say_status("Your claim for order ORD-10001 was approved.")
    assert "ORD-10001" in xml
    assert "<Hangup" in xml


def test_order_not_found_hangs_up(mocker):
    mocker.patch("app.voice.twiml_responses.tts.is_available", return_value=False)
    xml = twiml.order_not_found()
    assert "<Hangup" in xml


def test_claim_created_mentions_whatsapp(mocker):
    mocker.patch("app.voice.twiml_responses.tts.is_available", return_value=False)
    xml = twiml.claim_created_sent_whatsapp().lower()
    assert "whatsapp" in xml
    assert "<hangup" in xml


@pytest.mark.parametrize("claim_id", ["abc-123", "11111111-1111-1111-1111-111111111111"])
def test_clarification_question_records_to_callback(claim_id, mocker):
    mocker.patch("app.voice.twiml_responses.tts.is_available", return_value=False)
    xml = twiml.clarification_question("Where is the damage located?", claim_id)
    assert "<Record" in xml
    assert "Where is the damage located?" in xml
    assert f"claim_id={claim_id}" in xml
    assert "/webhooks/voice/clarification-response" in xml
