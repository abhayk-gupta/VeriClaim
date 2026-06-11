"""
Celery task: process_claim

Runs the LangGraph claim-analysis pipeline for one claim. Rate-limited to stay
under Gemini's 30 RPM free quota; transient failures retry with backoff.

The synchronous Celery worker drives the async graph via `asyncio.run`. Before
running, the claim is moved to ANALYZING so the status reflects in-flight work.
"""
from __future__ import annotations

import asyncio
import logging
import uuid

from worker.celery_app import celery_app
from app.database import AsyncSessionLocal
from app.models.claim import Claim, ClaimStatus
from app.langgraph_agent.graph import run_claim_graph

logger = logging.getLogger(__name__)


@celery_app.task(
    name="worker.tasks.process_claim.process_claim",
    bind=True,
    rate_limit="25/m",
    max_retries=3,
    default_retry_delay=30,
    acks_late=True,
)
def process_claim(self, claim_id: str) -> dict:
    try:
        return asyncio.run(_run(claim_id))
    except Exception as exc:
        logger.exception("process_claim failed for %s", claim_id)
        raise self.retry(exc=exc)


async def _run(claim_id: str) -> dict:
    await _mark_analyzing(claim_id)
    final_state = await run_claim_graph(claim_id)
    return {
        "claim_id": claim_id,
        "decision": final_state.get("decision"),
        "outcome": final_state.get("outcome"),
        "status": final_state.get("final_status"),
        "fraud_score": final_state.get("fraud_score"),
    }


async def _mark_analyzing(claim_id: str) -> None:
    async with AsyncSessionLocal() as session:
        claim = await session.get(Claim, uuid.UUID(claim_id))
        if claim and claim.status in (ClaimStatus.PENDING_MEDIA, ClaimStatus.MEDIA_RECEIVED):
            claim.status = ClaimStatus.ANALYZING
            await session.commit()
