"""
Enhanced Krishna Knowledge Base with semantic search.

Faithful port of enhanced-knowledge-base.js — loads Bhagavad Gita verses,
generates embeddings via Gemini, and provides semantic + keyword search.
"""

from __future__ import annotations

import asyncio
import json
import random
from pathlib import Path
from typing import Optional

from app.config import settings
from app.core.gemini_client import gemini_client
from app.models.verse import Verse, VerseWithEmbedding
from app.utils.logging import get_logger
from app.utils.math_utils import cosine_similarity, normalize_score

logger = get_logger(__name__)


class KnowledgeBase:
    """
    RAG-powered knowledge base for Bhagavad Gita verses.

    Features:
    - Semantic search via Gemini embeddings + cosine similarity
    - Fallback keyword matching when embeddings are unavailable
    - Multi-criteria advanced search (chapter, themes, emotions, situations)
    - Verse CRUD operations
    """

    def __init__(self) -> None:
        self.verses: list[Verse] = []
        self.context_keywords: dict[str, list[str]] = {}
        self.verses_with_embeddings: list[VerseWithEmbedding] = []
        self.is_initialized: bool = False

    # ── Initialization ──────────────────────────────────────────────────

    async def initialize(self) -> None:
        """Load verses and generate embeddings."""
        logger.info("Initializing Krishna Knowledge Base...")

        await self._load_verses_from_file()
        await self._generate_embeddings()

        self.is_initialized = True
        logger.info("Krishna Knowledge Base initialized with semantic search")

    async def _load_verses_from_file(self) -> None:
        """Load verses from the JSON knowledge base file."""
        try:
            # Resolve path relative to backend/ directory
            base_dir = Path(__file__).resolve().parent.parent.parent
            file_path = base_dir / settings.knowledge_base_path

            data = json.loads(file_path.read_text(encoding="utf-8"))

            self.verses = [Verse.from_dict(v) for v in data["verses"]]
            self.context_keywords = data.get("context_keywords", {})

            logger.info("Loaded %d verses from knowledge base", len(self.verses))

        except FileNotFoundError:
            logger.warning("Knowledge base file not found, using fallback verses")
            self._initialize_fallback_verses()
        except Exception as exc:
            logger.error("Error loading verses: %s", exc)
            self._initialize_fallback_verses()

    def _initialize_fallback_verses(self) -> None:
        """Minimal fallback when the JSON file is unavailable."""
        logger.info("Using fallback verses...")
        self.verses = [
            Verse(
                id="bg_2_47",
                chapter=2,
                verse=47,
                sanskrit="कर्मण्येवाधिकारस्ते मा फलेषु कदाचन। "
                         "मा कर्मफलहेतुर्भूर्मा ते सङ्गोऽस्त्वकर्मणि॥",
                hindi="तुम्हारा अधिकार केवल कर्म करने में है, फल में कभी नहीं। "
                      "तुम कर्मफल के हेतु मत बनो और न ही तुम्हारी अकर्म में आसक्ति हो।",
                meaning="यह निष्काम कर्म का मूल सिद्धांत है। फल की चिंता छोड़कर "
                        "पूरी निष्ठा से काम करना ही सच्चा कर्मयोग है।",
                context_tags=["कर्म", "निष्काम", "फल", "कर्मयोग", "कर्तव्य"],
                emotional_context=["चिंता", "तनाव", "प्रेशर"],
                themes=["detachment", "duty", "action"],
            )
        ]
        self.context_keywords = {
            "काम": ["कार्य", "नौकरी", "व्यापार", "करियर"],
            "मन": ["चिंता", "डर", "गुस्सा", "दुख"],
        }

    # ── Embedding Generation ────────────────────────────────────────────

    async def _generate_embeddings(self) -> None:
        """Generate embeddings for all verses using Gemini."""
        logger.info("Generating embeddings for semantic search...")

        self.verses_with_embeddings = []

        for i, verse in enumerate(self.verses):
            try:
                embedding_text = self._create_embedding_text(verse)
                embedding = await gemini_client.embed_content(embedding_text)

                self.verses_with_embeddings.append(
                    VerseWithEmbedding(
                        verse=verse,
                        embedding=embedding,
                        embedding_text=embedding_text,
                    )
                )

                logger.info(
                    "Generated embedding for verse %s (%d/%d)",
                    verse.id, i + 1, len(self.verses),
                )

                # Rate-limit to avoid API throttling
                await asyncio.sleep(settings.embedding_rate_limit_ms / 1000)

            except Exception as exc:
                logger.error("Error generating embedding for %s: %s", verse.id, exc)
                # Add verse without embedding as fallback
                self.verses_with_embeddings.append(
                    VerseWithEmbedding(verse=verse, embedding=None)
                )

    @staticmethod
    def _create_embedding_text(verse: Verse) -> str:
        """Combine all relevant text fields for richer embedding context."""
        parts = [
            verse.hindi,
            verse.meaning,
            verse.detailed_explanation,
            " ".join(verse.context_tags) if verse.context_tags else "",
            " ".join(verse.emotional_context) if verse.emotional_context else "",
            " ".join(verse.themes) if verse.themes else "",
            " ".join(verse.life_situations) if verse.life_situations else "",
        ]
        return " ".join(p for p in parts if p)

    # ── Semantic Search ─────────────────────────────────────────────────

    async def find_relevant_verses(
        self, query: str, max_results: int = 3
    ) -> list[Verse]:
        """
        Find the most relevant verses for a query using semantic similarity.

        Falls back to keyword search if embeddings are unavailable.
        """
        if not self.is_initialized:
            logger.warning("Knowledge base not initialized, using fallback search")
            return self._fallback_search(query, max_results)

        try:
            query_embedding = await gemini_client.embed_query(query)

            similarities: list[tuple[Verse, float]] = []

            for vwe in self.verses_with_embeddings:
                if vwe.embedding is not None:
                    score = cosine_similarity(query_embedding, vwe.embedding)
                else:
                    score = self._calculate_keyword_score(query, vwe.verse)
                similarities.append((vwe.verse, score))

            # Sort descending by similarity
            similarities.sort(key=lambda x: x[1], reverse=True)
            results = [v for v, _ in similarities[:max_results]]

            logger.info(
                'Found %d relevant verses for query: "%s"',
                len(results), query[:80],
            )
            return results

        except Exception as exc:
            logger.error("Error in semantic search: %s", exc)
            return self._fallback_search(query, max_results)

    # ── Fallback Keyword Search ─────────────────────────────────────────

    def _fallback_search(self, query: str, max_results: int) -> list[Verse]:
        """Keyword-based search when embeddings are not available."""
        query_lower = query.lower()
        query_words = query_lower.split()

        scored: list[tuple[Verse, int]] = []
        for verse in self.verses:
            score = 0
            for word in query_words:
                if any(word in tag for tag in verse.context_tags):
                    score += 3
                if any(word in ctx for ctx in verse.emotional_context):
                    score += 4
                if verse.hindi and word in verse.hindi.lower():
                    score += 2
                if verse.meaning and word in verse.meaning.lower():
                    score += 2

            # Categorical matches
            for category, keywords in self.context_keywords.items():
                if any(kw in query_lower for kw in keywords):
                    if category in verse.context_tags:
                        score += 5

            if score > 0:
                scored.append((verse, score))

        scored.sort(key=lambda x: x[1], reverse=True)
        return [v for v, _ in scored[:max_results]]

    @staticmethod
    def _calculate_keyword_score(query: str, verse: Verse) -> float:
        """Calculate a normalized keyword-match score (0–1 range)."""
        query_lower = query.lower()
        query_words = query_lower.split()
        score = 0

        for word in query_words:
            if verse.hindi and word in verse.hindi.lower():
                score += 2
            if verse.meaning and word in verse.meaning.lower():
                score += 2
            if any(word in tag for tag in verse.context_tags):
                score += 1
            if any(word in ctx for ctx in verse.emotional_context):
                score += 1

        return normalize_score(score)

    # ── Advanced Search ─────────────────────────────────────────────────

    async def advanced_search(
        self,
        query: str = "",
        chapter: Optional[int] = None,
        themes: Optional[list[str]] = None,
        emotional_context: Optional[list[str]] = None,
        life_situations: Optional[list[str]] = None,
        max_results: int = 5,
    ) -> list[Verse]:
        """
        Multi-criteria search with optional semantic ranking.

        Filters are applied first, then semantic search ranks the results.
        """
        results = list(self.verses)

        if chapter is not None:
            results = [v for v in results if v.chapter == chapter]

        if themes:
            results = [
                v for v in results
                if v.themes and any(t in v.themes for t in themes)
            ]

        if emotional_context:
            results = [
                v for v in results
                if v.emotional_context
                and any(e in v.emotional_context for e in emotional_context)
            ]

        if life_situations:
            results = [
                v for v in results
                if v.life_situations
                and any(s in v.life_situations for s in life_situations)
            ]

        # If a query is provided, use semantic search on the filtered set
        if query.strip():
            # Build a temporary lookup to filter embeddings
            result_ids = {v.id for v in results}
            original_embeddings = self.verses_with_embeddings
            self.verses_with_embeddings = [
                vwe for vwe in original_embeddings if vwe.verse.id in result_ids
            ]
            try:
                results = await self.find_relevant_verses(query, max_results)
            finally:
                self.verses_with_embeddings = original_embeddings
            return results

        return results[:max_results]

    # ── Simple Lookups ──────────────────────────────────────────────────

    def get_random_verse(self) -> Optional[Verse]:
        """Return a random verse, or None if empty."""
        if not self.verses:
            return None
        return random.choice(self.verses)

    def get_verses_by_chapter(self, chapter: int) -> list[Verse]:
        """Return all verses from a specific chapter."""
        return [v for v in self.verses if v.chapter == chapter]

    def get_verse_by_id(self, verse_id: str) -> Optional[Verse]:
        """Return a verse by its ID, or None if not found."""
        return next((v for v in self.verses if v.id == verse_id), None)

    # ── Knowledge Base Management ───────────────────────────────────────

    async def add_verse(self, verse_data: dict) -> None:
        """
        Add a new verse to the knowledge base and generate its embedding.

        Raises ValueError if required fields are missing or ID is duplicate.
        """
        required_fields = ["id", "chapter", "verse", "sanskrit", "hindi", "meaning"]
        for field in required_fields:
            if field not in verse_data:
                raise ValueError(f"Missing required field: {field}")

        if any(v.id == verse_data["id"] for v in self.verses):
            raise ValueError(f"Verse with ID {verse_data['id']} already exists")

        verse = Verse.from_dict(verse_data)
        self.verses.append(verse)

        # Generate embedding if initialized
        if self.is_initialized:
            embedding_text = self._create_embedding_text(verse)
            try:
                embedding = await gemini_client.embed_content(embedding_text)
                self.verses_with_embeddings.append(
                    VerseWithEmbedding(
                        verse=verse,
                        embedding=embedding,
                        embedding_text=embedding_text,
                    )
                )
            except Exception as exc:
                logger.error("Error generating embedding for new verse: %s", exc)
                self.verses_with_embeddings.append(
                    VerseWithEmbedding(verse=verse, embedding=None)
                )

        logger.info("Added new verse: %s", verse.id)

    async def save_to_file(self) -> None:
        """Persist the knowledge base back to its JSON file."""
        base_dir = Path(__file__).resolve().parent.parent.parent
        file_path = base_dir / settings.knowledge_base_path

        data = {
            "verses": [v.to_dict() for v in self.verses],
            "context_keywords": self.context_keywords,
        }

        file_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        logger.info("Knowledge base saved to file")

    # ── Statistics ──────────────────────────────────────────────────────

    def get_stats(self) -> dict:
        """Return knowledge base statistics."""
        return {
            "totalVerses": len(self.verses),
            "versesWithEmbeddings": sum(
                1 for vwe in self.verses_with_embeddings if vwe.embedding is not None
            ),
            "categories": len(self.context_keywords),
            "chapters": len({v.chapter for v in self.verses}),
            "isInitialized": self.is_initialized,
        }


# Singleton instance — import this throughout the app.
knowledge_base = KnowledgeBase()
