"""Verse browsing and stats endpoints."""

from __future__ import annotations

import time

from fastapi import APIRouter, Query

from app.core.knowledge_base import knowledge_base
from app.core.session_manager import session_manager

router = APIRouter(prefix="/api/krishna", tags=["verses"])


@router.get("/verses")
async def get_verses(
    chapter: int | None = Query(default=None, description="Filter by chapter"),
    random: str | None = Query(default=None, description="Set to 'true' for random verse"),
    limit: int = Query(default=10, ge=1, le=100, description="Max results"),
):
    """Browse verses — by chapter, random, or paginated."""
    if random == "true":
        verse = knowledge_base.get_random_verse()
        return {"verse": verse.to_dict() if verse else None}

    if chapter is not None:
        verses = knowledge_base.get_verses_by_chapter(chapter)
        return {"verses": [v.to_dict() for v in verses[:limit]]}

    all_verses = knowledge_base.verses[:limit]
    return {
        "verses": [v.to_dict() for v in all_verses],
        "total": len(knowledge_base.verses),
    }


@router.get("/stats")
async def get_stats():
    """Knowledge base and server statistics."""
    return {
        "knowledgeBase": knowledge_base.get_stats(),
        "server": {
            "activeSessions": session_manager.active_count,
            "totalConversations": session_manager.total_conversations,
            "uptime": time.process_time(),
        },
    }
