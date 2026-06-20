"""
Redis-backed voice call session.

Keyed by Twilio CallSid, TTL 600s — long enough for a full IVR interaction but
short enough that abandoned calls expire on their own. Stores the in-progress
intent and the fields collected across IVR turns.
"""
from __future__ import annotations

import json
from typing import Optional

from app.redis_client import get_redis

_PREFIX = "call:"
_TTL = 600  # 10 minutes


async def load(call_sid: str) -> dict:
    redis = await get_redis()
    raw = await redis.get(f"{_PREFIX}{call_sid}")
    if raw:
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            pass
    return {"call_sid": call_sid}


async def save(call_sid: str, state: dict) -> None:
    redis = await get_redis()
    await redis.set(f"{_PREFIX}{call_sid}", json.dumps(state), ex=_TTL)


async def update(call_sid: str, **fields) -> dict:
    state = await load(call_sid)
    state.update(fields)
    await save(call_sid, state)
    return state


async def clear(call_sid: str) -> None:
    redis = await get_redis()
    await redis.delete(f"{_PREFIX}{call_sid}")


def get(state: dict, key: str, default: Optional[object] = None):
    return state.get(key, default)
