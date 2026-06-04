"""
Pydantic schemas for API request/response validation.

Provides automatic validation, serialization, and OpenAPI documentation
for all REST and WebSocket endpoints.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


# ── Request Schemas ─────────────────────────────────────────────────────────

class SearchRequest(BaseModel):
    """Body for POST /api/krishna/search."""

    query: str = Field(default="", description="Search query text")
    max_results: int = Field(
        default=3, alias="maxResults", ge=1, le=20,
        description="Maximum number of results to return",
    )


class AdvancedSearchRequest(BaseModel):
    """Body for POST /api/krishna/advanced-search."""

    query: str = Field(default="", description="Search query text")
    chapter: Optional[int] = Field(default=None, description="Filter by chapter number")
    themes: list[str] = Field(default_factory=list, description="Filter by themes")
    emotional_context: list[str] = Field(
        default_factory=list, description="Filter by emotional context",
    )
    life_situations: list[str] = Field(
        default_factory=list, description="Filter by life situations",
    )
    max_results: int = Field(
        default=5, alias="maxResults", ge=1, le=50,
        description="Maximum number of results to return",
    )

    model_config = {"populate_by_name": True}


class AskRequest(BaseModel):
    """Body for POST /api/krishna/ask."""

    question: str = Field(..., min_length=1, description="The question to ask Krishna")
    session_id: Optional[str] = Field(
        default=None, alias="sessionId",
        description="Existing session ID for conversation continuity",
    )

    model_config = {"populate_by_name": True}


# ── Response Schemas ────────────────────────────────────────────────────────

class VerseResponse(BaseModel):
    """A single verse in API responses."""

    id: str
    chapter: int
    verse: int
    sanskrit: str
    hindi: str
    meaning: str
    english: str = ""
    detailed_explanation: str = ""
    context_tags: list[str] = []
    emotional_context: list[str] = []
    life_situations: list[str] = []
    themes: list[str] = []


class SearchResponse(BaseModel):
    """Response for POST /api/krishna/search."""

    query: str
    verses: list[VerseResponse]
    count: int
    search_time: int = Field(alias="searchTime", description="Search time in ms")
    search_type: str = Field(default="semantic_embedding", alias="searchType")

    model_config = {"populate_by_name": True}


class AdvancedSearchResponse(BaseModel):
    """Response for POST /api/krishna/advanced-search."""

    results: list[VerseResponse]
    search_options: dict = Field(alias="searchOptions")
    count: int
    search_time: int = Field(alias="searchTime")

    model_config = {"populate_by_name": True}


class SearchMetrics(BaseModel):
    """Metrics attached to ask responses."""

    query_processed: bool = Field(alias="queryProcessed")
    verses_found: int = Field(alias="versesFound")
    search_type: str = Field(default="semantic", alias="searchType")

    model_config = {"populate_by_name": True}


class AskResponse(BaseModel):
    """Response for POST /api/krishna/ask."""

    question: str
    response: str
    verses_used: list[VerseResponse] = Field(alias="versesUsed")
    search_metrics: SearchMetrics = Field(alias="searchMetrics")
    session_id: str = Field(alias="sessionId")

    model_config = {"populate_by_name": True}


class KnowledgeBaseStats(BaseModel):
    """Knowledge base statistics."""

    total_verses: int = Field(alias="totalVerses")
    verses_with_embeddings: int = Field(alias="versesWithEmbeddings")
    categories: int
    chapters: int
    is_initialized: bool = Field(alias="isInitialized")

    model_config = {"populate_by_name": True}


class FeaturesInfo(BaseModel):
    """Feature flags in health response."""

    semantic_search: bool = Field(default=True, alias="semanticSearch")
    embeddings: bool = True
    advanced_search: bool = Field(default=True, alias="advancedSearch")
    multilingual_support: bool = Field(default=True, alias="multilingualSupport")

    model_config = {"populate_by_name": True}


class HealthResponse(BaseModel):
    """Response for GET /health."""

    status: str = "OK"
    service: str
    version: str
    timestamp: str
    active_sessions: int = Field(alias="activeSessions")
    knowledge_base: KnowledgeBaseStats = Field(alias="knowledgeBase")
    features: FeaturesInfo

    model_config = {"populate_by_name": True}


class SessionInfo(BaseModel):
    """A single session in the sessions list response."""

    id: str
    duration: int
    last_activity: int = Field(alias="lastActivity")
    question_count: int = Field(alias="questionCount")
    devotional_level: int = Field(alias="devotionalLevel")

    model_config = {"populate_by_name": True}


class SessionsResponse(BaseModel):
    """Response for GET /api/krishna/sessions."""

    sessions: list[SessionInfo]


class ServerStats(BaseModel):
    """Server statistics in stats response."""

    active_sessions: int = Field(alias="activeSessions")
    total_conversations: int = Field(alias="totalConversations")
    uptime: float

    model_config = {"populate_by_name": True}


class StatsResponse(BaseModel):
    """Response for GET /api/krishna/stats."""

    knowledge_base: KnowledgeBaseStats = Field(alias="knowledgeBase")
    server: ServerStats

    model_config = {"populate_by_name": True}
