"""Tests for structure-aware document chunking and its CLI command."""

from datetime import UTC, datetime
from pathlib import Path

from knowledge_assistant.chunking.pipeline import _chunk_document, chunk_workspace
from knowledge_assistant.config import ChunkingSettings
from knowledge_assistant.ingestion.models import Document
from knowledge_assistant.main import main
from knowledge_assistant.managers.workspace_manager import Workspace


def _settings(size: int = 30, minimum_size: int = 10) -> ChunkingSettings:
    return ChunkingSettings(
        size=size,
        maximum_size=size,
        minimum_size=minimum_size,
        overlap=0,
        strategy="section",
        detect_headings=True,
    )


def _document(text: str, **overrides: object) -> Document:
    values: dict[str, object] = {
        "id": "document-1",
        "checksum": "checksum",
        "filename": "guide.md",
        "relative_path": Path("guides/guide.md"),
        "workspace": "example",
        "file_type": "md",
        "file_size": len(text),
        "created_at": datetime.now(UTC),
        "modified_at": datetime.now(UTC),
        "title": "Guide",
        "text": text,
        "metadata": {"author": "Ada", "page": 2},
    }
    values.update(overrides)
    return Document.model_validate(values)


def test_chunking_preserves_heading_hierarchy_and_paragraphs() -> None:
    document = _document(
        "# Introduction\n\nFirst paragraph stays together.\n\n"
        "## Details\n\nSecond paragraph stays together."
    )

    chunks = _chunk_document(document, _settings(size=30, minimum_size=20))

    assert len(chunks) == 1
    assert "Introduction" in chunks[0].text
    assert "Introduction > Details" in chunks[0].text
    assert "First paragraph stays together.\n\nIntroduction > Details" in chunks[0].text


def test_oversized_sections_split_at_paragraph_boundaries_and_obey_size() -> None:
    paragraphs = [" ".join([f"paragraph{number}"] * 10) for number in range(3)]
    chunks = _chunk_document(
        _document("# Topic\n\n" + "\n\n".join(paragraphs)), _settings()
    )

    assert len(chunks) == 2
    assert all(chunk.word_count <= 30 for chunk in chunks)
    assert "paragraph0" in chunks[0].text
    assert "paragraph1" in chunks[0].text
    assert "paragraph2" in chunks[1].text


def test_chunking_propagates_metadata_and_provenance() -> None:
    chunk = _chunk_document(_document("# Topic\n\nUseful context."), _settings())[0]

    assert chunk.document_id == "document-1"
    assert chunk.workspace == "example"
    assert chunk.relative_path == Path("guides/guide.md")
    assert chunk.source_root == "default"
    assert chunk.source_path == Path("default/guides/guide.md")
    assert chunk.page == 2
    assert chunk.checksum == "checksum"
    assert chunk.metadata == {"author": "Ada", "page": 2}
    assert chunk.chunk_index == chunk.chunk_count == 1
    assert chunk.heading_level == 1
    assert chunk.chunk_quality == "complete"


def test_chunking_infers_standalone_title_case_headings() -> None:
    chunks = _chunk_document(
        _document("\nMeeting Decisions\n\nThe committee approved the budget."),
        _settings(),
    )

    assert chunks[0].section_title == "Meeting Decisions"
    assert "Meeting Decisions" in chunks[0].text


def test_chunk_workspace_recovers_from_invalid_and_cross_workspace_artefacts(
    tmp_path: Path,
) -> None:
    workspace = Workspace(
        "example",
        "Example",
        tmp_path / "documents",
        tmp_path / "artifacts",
        "example",
        True,
    )
    ingestion = workspace.artifacts / "ingestion"
    ingestion.mkdir(parents=True)
    (ingestion / "valid.json").write_text(
        _document("# Topic\n\nUseful context.").model_dump_json(), encoding="utf-8"
    )
    (ingestion / "invalid.json").write_text("not json", encoding="utf-8")
    (ingestion / "other.json").write_text(
        _document("other", workspace="other").model_dump_json(), encoding="utf-8"
    )

    summary = chunk_workspace(workspace, _settings())

    assert summary.documents_processed == 1
    assert summary.chunks_created == 1
    assert len(summary.failures) == 2
    assert (workspace.artifacts / "chunks" / "report.json").is_file()


def test_chunk_cli_reports_statistics(tmp_path: Path, capsys) -> None:
    source = Path(__file__).parents[1] / "config" / "config.example.yaml"
    config = tmp_path / "config" / "config.yaml"
    config.parent.mkdir()
    config.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    ingestion = tmp_path / "workspaces" / "example" / "artifacts" / "ingestion"
    ingestion.mkdir(parents=True)
    (ingestion / "document.json").write_text(
        _document("# Topic\n\nUseful context.").model_dump_json(), encoding="utf-8"
    )

    assert main(["--config", str(config), "chunk"]) == 0
    output = capsys.readouterr().out
    assert "1 documents loaded" in output
    assert "1 chunks created" in output
    assert "Headings detected: 1" in output
    assert str(tmp_path / "workspaces" / "example" / "artifacts" / "chunks") in output
