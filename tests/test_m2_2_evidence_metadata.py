"""Synthetic coverage for M2.2 evidence-library metadata integration."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from knowledge_assistant.chunking import chunk_workspace
from knowledge_assistant.config import (
    ChunkingSettings,
    DocumentSettings,
    EmbeddingSettings,
    EvidenceLibrarySettings,
)
from knowledge_assistant.evidence.models import EvidenceManifest, ModuleRecord
from knowledge_assistant.evidence.service import (
    EvidenceLibraryError,
    EvidenceLibraryService,
    load_evidence_library,
    write_control_artifact,
)
from knowledge_assistant.ingestion import ingest_workspace
from knowledge_assistant.main import main
from knowledge_assistant.managers.workspace_manager import SourceRoot, Workspace
from knowledge_assistant.retrieval import generate_embeddings, index_workspace
from knowledge_assistant.vectorstore.chroma import ChromaVectorStore


def _settings() -> DocumentSettings:
    return DocumentSettings(include=["*.txt"], exclude=[], recursive=True)


def _workspace(tmp_path: Path, *, missing: str = "warn", unmatched: str = "warn"):
    course = tmp_path / "sources" / "course"
    evidence = tmp_path / "sources" / "evidence"
    controls = tmp_path / "controls"
    course.mkdir(parents=True)
    evidence.mkdir(parents=True)
    (controls / "modules").mkdir(parents=True)
    workspace = Workspace(
        "synthetic",
        "Synthetic evidence library",
        course,
        tmp_path / "artifacts",
        "synthetic",
        True,
        (
            SourceRoot("course", course, _settings()),
            SourceRoot("evidence", evidence, _settings()),
        ),
        "warn",
        False,
        EvidenceLibrarySettings(
            manifest=controls / "manifest.json",
            policy=controls / "policy.yaml",
            missing_referenced_document=missing,
            unmatched_document=unmatched,
        ),
    )
    return workspace, course, evidence, controls


def _write_library(
    workspace: Workspace,
    course: Path,
    evidence: Path,
    controls: Path,
    *,
    second_module: bool = False,
    local_file: str | None = "../../sources/evidence/reference.txt",
) -> None:
    (course / "module.txt").write_text("Course evidence sentence.", encoding="utf-8")
    if local_file is not None:
        (evidence / "reference.txt").write_text(
            "Authoritative evidence sentence.", encoding="utf-8"
        )
    modules = [
        {
            "module_id": "M01",
            "title": "Digestion",
            "record_file": "modules/m01.json",
            "course_document": "../sources/course/module.txt",
        }
    ]
    if second_module:
        modules.append(
            {
                "module_id": "M02",
                "title": "Shared evidence",
                "record_file": "modules/m02.json",
            }
        )
    (controls / "manifest.json").write_text(
        json.dumps({"schema_version": "1.0", "modules": modules}), encoding="utf-8"
    )
    (controls / "policy.yaml").write_text(
        yaml.safe_dump(
            {
                "schema_version": "1.0",
                "module_statuses": ["complete", "in_progress"],
                "claim_assessments": ["supported", "qualified"],
            }
        ),
        encoding="utf-8",
    )

    def record(module_id: str, title: str, source_id: str) -> dict:
        return {
            "module_id": module_id,
            "title": title,
            "status": "complete",
            "course_document": "../../sources/course/module.txt",
            "course_pdf_pages": 2,
            "subtopics": [{"id": "topic", "title": "Topic", "course_pages": [1]}],
            "sources": [
                {
                    "id": source_id,
                    "title": "Reference",
                    "organisation": "Example Authority",
                    "authority_type": "public body",
                    "url": "https://example.test/reference",
                    "local_file": local_file,
                    "download_status": "validated" if local_file else "unavailable",
                    "relevant_topics": ["topic"],
                }
            ],
            "claim_reviews": [
                {
                    "subtopic_id": "topic",
                    "assessment": "qualified",
                    "notes": f"Qualification for {module_id}",
                }
            ],
        }

    (controls / "modules" / "m01.json").write_text(
        json.dumps(record("M01", "Digestion", "source-one")), encoding="utf-8"
    )
    if second_module:
        (controls / "modules" / "m02.json").write_text(
            json.dumps(record("M02", "Shared evidence", "source-two")),
            encoding="utf-8",
        )


def test_strict_schemas_and_identity_integrity() -> None:
    with pytest.raises(ValidationError, match="extra_forbidden"):
        EvidenceManifest.model_validate(
            {
                "schema_version": "1.0",
                "modules": [{"module_id": "M01", "record_file": "m.json"}],
                "typo": True,
            }
        )
    with pytest.raises(ValidationError, match="unique ignoring case"):
        EvidenceManifest.model_validate(
            {
                "schema_version": "1.0",
                "modules": [
                    {"module_id": "M01", "record_file": "one.json"},
                    {"module_id": "m01", "record_file": "two.json"},
                ],
            }
        )
    with pytest.raises(ValidationError, match="unknown subtopic"):
        ModuleRecord.model_validate(
            {
                "module_id": "M01",
                "title": "Module",
                "status": "complete",
                "course_document": "course.txt",
                "claim_reviews": [
                    {
                        "subtopic_id": "missing",
                        "assessment": "supported",
                        "notes": "note",
                    }
                ],
            }
        )


def test_loading_matches_paths_remote_missing_unmatched_and_control_lookup(
    tmp_path: Path,
) -> None:
    workspace, course, evidence, controls = _workspace(tmp_path)
    _write_library(workspace, course, evidence, controls, local_file=None)
    (evidence / "unmatched.txt").write_text("Unmatched.", encoding="utf-8")
    library = load_evidence_library(workspace)
    assert library is not None
    assert library.summary.remote_only_references == 1
    assert library.summary.missing_references == 0
    assert library.summary.unmatched_documents == 1
    assert library.summary.associations == 1
    assert library.document_associations[0].source_path == Path("course/module.txt")
    artifact = write_control_artifact(library, workspace.artifacts / "metadata")
    service = EvidenceLibraryService.from_artifact(artifact)
    assert service.claim_reviews("m01", "TOPIC")[0].assessment == "qualified"
    assert "Course evidence sentence" not in artifact.read_text(encoding="utf-8")


def test_unsafe_inconsistent_and_fatal_policy_stop_validation(tmp_path: Path) -> None:
    workspace, course, evidence, controls = _workspace(tmp_path, missing="fatal")
    _write_library(workspace, course, evidence, controls)
    record_path = controls / "modules" / "m01.json"
    record = json.loads(record_path.read_text(encoding="utf-8"))
    record["sources"][0]["local_file"] = "../../outside.txt"
    record_path.write_text(json.dumps(record), encoding="utf-8")
    with pytest.raises(EvidenceLibraryError, match="outside every"):
        load_evidence_library(workspace)

    record["sources"][0]["local_file"] = "../../sources/evidence/missing.txt"
    record_path.write_text(json.dumps(record), encoding="utf-8")
    with pytest.raises(EvidenceLibraryError, match="Missing referenced"):
        load_evidence_library(workspace)
    assert not workspace.artifacts.exists()


def test_supported_version_course_agreement_and_unmatched_fatal(tmp_path: Path) -> None:
    workspace, course, evidence, controls = _workspace(tmp_path, unmatched="fatal")
    _write_library(workspace, course, evidence, controls)
    manifest_path = controls / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["schema_version"] = "2.0"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(EvidenceLibraryError, match="supported"):
        load_evidence_library(workspace)

    manifest["schema_version"] = "1.0"
    manifest["modules"][0]["course_document"] = "../sources/course/other.txt"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(EvidenceLibraryError, match="Course paths disagree"):
        load_evidence_library(workspace)

    manifest["modules"][0]["course_document"] = "../sources/course/module.txt"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    (evidence / "unmatched.txt").write_text("Unmatched.", encoding="utf-8")
    with pytest.raises(EvidenceLibraryError, match="Unmatched document"):
        load_evidence_library(workspace)


def test_multiple_associations_propagate_refresh_and_filter(tmp_path: Path) -> None:
    workspace, course, evidence, controls = _workspace(tmp_path)
    _write_library(workspace, course, evidence, controls, second_module=True)
    library = load_evidence_library(workspace)
    assert library is not None
    ingestion = ingest_workspace(workspace, _settings(), evidence_library=library)
    source = next(
        item for item in ingestion.documents if item.source_root == "evidence"
    )
    extractor = source.metadata["extractor"]
    associations = source.metadata["evidence"]["associations"]
    assert extractor["source_suffix"] == ".txt"
    assert [item["module_id"] for item in associations] == ["M01", "M02"]

    chunks = chunk_workspace(
        workspace,
        ChunkingSettings(
            size=50, maximum_size=50, minimum_size=0, overlap=0, strategy="section"
        ),
    )
    assert any(
        len(item.metadata["evidence"]["associations"]) == 2 for item in chunks.chunks
    )
    embedding_settings = EmbeddingSettings(
        provider="test", model="test", batch_size=10, version="1"
    )
    embedder = lambda texts: [[float(len(text)), 1.0] for text in texts]
    first = generate_embeddings(workspace, embedding_settings, embedder=embedder)
    assert first.embeddings_generated == len(chunks.chunks)
    index_workspace(workspace, tmp_path / "chroma")
    store = ChromaVectorStore(tmp_path / "chroma")
    found = store.search(
        workspace.name,
        workspace.collection,
        [31.0, 1.0],
        top_k=10,
        filters={"document_role": "authoritative_source", "module_id": "M02"},
    )
    assert found
    assert store.search(
        workspace.name,
        workspace.collection,
        [31.0, 1.0],
        top_k=10,
        filters={"source_id": "source-two", "module_id": "M02"},
    )

    module = json.loads((controls / "modules" / "m02.json").read_text(encoding="utf-8"))
    module["sources"] = []
    (controls / "modules" / "m02.json").write_text(json.dumps(module), encoding="utf-8")
    changed = load_evidence_library(workspace)
    assert changed is not None
    refresh = ingest_workspace(
        workspace, _settings(), roots={"evidence"}, evidence_library=changed
    )
    evidence_outcome = next(
        item for item in refresh.root_outcomes if item.name == "evidence"
    )
    course_outcome = next(
        item for item in refresh.root_outcomes if item.name == "course"
    )
    assert evidence_outcome.added_or_updated == 1
    assert course_outcome.status == "unselected"
    assert len(refresh.documents[0].metadata["evidence"]["associations"]) == 1
    updated_chunks = chunk_workspace(
        workspace,
        ChunkingSettings(
            size=50, maximum_size=50, minimum_size=0, overlap=0, strategy="section"
        ),
    )
    second = generate_embeddings(workspace, embedding_settings, embedder=embedder)
    assert second.embeddings_generated >= 1
    assert any(
        item.source_root == "course"
        and len(item.metadata["evidence"]["associations"]) == 2
        for item in updated_chunks.chunks
    )


def test_metadata_cli_summary_and_exit_codes(tmp_path: Path, capsys) -> None:
    workspace, course, evidence, controls = _workspace(tmp_path)
    _write_library(workspace, course, evidence, controls)
    template = yaml.safe_load(
        Path("config/config.example.yaml").read_text(encoding="utf-8")
    )
    template["workspaces"] = {
        "synthetic": {
            "enabled": True,
            "description": "Synthetic",
            "documents": {
                "defaults": {"include": ["*.txt"], "exclude": [], "recursive": True},
                "roots": [
                    {"name": "course", "path": str(course)},
                    {"name": "evidence", "path": str(evidence)},
                ],
            },
            "evidence_library": {
                "manifest": str(controls / "manifest.json"),
                "policy": str(controls / "policy.yaml"),
            },
            "artifacts": str(workspace.artifacts),
            "collection": "synthetic",
        }
    }
    config = tmp_path / "config.yaml"
    config.write_text(yaml.safe_dump(template), encoding="utf-8")
    assert main(["--config", str(config), "metadata", "validate", "synthetic"]) == 0
    output = capsys.readouterr().out
    assert "Manifest schema: 1.0" in output
    assert "Remote-only references: 0" in output
    assert (
        main(
            [
                "--config",
                str(config),
                "metadata",
                "show",
                "synthetic",
                "--module",
                "M01",
            ]
        )
        == 0
    )
    assert "Claim reviews" in capsys.readouterr().out
    assert (
        main(
            [
                "--config",
                str(config),
                "metadata",
                "show",
                "synthetic",
                "--module",
                "bad",
            ]
        )
        == 2
    )


def test_atomic_control_write_preserves_last_good_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace, course, evidence, controls = _workspace(tmp_path)
    _write_library(workspace, course, evidence, controls)
    library = load_evidence_library(workspace)
    assert library is not None
    destination = write_control_artifact(library, workspace.artifacts / "metadata")
    original = destination.read_bytes()
    monkeypatch.setattr(
        "knowledge_assistant.evidence.service.os.replace",
        lambda *_args: (_ for _ in ()).throw(PermissionError("denied")),
    )
    with pytest.raises(PermissionError, match="denied"):
        write_control_artifact(library, workspace.artifacts / "metadata")
    assert destination.read_bytes() == original
