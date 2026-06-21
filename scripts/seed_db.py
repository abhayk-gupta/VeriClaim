"""
Seed the database with test customers and orders for local development.

Usage (inside Docker):
    docker compose exec api python scripts/seed_db.py

Usage (local venv):
    DATABASE_URL=postgresql+asyncpg://vericlaim:secret@localhost:5432/vericlaim \
    python scripts/seed_db.py
"""
import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import get_settings
from app.models.customer import Customer
from app.models.order import Order

settings = get_settings()

engine = create_async_engine(settings.database_url, echo=False)
SessionLocal = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)


async def seed():
    async with SessionLocal() as session:
        async with session.begin():

            # ── Customers ──────────────────────────────────────────────────────
            customer1 = Customer(
                id=uuid.UUID("11111111-1111-1111-1111-111111111111"),
                phone_e164="+14155551001",
                full_name="Alice Johnson",
                email="alice@example.com",
                whatsapp_opt_in=True,
            )
            customer2 = Customer(
                id=uuid.UUID("22222222-2222-2222-2222-222222222222"),
                phone_e164="+14155551002",
                full_name="Bob Martinez",
                email="bob@example.com",
                whatsapp_opt_in=True,
            )
            customer3 = Customer(
                id=uuid.UUID("33333333-3333-3333-3333-333333333333"),
                phone_e164="+14155551003",
                full_name="Chidi Okeke",
                email="chidi@example.com",
                whatsapp_opt_in=False,
            )

            session.add_all([customer1, customer2, customer3])
            await session.flush()

            # Ensure 'now' is completely timezone-naive to match the database
            now = datetime.now(timezone.utc).replace(tzinfo=None)

            # ── Orders (Using explicit lowercase strings to match PG Enum values) ──
            orders = [
                Order(
                    id=uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
                    external_order_id="ORD-10001",
                    customer_id=customer1.id,
                    store_name="TechDeals",
                    product_description="Sony WH-1000XM5 Wireless Headphones — Black",
                    product_image_url="https://images.unsplash.com/photo-1618366712010-f4ae9c647dcb?w=500&q=80",
                    order_value_usd=Decimal("279.99"),
                    currency="USD",
                    status="delivered",
                    tracking_number="1Z999AA10123456784",
                    carrier="UPS",
                    shipped_at=now - timedelta(days=10),
                    delivered_at=now - timedelta(days=5),
                    policy_id="electronics",
                ),
                Order(
                    id=uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"),
                    external_order_id="ORD-10002",
                    customer_id=customer2.id,
                    store_name="HomeGoods",
                    product_description="Ceramic Coffee Mug Set (4 pack) — Ocean Blue",
                    product_image_url="https://images.unsplash.com/photo-1514228742587-6b1558fcca3d?w=500&q=80",
                    order_value_usd=Decimal("34.99"),
                    currency="USD",
                    status="delivered",
                    tracking_number="9400111899223775357977",
                    carrier="USPS",
                    shipped_at=now - timedelta(days=7),
                    delivered_at=now - timedelta(days=2),
                    policy_id="default",
                ),
                Order(
                    id=uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc"),
                    external_order_id="ORD-10003",
                    customer_id=customer3.id,
                    store_name="FashionHub",
                    product_description="Merino Wool Sweater — Size M — Forest Green",
                    order_value_usd=Decimal("89.00"),
                    currency="USD",
                    status="delivered",
                    shipped_at=now - timedelta(days=14),
                    delivered_at=now - timedelta(days=8),
                    policy_id="default",
                ),
                Order(
                    id=uuid.UUID("dddddddd-dddd-dddd-dddd-dddddddddddd"),
                    external_order_id="ORD-10004",
                    customer_id=customer1.id,
                    store_name="TechDeals",
                    product_description="USB-C 100W Charging Cable (2-pack)",
                    order_value_usd=Decimal("19.99"),
                    currency="USD",
                    status="shipped",
                    tracking_number="1Z999AA10123456999",
                    carrier="UPS",
                    shipped_at=now - timedelta(days=1),
                    policy_id="default",
                ),
                Order(
                    id=uuid.UUID("eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee"),
                    external_order_id="ORD-10005",
                    customer_id=customer2.id,
                    store_name="HomeGoods",
                    product_description="Glass Food Storage Containers (10 piece set)",
                    order_value_usd=Decimal("55.00"),
                    currency="USD",
                    status="delivered",
                    shipped_at=now - timedelta(days=20),
                    delivered_at=now - timedelta(days=15),
                    policy_id="default",
                ),
            ]

            session.add_all(orders)

    await engine.dispose()
    print("✓ Seeded 3 customers and 5 orders successfully.")
    print("\nTest data:")
    print("  Customer 1: Alice Johnson (+14155551001) — orders ORD-10001, ORD-10004")
    print("  Customer 2: Bob Martinez (+14155551002) — orders ORD-10002, ORD-10005")
    print("  Customer 3: Chidi Okeke  (+14155551003) — order  ORD-10003")
    print("\nUseful for testing:")
    print("  ORD-10001 — Delivered 5 days ago, electronics policy ($279.99)")
    print("  ORD-10002 — Delivered 2 days ago, default policy ($34.99)")
    print("  ORD-10003 — Delivered 8 days ago, default policy ($89.00)")


if __name__ == "__main__":
    asyncio.run(seed())