"""Tests for portable embeddings and workspace-isolated semantic retrieval."""

from pathlib import Path

from knowledge_assistant.config import EmbeddingSettings, RetrievalSettings
from knowledge_assistant.ingestion.models import Chunk
from knowledge_assistant.managers.workspace_manager import Workspace
from knowledge_assistant.retrieval import (
    evaluate_workspace,
    generate_embeddings,
    index_workspace,
    search_workspace,
    verify_index,
)


def _workspace(tmp_path: Path) -> Workspace:
    return Workspace(
        "example",
        "Example",
        tmp_path / "documents",
        tmp_path / "artifacts",
        "example",
        True,
    )


def _chunk(identifier: str, text: str, checksum: str = "checksum") -> Chunk:
    return Chunk(
        chunk_id=identifier,
        document_id="document-1",
        workspace="example",
        document_title="Funding",
        section_title="Grants",
        chunk_index=1,
        chunk_count=1,
        source_filename="funding.md",
        relative_path=Path("funding.md"),
        page=2,
        checksum=checksum,
        text=text,
        metadata={"file_type": "md", "topic": "funding"},
    )


def _embedder(texts: list[str]) -> list[list[float]]:
    return [[1.0, 0.0] if "grant" in text.lower() else [0.0, 1.0] for text in texts]


def test_embeddings_are_cached_and_chroma_search_preserves_provenance(
    tmp_path: Path,
) -> None:
    workspace = _workspace(tmp_path)
    chunks = workspace.artifacts / "chunks"
    chunks.mkdir(parents=True)
    (chunks / "chunk-1.json").write_text(
        _chunk("chunk-1", "Grant application submitted.").model_dump_json(),
        encoding="utf-8",
    )
    embedding = EmbeddingSettings(
        provider="test", model="test-model", batch_size=10, version="v1"
    )

    first = generate_embeddings(workspace, embedding, embedder=_embedder)
    second = generate_embeddings(workspace, embedding, embedder=_embedder)

    assert first.embeddings_generated == 1
    assert second.embeddings_reused == 1
    summary = index_workspace(workspace, tmp_path / "chroma")
    assert summary.index_size == 1
    assert verify_index(workspace, tmp_path / "chroma") == (True, 1, 1)
    results, _ = search_workspace(
        workspace,
        tmp_path / "chroma",
        RetrievalSettings(top_k=5, similarity_threshold=0, rerank=False),
        embedding,
        "Which grants did we apply for?",
        embedder=_embedder,
    )
    assert results[0].document_title == "Funding"
    assert results[0].section_title == "Grants"
    assert results[0].source_root == "default"
    assert results[0].relative_path == Path("funding.md")
    assert results[0].source_path == Path("default/funding.md")
    assert results[0].source_location == "default/funding.md page 2 section Grants"


def test_search_supports_metadata_filters_and_evaluation_metrics(
    tmp_path: Path,
) -> None:
    workspace = _workspace(tmp_path)
    chunks = workspace.artifacts / "chunks"
    chunks.mkdir(parents=True)
    (chunks / "chunk-1.json").write_text(
        _chunk("chunk-1", "Grant application submitted.").model_dump_json(),
        encoding="utf-8",
    )
    (chunks / "chunk-2.json").write_text(
        _chunk("chunk-2", "Training plan drafted.", checksum="other")
        .model_copy(
            update={
                "document_id": "document-2",
                "document_title": "Training",
                "section_title": "Fitness",
                "relative_path": Path("training.md"),
                "source_filename": "training.md",
                "text": "Training plan drafted.",
                "metadata": {"file_type": "md", "topic": "training"},
            }
        )
        .model_dump_json(),
        encoding="utf-8",
    )
    embedding = EmbeddingSettings(
        provider="test", model="test-model", batch_size=10, version="v1"
    )
    retrieval = RetrievalSettings(top_k=5, similarity_threshold=0, rerank=False)

    generate_embeddings(workspace, embedding, embedder=_embedder)
    index_workspace(workspace, tmp_path / "chroma")

    results, _ = search_workspace(
        workspace,
        tmp_path / "chroma",
        retrieval,
        embedding,
        "Which grants did we apply for?",
        filters={"topic": "funding"},
        embedder=_embedder,
    )

    assert [result.document_id for result in results] == ["document-1"]

    report = evaluate_workspace(
        workspace,
        tmp_path / "chroma",
        retrieval,
        embedding,
        [
            {
                "question": "Which grants did we apply for?",
                "expected_documents": ["document-1"],
                "expected_keywords": ["grant"],
            }
        ],
        embedder=_embedder,
    )
    assert report["recall_at_5"] == 1
    assert report["recall_at_10"] == 1
    assert report["mrr"] == 1
