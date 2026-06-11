"""
Node: analyze_image

Sends the ingested photo bytes to Gemini 2.5 Flash-Lite and records the
structured vision assessment (item description, damage type/severity, label
match, anomalies, confidence) onto the state.
"""
from __future__ import annotations

import logging

from app.langgraph_agent.tools import gemini_client
from app.langgraph_agent.state import ClaimState

logger = logging.getLogger(__name__)


async def analyze_image(state: ClaimState) -> dict:
    try:
        result = await gemini_client.analyze_damage(
            item_image=state["item_image"],
            label_image=state.get("label_image"),
            claim_type=state.get("claim_type", "damaged"),
            product_description=state.get("product_description", ""),
            customer_note=state.get("verbal_description"),
        )
    except Exception as exc:
        logger.exception("Gemini analysis failed for claim %s", state.get("claim_id"))
        return {"error": f"vision_analysis_failed: {exc}"}

    logger.info(
        "Analyzed claim %s: damage=%s/%s confidence=%.2f anomalies=%d",
        state.get("claim_id"),
        result["damage_type"],
        result["damage_severity"],
        result["confidence"],
        len(result["anomalies"]),
    )
    return {
        "gemini_item_description": result["item_description"],
        "gemini_damage_type": result["damage_type"],
        "gemini_damage_severity": result["damage_severity"],
        "gemini_label_match": result["label_match"],
        "gemini_confidence": result["confidence"],
        "gemini_anomalies": result["anomalies"],
        "gemini_assessment": result["assessment"],
    }
