"""
Celery task: place_clarification_call

Places an outbound Twilio voice call that asks the customer one targeted question
and records their answer. The recorded answer is posted back to
/webhooks/voice/clarification-response, which transcribes it (Whisper) and
re-runs the claim graph.

Runs on the `calls` queue. Twilio's REST client is synchronous, which suits the
Celery worker.
"""
from __future__ import annotations

import logging

from worker.celery_app import celery_app
from app.config import get_settings
from app.voice import twiml_responses as twiml

logger = logging.getLogger(__name__)
settings = get_settings()


@celery_app.task(
    name="worker.tasks.outbound_call.place_clarification_call",
    bind=True,
    ignore_result=True,
    max_retries=2,
    default_retry_delay=30,
)
def place_clarification_call(self, claim_id: str, question: str, to_phone: str) -> None:
    if not (settings.twilio_account_sid and settings.twilio_auth_token and settings.twilio_phone_number):
        logger.warning("Twilio not configured; skipping clarification call for claim %s", claim_id)
        return

    try:
        from twilio.rest import Client

        client = Client(settings.twilio_account_sid, settings.twilio_auth_token)
        call = client.calls.create(
            to=to_phone,
            from_=settings.twilio_phone_number,
            twiml=twiml.clarification_question(question, claim_id),
        )
        logger.info("Placed clarification call %s for claim %s", call.sid, claim_id)
    except Exception as exc:
        logger.warning("Clarification call failed for claim %s: %s — retrying", claim_id, exc)
        raise self.retry(exc=exc)
