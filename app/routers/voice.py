"""
Voice IVR webhooks (Twilio).

Two inbound flows + one outbound-response handler:
  - New claim:   incoming -> menu(1) -> order id -> claim type -> create claim,
                 send WhatsApp photo request, seed a WA session so the photos link.
  - Status check: incoming -> menu(2) -> order id -> read back latest claim status.
  - Clarification response: handles the recording from an outbound clarification
                 call, transcribes it (Whisper), stores it, and re-runs analysis.

All endpoints return TwiML XML. Every turn is written to the interaction log with
channel=voice so the per-order timeline spans voice + WhatsApp.
"""
from __future__ import annotations

import logging
import uuid

import httpx
from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response, FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_session
from app.services import order_service, claim_service, wa_intake, nlu
from app.services.interaction_log_service import log_event
from app.models.interaction_log import InteractionChannel, InteractionDirection
from app.models.claim import ClaimType
from app.voice import twiml_responses as twiml, call_state, stt

logger = logging.getLogger(__name__)
settings = get_settings()

router = APIRouter(prefix="/voice", tags=["voice"])

_XML = "application/xml"


def _xml(content: str) -> Response:
    return Response(content=content, media_type=_XML)


# ── Inbound IVR ─────────────────────────────────────────────────────────────

@router.post("/incoming")
async def incoming(request: Request, db: AsyncSession = Depends(get_session)):
    form = await request.form()
    call_sid = form.get("CallSid", "")
    from_phone = (form.get("From") or "").strip()

    customer = await order_service.get_customer_by_phone(db, from_phone)
    await call_state.update(call_sid, from_phone=from_phone,
                            customer_id=str(customer.id) if customer else None)
    await log_event(
        db,
        channel=InteractionChannel.VOICE,
        direction=InteractionDirection.INBOUND,
        event_type="call_started",
        customer_id=customer.id if customer else None,
        content_text=f"Inbound call from {from_phone}",
        metadata={"call_sid": call_sid},
    )
    return _xml(twiml.greeting_menu())


@router.post("/menu")
async def menu(request: Request):
    form = await request.form()
    call_sid = form.get("CallSid", "")
    choice = (form.get("Digits") or form.get("SpeechResult") or "").lower()

    if "2" in choice or "status" in choice or "check" in choice:
        intent = "check_status"
    else:
        intent = "file_claim"

    await call_state.update(call_sid, intent=intent)
    return _xml(twiml.ask_order_id())


@router.post("/collect-order-id")
async def collect_order_id(request: Request, db: AsyncSession = Depends(get_session)):
    form = await request.form()
    call_sid = form.get("CallSid", "")
    spoken = form.get("SpeechResult") or form.get("Digits") or ""

    state = await call_state.load(call_sid)
    customer_id = state.get("customer_id")
    matches = await order_service.lookup_fuzzy(
        db, spoken, uuid.UUID(customer_id) if customer_id else None
    )
    if not matches:
        matches = await order_service.lookup_fuzzy(db, spoken, None)

    if not matches:
        return _xml(twiml.order_not_found())

    order = matches[0]
    state = await call_state.update(
        call_sid,
        order_id=str(order.id),
        order_external=order.external_order_id,
        customer_id=str(order.customer_id),
    )
    await log_event(
        db,
        channel=InteractionChannel.VOICE,
        direction=InteractionDirection.INBOUND,
        event_type="order_identified",
        order_id=order.id,
        customer_id=order.customer_id,
        content_text=f"Caller identified order {order.external_order_id}",
        metadata={"call_sid": call_sid, "spoken": spoken},
    )

    if state.get("intent") == "check_status":
        return await _read_status(db, order.id, order.external_order_id)

    return _xml(twiml.ask_claim_type())


@router.post("/collect-claim-type")
async def collect_claim_type(request: Request, db: AsyncSession = Depends(get_session)):
    form = await request.form()
    call_sid = form.get("CallSid", "")
    spoken = form.get("SpeechResult") or ""

    state = await call_state.load(call_sid)
    if not state.get("order_id"):
        return _xml(twiml.ask_order_id())

    nlu_result = await nlu.extract_intent([spoken])
    claim_type = nlu_result.claim_type or "damaged"

    order_id = uuid.UUID(state["order_id"])
    customer_id = uuid.UUID(state["customer_id"])

    claim = await claim_service.create_claim(
        db,
        order_id=order_id,
        customer_id=customer_id,
        claim_type=ClaimType(claim_type),
        intake_channel="voice",
        call_sid=call_sid,
        verbal_description=spoken,
        commit=False,
    )
    await log_event(
        db,
        channel=InteractionChannel.VOICE,
        direction=InteractionDirection.INBOUND,
        event_type="claim_created",
        order_id=order_id,
        claim_id=claim.id,
        customer_id=customer_id,
        content_text=f"Claim opened via voice ({claim_type}): {spoken}",
        metadata={"call_sid": call_sid},
        commit=False,
    )
    await db.commit()

    # Bridge to WhatsApp: seed a session so the customer's photos attach to this
    # claim, then send the photo request to their number.
    customer = await order_service.get_customer_by_phone(db, state.get("from_phone", ""))
    phone = customer.phone_e164 if customer else state.get("from_phone")
    if phone:
        await wa_intake.seed_media_session(
            phone,
            claim_id=str(claim.id),
            order_id=str(order_id),
            order_external=state.get("order_external", ""),
            customer_id=str(customer_id),
            claim_type=claim_type,
        )
        _enqueue_send_text(
            phone,
            f"Hi! Following up on your call about order {state.get('order_external', '')}. "
            "Please send a photo of the item, then a photo of the shipping label, and "
            "we'll process your claim.",
        )
        await log_event(
            db,
            channel=InteractionChannel.WHATSAPP,
            direction=InteractionDirection.OUTBOUND,
            event_type="media_request_sent",
            order_id=order_id,
            claim_id=claim.id,
            customer_id=customer_id,
            content_text="Photo request sent after voice intake",
        )

    return _xml(twiml.claim_created_sent_whatsapp())


