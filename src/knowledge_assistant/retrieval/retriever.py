"""Query retrieval service independent of a concrete vector database."""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol

from knowledge_assistant.config import EmbeddingSettings, RetrievalSettings
from knowledge_assistant.managers.workspace_manager import Workspace
from knowledge_assistant.retrieval.models import SearchResult, VectorSearchResult
from knowledge_assistant.retrieval.scoring import distance_to_similarity


class VectorSearchBackend(Protocol):
    """Minimal vector search interface consumed by the retriever."""

    def search(
        self,
        workspace_name: str,
        collection_name: str,
        query_embedding: list[float],
        *,
        top_k: int,
        filters: dict[str, Any] | None = None,
    ) -> list[VectorSearchResult]:
        """Return ranked candidates from the underlying vector index."""


class Retriever:
    """Convert natural-language questions into ranked knowledge chunks."""

    def __init__(
        self,
        backend: VectorSearchBackend,
        settings: RetrievalSettings,
        embedding_settings: EmbeddingSettings,
        embedder: Callable[[list[str]], list[list[float]]],
    ) -> None:
        self.backend = backend
        self.settings = settings
        self.embedding_settings = embedding_settings
        self.embedder = embedder

    def search(
        self,
        workspace: Workspace,
        query: str,
        *,
        top_k: int | None = None,
        threshold: float | None = None,
        filters: dict[str, Any] | None = None,
    ) -> tuple[list[SearchResult], float]:
        started = time.monotonic()
        vectors = self.embedder([query])
        if len(vectors) != 1:
            raise ValueError(
                "embedding provider returned an unexpected number of vectors"
            )
        candidates = self.backend.search(
            workspace.name,
            workspace.collection,
            vectors[0],
            top_k=top_k or self.settings.top_k,
            filters=filters,
        )
        minimum = self.settings.similarity_threshold if threshold is None else threshold
        results = [
            self._result(candidate)
            for candidate in candidates
            if distance_to_similarity(candidate.distance) >= minimum
        ]
        return self._limit_context(results), time.monotonic() - started

    def _result(self, candidate: VectorSearchResult) -> SearchResult:
        metadata = candidate.metadata
        page = metadata.get("page")
        chunk_metadata = json.loads(str(metadata.get("metadata", "{}")))
        return SearchResult(
            chunk_id=str(metadata.get("chunk_id") or candidate.identifier),
            document_id=str(metadata["document_id"]),
            document_title=str(metadata.get("document_title") or "") or None,
            section_title=str(metadata.get("section_title") or "") or None,
            source_filename=str(metadata.get("source_filename") or "") or None,
            source_root=str(metadata.get("source_root") or "default"),
            relative_path=Path(str(metadata["relative_path"])),
            source_path=Path(
                str(metadata.get("source_path") or metadata["relative_path"])
            ),
            page=int(page) if page is not None else None,
            source_location=self._source_location(metadata),
            similarity=distance_to_similarity(candidate.distance),
            text=candidate.text,
            metadata=chunk_metadata,
        )

    def _source_location(self, metadata: dict[str, Any]) -> str:
        location = Path(
            str(metadata.get("source_path") or metadata["relative_path"])
        ).as_posix()
        page = metadata.get("page")
        section = str(metadata.get("section_title") or "")
        if page is not None:
            location = f"{location} page {page}"
        if section:
            location = f"{location} section {section}"
        return location

    def _limit_context(self, results: list[SearchResult]) -> list[SearchResult]:
        budget = self.settings.max_context_length
        if budget <= 0:
            return results
        total = 0
        limited: list[SearchResult] = []
        for result in results:
            size = len(result.text)
            if limited and total + size > budget:
                break
            limited.append(result)
            total += size
        return limited
