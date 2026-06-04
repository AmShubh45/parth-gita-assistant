"""Tests for Krishna ask/search API endpoints."""

import os
import pytest
from unittest.mock import patch, AsyncMock

os.environ.setdefault("GEMINI_API_KEY", "test-key")

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.models.verse import Verse
from app.core.knowledge_base import knowledge_base


@pytest.fixture
def client():
    """Create a test client with mocked search dependencies."""
    from app.api.routes.krishna import router as krishna_router

    knowledge_base.verses = [
        Verse(
            id="bg_2_47", chapter=2, verse=47,
            sanskrit="कर्मण्येवाधिकारस्ते", hindi="तुम्हारा अधिकार केवल कर्म में है",
            meaning="निष्काम कर्म", themes=["detachment"],
            context_tags=["कर्म"], emotional_context=["चिंता"],
        ),
    ]
    knowledge_base.is_initialized = True

    @asynccontextmanager
    async def noop_lifespan(app):
        yield

    test_app = FastAPI(lifespan=noop_lifespan)
    test_app.include_router(krishna_router)

    with TestClient(test_app) as c:
        yield c


class TestSearchEndpoint:
    def test_search_empty_query(self, client):
        resp = client.post("/api/krishna/search", json={"query": ""})
        assert resp.status_code == 200
        data = resp.json()
        assert data["verses"] == []

    @patch("app.core.knowledge_base.gemini_client")
    def test_search_with_query(self, mock_gemini, client):
        mock_gemini.embed_query = AsyncMock(return_value=[0.1] * 768)
        # Since we don't have real embeddings, fallback search will be used
        resp = client.post("/api/krishna/search", json={"query": "कर्म", "maxResults": 1})
        assert resp.status_code == 200
        data = resp.json()
        assert "searchTime" in data
        assert data["searchType"] == "semantic_embedding"


class TestAskEndpoint:
    @patch("app.core.speech_processor.gemini_client")
    @patch("app.core.knowledge_base.gemini_client")
    def test_ask_question(self, mock_kb_gemini, mock_sp_gemini, client):
        mock_kb_gemini.embed_query = AsyncMock(return_value=[0.1] * 768)
        mock_sp_gemini.generate_content = AsyncMock(return_value="वत्स, कर्म ही आधार है।")

        resp = client.post("/api/krishna/ask", json={"question": "कर्म क्या है?"})
        assert resp.status_code == 200
        data = resp.json()
        assert "response" in data
        assert "sessionId" in data
        assert data["question"] == "कर्म क्या है?"

    def test_ask_empty_question_rejected(self, client):
        resp = client.post("/api/krishna/ask", json={"question": ""})
        assert resp.status_code == 422  # Pydantic validation error
