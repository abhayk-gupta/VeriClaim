"""
WhatsApp send + media-download adapter.

Two backends, switched by the `USE_TWILIO_WHATSAPP` flag:
  - Twilio WhatsApp Sandbox (dev/default) — free, easy to test
  - Meta WhatsApp Cloud API (prod) — 1,000 free conversations/month

Outbound text goes through `send_text()`. Inbound media handling differs by
backend: Meta delivers a media *id* that must be resolved to a temporary URL
and downloaded with the access token; Twilio delivers a ready `MediaUrl` that
is fetched with basic auth. Both return raw bytes, which `media_storage`
then persists permanently (solving Meta's 24h CDN expiry).
"""
from __future__ import annotations

import base64
import logging
from typing import Optional

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

_TIMEOUT = httpx.Timeout(30.0, connect=10.0)


# ── Outbound text ──────────────────────────────────────────────────────────────

async def send_text(to: str, body: str) -> dict:
    """Send a plain text WhatsApp message. `to` is an E.164 number (no prefix)."""
    if settings.use_twilio_whatsapp:
        return await _send_text_twilio(to, body)
    return await _send_text_meta(to, body)


async def _send_text_meta(to: str, body: str) -> dict:
    url = f"{settings.whatsapp_api_base}/{settings.whatsapp_phone_number_id}/messages"
    headers = {
        "Authorization": f"Bearer {settings.whatsapp_access_token}",
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to.lstrip("+"),
        "type": "text",
        "text": {"preview_url": False, "body": body},
    }
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.post(url, headers=headers, json=payload)
        resp.raise_for_status()
        return resp.json()


async def _send_text_twilio(to: str, body: str) -> dict:
    sid = settings.twilio_account_sid
    url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json"
    from_ = settings.twilio_whatsapp_number  # e.g. "whatsapp:+14155238886"
    to_addr = to if to.startswith("whatsapp:") else f"whatsapp:{_ensure_plus(to)}"
    data = {"From": from_, "To": to_addr, "Body": body}
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.post(
            url, data=data, auth=(sid, settings.twilio_auth_token)
        )
        resp.raise_for_status()
        return resp.json()


# ── Inbound media download (returns raw bytes) ─────────────────────────────────

async def download_media(media_ref: str, mime_hint: Optional[str] = None) -> bytes:
    """
    Resolve and download inbound media to bytes.

    - Meta: `media_ref` is a media id -> GET metadata for a temporary URL -> download.
    - Twilio: `media_ref` is already an https MediaUrl -> download with basic auth.
    """
    if media_ref.startswith("http"):
        return await _download_twilio_media(media_ref)
    return await _download_meta_media(media_ref)


async def _download_meta_media(media_id: str) -> bytes:
    headers = {"Authorization": f"Bearer {settings.whatsapp_access_token}"}
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        meta_resp = await client.get(
            f"{settings.whatsapp_api_base}/{media_id}", headers=headers
        )
        meta_resp.raise_for_status()
        media_url = meta_resp.json()["url"]

        # The download must reuse the bearer token; this URL expires in ~24h,
        # which is exactly why callers persist the bytes immediately.
        bin_resp = await client.get(media_url, headers=headers)
        bin_resp.raise_for_status()
        return bin_resp.content


async def _download_twilio_media(media_url: str) -> bytes:
    auth = (settings.twilio_account_sid, settings.twilio_auth_token)
    async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=True) as client:
        resp = await client.get(media_url, auth=auth)
        resp.raise_for_status()
        return resp.content


# ── Helpers ────────────────────────────────────────────────────────────────────

def _ensure_plus(number: str) -> str:
    return number if number.startswith("+") else f"+{number}"


def normalize_phone(raw: str) -> str:
    """Normalize an inbound WhatsApp sender to E.164 (`+<digits>`)."""
    raw = raw.replace("whatsapp:", "").strip()
    return _ensure_plus(raw)


def encode_bytes_b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")
