from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.ext.asyncio import AsyncSession
import uuid
import yaml
import os

from app.database import get_session
from app.auth_deps import get_current_agent
from app.models.agent import Agent
from app.models.claim import Claim
from app.models.customer import Customer
from app.services.whatsapp_service import send_text
from app.services.interaction_log_service import log_event
from app.models.interaction_log import InteractionChannel, InteractionDirection

router = APIRouter(prefix="/dashboard", tags=["dashboard-whatsapp"])

def load_templates():
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "policies", "whatsapp_templates.yaml")
    if not os.path.exists(path):
        return {}
    with open(path, "r") as f:
        return yaml.safe_load(f)

@router.get("/whatsapp-templates")
async def get_whatsapp_templates(current_agent: Agent = Depends(get_current_agent)):
    return load_templates()

@router.post("/claims/{claim_id}/send-whatsapp")
async def send_dashboard_whatsapp(
    claim_id: uuid.UUID,
    message: str = Body(..., embed=True),
    is_template: bool = Body(False, embed=True),
    db: AsyncSession = Depends(get_session),
    current_agent: Agent = Depends(get_current_agent)
):
    claim = await db.get(Claim, claim_id)
    if not claim:
        raise HTTPException(status_code=404, detail="Claim not found")
        
    customer = await db.get(Customer, claim.customer_id)
    if not customer or not customer.phone_e164:
        raise HTTPException(status_code=400, detail="Customer has no valid phone number")
        
    try:
        from worker.tasks.send_whatsapp import send_text as celery_send_text
        celery_send_text.delay(customer.phone_e164, message)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to enqueue WhatsApp message: {str(e)}")
        
    await log_event(
        db,
        channel=InteractionChannel.WHATSAPP,
        direction=InteractionDirection.OUTBOUND,
        event_type="text_sent",
        order_id=claim.order_id,
        claim_id=claim.id,
        customer_id=claim.customer_id,
        content_text=message,
        metadata={"sent_by": current_agent.email, "is_template": is_template}
    )
    
    return {"status": "sent"}
