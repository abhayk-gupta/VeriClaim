"""
WhatsApp webhook — GET verification handshake + POST inbound handler.

Supports both backends transparently:
  - Meta WhatsApp Cloud API  → JSON body (WAWebhookPayload)
  - Twilio WhatsApp Sandbox  → application/x-www-form-urlencoded body

Inbound text is delegated to the NLU intake FSM (`wa_intake`); inbound images
are downloaded immediately and stored permanently (Cloudflare R2 / Redis) to
defeat Meta's 24-hour media-link expiry, then attached to the active claim.

Every inbound message and every outbound reply is written to `interaction_logs`
so the per-order timeline is complete across channels.
"""
from __future__ import annotations

import logging
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Request, Response, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_session
from app.redis_client import get_redis
from app.services import whatsapp_service, wa_intake, order_service, claim_service, media_storage
from app.services.interaction_log_service import log_event
from app.models.interaction_log import InteractionChannel, InteractionDirection
from app.schemas.webhooks import WAWebhookPayload, WAMessage

logger = logging.getLogger(__name__)
settings = get_settings()

router = APIRouter(tags=["whatsapp"])

_DEDUP_TTL = 3600  # ignore a given message id for 1 hour


# ── GET: Meta verification handshake ───────────────────────────────────────────

@router.get("/whatsapp")
async def verify(
    hub_mode: Optional[str] = Query(None, alias="hub.mode"),
    hub_verify_token: Optional[str] = Query(None, alias="hub.verify_token"),
    hub_challenge: Optional[str] = Query(None, alias="hub.challenge"),
):
    if hub_mode == "subscribe" and hub_verify_token == settings.whatsapp_verify_token:
        return PlainTextResponse(hub_challenge or "")
    return Response(status_code=403)


# ── POST: inbound messages ─────────────────────────────────────────────────────

@router.post("/whatsapp")
async def inbound(request: Request, db: AsyncSession = Depends(get_session)):
    content_type = request.headers.get("content-type", "")

    if "application/json" in content_type:
        messages = await _parse_meta(request)
    else:
        messages = await _parse_twilio(request)

    for msg in messages:
        await _dispatch(db, msg)

    # WhatsApp/Twilio only need a 200 to stop retrying.
    return Response(status_code=200)


# ── Normalized inbound message ─────────────────────────────────────────────────

class _Inbound:
    __slots__ = ("message_id", "phone", "type", "text", "media_ref", "mime")

    def __init__(self, message_id, phone, type_, text=None, media_ref=None, mime=None):
        self.message_id = message_id
        self.phone = phone
        self.type = type_  # "text" | "image" | "other"
        self.text = text
        self.media_ref = media_ref
        self.mime = mime


async def _parse_meta(request: Request) -> list[_Inbound]:
    body = await request.json()
    try:
        payload = WAWebhookPayload.model_validate(body)
    except Exception as exc:
        logger.warning("Unparseable Meta webhook payload: %s", exc)
        return []

    out: list[_Inbound] = []
    for entry in payload.entry:
        for change in entry.changes:
            for raw in (change.value.messages or []):
                msg = raw if isinstance(raw, WAMessage) else WAMessage.model_validate(raw)
                phone = whatsapp_service.normalize_phone(msg.from_)
                if msg.type == "text" and msg.text:
                    out.append(_Inbound(msg.id, phone, "text", text=msg.text.body))
                elif msg.type == "image" and msg.image:
                    out.append(_Inbound(msg.id, phone, "image",
                                        media_ref=msg.image.id, mime=msg.image.mime_type))
                else:
                    out.append(_Inbound(msg.id, phone, "other"))
    return out


async def _parse_twilio(request: Request) -> list[_Inbound]:
    form = await request.form()
    phone = whatsapp_service.normalize_phone(form.get("From", ""))
    message_id = form.get("MessageSid") or form.get("SmsMessageSid") or ""
    num_media = int(form.get("NumMedia", "0") or "0")

    if num_media > 0:
        media_ref = form.get("MediaUrl0")
        mime = form.get("MediaContentType0", "image/jpeg")
        type_ = "image" if (mime or "").startswith("image/") else "other"
        return [_Inbound(message_id, phone, type_, media_ref=media_ref, mime=mime)]

    body = (form.get("Body") or "").strip()
    return [_Inbound(message_id, phone, "text", text=body)]


# ── Dispatch a single inbound message ──────────────────────────────────────────

async def _dispatch(db: AsyncSession, msg: _Inbound) -> None:
    if msg.message_id and await _is_duplicate(msg.message_id):
        logger.info("Skipping duplicate WhatsApp message %s", msg.message_id)
        return

    if msg.type == "text":
        await _handle_text(db, msg)
    elif msg.type == "image":
        await _handle_image(db, msg)
    else:
        await _reply(db, msg.phone,
                     "I can help with damaged or problem orders. Please send a text "
                     "describing the issue, or a photo when asked.")


