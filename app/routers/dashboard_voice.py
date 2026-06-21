from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.ext.asyncio import AsyncSession
import uuid

from app.database import get_session
from app.auth_deps import get_current_agent
from app.models.agent import Agent
from app.models.claim import Claim
from app.models.customer import Customer
from app.services.interaction_log_service import log_event
from app.models.interaction_log import InteractionChannel, InteractionDirection
from worker.celery_app import celery_app

router = APIRouter(prefix="/dashboard", tags=["dashboard-voice"])

@router.post("/claims/{claim_id}/place-call")
async def place_dashboard_call(
    claim_id: uuid.UUID,
    question: str = Body(..., embed=True),
    db: AsyncSession = Depends(get_session),
    current_agent: Agent = Depends(get_current_agent)
):
    claim = await db.get(Claim, claim_id)
    if not claim:
        raise HTTPException(status_code=404, detail="Claim not found")
        
    customer = await db.get(Customer, claim.customer_id)
    if not customer or not customer.phone_e164:
        raise HTTPException(status_code=400, detail="Customer has no valid phone number")
        
    celery_app.send_task(
        "worker.tasks.outbound_call.place_clarification_call",
        args=[str(claim.id), question, customer.phone_e164],
        queue="calls",
    )
    
    await log_event(
        db,
        channel=InteractionChannel.SYSTEM,
        direction=InteractionDirection.INTERNAL,
        event_type="clarification_triggered",
        order_id=claim.order_id,
        claim_id=claim.id,
        customer_id=claim.customer_id,
        content_text=f"Agent initiated call: {question}",
        metadata={"triggered_by": current_agent.email}
    )
    
    return {"status": "enqueued"}
