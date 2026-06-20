"""
Permanent media storage — solves Meta's 24-hour WhatsApp CDN expiry.

When a customer sends a photo, the router downloads the bytes immediately and
calls `store_image()`. The LangGraph `ingest_media` node later reads the bytes
back via `get_image()` at analysis time — which may be well past the 24h window
when the original Meta/Twilio link would have 403'd.

Backends:
  - Production: Cloudflare R2 (S3-compatible, boto3). 10 GB free, zero egress.
  - Development (APP_ENV=development OR no R2 configured): gzip+Base64 in Redis,
    key `media:{claim_id}:{side}`, TTL 7 days. No cloud account needed locally.

`store_image()` returns an opaque `r2_key` string stored on the claim; pass that
same key to `get_image()` to retrieve the bytes regardless of backend.
"""
from __future__ import annotations

import gzip
import logging

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

_REDIS_TTL_SECONDS = 7 * 24 * 3600  # 7 days
_REDIS_PREFIX = "redis://"  # marker so get_image knows which backend produced a key


def _r2_configured() -> bool:
    return bool(
        settings.cloudflare_r2_endpoint
        and settings.cloudflare_r2_access_key
        and settings.cloudflare_r2_secret_key
    )


def _use_r2() -> bool:
    # Prefer R2 whenever it is fully configured, even in development, so devs can
    # opt in. Otherwise fall back to Redis.
    return _r2_configured()


# ── Public API ─────────────────────────────────────────────────────────────────

async def store_image(claim_id: str, side: str, data: bytes, content_type: str = "image/jpeg") -> str:
    """Persist image bytes and return a backend-agnostic key."""
    if _use_r2():
        return _store_r2(claim_id, side, data, content_type)
    return await _store_redis(claim_id, side, data)


async def get_image(key: str) -> bytes:
    """Retrieve image bytes previously stored under `key`."""
    if key.startswith(_REDIS_PREFIX):
        return await _get_redis(key)
    return _get_r2(key)


# ── Cloudflare R2 (boto3, S3-compatible) ───────────────────────────────────────

_s3_client = None


def _get_s3():
    global _s3_client
    if _s3_client is None:
        import boto3
        from botocore.config import Config

        _s3_client = boto3.client(
            "s3",
            endpoint_url=settings.cloudflare_r2_endpoint,
            aws_access_key_id=settings.cloudflare_r2_access_key,
            aws_secret_access_key=settings.cloudflare_r2_secret_key,
            config=Config(signature_version="s3v4"),
            region_name="auto",
        )
    return _s3_client


def _store_r2(claim_id: str, side: str, data: bytes, content_type: str) -> str:
    # Deterministic key; no timestamp needed since side is unique per claim.
    key = f"media/{claim_id}/{side}.jpg"
    _get_s3().put_object(
        Bucket=settings.cloudflare_r2_bucket,
        Key=key,
        Body=data,
        ContentType=content_type,
    )
    logger.info("Stored media in R2: %s (%d bytes)", key, len(data))
    return key


def _get_r2(key: str) -> bytes:
    resp = _get_s3().get_object(Bucket=settings.cloudflare_r2_bucket, Key=key)
    return resp["Body"].read()


# ── Redis dev fallback (gzip-compressed bytes, 7-day TTL) ──────────────────────

async def _store_redis(claim_id: str, side: str, data: bytes) -> str:
    redis = await _get_binary_redis()
    redis_key = f"media:{claim_id}:{side}"
    await redis.set(redis_key, gzip.compress(data), ex=_REDIS_TTL_SECONDS)
    logger.info("Stored media in Redis: %s (%d bytes raw)", redis_key, len(data))
    return f"{_REDIS_PREFIX}{redis_key}"


async def _get_redis(key: str) -> bytes:
    redis = await _get_binary_redis()
    redis_key = key[len(_REDIS_PREFIX):]
    blob = await redis.get(redis_key)
    if blob is None:
        raise KeyError(f"Media not found or expired in Redis: {redis_key}")
    return gzip.decompress(blob)


# The shared app Redis pool uses decode_responses=True, which corrupts binary
# data. Use a dedicated binary client for media bytes.
_binary_redis = None


async def _get_binary_redis():
    global _binary_redis
    if _binary_redis is None:
        import redis.asyncio as aioredis

        _binary_redis = aioredis.from_url(
            settings.redis_url, decode_responses=False, max_connections=5
        )
    return _binary_redis
