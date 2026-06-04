"""
Gemini AI client wrapper.

Provides a singleton interface to Google's GenAI SDK for
text generation, embedding generation, and audio transcription.
Uses the new `google.genai` package (replaces deprecated `google.generativeai`).
"""

from __future__ import annotations

from google import genai
from google.genai import types

from app.config import settings
from app.prompts.krishna_system import KRISHNA_SYSTEM_INSTRUCTIONS
from app.utils.logging import get_logger

logger = get_logger(__name__)


class GeminiClient:
    """Singleton wrapper around the Google GenAI SDK."""

    def __init__(self) -> None:
        self._configured = False
        self._client: genai.Client | None = None

    def configure(self) -> None:
        """Configure the SDK with the API key."""
        if self._configured:
            return

        self._client = genai.Client(api_key=settings.gemini_api_key)
        self._configured = True
        logger.info(
            "Gemini AI configured (generation=%s, embedding=%s)",
            settings.generation_model,
            settings.embedding_model,
        )

    # ── Text Generation ─────────────────────────────────────────────────

    async def generate_content(self, prompt: str) -> str:
        """
        Generate text content using the Krishna-persona model.

        Returns the generated text string.
        """
        self._ensure_configured()
        assert self._client is not None

        response = await self._client.aio.models.generate_content(
            model=settings.generation_model,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=KRISHNA_SYSTEM_INSTRUCTIONS,
            ),
        )
        return response.text

    # ── Audio Transcription ─────────────────────────────────────────────

    async def transcribe_audio(
        self,
        base64_audio: str,
        mime_type: str = "audio/webm",
        prompt: str = "",
    ) -> str:
        """
        Transcribe audio data using Gemini's multimodal capabilities.

        Args:
            base64_audio: Base64-encoded audio data.
            mime_type: MIME type of the audio.
            prompt: Instruction prompt for transcription.

        Returns:
            The transcribed text.
        """
        self._ensure_configured()
        assert self._client is not None

        response = await self._client.aio.models.generate_content(
            model=settings.generation_model,
            contents=[
                prompt,
                types.Part.from_bytes(
                    data=__import__("base64").b64decode(base64_audio),
                    mime_type=mime_type,
                ),
            ],
            config=types.GenerateContentConfig(
                system_instruction=KRISHNA_SYSTEM_INSTRUCTIONS,
            ),
        )
        return response.text.strip()

    # ── Embedding Generation ────────────────────────────────────────────

    async def embed_content(self, text: str) -> list[float]:
        """
        Generate an embedding vector for the given text (for documents).

        Returns a list of floats representing the embedding.
        """
        self._ensure_configured()
        assert self._client is not None

        response = await self._client.aio.models.embed_content(
            model=settings.embedding_model,
            contents=text,
            config=types.EmbedContentConfig(
                task_type="RETRIEVAL_DOCUMENT",
            ),
        )
        return list(response.embeddings[0].values)

    async def embed_query(self, text: str) -> list[float]:
        """
        Generate an embedding vector optimized for query matching.

        Returns a list of floats representing the query embedding.
        """
        self._ensure_configured()
        assert self._client is not None

        response = await self._client.aio.models.embed_content(
            model=settings.embedding_model,
            contents=text,
            config=types.EmbedContentConfig(
                task_type="RETRIEVAL_QUERY",
            ),
        )
        return list(response.embeddings[0].values)

    # ── Internals ───────────────────────────────────────────────────────

    def _ensure_configured(self) -> None:
        if not self._configured:
            raise RuntimeError(
                "GeminiClient not configured. Call configure() during startup."
            )


# Singleton instance — import this throughout the app.
gemini_client = GeminiClient()
