"""Embedding persistence, indexing, search and benchmark evaluation."""

from __future__ import annotations

import time
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

from ollama import Client
from pydantic import ValidationError

from knowledge_assistant.config import EmbeddingSettings, RetrievalSettings
from knowledge_assistant.ingestion.models import Chunk
from knowledge_assistant.managers.workspace_manager import Workspace
from knowledge_assistant.retrieval.models import (
    EmbeddingRecord,
    EmbeddingSummary,
    IndexSummary,
    RetrievalFailure,
    SearchResult,
)
from knowledge_assistant.retrieval.retriever import Retriever
from knowledge_assistant.vectorstore import ChromaVectorStore


def _embedding_directory(workspace: Workspace) -> Path:
    return workspace.artifacts / "embeddings"


def _read_chunks(workspace: Workspace) -> tuple[list[Chunk], list[RetrievalFailure]]:
    directory = workspace.artifacts / "chunks"
    if not directory.is_dir():
        raise FileNotFoundError(f"Chunk artefact directory does not exist: {directory}")
    chunks, failures = [], []
    for path in sorted(directory.glob("*.json")):
        if path.name == "report.json":
            continue
        try:
            chunk = Chunk.model_validate_json(path.read_text(encoding="utf-8"))
            if chunk.workspace != workspace.name:
                raise ValueError(f"Artefact belongs to workspace '{chunk.workspace}'")
            chunks.append(chunk)
        except (OSError, ValidationError, ValueError) as error:
            failures.append(RetrievalFailure(artifact=path.name, message=str(error)))
    return chunks, failures


def _embed_ollama(settings: EmbeddingSettings, texts: list[str]) -> list[list[float]]:
    response = Client().embed(model=settings.model, input=texts)
    return response["embeddings"] if isinstance(response, dict) else response.embeddings


def generate_embeddings(
    workspace: Workspace,
    settings: EmbeddingSettings,
    *,
    force: bool = False,
    embedder: Callable[[list[str]], list[list[float]]] | None = None,
) -> EmbeddingSummary:
    """Create or reuse one portable embedding record per valid chunk."""
    started = time.monotonic()
    chunks, failures = _read_chunks(workspace)
    directory = _embedding_directory(workspace)
    directory.mkdir(parents=True, exist_ok=True)
    embedder = embedder or (lambda texts: _embed_ollama(settings, texts))
    generated = reused = 0
    pending: list[Chunk] = []
    for chunk in chunks:
        path = directory / f"{chunk.chunk_id}.json"
        if not force and path.is_file():
            try:
                existing = EmbeddingRecord.model_validate_json(
                    path.read_text(encoding="utf-8")
                )
                if (
                    existing.chunk.checksum == chunk.checksum
                    and existing.chunk.text == chunk.text
                    and existing.chunk.metadata == chunk.metadata
                    and existing.embedding_model == settings.model
                    and existing.embedding_version == settings.version
                ):
                    reused += 1
                    continue
            except (OSError, ValidationError):
                pass
        pending.append(chunk)
    for offset in range(0, len(pending), settings.batch_size):
        batch = pending[offset : offset + settings.batch_size]
        try:
            vectors = embedder([chunk.text for chunk in batch])
            if len(vectors) != len(batch):
                raise ValueError(
                    "embedding provider returned an unexpected number of vectors"
                )
            for chunk, vector in zip(batch, vectors, strict=True):
                record = EmbeddingRecord(
                    chunk=chunk,
                    embedding=vector,
                    embedding_model=settings.model,
                    embedding_version=settings.version,
                    created=time.time(),
                )
                (directory / f"{chunk.chunk_id}.json").write_text(
                    record.model_dump_json(indent=2) + "\n", encoding="utf-8"
                )
                generated += 1
        except Exception as error:  # noqa: BLE001
            failures.extend(
                RetrievalFailure(artifact=chunk.chunk_id, message=str(error))
                for chunk in batch
            )
    removed = 0
    if not failures:
        active = {chunk.chunk_id for chunk in chunks}
        for path in directory.glob("*.json"):
            if path.stem not in active:
                path.unlink()
                removed += 1
    return EmbeddingSummary(
        workspace=workspace.name,
        chunks_processed=len(chunks),
        embeddings_generated=generated,
        embeddings_reused=reused,
        embeddings_removed=removed,
        failures=failures,
        artifact_directory=directory,
        elapsed_seconds=time.monotonic() - started,
    )


