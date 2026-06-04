"""Session analytics endpoint."""

from fastapi import APIRouter

from app.core.session_manager import session_manager

router = APIRouter(prefix="/api/krishna", tags=["sessions"])


@router.get("/sessions")
async def get_sessions():
    """List all active sessions with analytics."""
    import time

    sessions = []
    for sid, session in session_manager.sessions.items():
        sessions.append({
            "id": sid,
            "duration": int((time.time() - session.start_time) * 1000),
            "lastActivity": int(session.last_activity * 1000),
            "questionCount": len(session.conversation_history),
            "devotionalLevel": session.devotional_level,
        })

    return {"sessions": sessions}
