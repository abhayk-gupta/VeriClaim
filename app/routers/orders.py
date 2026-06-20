"""
Orders REST API (`/api/v1/orders`).

  GET /orders/{order_ref}            order detail (by UUID or external_order_id)
  GET /orders/{order_ref}/timeline   full cross-channel interaction history

The timeline endpoint is the support agent's single pane of glass: every WhatsApp
message, voice call, system decision, and Gemini run linked to the order, sorted
chronologically — regardless of which channel the customer used.
"""
from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.models.order import Order
from app.models.claim import Claim
from app.models.interaction_log import InteractionLog
from app.schemas.order import OrderRead
from app.schemas.interaction import OrderTimeline, InteractionLogRead

router = APIRouter(prefix="/orders", tags=["orders"])


async def _resolve_order(db: AsyncSession, order_ref: str) -> Optional[Order]:
    """Look up an order by UUID primary key or by external_order_id."""
    try:
        oid = uuid.UUID(order_ref)
    except ValueError:
        oid = None

    if oid is not None:
        order = await db.get(Order, oid)
        if order is not None:
            return order

    result = await db.execute(
        select(Order).where(Order.external_order_id == order_ref)
    )
    return result.scalar_one_or_none()


@router.get("/{order_ref}", response_model=OrderRead)
async def get_order(order_ref: str, db: AsyncSession = Depends(get_session)):
    order = await _resolve_order(db, order_ref)
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")
    return order


@router.get("/{order_ref}/timeline", response_model=OrderTimeline)
async def get_order_timeline(order_ref: str, db: AsyncSession = Depends(get_session)):
    order = await _resolve_order(db, order_ref)
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")

    events = (await db.execute(
        select(InteractionLog)
        .where(InteractionLog.order_id == order.id)
        .order_by(InteractionLog.created_at)
    )).scalars().all()

    claim_count = await db.scalar(
        select(func.count()).select_from(Claim).where(Claim.order_id == order.id)
    )

    return OrderTimeline(
        order=OrderRead.model_validate(order),
        events=[InteractionLogRead.model_validate(e) for e in events],
        claim_count=int(claim_count or 0),
    )
