"""
Mathematical utility functions for vector operations.

Used by the knowledge base for semantic similarity search.
"""

import numpy as np
from numpy.typing import NDArray


def cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    """
    Compute cosine similarity between two vectors.

    Returns a value between -1 and 1, where 1 means identical direction.
    Returns 0 if either vector has zero magnitude.
    """
    a = np.array(vec_a, dtype=np.float64)
    b = np.array(vec_b, dtype=np.float64)

    if a.shape != b.shape:
        return 0.0

    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)

    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0

    return float(np.dot(a, b) / (norm_a * norm_b))


def normalize_score(score: float, max_value: float = 100.0) -> float:
    """Normalize a keyword match score to the 0–1 range."""
    if max_value == 0.0:
        return 0.0
    return score / max_value
