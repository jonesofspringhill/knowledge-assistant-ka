"""Portable embeddings, vector indexing and semantic retrieval services."""

from knowledge_assistant.retrieval.models import (
    EmbeddingRecord,
    EmbeddingSummary,
    IndexSummary,
    RetrievalFailure,
    SearchResult,
)
from knowledge_assistant.retrieval.pipeline import (
    evaluate_workspace,
    generate_embeddings,
    index_workspace,
    search_workspace,
    verify_index,
)

__all__ = [
    "EmbeddingRecord",
    "EmbeddingSummary",
    "IndexSummary",
    "RetrievalFailure",
    "SearchResult",
    "evaluate_workspace",
    "generate_embeddings",
    "index_workspace",
    "search_workspace",
    "verify_index",
]
