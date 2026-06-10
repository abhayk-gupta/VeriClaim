from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.database import get_session
from app.redis_client import get_redis

router = APIRouter(tags=["health"])


@router.get("/health")
async def liveness():
    return {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}


@router.get("/ready")
async def readiness(
    db: AsyncSession = Depends(get_session),
    response: Response = None,
):
    checks = {}

    # PostgreSQL ping
    try:
        await db.execute(text("SELECT 1"))
        checks["postgres"] = "ok"
    except Exception as exc:
        checks["postgres"] = f"error: {exc}"

    # Redis ping
    try:
        redis = await get_redis()
        await redis.ping()
        checks["redis"] = "ok"
    except Exception as exc:
        checks["redis"] = f"error: {exc}"

    all_ok = all(v == "ok" for v in checks.values())
    if not all_ok and response is not None:
        response.status_code = 503

    return {"status": "ready" if all_ok else "degraded", "checks": checks}
