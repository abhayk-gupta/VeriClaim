from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.database import engine
from app.redis_client import get_redis, close_redis
from app.routers.health import router as health_router

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: warm up connections
    await get_redis()
    yield
    # Shutdown: close connections
    await close_redis()
    await engine.dispose()


app = FastAPI(
    title="VeriClaim",
    description="Automated customer support and fraud-prevention platform for e-commerce",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.is_development else None,
    redoc_url="/redoc" if settings.is_development else None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.is_development else [],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(health_router)

# Phase 2 routers (added as they are implemented)
# from app.routers.whatsapp import router as whatsapp_router
# from app.routers.voice import router as voice_router
# from app.routers.claims import router as claims_router
# from app.routers.orders import router as orders_router
# app.include_router(whatsapp_router, prefix="/webhooks")
# app.include_router(voice_router, prefix="/webhooks")
# app.include_router(claims_router, prefix="/api/v1")
# app.include_router(orders_router, prefix="/api/v1")
