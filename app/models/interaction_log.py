import uuid
from datetime import datetime
from enum import Enum
from typing import Optional

from sqlalchemy import BigInteger, String, Text, ForeignKey, func
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class InteractionChannel(str, Enum):
    WHATSAPP = "whatsapp"
    VOICE = "voice"
    SYSTEM = "system"
    API = "api"


class InteractionDirection(str, Enum):
    INBOUND = "inbound"
    OUTBOUND = "outbound"
    INTERNAL = "internal"


class InteractionLog(Base):
    """
    Cross-channel event store. Every customer-facing and system event is
    written here, linked to order_id so a full timeline is queryable
    without joining through claims.
    """
    __tablename__ = "interaction_logs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    order_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("orders.id"), index=True, nullable=True)
    claim_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("claims.id"), index=True, nullable=True)
    customer_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("customers.id"), index=True, nullable=True)

    channel: Mapped[InteractionChannel] = mapped_column(SQLEnum(InteractionChannel))
    direction: Mapped[InteractionDirection] = mapped_column(SQLEnum(InteractionDirection))

    # e.g. "text_received", "image_received", "call_started", "claim_created",
    # "verdict_issued", "clarification_requested", "status_check", "resolution_sent"
    event_type: Mapped[str] = mapped_column(String(100), index=True)

    content_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    media_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), index=True)

    def __repr__(self) -> str:
        return (
            f"<InteractionLog id={self.id} channel={self.channel} "
            f"event={self.event_type} order={self.order_id}>"
        )
