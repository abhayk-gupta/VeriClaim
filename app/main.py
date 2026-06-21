from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.database import engine
from app.redis_client import get_redis, close_redis
from app.routers.health import router as health_router
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import os

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
from app.routers.whatsapp import router as whatsapp_router
from app.routers.voice import router as voice_router
from app.routers.claims import router as claims_router
from app.routers.orders import router as orders_router
from app.routers.auth import router as auth_router
from app.routers.media import router as media_router
from app.routers.dashboard_whatsapp import router as dashboard_whatsapp_router
from app.routers.dashboard_voice import router as dashboard_voice_router

app.include_router(whatsapp_router, prefix="/webhooks")
app.include_router(voice_router, prefix="/webhooks")
app.include_router(claims_router, prefix="/api/v1")
app.include_router(orders_router, prefix="/api/v1")
app.include_router(auth_router, prefix="/api/v1")
app.include_router(media_router, prefix="/api/v1")
app.include_router(dashboard_whatsapp_router, prefix="/api/v1")
app.include_router(dashboard_voice_router, prefix="/api/v1")

dashboard_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "dashboard", "dist")
if os.path.isdir(dashboard_dir):
    app.mount("/dashboard/assets", StaticFiles(directory=os.path.join(dashboard_dir, "assets")), name="assets")
    
    @app.get("/dashboard/{full_path:path}", include_in_schema=False)
    async def serve_dashboard(full_path: str):
        index_path = os.path.join(dashboard_dir, "index.html")
        if os.path.isfile(index_path):
            return FileResponse(index_path)
        return "Dashboard build not found", 404

