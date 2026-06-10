import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, String, ForeignKey, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class AuditLog(Base):
    """
    Internal LangGraph reasoning trail. Captures node transitions,
    intermediate scores, and retry attempts. Not customer-facing.
    """
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    claim_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("claims.id"), index=True, nullable=True)

    # e.g. "node_ingest_media", "node_analyze_image", "fraud_score_computed",
    # "policy_verdict_set", "outcome_decided", "clarification_triggered"
    event_type: Mapped[str] = mapped_column(String(100))

    payload: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    def __repr__(self) -> str:
        return f"<AuditLog id={self.id} claim={self.claim_id} event={self.event_type}>"
