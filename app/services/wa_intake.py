"""
WhatsApp intake — NLU-driven, multi-turn natural conversation.

A customer can complete an entire claim over WhatsApp without ever calling and
without any special commands. Every inbound text is run through `extract_intent`
(Gemini, with a heuristic fallback); the FSM fills whatever fields it can from
each message and asks — conversationally — only for what is still missing.

Conversation state lives in Redis (`wa_session:{phone}`, TTL 1 hour) so it
survives across messages. The handlers return the reply text; the router is
responsible for actually sending it and logging the outbound event.

Flow (fields gathered in any order the customer provides them):
    intent ─▶ order ─▶ claim_type ─▶ create claim ─▶ item photo ─▶ label photo ─▶ analyze
"""
from __future__ import annotations

import json
import logging
import uuid
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.redis_client import get_redis
from app.services import nlu, order_service, claim_service
from app.services.interaction_log_service import log_event
from app.models.interaction_log import InteractionChannel, InteractionDirection
from app.models.claim import Claim, ClaimStatus, ClaimType

logger = logging.getLogger(__name__)

_SESSION_PREFIX = "wa_session:"
_SESSION_TTL = 3600  # 1 hour
_HISTORY_MAX = 8

_CLAIM_TYPE_LABEL = {
    "damaged": "damaged",
    "not_received": "not received",
    "wrong_item": "the wrong item",
    "missing_parts": "missing parts",
}


# ── Session helpers ────────────────────────────────────────────────────────────

async def _load_session(phone: str) -> dict:
    redis = await get_redis()
    raw = await redis.get(f"{_SESSION_PREFIX}{phone}")
    if raw:
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            pass
    return {"phone": phone, "history": []}


async def _save_session(phone: str, session: dict) -> None:
    redis = await get_redis()
    await redis.set(f"{_SESSION_PREFIX}{phone}", json.dumps(session), ex=_SESSION_TTL)


async def reset_session(phone: str) -> None:
    redis = await get_redis()
    await redis.delete(f"{_SESSION_PREFIX}{phone}")


async def seed_media_session(
    phone: str,
    *,
    claim_id: str,
    order_id: str,
    order_external: str,
    customer_id: str,
    claim_type: str,
) -> None:
    """
    Pre-populate a WhatsApp session for a claim that was started on another
    channel (e.g. a voice call). When the customer then sends photos over
    WhatsApp, the inbound router finds this active claim via
    `get_active_claim_id()` and attaches the media correctly.
    """
    session = {
        "phone": phone,
        "history": [],
        "intent": "file_claim",
        "claim_id": claim_id,
        "order_id": order_id,
        "order_external": order_external,
        "customer_id": customer_id,
        "claim_type": claim_type,
        "awaiting": "media_item",
    }
    await _save_session(phone, session)


# ── Text handler ───────────────────────────────────────────────────────────────

async def handle_text_message(db: AsyncSession, phone: str, text: str) -> str:
    """Process one inbound text message and return the bot's reply."""
    session = await _load_session(phone)
    session["history"] = (session.get("history", []) + [text])[-_HISTORY_MAX:]

    # If we previously offered a choice between several orders, try to resolve it.
    if session.get("pending_order_choices"):
        resolved = _resolve_order_choice(session, text)
        if resolved is None:
            await _save_session(phone, session)
            return _format_order_choices(session["pending_order_choices"])
        _apply_order(session, resolved)
        session.pop("pending_order_choices", None)

    result = await nlu.extract_intent(session["history"])

    # Merge newly extracted fields without overwriting what we already know.
    if result.intent and session.get("intent") in (None, "unknown"):
        session["intent"] = result.intent
    if result.claim_type and not session.get("claim_type"):
        session["claim_type"] = result.claim_type
    if result.order_id and not session.get("order_id"):
        reply = await _try_resolve_order(db, session, result.order_id)
        if reply is not None:  # ambiguous or not found → ask, stop here
            await _save_session(phone, session)
            return reply

    reply = await _advance(db, session)
    await _save_session(phone, session)
    return reply


# ── Image handler ──────────────────────────────────────────────────────────────

