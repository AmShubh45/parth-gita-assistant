"""Tests for the KnowledgeBase core module."""

import pytest

from app.models.verse import Verse
from app.core.knowledge_base import KnowledgeBase


class TestVerseModel:
    """Tests for the Verse dataclass."""

    def test_from_dict(self, sample_verse_data):
        verse = Verse.from_dict(sample_verse_data)
        assert verse.id == "bg_2_47"
        assert verse.chapter == 2
        assert verse.verse == 47
        assert "कर्म" in verse.context_tags
        assert "detachment" in verse.themes

    def test_to_dict_roundtrip(self, sample_verse_data):
        verse = Verse.from_dict(sample_verse_data)
        output = verse.to_dict()
        assert output["id"] == sample_verse_data["id"]
        assert output["chapter"] == sample_verse_data["chapter"]
        assert output["context_tags"] == sample_verse_data["context_tags"]

    def test_optional_fields_default_empty(self):
        verse = Verse(
            id="test",
            chapter=1,
            verse=1,
            sanskrit="test",
            hindi="test",
            meaning="test",
        )
        assert verse.english == ""
        assert verse.context_tags == []
        assert verse.themes == []


class TestKnowledgeBase:
    """Tests for the KnowledgeBase class."""

    def _make_kb_with_verses(self, sample_verse_data):
        kb = KnowledgeBase()
        kb.verses = [Verse.from_dict(sample_verse_data)]
        kb.context_keywords = {"काम": ["कार्य", "नौकरी"], "मन": ["चिंता", "डर"]}
        kb.is_initialized = False  # Skip embedding checks
        return kb

    def test_get_random_verse(self, sample_verse_data):
        kb = self._make_kb_with_verses(sample_verse_data)
        verse = kb.get_random_verse()
        assert verse is not None
        assert verse.id == "bg_2_47"

    def test_get_random_verse_empty(self):
        kb = KnowledgeBase()
        assert kb.get_random_verse() is None

    def test_get_verses_by_chapter(self, sample_verse_data):
        kb = self._make_kb_with_verses(sample_verse_data)
        verses = kb.get_verses_by_chapter(2)
        assert len(verses) == 1
        assert verses[0].chapter == 2

    def test_get_verses_by_chapter_none(self, sample_verse_data):
        kb = self._make_kb_with_verses(sample_verse_data)
        verses = kb.get_verses_by_chapter(99)
        assert len(verses) == 0

    def test_get_verse_by_id(self, sample_verse_data):
        kb = self._make_kb_with_verses(sample_verse_data)
        verse = kb.get_verse_by_id("bg_2_47")
        assert verse is not None
        assert verse.id == "bg_2_47"

    def test_get_verse_by_id_not_found(self, sample_verse_data):
        kb = self._make_kb_with_verses(sample_verse_data)
        assert kb.get_verse_by_id("nonexistent") is None

    def test_fallback_search_finds_matching(self, sample_verse_data):
        kb = self._make_kb_with_verses(sample_verse_data)
        results = kb._fallback_search("कर्म करना", 3)
        assert len(results) >= 1
        assert results[0].id == "bg_2_47"

    def test_fallback_search_no_match(self, sample_verse_data):
        kb = self._make_kb_with_verses(sample_verse_data)
        results = kb._fallback_search("completely unrelated xyz", 3)
        assert len(results) == 0

    def test_get_stats(self, sample_verse_data):
        kb = self._make_kb_with_verses(sample_verse_data)
        stats = kb.get_stats()
        assert stats["totalVerses"] == 1
        assert stats["isInitialized"] is False
        assert stats["chapters"] == 1

    def test_create_embedding_text(self, sample_verse_data):
        verse = Verse.from_dict(sample_verse_data)
        text = KnowledgeBase._create_embedding_text(verse)
        assert "कर्म" in text
        assert "detachment" in text
        assert len(text) > 50

    @pytest.mark.asyncio
    async def test_add_verse_duplicate_raises(self, sample_verse_data):
        kb = KnowledgeBase()
        kb.verses = [Verse.from_dict(sample_verse_data)]
        with pytest.raises(ValueError, match="already exists"):
            await kb.add_verse(sample_verse_data)

    @pytest.mark.asyncio
    async def test_add_verse_missing_field(self):
        kb = KnowledgeBase()
        with pytest.raises(ValueError, match="Missing required field"):
            await kb.add_verse({"id": "test"})
