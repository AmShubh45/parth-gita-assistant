"""
WebSocket session lifecycle manager.

Tracks connected clients, their conversation history, and handles
heartbeat monitoring and inactive session cleanup.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

from fastapi import WebSocket

from app.config import settings
from app.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class Session:
    """Represents a single connected user session."""

    id: str
    ws: WebSocket
    start_time: float
    last_activity: float
    conversation_history: list[dict[str, Any]] = field(default_factory=list)
    user_questions: list[str] = field(default_factory=list)
    devotional_level: int = 0
    is_alive: bool = True


class SessionManager:
    """Manages WebSocket sessions for Krishna conversations."""

    def __init__(self) -> None:
        self.sessions: dict[str, Session] = {}
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._cleanup_task: Optional[asyncio.Task] = None

    def create_session(self, ws: WebSocket) -> Session:
        now = time.time()
        session_id = f"krishna_{int(now * 1000)}_{uuid.uuid4().hex[:9]}"
        session = Session(id=session_id, ws=ws, start_time=now, last_activity=now)
        self.sessions[session_id] = session
        logger.info("Session created: %s", session_id)
        return session

    def get_session(self, session_id: str) -> Optional[Session]:
        return self.sessions.get(session_id)

    def update_activity(self, session_id: str) -> None:
        session = self.sessions.get(session_id)
        if session:
            session.last_activity = time.time()
            session.is_alive = True

    def remove_session(self, session_id: str) -> None:
        session = self.sessions.pop(session_id, None)
        if session:
            session.is_alive = False
            logger.info("Session removed: %s", session_id)

    async def start_background_tasks(self) -> None:
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        logger.info("Session background tasks started")

    async def stop_background_tasks(self) -> None:
        for task in (self._heartbeat_task, self._cleanup_task):
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

    async def _heartbeat_loop(self) -> None:
        interval = settings.heartbeat_interval_seconds
        while True:
            await asyncio.sleep(interval)
            dead: list[str] = []
            for sid, session in list(self.sessions.items()):
                try:
                    await session.ws.send_json({"type": "pong", "timestamp": int(time.time() * 1000)})
                except Exception:
                    dead.append(sid)
            for sid in dead:
                self.remove_session(sid)

    async def _cleanup_loop(self) -> None:
        interval = settings.session_cleanup_interval_minutes * 60
        timeout = settings.session_timeout_minutes * 60
        while True:
            await asyncio.sleep(interval)
            now = time.time()
            for sid, session in list(self.sessions.items()):
                if now - session.last_activity > timeout:
                    logger.info("Cleaning up inactive session: %s", sid)
                    try:
                        await session.ws.close()
                    except Exception:
                        pass
                    self.remove_session(sid)

    @property
    def active_count(self) -> int:
        return len(self.sessions)

    @property
    def total_conversations(self) -> int:
        return sum(len(s.conversation_history) for s in self.sessions.values())

    async def close_all(self) -> None:
        for sid, session in list(self.sessions.items()):
            try:
                await session.ws.send_json({
                    "type": "server_shutdown",
                    "message": "सर्वर बंद हो रहा है। कृपया पुनः कनेक्ट करें।",
                })
                await session.ws.close()
            except Exception:
                pass
            self.remove_session(sid)


session_manager = SessionManager()
