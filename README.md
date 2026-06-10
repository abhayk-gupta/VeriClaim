# VeriClaim

Automated customer support and fraud-prevention platform for international e-commerce brands. VeriClaim resolves damaged-product claims via multi-channel **voice + WhatsApp** in under 60 seconds.

A customer contacts support, the bot triages and verifies order identity, then requests a photo of the damaged item and shipping label over WhatsApp. A [LangGraph](https://langchain-ai.github.io/langgraph/) state machine (Google Gemini 2.5 Flash-Lite) analyzes the photos, verifies them against store policy, scores fraud risk, and writes a verdict (replacement / refund / rejection / escalate) back to PostgreSQL.

**Design constraint:** every component runs on a free tier, free open-source software, or a free cloud plan — no paid infrastructure.

## Stack

| Layer | Technology |
|---|---|
| API | FastAPI + Uvicorn (async) |
| ORM / DB | SQLAlchemy 2.0 (async) + asyncpg, PostgreSQL 16 (local / Neon.tech) |
| Cache / broker | Redis (local / Upstash) |
| Tasks | Celery 5.4 (queues: claims, notifications, calls) |
| AI agent | LangGraph state machine + Google Gemini 2.5 Flash-Lite |
| Voice | Whisper (STT) + Piper (TTS) + Twilio |
| WhatsApp | Meta WhatsApp Cloud API / Twilio sandbox |
| Media | Cloudflare R2 (permanent storage; solves 24h CDN expiry) |
| Tunnel | ngrok (shared by Twilio + Meta webhooks) |

## Prerequisites

- [Docker](https://docs.docker.com/get-docker/) + Docker Compose
- [uv](https://docs.astral.sh/uv/) (for local development outside Docker)

## Quick start

```bash
# 1. Configure environment
cp .env.example .env        # then fill in at least GEMINI_API_KEY

# 2. Bring up the stack (db + redis + api + worker)
make dev

# 3. Run migrations and seed test data
make migrate
make seed

# 4. Verify
curl localhost:8000/health   # → {"status":"ok"}
curl localhost:8000/ready    # → {"status":"ready", ...}
```

## Local development with uv

```bash
uv sync --dev              # create .venv and install all deps from uv.lock
uv run uvicorn app.main:app --reload
uv run pytest
```

## Project layout

```
app/
  main.py            FastAPI app factory + lifespan
  config.py          Pydantic settings (.env)
  database.py        async SQLAlchemy engine + session dependency
  redis_client.py    aioredis pool
  models/            Customer, Order, Claim, InteractionLog, AuditLog
  schemas/           Pydantic request/response + webhook payloads
  routers/           voice, whatsapp, claims, orders, health
  services/          whatsapp, wa_intake (NLU), media_storage, interaction_log, ...
  voice/             twiml, stt (Whisper), tts (Piper), call_state
  langgraph_agent/   state, graph, nodes/, tools/
worker/              celery_app + tasks/
policies/            per-store YAML policy files
alembic/             async migrations
scripts/             seed_db, download_piper_model, test_gemini_vision
tests/
```

See the implementation plan for the full architecture and the three channel behaviors (WhatsApp-only NLU flow, voice status/clarification calls, cross-channel order timeline).
