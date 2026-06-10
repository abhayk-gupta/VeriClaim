"""
Lightweight natural-language understanding for inbound WhatsApp text.

Every inbound message — however it is phrased — is passed through
`extract_intent()`, which returns a small structured object the intake FSM
uses to decide what to ask next. This is the cheap NLU call, NOT the
expensive Gemini vision call used during claim analysis.

If no Gemini API key is configured (local dev), a regex/keyword heuristic
is used so the entire WhatsApp flow still works offline.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, asdict
from typing import Optional

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


# Intent + claim-type vocabularies kept in sync with app.models.claim.ClaimType
VALID_INTENTS = {"file_claim", "check_status", "greeting", "unknown"}
VALID_CLAIM_TYPES = {"damaged", "not_received", "wrong_item", "missing_parts"}


@dataclass
class NLUResult:
    intent: str = "unknown"
    claim_type: Optional[str] = None
    order_id: Optional[str] = None
    confidence: float = 0.0

    def as_dict(self) -> dict:
        return asdict(self)


_SYSTEM_PROMPT = """You are an intent classifier for an e-commerce damaged-goods support bot.
Given the recent conversation, extract a JSON object with these exact keys:
- "intent": one of ["file_claim", "check_status", "greeting", "unknown"]
- "claim_type": one of ["damaged", "not_received", "wrong_item", "missing_parts"] or null
- "order_id": the order number the customer mentions (digits/letters), or null
- "confidence": a float 0.0-1.0 for how confident you are about the intent

Rules:
- "my package is broken/damaged/cracked/shattered" -> intent=file_claim, claim_type=damaged
- "never arrived / didn't get it / missing package" -> file_claim, not_received
- "wrong item / not what I ordered / different product" -> file_claim, wrong_item
- "parts missing / incomplete / pieces missing" -> file_claim, missing_parts
- "where is my refund / claim status / what's happening with" -> check_status
- "hi / hello / hey" with nothing else -> greeting
- Only set order_id if a number/code is actually present.
Return ONLY the JSON object, no prose, no markdown fences."""


async def extract_intent(messages: list[str]) -> NLUResult:
    """
    `messages` is the recent conversation history (oldest first), the last
    element being the newest inbound text. Returns an NLUResult.
    """
    text = messages[-1] if messages else ""
    if not settings.gemini_api_key:
        return _heuristic(text)

    try:
        return await _gemini_extract(messages)
    except Exception as exc:  # never let NLU failure break the conversation
        logger.warning("Gemini NLU failed, falling back to heuristic: %s", exc)
        return _heuristic(text)


async def _gemini_extract(messages: list[str]) -> NLUResult:
    import google.generativeai as genai

    genai.configure(api_key=settings.gemini_api_key)
    model = genai.GenerativeModel(
        settings.gemini_model,
        system_instruction=_SYSTEM_PROMPT,
    )
    convo = "\n".join(f"- {m}" for m in messages[-5:])
    prompt = f"Conversation so far:\n{convo}\n\nReturn the JSON object now."

    resp = await model.generate_content_async(
        prompt,
        generation_config={"temperature": 0.0, "response_mime_type": "application/json"},
    )
    raw = (resp.text or "").strip()
    data = json.loads(_strip_fences(raw))

    intent = data.get("intent") if data.get("intent") in VALID_INTENTS else "unknown"
    claim_type = data.get("claim_type")
    if claim_type not in VALID_CLAIM_TYPES:
        claim_type = None
    order_id = data.get("order_id")
    order_id = str(order_id).strip() if order_id else None
    try:
        confidence = float(data.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0

    return NLUResult(intent=intent, claim_type=claim_type, order_id=order_id, confidence=confidence)


def _strip_fences(raw: str) -> str:
    """Remove ```json ... ``` fences if the model added them despite instructions."""
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```[a-zA-Z]*\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw)
    return raw.strip()


# ── Heuristic fallback (no API key) ────────────────────────────────────────────

_DAMAGED = re.compile(r"\b(damag|broke|broken|crack|shatter|smash|dent|destroy|spill|leak|torn|bent)", re.I)
_NOT_RECEIVED = re.compile(r"\b(not (arrive|receiv|deliver|come|get|got)|never (arrive|came|got|receiv)|missing package|didn'?t (arrive|come|get|receiv)|where is my (order|package|parcel))", re.I)
_WRONG_ITEM = re.compile(r"\b(wrong (item|product|thing|order)|(is\s?n'?t|not|n'?t) what i ordered|different (item|product)|incorrect item)", re.I)
_MISSING_PARTS = re.compile(r"\b(missing (part|piece|component)|part[s]?\b.{0,15}\bmissing|parts? (not included|are gone)|incomplete|pieces? missing|not all (the )?(parts|pieces))", re.I)
_STATUS = re.compile(r"\b(status|where is my refund|what'?s happening|any update|how long|track my claim|refund yet)", re.I)
_GREETING = re.compile(r"^\s*(hi|hello+|hey+|yo|good (morning|afternoon|evening))[\s!.]*$", re.I)
_ORDER_ID = re.compile(r"\b((?:ord[-\s]?)?\d{3,}[a-z0-9-]*)\b", re.I)


def _heuristic(text: str) -> NLUResult:
    t = text or ""

    claim_type = None
    if _NOT_RECEIVED.search(t):
        claim_type = "not_received"
    elif _WRONG_ITEM.search(t):
        claim_type = "wrong_item"
    elif _MISSING_PARTS.search(t):
        claim_type = "missing_parts"
    elif _DAMAGED.search(t):
        claim_type = "damaged"

    order_match = _ORDER_ID.search(t)
    order_id = order_match.group(1) if order_match else None

    if _STATUS.search(t):
        intent, conf = "check_status", 0.7
    elif claim_type is not None:
        intent, conf = "file_claim", 0.65
    elif _GREETING.match(t):
        intent, conf = "greeting", 0.6
    else:
        intent, conf = "unknown", 0.3

    return NLUResult(intent=intent, claim_type=claim_type, order_id=order_id, confidence=conf)
