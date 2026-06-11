"""
TwiML response builders for the voice IVR.

Each function returns a TwiML XML string for a Twilio webhook to return. Prompts
use Twilio's built-in `<Say>` by default; if a Piper model is installed they are
pre-synthesized and played via `<Play>` for a consistent custom voice.

All `action`/`recording` URLs are absolute (built from BASE_URL) because Twilio
fetches them directly.
"""
from __future__ import annotations

import logging

from twilio.twiml.voice_response import VoiceResponse, Gather

from app.config import get_settings
from app.voice import tts

logger = logging.getLogger(__name__)
settings = get_settings()

_VOICE = "Polly.Joanna"  # Twilio <Say> voice; ignored when Piper <Play> is used


def _url(path: str) -> str:
    return f"{settings.base_url.rstrip('/')}{path}"


def _prompt(container, text: str) -> None:
    """Add a spoken prompt to a VoiceResponse or Gather, via Piper <Play> or <Say>."""
    try:
        if tts.is_available():
            filename = tts.synthesize(text)
            container.play(_url(f"/webhooks/voice/audio/{filename}"))
            return
    except Exception as exc:  # fall back to <Say> on any TTS failure
        logger.warning("Piper TTS failed, using <Say>: %s", exc)
    container.say(text, voice=_VOICE)


# ── Inbound IVR ─────────────────────────────────────────────────────────────

def greeting_menu() -> str:
    vr = VoiceResponse()
    gather = Gather(
        input="dtmf speech",
        num_digits=1,
        timeout=6,
        action=_url("/webhooks/voice/menu"),
        method="POST",
    )
    _prompt(gather,
            "Welcome to VeriClaim support. To file a new claim about a damaged or "
            "problem order, press 1 or say 'new claim'. To check the status of an "
            "existing claim, press 2 or say 'status'.")
    vr.append(gather)
    # If the caller says nothing, repeat.
    vr.redirect(_url("/webhooks/voice/incoming"), method="POST")
    return str(vr)


def ask_order_id() -> str:
    vr = VoiceResponse()
    gather = Gather(
        input="dtmf speech",
        timeout=7,
        finish_on_key="#",
        action=_url("/webhooks/voice/collect-order-id"),
        method="POST",
    )
    _prompt(gather,
            "Please say or enter your order number, then press pound. "
            "You can find it in your confirmation email.")
    vr.append(gather)
    vr.redirect(_url("/webhooks/voice/incoming"), method="POST")
    return str(vr)


def ask_claim_type() -> str:
    vr = VoiceResponse()
    gather = Gather(
        input="speech",
        timeout=6,
        action=_url("/webhooks/voice/collect-claim-type"),
        method="POST",
    )
    _prompt(gather,
            "What went wrong with your order? You can say: damaged, not received, "
            "wrong item, or missing parts.")
    vr.append(gather)
    vr.redirect(_url("/webhooks/voice/incoming"), method="POST")
    return str(vr)


def order_not_found() -> str:
    vr = VoiceResponse()
    _prompt(vr, "I'm sorry, I couldn't find an order with that number. "
                "Please check your confirmation email and call back. Goodbye.")
    vr.hangup()
    return str(vr)


def claim_created_sent_whatsapp() -> str:
    vr = VoiceResponse()
    _prompt(vr, "Thank you. I've opened your claim and sent a WhatsApp message to your "
                "number. Please reply there with a photo of the item and the shipping "
                "label, and we'll process your claim. Goodbye.")
    vr.hangup()
    return str(vr)


def say_status(message: str) -> str:
    vr = VoiceResponse()
    _prompt(vr, message)
    _prompt(vr, "Thank you for calling VeriClaim. Goodbye.")
    vr.hangup()
    return str(vr)


def say_and_hangup(message: str) -> str:
    vr = VoiceResponse()
    _prompt(vr, message)
    vr.hangup()
    return str(vr)


# ── Outbound clarification call ───────────────────────────────────────────────

def clarification_question(question: str, claim_id: str) -> str:
    """
    Outbound-call TwiML: ask the question, record the answer, then post it to the
    clarification-response webhook for transcription + re-analysis.
    """
    vr = VoiceResponse()
    _prompt(vr, "Hello, this is VeriClaim support calling about your recent claim.")
    _prompt(vr, question)
    _prompt(vr, "Please describe your answer after the beep, then stay on the line.")
    vr.record(
        max_length=30,
        play_beep=True,
        timeout=4,
        action=_url(f"/webhooks/voice/clarification-response?claim_id={claim_id}"),
        method="POST",
        recording_status_callback=_url(
            f"/webhooks/voice/clarification-response?claim_id={claim_id}"
        ),
    )
    _prompt(vr, "We didn't catch that, but we'll review your claim. Goodbye.")
    vr.hangup()
    return str(vr)


def clarification_thanks() -> str:
    vr = VoiceResponse()
    _prompt(vr, "Thank you. We've recorded your answer and will finish reviewing your "
                "claim right away. You'll get a WhatsApp message shortly. Goodbye.")
    vr.hangup()
    return str(vr)
