"""Similarity scoring helpers for retrieval."""

from __future__ import annotations


def distance_to_similarity(distance: float) -> float:
    """Normalise Chroma distance values to the public 0..1 similarity scale."""
    return max(0.0, min(1.0, 1.0 - float(distance)))
