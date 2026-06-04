"""Tests for verse API endpoints."""

import os
import pytest
from unittest.mock import patch, MagicMock, AsyncMock

# Set env before importing app
os.environ.setdefault("GEMINI_API_KEY", "test-key")

from fastapi.testclient import TestClient

from app.models.verse import Verse


# We need to patch the lifespan to avoid actual Gemini initialization
@pytest.fixture
def client():
    """Create a test client with mocked dependencies."""
    from contextlib import asynccontextmanager
    from fastapi import FastAPI
    from app.api.routes.health import router as health_router
    from app.api.routes.verses import router as verses_router
    from app.core.knowledge_base import knowledge_base

    # Pre-populate the knowledge base with test data
    knowledge_base.verses = [
        Verse(
            id="bg_2_47", chapter=2, verse=47,
            sanskrit="कर्मण्येवाधिकारस्ते", hindi="तुम्हारा अधिकार केवल कर्म में है",
            meaning="निष्काम कर्म का सिद्धांत", themes=["detachment"],
            context_tags=["कर्म"], emotional_context=["चिंता"],
        ),
        Verse(
            id="bg_3_21", chapter=3, verse=21,
            sanskrit="यद्यदाचरति श्रेष्ठः", hindi="श्रेष्ठ पुरुष जो आचरण करता है",
            meaning="नेतृत्व की जिम्मेदारी", themes=["leadership"],
            context_tags=["नेतृत्व"], emotional_context=["जिम्मेदारी"],
        ),
    ]
    knowledge_base.is_initialized = True

    @asynccontextmanager
    async def noop_lifespan(app):
        yield

    test_app = FastAPI(lifespan=noop_lifespan)
    test_app.include_router(health_router)
    test_app.include_router(verses_router)

    with TestClient(test_app) as c:
        yield c


class TestHealthEndpoint:
    def test_health_returns_ok(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "OK"
        assert "knowledgeBase" in data


class TestVersesEndpoint:
    def test_get_all_verses(self, client):
        resp = client.get("/api/krishna/verses")
        assert resp.status_code == 200
        data = resp.json()
        assert "verses" in data
        assert len(data["verses"]) == 2
        assert data["total"] == 2

    def test_get_verses_with_limit(self, client):
        resp = client.get("/api/krishna/verses?limit=1")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["verses"]) == 1

    def test_get_verses_by_chapter(self, client):
        resp = client.get("/api/krishna/verses?chapter=2")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["verses"]) == 1
        assert data["verses"][0]["chapter"] == 2

    def test_get_random_verse(self, client):
        resp = client.get("/api/krishna/verses?random=true")
        assert resp.status_code == 200
        data = resp.json()
        assert "verse" in data
        assert data["verse"]["id"] in ("bg_2_47", "bg_3_21")

    def test_get_stats(self, client):
        resp = client.get("/api/krishna/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert "knowledgeBase" in data
        assert "server" in data
        assert data["knowledgeBase"]["totalVerses"] == 2
