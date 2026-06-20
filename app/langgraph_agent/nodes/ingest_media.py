"""
Node: ingest_media

Loads the stored photo bytes from permanent storage (Cloudflare R2 / Redis) using
the keys captured at webhook time. Reading from permanent storage — never the
expiring Meta/Twilio CDN link — is what lets analysis run safely more than 24h
after the customer sent the photos.

On any failure it sets `state["error"]`, which the graph routes straight to
update_database (so the claim is marked for manual review rather than silently
stalling).
"""
from __future__ import annotations

import logging

from app.services import media_storage
from app.langgraph_agent.state import ClaimState

logger = logging.getLogger(__name__)


async def ingest_media(state: ClaimState) -> dict:
    item_key = state.get("media_r2_key_item")
    if not item_key:
        return {"error": "no_item_media_key"}

    try:
        item_bytes = await media_storage.get_image(item_key)
    except Exception as exc:
        logger.exception("Failed to load item media %s", item_key)
        return {"error": f"item_media_load_failed: {exc}"}

    update: dict = {"item_image": item_bytes}

    label_key = state.get("media_r2_key_label")
    if label_key:
        try:
            update["label_image"] = await media_storage.get_image(label_key)
        except Exception as exc:
            # Missing label is not fatal — analysis can proceed and the label
            # match simply reads as unavailable.
            logger.warning("Failed to load label media %s: %s", label_key, exc)
            update["label_image"] = None
    else:
        update["label_image"] = None

    logger.info(
        "Ingested media for claim %s (item=%d bytes, label=%s)",
        state.get("claim_id"),
        len(item_bytes),
        "yes" if update.get("label_image") else "no",
    )
    return update