def _records(
    workspace: Workspace,
) -> tuple[list[EmbeddingRecord], list[RetrievalFailure]]:
    records, failures = [], []
    for path in sorted(_embedding_directory(workspace).glob("*.json")):
        try:
            records.append(
                EmbeddingRecord.model_validate_json(path.read_text(encoding="utf-8"))
            )
        except (OSError, ValidationError) as error:
            failures.append(RetrievalFailure(artifact=path.name, message=str(error)))
    return records, failures


def index_workspace(
    workspace: Workspace, chroma_directory: Path, *, rebuild: bool = False
) -> IndexSummary:
    """Synchronise portable embedding artefacts into the workspace's Chroma collection."""
    started = time.monotonic()
    records, failures = _records(workspace)
    if failures:
        return IndexSummary(
            workspace=workspace.name,
            failures=failures,
            elapsed_seconds=time.monotonic() - started,
        )
    store = ChromaVectorStore(chroma_directory)
    indexed, deleted = store.upsert_workspace(
        workspace.name, workspace.collection, records, rebuild=rebuild
    )
    return IndexSummary(
        workspace=workspace.name,
        indexed=indexed,
        deleted=deleted,
        index_size=store.count_workspace(workspace.name, workspace.collection),
        failures=failures,
        elapsed_seconds=time.monotonic() - started,
    )


def verify_index(workspace: Workspace, chroma_directory: Path) -> tuple[bool, int, int]:
    records, _ = _records(workspace)
    count = ChromaVectorStore(chroma_directory).count_workspace(
        workspace.name, workspace.collection
    )
    return count == len(records), len(records), count


def search_workspace(
    workspace: Workspace,
    chroma_directory: Path,
    settings: RetrievalSettings,
    embedding_settings: EmbeddingSettings,
    query: str,
    *,
    top_k: int | None = None,
    threshold: float | None = None,
    filters: dict[str, Any] | None = None,
    embedder: Callable[[list[str]], list[list[float]]] | None = None,
) -> tuple[list[SearchResult], float]:
    """Search only the active workspace and return citation-ready provenance."""
    retriever = Retriever(
        ChromaVectorStore(chroma_directory),
        settings,
        embedding_settings,
        embedder or (lambda texts: _embed_ollama(embedding_settings, texts)),
    )
    return retriever.search(
        workspace,
        query,
        top_k=top_k,
        threshold=threshold,
        filters=filters,
    )


def evaluate_workspace(
    workspace: Workspace,
    chroma_directory: Path,
    settings: RetrievalSettings,
    embedding_settings: EmbeddingSettings,
    benchmarks: Iterable[dict[str, Any]],
    *,
    embedder: Callable[[list[str]], list[list[float]]] | None = None,
) -> dict[str, float | int]:
    """Calculate retrieval metrics from portable JSON benchmark definitions."""
    rows = list(benchmarks)
    reciprocal_ranks, recalls5, recalls10, similarities, latencies = [], [], [], [], []
    for row in rows:
        results, latency = search_workspace(
            workspace,
            chroma_directory,
            settings,
            embedding_settings,
            row["question"],
            top_k=10,
            threshold=row.get("similarity_threshold", 0),
            embedder=embedder,
        )
        expected_documents = set(row.get("expected_documents", []))
        expected_sections = set(row.get("expected_sections", []))
        expected_keywords = [
            str(value).lower() for value in row.get("expected_keywords", [])
        ]

        def matches(
            item: SearchResult,
            documents: set[str] = expected_documents,
            sections: set[str] = expected_sections,
            keywords: list[str] = expected_keywords,
        ) -> bool:
            document_match = not documents or item.document_id in documents
            section_match = not sections or item.section_title in sections
            keyword_match = not keywords or all(
                keyword in item.text.lower() for keyword in keywords
            )
            return document_match and section_match and keyword_match

        ranks = [index + 1 for index, item in enumerate(results) if matches(item)]
        reciprocal_ranks.append(1 / ranks[0] if ranks else 0)
        recalls5.append(float(any(matches(item) for item in results[:5])))
        recalls10.append(float(any(matches(item) for item in results[:10])))
        similarities.extend(item.similarity for item in results)
        latencies.append(latency)
    count = len(rows)
    return {
        "questions": count,
        "recall_at_5": sum(recalls5) / count if count else 0,
        "recall_at_10": sum(recalls10) / count if count else 0,
        "mrr": sum(reciprocal_ranks) / count if count else 0,
        "average_similarity": (
            sum(similarities) / len(similarities) if similarities else 0
        ),
        "search_latency_seconds": sum(latencies) / count if count else 0,
        "index_size": ChromaVectorStore(chroma_directory).count_workspace(
            workspace.name, workspace.collection
        ),
    }
