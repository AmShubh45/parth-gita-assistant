"""Krishna ask/search endpoints."""

from __future__ import annotations

import time as time_mod

from fastapi import APIRouter, HTTPException

from app.core.knowledge_base import knowledge_base
from app.core.session_manager import session_manager
from app.core.speech_processor import speech_processor
from app.models.schemas import (
    AdvancedSearchRequest,
    AskRequest,
    SearchRequest,
)

router = APIRouter(prefix="/api/krishna", tags=["krishna"])


@router.post("/search")
async def search_verses(body: SearchRequest):
    """Semantic verse search."""
    if not body.query:
        return {"verses": [], "message": "No query provided"}

    start = time_mod.time()
    verses = await knowledge_base.find_relevant_verses(body.query, body.max_results)
    search_time = int((time_mod.time() - start) * 1000)

    return {
        "query": body.query,
        "verses": [v.to_dict() for v in verses],
        "count": len(verses),
        "searchTime": search_time,
        "searchType": "semantic_embedding",
    }


@router.post("/advanced-search")
async def advanced_search(body: AdvancedSearchRequest):
    """Multi-criteria verse search."""
    start = time_mod.time()
    results = await knowledge_base.advanced_search(
        query=body.query,
        chapter=body.chapter,
        themes=body.themes or None,
        emotional_context=body.emotional_context or None,
        life_situations=body.life_situations or None,
        max_results=body.max_results,
    )
    search_time = int((time_mod.time() - start) * 1000)

    return {
        "results": [v.to_dict() for v in results],
        "searchOptions": body.model_dump(by_alias=True),
        "count": len(results),
        "searchTime": search_time,
    }


@router.post("/ask")
async def ask_krishna(body: AskRequest):
    """Ask Krishna a question and receive a response with verse references."""
    # Use existing session or create a temporary one
    session = None
    session_id = body.session_id
    if session_id:
        session = session_manager.get_session(session_id)

    if session is None:
        session_id = f"temp_{int(time_mod.time() * 1000)}"
        # Create a minimal temporary session for the speech processor
        # We store it temporarily in the session manager
        from app.core.session_manager import Session
        from unittest.mock import MagicMock

        temp_ws = MagicMock()
        temp_session = Session(
            id=session_id,
            ws=temp_ws,
            start_time=time_mod.time(),
            last_activity=time_mod.time(),
        )
        session_manager.sessions[session_id] = temp_session

    try:
        result = await speech_processor.process_text_query(body.question, session_id)

        verses_used = result.get("versesUsed", [])
        verses_dicts = [v.to_dict() if hasattr(v, "to_dict") else v for v in verses_used]

        return {
            "question": body.question,
            "response": result["response"],
            "versesUsed": verses_dicts,
            "searchMetrics": result.get("searchMetrics", {}),
            "sessionId": session_id,
        }
    finally:
        # Clean up temp sessions
        if session_id and session_id.startswith("temp_"):
            session_manager.sessions.pop(session_id, None)
