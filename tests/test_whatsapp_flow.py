"""
WhatsApp webhook parsing tests.

Covers the backend-agnostic normalization of inbound payloads (Meta JSON +
Twilio form) into the internal `_Inbound` shape, and the GET verification
handshake. These are DB-free.
"""
import pytest

from app.routers import whatsapp as wa
from app.config import get_settings

settings = get_settings()


class _FakeRequest:
    """Minimal stand-in for starlette.Request for parser unit tests."""
    def __init__(self, *, json_body=None, form_body=None, headers=None):
        self._json = json_body
        self._form = form_body
        self.headers = headers or {}

    async def json(self):
        return self._json

    async def form(self):
        return self._form


# ── Twilio form payloads ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_parse_twilio_text():
    req = _FakeRequest(form_body={
        "From": "whatsapp:+14155551001", "Body": "my package is broken",
        "MessageSid": "SM123", "NumMedia": "0",
    })
    msgs = await wa._parse_twilio(req)
    assert len(msgs) == 1
    m = msgs[0]
    assert m.type == "text"
    assert m.text == "my package is broken"
    assert m.phone == "+14155551001"
    assert m.message_id == "SM123"


@pytest.mark.asyncio
async def test_parse_twilio_image():
    req = _FakeRequest(form_body={
        "From": "whatsapp:+14155551001", "MessageSid": "SM456", "NumMedia": "1",
        "MediaUrl0": "https://api.twilio.com/media/abc",
        "MediaContentType0": "image/jpeg",
    })
    msgs = await wa._parse_twilio(req)
    assert msgs[0].type == "image"
    assert msgs[0].media_ref == "https://api.twilio.com/media/abc"


# ── Meta JSON payloads ────────────────────────────────────────────────────────

def _meta_envelope(message: dict) -> dict:
    return {
        "object": "whatsapp_business_account",
        "entry": [{
            "id": "WABA_ID",
            "changes": [{
                "field": "messages",
                "value": {
                    "messaging_product": "whatsapp",
                    "metadata": {"phone_number_id": "PNID"},
                    "messages": [message],
                },
            }],
        }],
    }


@pytest.mark.asyncio
async def test_parse_meta_text():
    body = _meta_envelope({
        "id": "wamid.TEXT", "from": "14155551001", "timestamp": "1700000000",
        "type": "text", "text": {"body": "hello it arrived damaged"},
    })
    req = _FakeRequest(json_body=body)
    msgs = await wa._parse_meta(req)
    assert len(msgs) == 1
    assert msgs[0].type == "text"
    assert msgs[0].text == "hello it arrived damaged"
    assert msgs[0].phone == "+14155551001"   # normalized to E.164


@pytest.mark.asyncio
async def test_parse_meta_image():
    body = _meta_envelope({
        "id": "wamid.IMG", "from": "14155551001", "timestamp": "1700000000",
        "type": "image", "image": {"id": "MEDIA_ID_123", "mime_type": "image/jpeg"},
    })
    req = _FakeRequest(json_body=body)
    msgs = await wa._parse_meta(req)
    assert msgs[0].type == "image"
    assert msgs[0].media_ref == "MEDIA_ID_123"


# ── GET verification handshake ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_verify_handshake_success():
    resp = await wa.verify(
        hub_mode="subscribe",
        hub_verify_token=settings.whatsapp_verify_token,
        hub_challenge="challenge-42",
    )
    assert resp.body == b"challenge-42"


@pytest.mark.asyncio
async def test_verify_handshake_bad_token():
    resp = await wa.verify(
        hub_mode="subscribe", hub_verify_token="wrong-token", hub_challenge="x",
    )
    assert resp.status_code == 403
