"""Safety and reconciliation coverage for M2.1 workspace operations."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

import knowledge_assistant.ingestion.pipeline as ingestion_pipeline
from knowledge_assistant.chunking import chunk_workspace
from knowledge_assistant.config import (
    ChunkingSettings,
    ConfigurationError,
    DocumentSettings,
    EmbeddingSettings,
    load_settings,
)
from knowledge_assistant.ingestion import ingest_workspace
from knowledge_assistant.managers.workspace_manager import SourceRoot, Workspace
from knowledge_assistant.retrieval import (
    generate_embeddings,
    index_workspace,
    verify_index,
)


def _document_settings() -> DocumentSettings:
    return DocumentSettings(include=["*.txt"], exclude=[], recursive=True)


def _workspace(
    tmp_path: Path, *, unavailable_root: str = "warn", legacy: bool = False
) -> Workspace:
    course = tmp_path / "sources" / "course"
    evidence = tmp_path / "sources" / "evidence"
    if legacy:
        return Workspace(
            "example",
            "Example",
            course,
            tmp_path / "artifacts",
            "example",
            True,
            (SourceRoot("default", course, _document_settings()),),
            "fatal",
            True,
        )
    return Workspace(
        "example",
        "Example",
        course,
        tmp_path / "artifacts",
        "example",
        True,
        (
            SourceRoot("course", course, _document_settings()),
            SourceRoot("evidence", evidence, _document_settings()),
        ),
        unavailable_root,  # type: ignore[arg-type]
    )


def _document_artifacts(workspace: Workspace) -> list[Path]:
    return sorted(
        path
        for path in (workspace.artifacts / "ingestion").glob("*.json")
        if path.name != "report.json"
    )


def _embedding(texts: list[str]) -> list[list[float]]:
    return [[float(len(text)), 1.0] for text in texts]


def test_unavailable_root_policy_validation_and_default(tmp_path: Path) -> None:
    source = Path("config/config.example.yaml").read_text(encoding="utf-8")
    config = tmp_path / "config" / "config.yaml"
    config.parent.mkdir()
    config.write_text(source, encoding="utf-8")

    settings = load_settings(config)
    assert settings.workspaces["example"].documents.unavailable_root == "warn"

    config.write_text(
        source.replace("unavailable_root: warn", "unavailable_root: fatal"),
        encoding="utf-8",
    )
    assert (
        load_settings(config).workspaces["example"].documents.unavailable_root
        == "fatal"
    )

    config.write_text(
        source.replace("unavailable_root: warn", "unavailable_root: ignore"),
        encoding="utf-8",
    )
    with pytest.raises(ConfigurationError, match="unavailable_root"):
        load_settings(config)


def test_root_outcomes_warn_retention_selection_and_idempotence(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    course, evidence = (root.path for root in workspace.sources)
    course.mkdir(parents=True)
    evidence.mkdir(parents=True)
    (course / "guide.txt").write_text("same content", encoding="utf-8")
    (evidence / "guide.txt").write_text("same content", encoding="utf-8")

    first = ingest_workspace(workspace, _document_settings())
    assert len(first.documents) == 2
    assert len({document.id for document in first.documents}) == 2
    assert all(outcome.status == "scanned" for outcome in first.root_outcomes)
    assert sum(outcome.added_or_updated for outcome in first.root_outcomes) == 2

    second = ingest_workspace(workspace, _document_settings())
    assert sum(outcome.added_or_updated for outcome in second.root_outcomes) == 0
    assert sum(outcome.retained for outcome in second.root_outcomes) == 2

    (course / "guide.txt").unlink()
    selective = ingest_workspace(workspace, _document_settings(), roots={"evidence"})
    outcomes = {outcome.name: outcome for outcome in selective.root_outcomes}
    assert outcomes["course"].status == "unselected"
    assert outcomes["course"].retained == 1
    assert outcomes["evidence"].status == "scanned"
    assert len(_document_artifacts(workspace)) == 2

    evidence.rename(evidence.with_name("evidence-offline"))
    warning = ingest_workspace(workspace, _document_settings())
    outcomes = {outcome.name: outcome for outcome in warning.root_outcomes}
    assert outcomes["course"].status == "scanned"
    assert outcomes["course"].removed == 1
    assert outcomes["evidence"].status == "unavailable"
    assert outcomes["evidence"].retained == 1
    assert len(_document_artifacts(workspace)) == 1

    report = json.loads(
        (workspace.artifacts / "ingestion" / "report.json").read_text(encoding="utf-8")
    )
    assert {item["status"] for item in report["roots"]} == {
        "scanned",
        "unavailable",
    }


def test_fatal_and_legacy_unavailable_roots_stop_before_changes(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    course, evidence = (root.path for root in workspace.sources)
    course.mkdir(parents=True)
    evidence.mkdir(parents=True)
    (course / "guide.txt").write_text("course", encoding="utf-8")
    (evidence / "guide.txt").write_text("evidence", encoding="utf-8")
    ingest_workspace(workspace, _document_settings())
    before = {
        path.name: path.read_bytes()
        for path in (workspace.artifacts / "ingestion").glob("*.json")
    }
    evidence.rename(evidence.with_name("evidence-offline"))

    with pytest.raises(FileNotFoundError, match="evidence"):
        ingest_workspace(
            replace(workspace, unavailable_root="fatal"), _document_settings()
        )
    after = {
        path.name: path.read_bytes()
        for path in (workspace.artifacts / "ingestion").glob("*.json")
    }
    assert after == before

    legacy = _workspace(tmp_path / "legacy", legacy=True)
    with pytest.raises(FileNotFoundError, match="default"):
        ingest_workspace(legacy, _document_settings())
    assert not legacy.artifacts.exists()


def test_failed_scan_and_extraction_retain_prior_artifacts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = _workspace(tmp_path)
    course, evidence = (root.path for root in workspace.sources)
    course.mkdir(parents=True)
    evidence.mkdir(parents=True)
    source = course / "guide.txt"
    source.write_text("original", encoding="utf-8")
    ingest_workspace(workspace, _document_settings())
    artifact = _document_artifacts(workspace)[0]
    original = artifact.read_bytes()

    source.write_text("changed", encoding="utf-8")
    monkeypatch.setitem(
        ingestion_pipeline.EXTRACTORS,
        ".txt",
        lambda _path: (_ for _ in ()).throw(ValueError("extraction failed")),
    )
    extraction = ingest_workspace(workspace, _document_settings(), roots={"course"})
    outcome = next(item for item in extraction.root_outcomes if item.name == "course")
    assert outcome.status == "scanned"
    assert outcome.failed == 1
    assert outcome.retained == 1
    assert artifact.read_bytes() == original

    original_discover = ingestion_pipeline.discover_documents

    def fail_course(root: Path, settings: DocumentSettings):
        if root == course:
            raise PermissionError("scan denied")
        return original_discover(root, settings)

    monkeypatch.setattr(ingestion_pipeline, "discover_documents", fail_course)
    failed_scan = ingest_workspace(workspace, _document_settings(), roots={"course"})
    outcome = next(item for item in failed_scan.root_outcomes if item.name == "course")
    assert outcome.status == "failed"
    assert outcome.retained == 1
    assert artifact.read_bytes() == original


def test_confirmed_removal_propagates_without_index_rebuild(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    course, evidence = (root.path for root in workspace.sources)
    course.mkdir(parents=True)
    evidence.mkdir(parents=True)
    source = course / "guide.txt"
    source.write_text("A complete source sentence.", encoding="utf-8")
    ingest_workspace(workspace, _document_settings())
    chunking = ChunkingSettings(
        size=50,
        maximum_size=50,
        minimum_size=0,
        overlap=0,
        strategy="section",
    )
    embedding = EmbeddingSettings(
        provider="test", model="test", batch_size=10, version="1"
    )
    chunk_workspace(workspace, chunking)
    generate_embeddings(workspace, embedding, embedder=_embedding)
    initial_index = index_workspace(workspace, tmp_path / "chroma")
    assert initial_index.index_size == 1

    source.unlink()
    ingestion = ingest_workspace(workspace, _document_settings(), roots={"course"})
    chunks = chunk_workspace(workspace, chunking)
    embeddings = generate_embeddings(workspace, embedding, embedder=_embedding)
    index = index_workspace(workspace, tmp_path / "chroma")

    assert sum(outcome.removed for outcome in ingestion.root_outcomes) == 1
    assert chunks.chunks_removed == 1
    assert embeddings.embeddings_removed == 1
    assert index.deleted == 1
    assert index.index_size == 0
    assert verify_index(workspace, tmp_path / "chroma") == (True, 0, 0)
