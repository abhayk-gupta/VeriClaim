"""
Gemini 2.5 Flash-Lite vision wrapper for damage analysis.

`analyze_damage()` sends the item photo (and the shipping-label photo when
present) to Gemini and returns a structured assessment. Rate-limit errors
(429 / ResourceExhausted) are retried with exponential backoff via tenacity.

If no API key is configured, a deterministic mock result is returned so the
whole pipeline can be exercised locally without burning quota.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Optional

from tenacity import (
    retry,
    wait_exponential,
    stop_after_attempt,
    retry_if_exception_type,
)

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


# Retry only on transient rate-limit/quota errors. Import lazily/defensively so
# the module loads even if google-api-core's exception layout shifts.
try:  # pragma: no cover - import shape varies by version
    from google.api_core.exceptions import ResourceExhausted, ServiceUnavailable
    _RETRYABLE: tuple = (ResourceExhausted, ServiceUnavailable)
except Exception:  # pragma: no cover
    _RETRYABLE = (Exception,)


_VISION_PROMPT = """You are a damage-claims vision analyst for an e-commerce store.
You are given a photo of a product the customer says has a problem, and (optionally)
a photo of the shipping label on the package.

The customer's stated claim type is: {claim_type}
The ordered product is described as: {product_description}

Analyze the image(s) and return ONLY a JSON object with these exact keys:
- "item_description": short description of what you see in the item photo
- "damage_type": e.g. "cracked_screen", "dented", "shattered", "torn_packaging",
  "water_damage", "none", "not_applicable"
- "damage_severity": one of ["none", "minor", "moderate", "severe"]
- "label_match": true if the shipping label appears genuine and matches a real
  shipment (carrier markings, barcode, address block), false if missing/obscured,
  null if no label photo was provided
- "anomalies": array of short strings for anything suspicious — e.g.
  "appears to be a stock/marketing image", "screenshot of another photo",
  "label is blurry or obscured", "item does not match ordered product",
  "no visible damage despite damage claim". Empty array if nothing suspicious.
- "confidence": float 0.0-1.0 — how confident you are in this overall assessment
- "assessment": one-sentence plain-language summary for the case notes

Return ONLY the JSON object. No markdown fences, no prose."""


async def analyze_damage(
    *,
    item_image: bytes,
    label_image: Optional[bytes],
    claim_type: str,
    product_description: str,
    customer_note: Optional[str] = None,
) -> dict:
    if not settings.gemini_api_key:
        logger.info("No GEMINI_API_KEY — returning mock vision analysis")
        return _mock_analysis(claim_type, has_label=label_image is not None)

    return await _gemini_analyze(
        item_image=item_image,
        label_image=label_image,
        claim_type=claim_type,
        product_description=product_description,
        customer_note=customer_note,
    )


@retry(
    wait=wait_exponential(min=4, max=60),
    stop=stop_after_attempt(3),
    retry=retry_if_exception_type(_RETRYABLE),
    reraise=True,
)
async def _gemini_analyze(
    *,
    item_image: bytes,
    label_image: Optional[bytes],
    claim_type: str,
    product_description: str,
    customer_note: Optional[str] = None,
) -> dict:
    import google.generativeai as genai

    genai.configure(api_key=settings.gemini_api_key)
    model = genai.GenerativeModel(settings.gemini_model)

    prompt = _VISION_PROMPT.format(
        claim_type=claim_type, product_description=product_description
    )
    if customer_note:
        prompt += f"\n\nAdditional context from the customer: {customer_note}"
    parts: list = [prompt, {"mime_type": "image/jpeg", "data": item_image}]
    if label_image is not None:
        parts.append({"mime_type": "image/jpeg", "data": label_image})

    resp = await model.generate_content_async(
        parts,
        generation_config={"temperature": 0.1, "response_mime_type": "application/json"},
    )
    return _parse_response(resp.text or "")


def _parse_response(raw: str) -> dict:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```[a-zA-Z]*\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw).strip()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("Gemini returned non-JSON, treating as low-confidence: %r", raw[:200])
        return {
            "item_description": "",
            "damage_type": "unknown",
            "damage_severity": "none",
            "label_match": None,
            "anomalies": ["model_response_unparseable"],
            "confidence": 0.0,
            "assessment": "Could not parse model response.",
        }

    return {
        "item_description": str(data.get("item_description", "")),
        "damage_type": str(data.get("damage_type", "unknown")),
        "damage_severity": _norm_severity(data.get("damage_severity")),
        "label_match": data.get("label_match"),
        "anomalies": list(data.get("anomalies") or []),
        "confidence": _norm_confidence(data.get("confidence")),
        "assessment": str(data.get("assessment", "")),
    }


def _norm_severity(value) -> str:
    v = str(value or "none").lower()
    return v if v in {"none", "minor", "moderate", "severe"} else "none"


def _norm_confidence(value) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return 0.0


def _mock_analysis(claim_type: str, has_label: bool) -> dict:
    """Deterministic stand-in used when no API key is configured."""
    return {
        "item_description": "Mock analysis (no Gemini API key configured).",
        "damage_type": "cracked" if claim_type == "damaged" else "not_applicable",
        "damage_severity": "moderate" if claim_type == "damaged" else "none",
        "label_match": True if has_label else None,
        "anomalies": [],
        "confidence": 0.82,
        "assessment": f"Mock assessment for a '{claim_type}' claim; visible issue consistent with claim.",
    }