async def handle_image_received(db: AsyncSession, phone: str, claim: Claim) -> str:
    """
    Called by the router AFTER it has downloaded+stored the photo and attached it
    to the claim. Decides what to say next based on which photos are now present.
    """
    session = await _load_session(phone)

    if claim_service.has_both_photos(claim):
        session["awaiting"] = "analysis"
        await _save_session(phone, session)
        return (
            "Got both photos — analyzing them now. "
            "You'll hear back within a minute with the outcome of your claim. 🔍"
        )

    # Only one photo so far → ask for whichever is missing.
    if claim.media_r2_key_item and not claim.media_r2_key_label:
        session["awaiting"] = "media_label"
        await _save_session(phone, session)
        return "Thanks! Now please send a clear photo of the *shipping label* on the package."

    session["awaiting"] = "media_item"
    await _save_session(phone, session)
    return "Thanks! Now please send a photo of the *damaged item* itself."


async def get_active_claim_id(phone: str) -> Optional[uuid.UUID]:
    session = await _load_session(phone)
    cid = session.get("claim_id")
    return uuid.UUID(cid) if cid else None


# ── FSM core: decide the next prompt ───────────────────────────────────────────

async def _advance(db: AsyncSession, session: dict) -> str:
    intent = session.get("intent")

    # Status check is terminal: report and (if resolved) stop here.
    if intent == "check_status":
        if not session.get("order_id"):
            return ("Sure — I can check that for you. What's your order number? "
                    "You'll find it in your confirmation email.")
        return await _build_status_reply(db, session)

    # Claim-filing path (also the default once a claim_type is known).
    if not session.get("order_id"):
        if intent == "greeting":
            return ("Hi! 👋 I'm here to help with any problems with your order. "
                    "What happened, and what's your order number?")
        if intent in (None, "unknown") and not session.get("claim_type"):
            return ("I'm sorry to hear there's an issue. Could you tell me what happened "
                    "with your order, and share your order number?")
        return ("I can help with that! Could you share your *order number*? "
                "You'll find it in your confirmation email.")

    if not session.get("claim_type"):
        return ("Got it. What went wrong with the order? Was the item *damaged*, "
                "did it *not arrive*, was it the *wrong item*, or were there *missing parts*?")

    # We have order + claim_type → ensure a claim exists.
    if not session.get("claim_id"):
        claim = await _create_claim(db, session)
        session["claim_id"] = str(claim.id)
        session["awaiting"] = "media_item"
        label = _CLAIM_TYPE_LABEL.get(session["claim_type"], "affected")
        return (f"I've opened a claim for order *{session.get('order_external', '')}* "
                f"({label}). Please send a photo of the item.")

    # Claim already exists → re-prompt for whichever photo we're still waiting on.
    awaiting = session.get("awaiting")
    if awaiting == "media_label":
        return "I'm still waiting on a photo of the *shipping label*. Please send it when you can."
    if awaiting == "analysis":
        return "Your photos are in and being analyzed — I'll message you the moment there's an update."
    return "Please send a photo of the *damaged item* to continue with your claim."


# ── Order resolution ───────────────────────────────────────────────────────────

async def _try_resolve_order(db: AsyncSession, session: dict, raw_order: str) -> Optional[str]:
    """
    Attempt to resolve an order from the customer's text.
    Returns a reply string if the caller must ask the customer something
    (ambiguous / not found), or None if resolution succeeded silently.
    """
    customer = await order_service.get_customer_by_phone(db, session["phone"])
    customer_id = customer.id if customer else None

    matches = await order_service.lookup_fuzzy(db, raw_order, customer_id)
    if not matches and customer_id is not None:
        # Fall back to an unscoped search (WhatsApp number may differ from the
        # number on file for the order).
        matches = await order_service.lookup_fuzzy(db, raw_order, None)

    if len(matches) == 1:
        _apply_order(session, matches[0])
        return None

    if len(matches) > 1:
        choices = [{"id": str(o.id), "external": o.external_order_id,
                    "customer_id": str(o.customer_id),
                    "product": o.product_description[:40]} for o in matches]
        session["pending_order_choices"] = choices
        return _format_order_choices(choices)

    return (f"I couldn't find an order matching \"{raw_order}\". "
            "Could you double-check the number? It's in your confirmation email.")


