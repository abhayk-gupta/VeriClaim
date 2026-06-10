"""Initial schema: customers, orders, claims, interaction_logs, audit_logs

Revision ID: 0001
Revises:
Create Date: 2026-06-10
"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from alembic import op

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── customers ──────────────────────────────────────────────────────────────
    op.create_table(
        "customers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("phone_e164", sa.String(20), nullable=False),
        sa.Column("full_name", sa.String(255), nullable=False),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("whatsapp_opt_in", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("phone_e164", name="uq_customers_phone"),
    )
    op.create_index("ix_customers_phone_e164", "customers", ["phone_e164"])

    # ── orders ─────────────────────────────────────────────────────────────────
    op.create_table(
        "orders",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("external_order_id", sa.String(100), nullable=False),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("store_name", sa.String(100), nullable=False),
        sa.Column("product_description", sa.Text(), nullable=False),
        sa.Column("order_value_usd", sa.Numeric(10, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="USD"),
        sa.Column(
            "status",
            sa.Enum("processing", "shipped", "delivered", "cancelled", name="orderstatus"),
            nullable=False,
            server_default="processing",
        ),
        sa.Column("tracking_number", sa.String(100), nullable=True),
        sa.Column("carrier", sa.String(50), nullable=True),
        sa.Column("shipped_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("policy_id", sa.String(50), nullable=False, server_default="default"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"], name="fk_orders_customer"),
        sa.UniqueConstraint("external_order_id", name="uq_orders_external_id"),
    )
    op.create_index("ix_orders_external_order_id", "orders", ["external_order_id"])
    op.create_index("ix_orders_customer_id", "orders", ["customer_id"])

    # ── claims ─────────────────────────────────────────────────────────────────
    op.create_table(
        "claims",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("order_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "claim_type",
            sa.Enum("damaged", "not_received", "wrong_item", "missing_parts", name="claimtype"),
            nullable=True,
        ),
        sa.Column(
            "status",
            sa.Enum(
                "pending_media", "media_received", "analyzing", "pending_clarification",
                "approved", "rejected", "escalated", "refunded", "replaced",
                name="claimstatus",
            ),
            nullable=False,
            server_default="pending_media",
        ),
        sa.Column(
            "outcome",
            sa.Enum("replacement", "refund", "rejection", "manual_review", name="claimoutcome"),
            nullable=True,
        ),
        sa.Column("call_sid", sa.String(50), nullable=True),
        sa.Column("verbal_description", sa.Text(), nullable=True),
        sa.Column("transcript_raw", sa.Text(), nullable=True),
        sa.Column("media_url_item", sa.Text(), nullable=True),
        sa.Column("media_url_label", sa.Text(), nullable=True),
        sa.Column("media_received_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("media_r2_key_item", sa.Text(), nullable=True),
        sa.Column("media_r2_key_label", sa.Text(), nullable=True),
        sa.Column("gemini_item_description", sa.Text(), nullable=True),
        sa.Column("gemini_damage_assessment", sa.Text(), nullable=True),
        sa.Column("gemini_damage_type", sa.String(100), nullable=True),
        sa.Column("gemini_damage_severity", sa.String(50), nullable=True),
        sa.Column("gemini_label_match", sa.Boolean(), nullable=True),
        sa.Column("gemini_confidence", sa.Float(), nullable=True),
        sa.Column("fraud_score", sa.Float(), nullable=True),
        sa.Column("fraud_signals", postgresql.JSONB(), nullable=True),
        sa.Column("policy_verdict", sa.String(50), nullable=True),
        sa.Column("agent_reasoning", sa.Text(), nullable=True),
        sa.Column("clarification_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("resolution_notes", sa.Text(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_by", sa.String(100), nullable=True),
        sa.Column("intake_channel", sa.String(20), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], name="fk_claims_order"),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"], name="fk_claims_customer"),
    )
    op.create_index("ix_claims_order_id", "claims", ["order_id"])
    op.create_index("ix_claims_customer_id", "claims", ["customer_id"])

    # ── interaction_logs ───────────────────────────────────────────────────────
    op.create_table(
        "interaction_logs",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("order_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("claim_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "channel",
            sa.Enum("whatsapp", "voice", "system", "api", name="interactionchannel"),
            nullable=False,
        ),
        sa.Column(
            "direction",
            sa.Enum("inbound", "outbound", "internal", name="interactiondirection"),
            nullable=False,
        ),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("content_text", sa.Text(), nullable=True),
        sa.Column("media_url", sa.Text(), nullable=True),
        sa.Column("metadata", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], name="fk_interaction_logs_order"),
        sa.ForeignKeyConstraint(["claim_id"], ["claims.id"], name="fk_interaction_logs_claim"),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"], name="fk_interaction_logs_customer"),
    )
    op.create_index("ix_interaction_logs_order_id", "interaction_logs", ["order_id"])
    op.create_index("ix_interaction_logs_claim_id", "interaction_logs", ["claim_id"])
    op.create_index("ix_interaction_logs_customer_id", "interaction_logs", ["customer_id"])
    op.create_index("ix_interaction_logs_event_type", "interaction_logs", ["event_type"])
    op.create_index("ix_interaction_logs_created_at", "interaction_logs", ["created_at"])

    # ── audit_logs ─────────────────────────────────────────────────────────────
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("claim_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["claim_id"], ["claims.id"], name="fk_audit_logs_claim"),
    )
    op.create_index("ix_audit_logs_claim_id", "audit_logs", ["claim_id"])


def downgrade() -> None:
    op.drop_table("audit_logs")
    op.drop_table("interaction_logs")
    op.drop_table("claims")
    op.drop_table("orders")
    op.drop_table("customers")

    # Drop custom enums
    for enum_name in [
        "orderstatus", "claimtype", "claimstatus", "claimoutcome",
        "interactionchannel", "interactiondirection",
    ]:
        op.execute(f"DROP TYPE IF EXISTS {enum_name}")
