"""
Claim lifecycle helpers: create a claim, attach media keys as photos arrive,
and transition status. Shared by WhatsApp intake, voice intake, and the
LangGraph engine.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.claim import Claim, ClaimType, ClaimStatus


async def create_claim(
    session: AsyncSession,
    *,
    order_id: uuid.UUID,
    customer_id: uuid.UUID,
    claim_type: Optional[ClaimType | str] = None,
    intake_channel: str = "whatsapp",
    call_sid: Optional[str] = None,
    verbal_description: Optional[str] = None,
    commit: bool = True,
) -> Claim:
    if isinstance(claim_type, str):
        claim_type = ClaimType(claim_type)

    claim = Claim(
        order_id=order_id,
        customer_id=customer_id,
        claim_type=claim_type,
        status=ClaimStatus.PENDING_MEDIA,
        intake_channel=intake_channel,
        call_sid=call_sid,
        verbal_description=verbal_description,
    )
    session.add(claim)
    if commit:
        await session.commit()
    else:
        await session.flush()
    return claim


async def get_claim(session: AsyncSession, claim_id: uuid.UUID) -> Optional[Claim]:
    result = await session.execute(select(Claim).where(Claim.id == claim_id))
    return result.scalar_one_or_none()


async def attach_media(
    session: AsyncSession,
    claim: Claim,
    *,
    side: str,  # "item" | "label"
    meta_media_id: str,
    r2_key: str,
    commit: bool = True,
) -> Claim:
    """Record a received photo. Marks media_received_at and advances status once
    both photos are present."""
    if side == "item":
        claim.media_url_item = meta_media_id
        claim.media_r2_key_item = r2_key
    elif side == "label":
        claim.media_url_label = meta_media_id
        claim.media_r2_key_label = r2_key
    else:
        raise ValueError(f"Unknown media side: {side!r}")

    claim.media_received_at = datetime.now(timezone.utc)

    if claim.media_r2_key_item and claim.media_r2_key_label:
        claim.status = ClaimStatus.MEDIA_RECEIVED

    if commit:
        await session.commit()
    else:
        await session.flush()
    return claim


async def set_status(
    session: AsyncSession,
    claim: Claim,
    status: ClaimStatus,
    commit: bool = True,
) -> Claim:
    claim.status = status
    if commit:
        await session.commit()
    else:
        await session.flush()
    return claim


def has_both_photos(claim: Claim) -> bool:
    return bool(claim.media_r2_key_item and claim.media_r2_key_label)