def _apply_order(session: dict, order) -> None:
    session["order_id"] = str(order.id)
    session["order_external"] = order.external_order_id
    if order.customer_id is not None:
        session["customer_id"] = str(order.customer_id)


def _resolve_order_choice(session: dict, text: str) -> Optional[object]:
    """Match the customer's reply against a previously offered list of orders."""
    choices = session.get("pending_order_choices", [])
    t = text.strip().lower()

    # Reply by position ("1", "2", ...)
    if t.isdigit():
        idx = int(t) - 1
        if 0 <= idx < len(choices):
            return _ChoiceOrder(choices[idx])

    # Reply by (part of) the order number
    for c in choices:
        if c["external"].lower() in t or t in c["external"].lower():
            return _ChoiceOrder(c)
    return None


class _ChoiceOrder:
    """Lightweight stand-in so `_apply_order` can consume a choice dict."""
    def __init__(self, choice: dict):
        self.id = uuid.UUID(choice["id"])
        self.external_order_id = choice["external"]
        cust = choice.get("customer_id")
        self.customer_id = uuid.UUID(cust) if cust else None


def _format_order_choices(choices: list[dict]) -> str:
    lines = ["I found a few orders. Which one is it? Reply with the number:"]
    for i, c in enumerate(choices, 1):
        lines.append(f"{i}. {c['external']} — {c['product']}")
    return "\n".join(lines)


# ── Claim creation + status reply ──────────────────────────────────────────────

async def _create_claim(db: AsyncSession, session: dict) -> Claim:
    order_id = uuid.UUID(session["order_id"])
    customer_id = session.get("customer_id")
    if customer_id is None:
        # Resolve from the order if we don't already have it.
        order = await order_service.get_order_by_external_id(db, session["order_external"])
        customer_id = order.customer_id if order else None
    else:
        customer_id = uuid.UUID(customer_id)

    claim = await claim_service.create_claim(
        db,
        order_id=order_id,
        customer_id=customer_id,
        claim_type=ClaimType(session["claim_type"]),
        intake_channel="whatsapp",
        commit=False,
    )
    await log_event(
        db,
        channel=InteractionChannel.SYSTEM,
        direction=InteractionDirection.INTERNAL,
        event_type="claim_created",
        order_id=order_id,
        claim_id=claim.id,
        customer_id=customer_id,
        content_text=f"Claim opened via WhatsApp ({session['claim_type']})",
        commit=False,
    )
    await db.commit()
    return claim


async def _build_status_reply(db: AsyncSession, session: dict) -> str:
    order_id = uuid.UUID(session["order_id"])
    claim = await order_service.get_latest_claim_for_order(db, order_id)
    ext = session.get("order_external", "")
    if claim is None:
        return (f"I don't see any active claim for order *{ext}*. "
                "If something's wrong with it, tell me what happened and I'll start one.")
    return _status_message(ext, claim)


def _status_message(ext: str, claim: Claim) -> str:
    status = claim.status
    if status in (ClaimStatus.PENDING_MEDIA,):
        return (f"Your claim for order *{ext}* is open and waiting on photos. "
                "Please send a photo of the item and the shipping label to continue.")
    if status in (ClaimStatus.MEDIA_RECEIVED, ClaimStatus.ANALYZING):
        return f"Your claim for order *{ext}* is currently being reviewed. I'll update you shortly."
    if status == ClaimStatus.PENDING_CLARIFICATION:
        return (f"Your claim for order *{ext}* needs a little more information — "
                "we'll reach out shortly to clarify.")
    if status in (ClaimStatus.APPROVED, ClaimStatus.REPLACED):
        return f"Good news — your claim for order *{ext}* was approved and a replacement is on the way. ✅"
    if status == ClaimStatus.REFUNDED:
        return f"Your claim for order *{ext}* was approved and a refund has been issued. ✅"
    if status == ClaimStatus.REJECTED:
        return (f"Your claim for order *{ext}* was reviewed and could not be approved. "
                "Reply here if you'd like to discuss it further.")
    if status == ClaimStatus.ESCALATED:
        return (f"Your claim for order *{ext}* is under manual review by our team. "
                "We'll be in touch soon.")
    return f"Your claim for order *{ext}* is currently: {status.value}."
