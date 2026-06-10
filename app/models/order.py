import uuid
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional, List, TYPE_CHECKING

from sqlalchemy import String, Text, Numeric, ForeignKey, func
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.customer import Customer
    from app.models.claim import Claim


class OrderStatus(str, Enum):
    PROCESSING = "processing"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    external_order_id: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    customer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("customers.id"), index=True)
    store_name: Mapped[str] = mapped_column(String(100))
    product_description: Mapped[str] = mapped_column(Text)
    order_value_usd: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    status: Mapped[OrderStatus] = mapped_column(SQLEnum(OrderStatus), default=OrderStatus.PROCESSING)
    tracking_number: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    carrier: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    shipped_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    delivered_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    policy_id: Mapped[str] = mapped_column(String(50), default="default")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[Optional[datetime]] = mapped_column(onupdate=func.now(), nullable=True)

    customer: Mapped["Customer"] = relationship("Customer", back_populates="orders")
    claims: Mapped[List["Claim"]] = relationship("Claim", back_populates="order", lazy="select")

    def __repr__(self) -> str:
        return f"<Order id={self.id} external_id={self.external_order_id} status={self.status}>"
