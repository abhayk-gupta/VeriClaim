"""
Fire-and-forget outbound WhatsApp send tasks.

The webhook handler computes the reply text and the interaction is logged
there; this task only performs the actual network send so the webhook can
return 200 immediately. Sends run on the `notifications` queue.

A thin async-over-sync shim (`asyncio.run`) lets the synchronous Celery worker
call the async `whatsapp_service`.
"""
from __future__ import annotations

import asyncio
import logging

from worker.celery_app import celery_app
from app.services import whatsapp_service

logger = logging.getLogger(__name__)


@celery_app.task(
    name="worker.tasks.send_whatsapp.send_text",
    bind=True,
    ignore_result=True,
    max_retries=3,
    default_retry_delay=10,
)
def send_text(self, to: str, body: str) -> None:
    """Send a WhatsApp text message to `to` (E.164)."""
    try:
        asyncio.run(whatsapp_service.send_text(to, body))
        logger.info("Sent WhatsApp message to %s (%d chars)", to, len(body))
    except Exception as exc:
        logger.warning("WhatsApp send to %s failed: %s — retrying", to, exc)
        raise self.retry(exc=exc)
