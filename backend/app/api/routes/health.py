"""Health check endpoint."""

from datetime import datetime, timezone

from fastapi import APIRouter

from app.config import settings
from app.core.knowledge_base import knowledge_base
from app.core.session_manager import session_manager

router = APIRouter()


@router.get("/health")
async def health_check():
    """System health check with knowledge base and session stats."""
    stats = knowledge_base.get_stats() if knowledge_base.is_initialized else {"status": "initializing"}

    return {
        "status": "OK",
        "service": f"{settings.app_name} (Enhanced)",
        "version": settings.app_version,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "activeSessions": session_manager.active_count,
        "knowledgeBase": stats,
        "features": {
            "semanticSearch": True,
            "embeddings": True,
            "advancedSearch": True,
            "multilingualSupport": True,
        },
    }
