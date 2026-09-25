"""Models shared by retrieval services and vector-store adapters."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from knowledge_assistant.ingestion.models import Chunk


class EmbeddingRecord(BaseModel):
    """A vector persisted independently from a vector database."""

    chunk: Chunk
    embedding: list[float]
    embedding_model: str
    embedding_version: str
    created: float


class RetrievalFailure(BaseModel):
    """A non-fatal failure encountered during retrieval preparation."""

    artifact: str
    message: str


class EmbeddingSummary(BaseModel):
    """Outcome of generating portable embedding artefacts."""

    workspace: str
    chunks_processed: int = 0
    embeddings_generated: int = 0
    embeddings_reused: int = 0
    embeddings_removed: int = 0
    failures: list[RetrievalFailure] = Field(default_factory=list)
    artifact_directory: Path
    elapsed_seconds: float = 0


class IndexSummary(BaseModel):
    """Outcome of synchronising embedding artefacts to a vector index."""

    workspace: str
    indexed: int = 0
    deleted: int = 0
    index_size: int = 0
    failures: list[RetrievalFailure] = Field(default_factory=list)
    elapsed_seconds: float = 0


class VectorSearchResult(BaseModel):
    """A raw result returned by a vector-store adapter."""

    identifier: str
    text: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    distance: float


class SearchResult(BaseModel):
    """A ranked, citation-ready retrieval result."""

    chunk_id: str
    document_id: str
    document_title: str | None = None
    section_title: str | None = None
    source_filename: str | None = None
    source_root: str = "default"
    relative_path: Path
    source_path: Path
    page: int | None = None
    source_location: str
    similarity: float
    text: str
    metadata: dict[str, Any] = Field(default_factory=dict)
