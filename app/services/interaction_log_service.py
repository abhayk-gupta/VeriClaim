"""
Cross-channel event logging. Every inbound/outbound/internal event — WhatsApp
messages, voice calls, system decisions, Gemini runs — is written to
`interaction_logs` so a full per-order timeline is queryable regardless of
channel.

`log_event()` is the single entry point used by every handler.
"""
from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.interaction_log import (
    InteractionLog,
    InteractionChannel,
    InteractionDirection,
)


async def log_event(
    session: AsyncSession,
    *,
    channel: InteractionChannel | str,
    direction: InteractionDirection | str,
    event_type: str,
    order_id: Optional[uuid.UUID] = None,
    claim_id: Optional[uuid.UUID] = None,
    customer_id: Optional[uuid.UUID] = None,
    content_text: Optional[str] = None,
    media_url: Optional[str] = None,
    metadata: Optional[dict] = None,
    commit: bool = True,
) -> InteractionLog:
    """
    Insert one interaction log row. Accepts either enum members or their string
    values for `channel`/`direction` so callers can pass plain strings.

    When `commit` is False the row is flushed (so its id is populated) but the
    surrounding transaction is left open for the caller to commit.
    """
    entry = InteractionLog(
        order_id=order_id,
        claim_id=claim_id,
        customer_id=customer_id,
        channel=InteractionChannel(channel) if not isinstance(channel, InteractionChannel) else channel,
        direction=InteractionDirection(direction) if not isinstance(direction, InteractionDirection) else direction,
        event_type=event_type,
        content_text=content_text,
        media_url=media_url,
        metadata_=metadata,
    )
    session.add(entry)
    if commit:
        await session.commit()
    else:
        await session.flush()
    return entry