@router.post("/check-status")
async def check_status(request: Request, db: AsyncSession = Depends(get_session)):
    form = await request.form()
    call_sid = form.get("CallSid", "")
    state = await call_state.load(call_sid)
    order_id = state.get("order_id")
    if not order_id:
        return _xml(twiml.ask_order_id())
    return await _read_status(db, uuid.UUID(order_id), state.get("order_external", ""))


async def _read_status(db: AsyncSession, order_id: uuid.UUID, order_external: str) -> Response:
    claim = await order_service.get_latest_claim_for_order(db, order_id)
    if claim is None:
        message = (f"I don't see any active claim for order {order_external}. "
                   "If something is wrong with your order, please press 1 to file a claim.")
    else:
        # Reuse the WhatsApp status copy, stripped of chat formatting.
        message = wa_intake._status_message(order_external, claim).replace("*", "")

    await log_event(
        db,
        channel=InteractionChannel.VOICE,
        direction=InteractionDirection.OUTBOUND,
        event_type="status_check",
        order_id=order_id,
        claim_id=claim.id if claim else None,
        customer_id=claim.customer_id if claim else None,
        content_text=message,
    )
    return _xml(twiml.say_status(message))


# ── Outbound clarification response ───────────────────────────────────────────

@router.post("/clarification-response")
async def clarification_response(
    request: Request,
    claim_id: str,
    db: AsyncSession = Depends(get_session),
):
    form = await request.form()
    recording_url = form.get("RecordingUrl")
    speech_result = form.get("SpeechResult")

    answer = (speech_result or "").strip()
    if not answer and recording_url:
        answer = await _transcribe_recording(recording_url)

    cid = uuid.UUID(claim_id)
    claim = await claim_service.get_claim(db, cid)
    if claim is None:
        return _xml(twiml.say_and_hangup("We couldn't find your claim. Goodbye."))

    # Append the clarification to the claim and re-run analysis.
    existing = claim.verbal_description or ""
    claim.verbal_description = (existing + "\n[clarification] " + answer).strip()
    await log_event(
        db,
        channel=InteractionChannel.VOICE,
        direction=InteractionDirection.INBOUND,
        event_type="clarification_received",
        order_id=claim.order_id,
        claim_id=claim.id,
        customer_id=claim.customer_id,
        content_text=answer,
        media_url=recording_url,
        commit=False,
    )
    await db.commit()

    _enqueue_process_claim(claim.id)
    return _xml(twiml.clarification_thanks())


async def _transcribe_recording(recording_url: str) -> str:
    """Download the Twilio recording and transcribe it with Whisper."""
    url = recording_url if recording_url.endswith(".wav") else f"{recording_url}.wav"
    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            resp = await client.get(
                url, auth=(settings.twilio_account_sid, settings.twilio_auth_token)
            )
            resp.raise_for_status()
        return stt.transcribe_bytes(resp.content, suffix=".wav")
    except Exception as exc:
        logger.warning("Failed to transcribe clarification recording: %s", exc)
        return ""


# ── Audio serving (Piper <Play>) ──────────────────────────────────────────────

@router.get("/audio/{filename}")
async def serve_audio(filename: str):
    from app.voice import tts

    path = tts.audio_path(filename)
    if not path.exists():
        return Response(status_code=404)
    return FileResponse(str(path), media_type="audio/wav")


# ── Celery enqueue helpers ────────────────────────────────────────────────────

def _enqueue_send_text(phone: str, body: str) -> None:
    from worker.tasks.send_whatsapp import send_text
    send_text.delay(phone, body)


def _enqueue_process_claim(claim_id: uuid.UUID) -> None:
    from worker.celery_app import celery_app
    celery_app.send_task(
        "worker.tasks.process_claim.process_claim", args=[str(claim_id)], queue="claims"
    )
