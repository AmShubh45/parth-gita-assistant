"""
Krishna Speech Processor — handles audio transcription and response generation.

Port of KrishnaSpeechProcessor from server.js.
"""

from __future__ import annotations

import time
from typing import Any

from app.core.gemini_client import gemini_client
from app.core.knowledge_base import knowledge_base
from app.core.session_manager import Session, session_manager
from app.prompts.krishna_system import (
    AUDIO_TRANSCRIPTION_PROMPT,
    build_krishna_response_prompt,
)
from app.utils.logging import get_logger

logger = get_logger(__name__)

FALLBACK_RESPONSE = "वत्स, थोड़ी देर में फिर प्रश्न पूछें। तकनीकी समस्या आ रही है।"


class SpeechProcessor:
    """Processes audio and text queries to generate Krishna's responses."""

    def __init__(self) -> None:
        self.active_requests: dict[str, bool] = {}

    async def process_audio(self, base64_audio: str, session_id: str) -> dict[str, Any]:
        """
        Full audio pipeline: transcribe → find verses → generate response.

        Returns dict with response, transcription, and versesUsed count.
        """
        request_id = f"audio_{int(time.time() * 1000)}_{session_id}"
        self.active_requests[request_id] = True

        try:
            session = session_manager.get_session(session_id)
            if not session:
                raise ValueError("Session not found")

            logger.info("Processing audio for session: %s", session_id)

            # Step 1: Transcribe audio
            user_question = await gemini_client.transcribe_audio(
                base64_audio=base64_audio,
                mime_type="audio/webm",
                prompt=AUDIO_TRANSCRIPTION_PROMPT,
            )
            logger.info("User question: %s", user_question)

            # Step 2: Find relevant verses
            relevant_verses = await knowledge_base.find_relevant_verses(user_question, 3)

            # Step 3: Generate Krishna's response
            krishna_response = await self._generate_krishna_response(
                user_question, relevant_verses, session,
            )

            # Step 4: Update session history
            session.conversation_history.append({
                "timestamp": int(time.time() * 1000),
                "userQuestion": user_question,
                "krishnaResponse": krishna_response,
                "versesUsed": [v.id for v in relevant_verses],
            })

            return {
                "response": krishna_response,
                "transcription": user_question,
                "versesUsed": len(relevant_verses),
            }

        finally:
            self.active_requests.pop(request_id, None)

    async def process_text_query(self, question: str, session_id: str) -> dict[str, Any]:
        """
        Text query pipeline: find verses → generate response.

        Returns dict with response, versesUsed list, and searchMetrics.
        """
        session = session_manager.get_session(session_id)
        if not session:
            raise ValueError("Session not found")

        logger.info("Processing text query: %s", question)

        relevant_verses = await knowledge_base.find_relevant_verses(question, 2)

        krishna_response = await self._generate_krishna_response(
            question, relevant_verses, session,
        )

        session.conversation_history.append({
            "timestamp": int(time.time() * 1000),
            "userQuestion": question,
            "krishnaResponse": krishna_response,
            "versesUsed": [v.id for v in relevant_verses] if relevant_verses else [],
            "type": "text",
        })

        return {
            "response": krishna_response,
            "versesUsed": relevant_verses or [],
            "searchMetrics": {
                "queryProcessed": True,
                "versesFound": len(relevant_verses) if relevant_verses else 0,
                "searchType": "semantic",
            },
        }

    async def _generate_krishna_response(
        self,
        question: str,
        relevant_verses: list,
        session: Session,
    ) -> str:
        """Generate Krishna's response using the Gemini model."""
        try:
            prompt = build_krishna_response_prompt(
                question=question,
                relevant_verses=relevant_verses,
                conversation_history=session.conversation_history,
            )
            return await gemini_client.generate_content(prompt)

        except Exception as exc:
            logger.error("Error generating Krishna response: %s", exc)
            return FALLBACK_RESPONSE

    def cancel_active_requests(self, session_id: str) -> None:
        """Cancel all active requests for a session."""
        to_remove = [rid for rid in self.active_requests if session_id in rid]
        for rid in to_remove:
            self.active_requests.pop(rid, None)
        if to_remove:
            logger.info("Cancelled %d active requests for session: %s", len(to_remove), session_id)


# Singleton instance
speech_processor = SpeechProcessor()
