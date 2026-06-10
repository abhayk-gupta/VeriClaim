import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel

from app.models.order import OrderStatus


class OrderBase(BaseModel):
    external_order_id: str
    store_name: str
    product_description: str
    order_value_usd: Decimal
    currency: str = "USD"
    status: OrderStatus = OrderStatus.PROCESSING
    tracking_number: Optional[str] = None
    carrier: Optional[str] = None
    shipped_at: Optional[datetime] = None
    delivered_at: Optional[datetime] = None
    policy_id: str = "default"


class OrderCreate(OrderBase):
    customer_id: uuid.UUID


class OrderRead(OrderBase):
    id: uuid.UUID
    customer_id: uuid.UUID
    created_at: datetime

    model_config = {"from_attributes": True}
