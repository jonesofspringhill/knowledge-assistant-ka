"""Tests for portable workspace setup and pipeline utilities."""

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from knowledge_assistant.utilities import (
    WorkspaceUtilityError,
    create_workspace,
    parse_document_root,
    run_workspace_pipeline,
)


def _config(tmp_path: Path) -> Path:
    destination = tmp_path / "config" / "config.yaml"
    destination.parent.mkdir()
    source = Path(__file__).parents[1] / "config" / "config.example.yaml"
    destination.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    return destination


def _script(name: str):
    path = Path(__file__).parents[1] / "scripts" / name
    spec = importlib.util.spec_from_file_location(name.removesuffix(".py"), path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_parse_document_root_requires_a_name_and_path() -> None:
    assert parse_document_root("evidence=D:/nutrition/pdf") == (
        "evidence",
        Path("D:/nutrition/pdf"),
    )
    with pytest.raises(WorkspaceUtilityError, match="name=path"):
        parse_document_root("evidence")


def test_scripts_return_non_zero_for_invalid_requests() -> None:
    create = _script("create_workspace.py")
    pipeline = _script("run_workspace_pipeline.py")

    assert create.main(["demo", "--document-root", "source=D:/docs"]) == 2
    assert pipeline.main(["missing", "--config", "does-not-exist.yaml"]) == 2


def test_create_workspace_requires_confirmation_and_writes_canonical_roots(
    tmp_path: Path,
) -> None:
    config = _config(tmp_path)
    course = tmp_path / "sources" / "course"
    evidence = tmp_path / "sources" / "evidence"
    with pytest.raises(WorkspaceUtilityError, match="--yes"):
        create_workspace(config, "nutrition", [("course", course)])

    artifacts = create_workspace(
        config,
        "nutrition",
        [("course", course), ("evidence", evidence)],
        description="Nutrition evidence library",
        confirm=True,
    )

    raw = yaml.safe_load(config.read_text(encoding="utf-8"))
    workspace = raw["workspaces"]["nutrition"]
    assert workspace["documents"]["unavailable_root"] == "warn"
    assert [root["name"] for root in workspace["documents"]["roots"]] == [
        "course",
        "evidence",
    ]
    assert artifacts.is_dir()
    assert not course.exists()
    assert not evidence.exists()


def test_create_workspace_validates_overlapping_roots_before_writing(
    tmp_path: Path,
) -> None:
    config = _config(tmp_path)
    original = config.read_text(encoding="utf-8")
    with pytest.raises(WorkspaceUtilityError, match="overlap"):
        create_workspace(
            config,
            "nutrition",
            [("all", tmp_path / "sources"), ("nested", tmp_path / "sources" / "pdf")],
            confirm=True,
        )
    assert config.read_text(encoding="utf-8") == original


def test_run_workspace_pipeline_orders_stages_and_stops_on_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = _config(tmp_path)
    calls: list[str] = []
    artifacts = tmp_path / "artifacts"

    def ingest(*_args, **kwargs):
        calls.append(f"ingest:{kwargs['roots']}")
        outcome = SimpleNamespace(added_or_updated=1, retained=2, failed=0, removed=0)
        return SimpleNamespace(
            failures=[],
            root_outcomes=[outcome],
            artifact_directory=artifacts / "ingestion",
        )

    def chunk(*_args):
        calls.append("chunk")
        return SimpleNamespace(
            failures=[],
            chunks_removed=0,
            artifact_directory=artifacts / "chunks",
        )

    def embed(*_args, **_kwargs):
        calls.append("embed")
        return SimpleNamespace(
            failures=[],
            embeddings_removed=0,
            artifact_directory=artifacts / "embeddings",
        )

    def index(*_args, **kwargs):
        calls.append(f"index:{kwargs['rebuild']}")
        return SimpleNamespace(failures=[], index_size=3, deleted=0)

    import knowledge_assistant.utilities.workspaces as utilities

    monkeypatch.setattr(utilities, "ingest_workspace", ingest)
    monkeypatch.setattr(utilities, "chunk_workspace", chunk)
    monkeypatch.setattr(utilities, "generate_embeddings", embed)
    monkeypatch.setattr(utilities, "index_workspace", index)
    monkeypatch.setattr(utilities, "verify_index", lambda *_args: (True, 3, 3))

    summary = run_workspace_pipeline(
        config, None, "example", root="documents", rebuild_index=True
    )

    assert calls == ["ingest:{'documents'}", "chunk", "embed", "index:True"]
    assert summary.index_size == 3
    assert summary.scope == "documents"
    assert summary.added_or_updated == 1
    assert summary.retained == 2

    monkeypatch.setattr(
        utilities,
        "ingest_workspace",
        lambda *_args, **_kwargs: SimpleNamespace(
            failures=[
                SimpleNamespace(
                    source_root="documents",
                    relative_path=Path("bad.txt"),
                    message="failure",
                )
            ]
        ),
    )
    with pytest.raises(WorkspaceUtilityError, match="ingestion") as error:
        run_workspace_pipeline(config, None, "example")
    assert error.value.exit_code == 1


def test_pipeline_index_mismatch_and_script_exit_codes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    config = _config(tmp_path)
    artifacts = tmp_path / "artifacts"
    outcome = SimpleNamespace(
        name="documents",
        path=tmp_path / "documents",
        status="scanned",
        discovered=1,
        processed=1,
        failed=0,
        added_or_updated=1,
        retained=0,
        removed=0,
    )
    ingestion = SimpleNamespace(
        failures=[], root_outcomes=[outcome], artifact_directory=artifacts / "ingestion"
    )
    chunking = SimpleNamespace(
        failures=[], chunks_removed=0, artifact_directory=artifacts / "chunks"
    )
    embeddings = SimpleNamespace(
        failures=[], embeddings_removed=0, artifact_directory=artifacts / "embeddings"
    )
    indexing = SimpleNamespace(failures=[], deleted=0, index_size=1)

    import knowledge_assistant.utilities.workspaces as utilities

    monkeypatch.setattr(
        utilities, "ingest_workspace", lambda *_args, **_kwargs: ingestion
    )
    monkeypatch.setattr(utilities, "chunk_workspace", lambda *_args: chunking)
    monkeypatch.setattr(
        utilities, "generate_embeddings", lambda *_args, **_kwargs: embeddings
    )
    monkeypatch.setattr(
        utilities, "index_workspace", lambda *_args, **_kwargs: indexing
    )
    monkeypatch.setattr(utilities, "verify_index", lambda *_args: (False, 1, 0))

    with pytest.raises(WorkspaceUtilityError, match="expected 1 vectors") as error:
        run_workspace_pipeline(config, None, "example")
    assert error.value.exit_code == 1

    script = _script("run_workspace_pipeline.py")
    unavailable = SimpleNamespace(
        **{
            **vars(outcome),
            "status": "unavailable",
            "retained": 1,
            "added_or_updated": 0,
        }
    )
    script_summary = SimpleNamespace(
        workspace="example",
        scope="all",
        root_outcomes=[unavailable],
        added_or_updated=0,
        retained=1,
        failed=0,
        documents_removed=0,
        ingestion_artifacts=artifacts / "ingestion",
        chunk_artifacts=artifacts / "chunks",
        embedding_artifacts=artifacts / "embeddings",
        chunks_removed=0,
        embeddings_removed=0,
        vectors_removed=0,
        index_size=1,
    )
    monkeypatch.setattr(
        script, "run_workspace_pipeline", lambda *_args, **_kwargs: script_summary
    )
    assert script.main(["example", "--config", str(config)]) == 0
    output = capsys.readouterr()
    assert "UNAVAILABLE" in output.out
    assert "WARNING" in output.err

    monkeypatch.setattr(
        script,
        "run_workspace_pipeline",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            WorkspaceUtilityError("unsafe request", exit_code=2)
        ),
    )
    assert script.main(["example", "--config", str(config)]) == 2
    assert "unsafe request" in capsys.readouterr().err
