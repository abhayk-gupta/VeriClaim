"""
Claim-analysis state machine.

    ingest_media ──(error)──────────────────────────────► update_database ─► END
         │(ok)
         ▼
    analyze_image ──(error)─────────────────────────────► update_database
         │(ok)
         ▼
    verify_policy ─► fraud_check ─► decide_outcome ─► update_database

`request_clarification` (the CLARIFY branch) is added in Phase 4; for now a
`clarify` decision is persisted as PENDING_CLARIFICATION by update_database.

The graph is compiled once at import time with a checkpointer. RedisSaver is used
when available; otherwise MemorySaver — each claim runs the graph exactly once
and the durable record always lives in Postgres, so in-memory checkpointing is
sufficient.
"""
from __future__ import annotations

import logging
import uuid
from functools import lru_cache

from langgraph.graph import StateGraph, END

from app.database import AsyncSessionLocal
from app.models.claim import Claim
from app.models.order import Order
from app.models.customer import Customer
from app.langgraph_agent.state import ClaimState
from app.langgraph_agent.nodes.ingest_media import ingest_media
from app.langgraph_agent.nodes.analyze_image import analyze_image
from app.langgraph_agent.nodes.verify_policy import verify_policy
from app.langgraph_agent.nodes.fraud_check import fraud_check
from app.langgraph_agent.nodes.decide_outcome import decide_outcome
from app.langgraph_agent.nodes.request_clarification import request_clarification
from app.langgraph_agent.nodes.update_database import update_database

logger = logging.getLogger(__name__)


def _make_checkpointer():
    try:  # pragma: no cover - depends on optional package
        from langgraph.checkpoint.redis import RedisSaver
        from app.config import get_settings

        return RedisSaver.from_conn_string(get_settings().redis_url)
    except Exception:
        from langgraph.checkpoint.memory import MemorySaver

        logger.info("RedisSaver unavailable; using in-memory checkpointer for claim graph.")
        return MemorySaver()


def _route_after(node_state: ClaimState) -> str:
    """Send to update_database on error, otherwise continue."""
    return "update_database" if node_state.get("error") else "continue"


def _route_decision(node_state: ClaimState) -> str:
    """A 'clarify' decision goes to the clarification node; everything else persists."""
    return "clarify" if node_state.get("decision") == "clarify" else "finalize"


@lru_cache(maxsize=1)
def get_graph():
    """Build and compile the claim graph once."""
    builder = StateGraph(ClaimState)

    builder.add_node("ingest_media", ingest_media)
    builder.add_node("analyze_image", analyze_image)
    builder.add_node("verify_policy", verify_policy)
    builder.add_node("fraud_check", fraud_check)
    builder.add_node("decide_outcome", decide_outcome)
    builder.add_node("request_clarification", request_clarification)
    builder.add_node("update_database", update_database)

    builder.set_entry_point("ingest_media")
    builder.add_conditional_edges(
        "ingest_media", _route_after,
        {"continue": "analyze_image", "update_database": "update_database"},
    )
    builder.add_conditional_edges(
        "analyze_image", _route_after,
        {"continue": "verify_policy", "update_database": "update_database"},
    )
    builder.add_edge("verify_policy", "fraud_check")
    builder.add_edge("fraud_check", "decide_outcome")
    builder.add_conditional_edges(
        "decide_outcome", _route_decision,
        {"clarify": "request_clarification", "finalize": "update_database"},
    )
    builder.add_edge("request_clarification", END)
    builder.add_edge("update_database", END)

    return builder.compile(checkpointer=_make_checkpointer())


async def build_initial_state(claim_id: str | uuid.UUID) -> ClaimState | None:
    """Load the claim + order from the DB into a fresh ClaimState."""
    cid = uuid.UUID(str(claim_id))
    async with AsyncSessionLocal() as session:
        claim = await session.get(Claim, cid)
        if claim is None:
            return None
        order = await session.get(Order, claim.order_id)
        customer = await session.get(Customer, claim.customer_id)

    state: ClaimState = {
        "claim_id": str(claim.id),
        "order_id": str(claim.order_id),
        "customer_id": str(claim.customer_id),
        "customer_phone": customer.phone_e164 if customer else None,
        "claim_type": claim.claim_type.value if claim.claim_type else None,
        "verbal_description": claim.verbal_description,
        "media_r2_key_item": claim.media_r2_key_item,
        "media_r2_key_label": claim.media_r2_key_label,
        "claim_created_at": claim.created_at.isoformat() if claim.created_at else None,
        "clarification_count": claim.clarification_count or 0,
    }
    if order is not None:
        state.update({
            "policy_id": order.policy_id or "default",
            "order_external": order.external_order_id,
            "product_description": order.product_description,
            "order_value_usd": float(order.order_value_usd) if order.order_value_usd is not None else 0.0,
            "delivered_at": order.delivered_at.isoformat() if order.delivered_at else None,
        })
    return state


async def run_claim_graph(claim_id: str | uuid.UUID) -> ClaimState:
    """Entry point used by the Celery task. Builds state, runs the graph, returns final state."""
    state = await build_initial_state(claim_id)
    if state is None:
        raise ValueError(f"Claim {claim_id} not found")

    graph = get_graph()
    config = {"configurable": {"thread_id": str(claim_id)}}
    final_state = await graph.ainvoke(state, config=config)
    logger.info("Claim %s graph complete: decision=%s status=%s",
                claim_id, final_state.get("decision"), final_state.get("final_status"))
    return final_state
