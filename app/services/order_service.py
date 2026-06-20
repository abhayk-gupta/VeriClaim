"""
Order + customer lookup helpers used by both WhatsApp and voice intake.

`lookup_fuzzy()` powers natural-language order matching: customers rarely type
the exact `external_order_id`, so we normalize their text (strip spaces,
hyphens, surrounding words) and match on the digit core.
"""
from __future__ import annotations

import re
import uuid
from typing import Optional

from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.customer import Customer
from app.models.order import Order
from app.models.claim import Claim


_DIGITS = re.compile(r"\d+")


def _digit_core(raw: str) -> str:
    """Extract the longest run of digits from arbitrary customer text."""
    if not raw:
        return ""
    runs = _DIGITS.findall(raw)
    return max(runs, key=len) if runs else ""


async def get_customer_by_phone(session: AsyncSession, phone_e164: str) -> Optional[Customer]:
    result = await session.execute(
        select(Customer).where(Customer.phone_e164 == phone_e164)
    )
    return result.scalar_one_or_none()


async def get_or_create_customer(
    session: AsyncSession, phone_e164: str, full_name: str = "WhatsApp Customer"
) -> Customer:
    customer = await get_customer_by_phone(session, phone_e164)
    if customer is None:
        customer = Customer(phone_e164=phone_e164, full_name=full_name, whatsapp_opt_in=True)
        session.add(customer)
        await session.flush()
    return customer


async def get_order_by_external_id(session: AsyncSession, external_order_id: str) -> Optional[Order]:
    result = await session.execute(
        select(Order).where(Order.external_order_id == external_order_id)
    )
    return result.scalar_one_or_none()


async def lookup_fuzzy(
    session: AsyncSession,
    raw_text: str,
    customer_id: Optional[uuid.UUID] = None,
) -> list[Order]:
    """
    Find orders whose external_order_id contains the digit core of `raw_text`.
    If `customer_id` is given, results are scoped to that customer (preferred —
    avoids cross-customer matches on short numbers).

    Returns a list (possibly empty). The caller decides:
      - 0 matches  -> ask the customer to re-check the number
      - 1 match    -> proceed
      - >1 matches -> ask the customer to confirm which order
    """
    core = _digit_core(raw_text)
    if not core:
        return []

    stmt = select(Order).where(
        func.lower(Order.external_order_id).like(f"%{core.lower()}%")
    )
    if customer_id is not None:
        stmt = stmt.where(Order.customer_id == customer_id)
    stmt = stmt.order_by(desc(Order.created_at)).limit(5)

    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_latest_claim_for_order(session: AsyncSession, order_id: uuid.UUID) -> Optional[Claim]:
    result = await session.execute(
        select(Claim).where(Claim.order_id == order_id).order_by(desc(Claim.created_at)).limit(1)
    )
    return result.scalar_one_or_none()
