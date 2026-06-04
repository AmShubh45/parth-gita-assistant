"""
Verse data models.

Defines the Verse and VerseWithEmbedding dataclasses used throughout
the knowledge base and API layers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Verse:
    """A single Bhagavad Gita verse with all metadata."""

    id: str
    chapter: int
    verse: int
    sanskrit: str
    hindi: str
    meaning: str
    english: str = ""
    detailed_explanation: str = ""
    context_tags: list[str] = field(default_factory=list)
    emotional_context: list[str] = field(default_factory=list)
    life_situations: list[str] = field(default_factory=list)
    themes: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict) -> Verse:
        """Create a Verse from a dictionary (JSON deserialization)."""
        return cls(
            id=data["id"],
            chapter=data["chapter"],
            verse=data["verse"],
            sanskrit=data["sanskrit"],
            hindi=data["hindi"],
            meaning=data["meaning"],
            english=data.get("english", ""),
            detailed_explanation=data.get("detailed_explanation", ""),
            context_tags=data.get("context_tags", []),
            emotional_context=data.get("emotional_context", []),
            life_situations=data.get("life_situations", []),
            themes=data.get("themes", []),
        )

    def to_dict(self) -> dict:
        """Serialize to a dictionary for JSON output."""
        return {
            "id": self.id,
            "chapter": self.chapter,
            "verse": self.verse,
            "sanskrit": self.sanskrit,
            "hindi": self.hindi,
            "meaning": self.meaning,
            "english": self.english,
            "detailed_explanation": self.detailed_explanation,
            "context_tags": self.context_tags,
            "emotional_context": self.emotional_context,
            "life_situations": self.life_situations,
            "themes": self.themes,
        }


@dataclass
class VerseWithEmbedding:
    """A verse paired with its embedding vector for semantic search."""

    verse: Verse
    embedding: Optional[list[float]] = None
    embedding_text: str = ""
