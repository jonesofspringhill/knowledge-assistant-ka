"""Content reuse must preserve source identity, refresh metadata, and recover safely."""

import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from knowledge_assistant.config import DocumentSettings
from knowledge_assistant.ingestion import cache as cache_module
from knowledge_assistant.ingestion import pipeline
from knowledge_assistant.managers.workspace_manager import SourceRoot, Workspace


@pytest.fixture
def setup(tmp_path):
    documents = tmp_path / "documents"
    documents.mkdir()
    source = documents / "minutes.txt"
    source.write_text("Approved the roof repairs.", encoding="utf-8")
    workspace = Workspace(
        "example", "Example", documents, tmp_path / "artifacts", "example", True
    )
    settings = DocumentSettings(include=["*.txt"], exclude=[], recursive=True)
    return workspace, settings, source


def test_unchanged_files_reuse_extraction_without_rewriting_artifact(
    setup, monkeypatch
):
    workspace, settings, source = setup
    original = source.read_bytes()
    first = pipeline.ingest_workspace(workspace, settings)
    artifact = first.artifact_directory / f"{first.documents[0].id}.json"
    stamp = artifact.stat().st_mtime_ns
    monkeypatch.setitem(
        pipeline.EXTRACTORS, ".txt", lambda _: pytest.fail("re-extracted")
    )
    second = pipeline.ingest_workspace(workspace, settings)
    assert first.extractions_performed == 1
    assert second.extractions_performed == 0
    assert second.extractions_reused == 1
    assert second.documents == first.documents
    assert artifact.stat().st_mtime_ns == stamp
    assert source.read_bytes() == original


def test_changed_bytes_invalidate_even_with_same_size_and_timestamp(setup):
    workspace, settings, source = setup
    first = pipeline.ingest_workspace(workspace, settings)
    stamp = source.stat()
    source.write_text("Rejected the roof repairs.", encoding="utf-8")
    os.utime(source, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
    second = pipeline.ingest_workspace(workspace, settings)
    assert second.extractions_performed == 1
    assert second.documents[0].checksum != first.documents[0].checksum
    assert second.documents[0].text.startswith("Rejected")


def test_identical_files_share_extraction_but_not_source_identity(setup):
    workspace, settings, source = setup
    (source.parent / "duplicate.txt").write_bytes(source.read_bytes())
    summary = pipeline.ingest_workspace(workspace, settings)
    assert summary.extractions_performed == 1
    assert summary.extractions_reused == 1
    assert len({item.id for item in summary.documents}) == 2
    assert len({item.relative_path for item in summary.documents}) == 2


@pytest.mark.parametrize("invalidate", ["force", "revision", "corrupt"])
def test_cache_can_be_refreshed_and_recovers_from_corruption(
    setup, monkeypatch, invalidate
):
    workspace, settings, _ = setup
    pipeline.ingest_workspace(workspace, settings)
    if invalidate == "revision":
        monkeypatch.setattr(cache_module, "EXTRACTOR_REVISION", "next")
    if invalidate == "corrupt":
        next((workspace.artifacts / "extraction-cache").glob("*.json")).write_bytes(
            b"bad"
        )
    summary = pipeline.ingest_workspace(
        workspace, settings, force=invalidate == "force"
    )
    assert not summary.failures
    assert summary.extractions_performed == 1
    assert summary.extractions_reused == 0


def test_evidence_metadata_is_refreshed_even_when_text_is_cached(setup):
    workspace, settings, _ = setup
    pipeline.ingest_workspace(workspace, settings)

    class Association:
        document_role = "minutes"
        module_id = "board"
        source_id = "meeting"

        def model_dump(self, **kwargs):
            return {"document_role": self.document_role, "module_id": self.module_id}

    library = SimpleNamespace(associations_for=lambda *_: [Association()])
    summary = pipeline.ingest_workspace(workspace, settings, evidence_library=library)
    assert summary.extractions_reused == 1
    assert summary.documents[0].metadata["evidence"]["module_ids"] == ["board"]
    assert summary.root_outcomes[0].added_or_updated == 1


def test_source_modified_during_extraction_keeps_previous_artifact(setup, monkeypatch):
    workspace, settings, _source = setup
    first = pipeline.ingest_workspace(workspace, settings)
    artifact = first.artifact_directory / f"{first.documents[0].id}.json"
    original = artifact.read_bytes()

    def changing_extractor(path):
        path.write_text("changed during extraction", encoding="utf-8")
        return "stale result", {}

    monkeypatch.setitem(pipeline.EXTRACTORS, ".txt", changing_extractor)
    summary = pipeline.ingest_workspace(workspace, settings, force=True)
    assert len(summary.failures) == 1
    assert "source changed" in summary.failures[0].message
    assert artifact.read_bytes() == original
    assert summary.extractions_performed == 0


def test_missing_root_retains_records_and_cache(setup):
    workspace, settings, source = setup
    named = Workspace(
        workspace.name,
        workspace.description,
        workspace.documents,
        workspace.artifacts,
        workspace.collection,
        True,
        (SourceRoot("hp", source.parent),),
    )
    first = pipeline.ingest_workspace(named, settings)
    artifact = first.artifact_directory / f"{first.documents[0].id}.json"
    original = artifact.read_bytes()
    source.parent.rename(source.parent.with_name("disconnected"))
    second = pipeline.ingest_workspace(named, settings)
    assert second.root_outcomes[0].status == "unavailable"
    assert artifact.read_bytes() == original
    assert second.extractions_performed == second.extractions_reused == 0


def test_ka_entry_point_and_force_argument():
    import tomllib

    from knowledge_assistant.main import build_parser

    project = Path(__file__).parents[1] / "pyproject.toml"
    scripts = tomllib.loads(project.read_text(encoding="utf-8"))["project"]["scripts"]
    assert scripts["ka"] == scripts["knowledge-assistant"]
    assert build_parser().parse_args(["ingest", "--force"]).force
