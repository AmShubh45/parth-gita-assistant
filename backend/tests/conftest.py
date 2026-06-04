"""Shared test fixtures."""

import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Ensure the backend package is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Set required env vars BEFORE importing anything from app
os.environ.setdefault("GEMINI_API_KEY", "test-key-for-testing")


@pytest.fixture
def sample_verse_data():
    """A single verse dict as it appears in the JSON file."""
    return {
        "id": "bg_2_47",
        "chapter": 2,
        "verse": 47,
        "sanskrit": "कर्मण्येवाधिकारस्ते मा फलेषु कदाचन।",
        "hindi": "तुम्हारा अधिकार केवल कर्म करने में है, फल में कभी नहीं।",
        "english": "You have a right to perform your prescribed duty.",
        "meaning": "निष्काम कर्म का मूल सिद्धांत।",
        "detailed_explanation": "कर्मयोग का सबसे महत्वपूर्ण सिद्धांत।",
        "context_tags": ["कर्म", "निष्काम", "फल", "कर्मयोग"],
        "emotional_context": ["चिंता", "तनाव", "प्रेशर"],
        "life_situations": ["work_pressure", "career_anxiety"],
        "themes": ["detachment", "duty", "action"],
    }


@pytest.fixture
def sample_verses_json(sample_verse_data, tmp_path):
    """Write a minimal knowledge base JSON file and return its path."""
    import json

    data = {
        "verses": [sample_verse_data],
        "context_keywords": {
            "काम": ["कार्य", "नौकरी"],
            "मन": ["चिंता", "डर"],
        },
    }
    file_path = tmp_path / "test-kb.json"
    file_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return file_path


@pytest.fixture
def mock_gemini_client():
    """Patch the gemini_client singleton with mocks."""
    with patch("app.core.knowledge_base.gemini_client") as mock:
        mock.embed_content = AsyncMock(return_value=[0.1] * 768)
        mock.embed_query = AsyncMock(return_value=[0.1] * 768)
        mock.generate_content = AsyncMock(return_value="वत्स, कर्म ही जीवन का आधार है।")
        mock.transcribe_audio = AsyncMock(return_value="जीवन में कर्म का क्या महत्व है?")
        mock.configure = MagicMock()
        yield mock