async def _handle_text(db: AsyncSession, msg: _Inbound) -> None:
    customer = await order_service.get_customer_by_phone(db, msg.phone)
    await log_event(
        db,
        channel=InteractionChannel.WHATSAPP,
        direction=InteractionDirection.INBOUND,
        event_type="text_received",
        customer_id=customer.id if customer else None,
        content_text=msg.text,
        metadata={"message_id": msg.message_id},
    )
    reply = await wa_intake.handle_text_message(db, msg.phone, msg.text or "")
    await _reply(db, msg.phone, reply)


async def _handle_image(db: AsyncSession, msg: _Inbound) -> None:
    claim_id = await wa_intake.get_active_claim_id(msg.phone)
    if claim_id is None:
        await _reply(db, msg.phone,
                     "Thanks for the photo! First, could you tell me your order number "
                     "and what went wrong so I can open a claim?")
        return

    claim = await claim_service.get_claim(db, claim_id)
    if claim is None:
        await _reply(db, msg.phone,
                     "I couldn't find your claim anymore. Let's start again — what's "
                     "your order number and what happened?")
        return

    side = "item" if not claim.media_r2_key_item else "label"

    # Download the bytes NOW and store permanently — the source link expires in 24h.
    try:
        data = await whatsapp_service.download_media(msg.media_ref, msg.mime)
        r2_key = await media_storage.store_image(str(claim.id), side, data, msg.mime or "image/jpeg")
    except Exception as exc:
        logger.exception("Failed to download/store inbound media: %s", exc)
        await _reply(db, msg.phone,
                     "I had trouble saving that photo — could you send it again?")
        return

    await claim_service.attach_media(
        db, claim, side=side, meta_media_id=msg.media_ref, r2_key=r2_key, commit=False,
    )
    await log_event(
        db,
        channel=InteractionChannel.WHATSAPP,
        direction=InteractionDirection.INBOUND,
        event_type="image_received",
        order_id=claim.order_id,
        claim_id=claim.id,
        customer_id=claim.customer_id,
        content_text=f"{side} photo received",
        media_url=msg.media_ref,
        metadata={"message_id": msg.message_id, "side": side, "r2_key": r2_key},
        commit=False,
    )
    await db.commit()

    reply = await wa_intake.handle_image_received(db, msg.phone, claim)
    await _reply(db, msg.phone, reply)

    # Both photos in → kick off the LangGraph analysis (Phase 3 consumer).
    if claim_service.has_both_photos(claim):
        _enqueue_process_claim(claim.id)
        await log_event(
            db,
            channel=InteractionChannel.SYSTEM,
            direction=InteractionDirection.INTERNAL,
            event_type="analysis_enqueued",
            order_id=claim.order_id,
            claim_id=claim.id,
            customer_id=claim.customer_id,
        )


# ── Outbound reply (log here, send via Celery) ─────────────────────────────────

async def _reply(db: AsyncSession, phone: str, body: str) -> None:
    # Attach order/claim context from the live session so the timeline links up.
    order_id, claim_id, customer_id = await _session_context(db, phone)
    await log_event(
        db,
        channel=InteractionChannel.WHATSAPP,
        direction=InteractionDirection.OUTBOUND,
        event_type="message_sent",
        order_id=order_id,
        claim_id=claim_id,
        customer_id=customer_id,
        content_text=body,
    )
    _enqueue_send_text(phone, body)


async def _session_context(db: AsyncSession, phone: str):
    """Best-effort order/claim/customer ids for outbound logging."""
    session = await wa_intake._load_session(phone)  # internal but intentional reuse
    order_id = uuid.UUID(session["order_id"]) if session.get("order_id") else None
    claim_id = uuid.UUID(session["claim_id"]) if session.get("claim_id") else None
    customer_id = uuid.UUID(session["customer_id"]) if session.get("customer_id") else None
    if customer_id is None:
        customer = await order_service.get_customer_by_phone(db, phone)
        customer_id = customer.id if customer else None
    return order_id, claim_id, customer_id


# ── Celery enqueue helpers (imported lazily to avoid import cycles) ────────────

def _enqueue_send_text(phone: str, body: str) -> None:
    from worker.tasks.send_whatsapp import send_text
    send_text.delay(phone, body)


def _enqueue_process_claim(claim_id: uuid.UUID) -> None:
    # send_task by name so this works before the Phase 3 task module is imported here.
    from worker.celery_app import celery_app
    celery_app.send_task(
        "worker.tasks.process_claim.process_claim",
        args=[str(claim_id)],
        queue="claims",
    )


# ── Dedup ──────────────────────────────────────────────────────────────────────

async def _is_duplicate(message_id: str) -> bool:
    redis = await get_redis()
    # SET NX returns True only the first time we see this id.
    was_set = await redis.set(f"whatsapp:msg:{message_id}", "1", ex=_DEDUP_TTL, nx=True)
    return not was_set
