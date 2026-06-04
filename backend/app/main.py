"""
FastAPI application entry point.

Configures the app with lifespan management, routes, static files,
CORS, and error handling.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.core.gemini_client import gemini_client
from app.core.knowledge_base import knowledge_base
from app.core.session_manager import session_manager
from app.utils.logging import get_logger, setup_logging

# ── Lifespan ────────────────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle."""
    setup_logging()
    logger = get_logger(__name__)

    logger.info("🚀 Initializing %s...", settings.app_name)

    # 1. Configure Gemini AI
    gemini_client.configure()

    # 2. Initialize knowledge base (loads verses + generates embeddings)
    await knowledge_base.initialize()

    # 3. Start session background tasks
    await session_manager.start_background_tasks()

    stats = knowledge_base.get_stats()
    logger.info("📿 %d Gita verses loaded with semantic search", stats["totalVerses"])
    logger.info("🧠 %d verses with embeddings", stats["versesWithEmbeddings"])
    logger.info("✅ All components initialized — ready to serve divine wisdom")
    logger.info("🔧 Environment: %s", settings.node_env)

    yield  # ← Application is running

    # Shutdown
    logger.info("🙏 Shutting down gracefully...")
    await session_manager.close_all()
    await session_manager.stop_background_tasks()
    logger.info("✅ Shutdown complete")


# ── App Creation ────────────────────────────────────────────────────────────

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="AI-powered voice assistant embodying the wisdom of Lord Krishna",
    lifespan=lifespan,
)

# CORS — allow all origins for dev; tighten in production
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Register Routers ────────────────────────────────────────────────────────

from app.api.routes.health import router as health_router
from app.api.routes.verses import router as verses_router
from app.api.routes.krishna import router as krishna_router
from app.api.routes.sessions import router as sessions_router
from app.api.websocket import router as ws_router

app.include_router(health_router)
app.include_router(verses_router)
app.include_router(krishna_router)
app.include_router(sessions_router)
app.include_router(ws_router)

# ── Static Files (Frontend) ────────────────────────────────────────────────

frontend_dir = Path(__file__).resolve().parent.parent.parent / "frontend"
if frontend_dir.exists():
    app.mount("/css", StaticFiles(directory=str(frontend_dir / "css")), name="css")
    app.mount("/js", StaticFiles(directory=str(frontend_dir / "js")), name="js")


# ── Root → serve index.html ────────────────────────────────────────────────

@app.get("/", include_in_schema=False)
async def serve_frontend():
    """Serve the frontend index.html."""
    index_path = frontend_dir / "index.html"
    if index_path.exists():
        return FileResponse(str(index_path))
    return JSONResponse(
        content={
            "message": "पार्थ - Krishna AI Voice Assistant",
            "version": settings.app_version,
            "endpoints": {
                "websocket": "/ws",
                "health": "/health",
                "api": "/api/krishna/*",
                "docs": "/docs",
            },
        }
    )


# ── Error Handlers ──────────────────────────────────────────────────────────

@app.exception_handler(404)
async def not_found_handler(request: Request, exc):
    return JSONResponse(
        status_code=404,
        content={
            "error": "पथ नहीं मिला",
            "message": "यह URL उपलब्ध नहीं है",
        },
    )


@app.exception_handler(500)
async def internal_error_handler(request: Request, exc):
    return JSONResponse(
        status_code=500,
        content={
            "error": "सर्वर में समस्या है",
            "message": str(exc),
        },
    )
