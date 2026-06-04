"""
WebSocket connection handler.

Handles all real-time communication: audio processing, text queries,
random verses, advanced search, and ping/pong heartbeat.
"""

from __future__ import annotations

import json
import time

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.knowledge_base import knowledge_base
from app.core.session_manager import session_manager
from app.core.speech_processor import speech_processor
from app.utils.logging import get_logger

logger = get_logger(__name__)

router = APIRouter()


@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    """Handle a WebSocket connection for Krishna conversations."""
    await ws.accept()

    session = session_manager.create_session(ws)
    logger.info("Client connected, session: %s", session.id)

    # Send greeting
    stats = knowledge_base.get_stats() if knowledge_base.is_initialized else {}
    await ws.send_json({
        "type": "connection_established",
        "message": "पार्थ, मैं कृष्ण हूं। आपका स्वागत है।",
        "sessionId": session.id,
        "knowledgeBaseStats": stats,
    })

    try:
        while True:
            raw = await ws.receive_text()

            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                await ws.send_json({"type": "error", "message": "Invalid message format"})
                continue

            current_session = session_manager.get_session(session.id)
            if not current_session:
                await ws.send_json({"type": "error", "message": "Session not found"})
                continue

            session_manager.update_activity(session.id)
            msg_type = data.get("type", "")

            try:
                if msg_type == "audio_data":
                    await _handle_audio(ws, data, session.id)
                elif msg_type == "text_query":
                    await _handle_text_query(ws, data, session.id)
                elif msg_type == "get_random_verse":
                    await _handle_random_verse(ws, session.id)
                elif msg_type == "advanced_search":
                    await _handle_advanced_search(ws, data, session.id)
                elif msg_type == "ping":
                    await ws.send_json({"type": "pong", "timestamp": int(time.time() * 1000)})
                else:
                    await ws.send_json({
                        "type": "error",
                        "message": "अज्ञात संदेश प्रकार",
                        "sessionId": session.id,
                    })
            except Exception as exc:
                logger.error("Error handling message type '%s': %s", msg_type, exc)
                await ws.send_json({"type": "error", "message": "संदेश प्रसंस्करण में त्रुटि"})

    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.error("WebSocket error: %s", exc)
    finally:
        speech_processor.cancel_active_requests(session.id)
        duration = time.time() - session.start_time
        questions = len(session.conversation_history)
        logger.info("Session ended: %s, Duration: %ds, Questions: %d", session.id, int(duration), questions)
        session_manager.remove_session(session.id)


# ── Message Handlers ────────────────────────────────────────────────────────

async def _handle_audio(ws: WebSocket, data: dict, session_id: str) -> None:
    audio = data.get("audio")
    if not audio:
        await ws.send_json({"type": "error", "message": "No audio data provided"})
        return

    start = time.time()
    result = await speech_processor.process_audio(audio, session_id)
    processing_time = int((time.time() - start) * 1000)

    logger.info("Krishna responded in %dms", processing_time)

    await ws.send_json({
        "type": "text_response",
        "text": result["response"],
        "transcription": result["transcription"],
        "versesUsed": result["versesUsed"],
        "processingTime": processing_time,
        "sessionId": session_id,
        "speaker": "krishna",
    })


async def _handle_text_query(ws: WebSocket, data: dict, session_id: str) -> None:
    query = data.get("query")
    if not query:
        await ws.send_json({"type": "error", "message": "No query provided"})
        return

    start = time.time()
    result = await speech_processor.process_text_query(query, session_id)
    processing_time = int((time.time() - start) * 1000)

    verses_used = result.get("versesUsed", [])
    verses_dicts = [v.to_dict() if hasattr(v, "to_dict") else v for v in verses_used]

    await ws.send_json({
        "type": "text_response",
        "text": result["response"],
        "versesUsed": verses_dicts,
        "searchMetrics": result.get("searchMetrics", {}),
        "processingTime": processing_time,
        "sessionId": session_id,
        "speaker": "krishna",
    })


async def _handle_random_verse(ws: WebSocket, session_id: str) -> None:
    verse = knowledge_base.get_random_verse()
    await ws.send_json({
        "type": "random_verse",
        "verse": verse.to_dict() if verse else None,
        "sessionId": session_id,
    })


async def _handle_advanced_search(ws: WebSocket, data: dict, session_id: str) -> None:
    options = data.get("options", {})
    results = await knowledge_base.advanced_search(
        query=options.get("query", ""),
        chapter=options.get("chapter"),
        themes=options.get("themes"),
        emotional_context=options.get("emotional_context"),
        life_situations=options.get("life_situations"),
        max_results=options.get("maxResults", 5),
    )
    await ws.send_json({
        "type": "search_results",
        "results": [v.to_dict() for v in results],
        "searchOptions": options,
        "sessionId": session_id,
    })
