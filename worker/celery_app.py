"""
Celery application factory.

Queues:
  - claims        : LangGraph claim analysis (process_claim), rate-limited
  - notifications : outbound WhatsApp sends (fire-and-forget)
  - calls         : outbound voice clarification calls (Phase 4)

Result backend is enabled but fire-and-forget tasks set `ignore_result=True`
individually to conserve Redis ops on the free Upstash tier.
"""
from celery import Celery

from app.config import get_settings

settings = get_settings()

celery_app = Celery(
    "vericlaim",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=[
        "worker.tasks.send_whatsapp",
        "worker.tasks.process_claim",
        "worker.tasks.outbound_call",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_default_queue="claims",
    task_routes={
        "worker.tasks.send_whatsapp.*": {"queue": "notifications"},
        "worker.tasks.process_claim.*": {"queue": "claims"},
        "worker.tasks.outbound_call.*": {"queue": "calls"},
    },
)
