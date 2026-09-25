"""Tests for document discovery, normalisation, and the ingest CLI."""

from email.message import EmailMessage
from pathlib import Path
from types import SimpleNamespace

import knowledge_assistant.main as main_module
from knowledge_assistant.config import DocumentSettings
from knowledge_assistant.ingestion.pipeline import (
    checksum,
    discover_documents,
    ingest_workspace,
)
from knowledge_assistant.main import main
from knowledge_assistant.managers.workspace_manager import SourceRoot, Workspace


def _settings() -> DocumentSettings:
    return DocumentSettings(
        include=["*.txt", "*.md"], exclude=["archive/"], recursive=True
    )


def _workspace(root: Path) -> Workspace:
    return Workspace(
        "example", "Example", root, root.parent / "artifacts", "example", True
    )


def test_discovery_is_recursive_and_ignores_unsupported_and_excluded(
    tmp_path: Path,
) -> None:
    (tmp_path / "nested").mkdir()
    (tmp_path / "archive").mkdir()
    (tmp_path / "note.txt").write_text("hello", encoding="utf-8")
    (tmp_path / "nested" / "readme.md").write_text("# Heading", encoding="utf-8")
    (tmp_path / "image.png").write_bytes(b"image")
    (tmp_path / "archive" / "old.txt").write_text("old", encoding="utf-8")

    discovered, ignored = discover_documents(tmp_path, _settings())

    assert [path.name for path in discovered] == ["readme.md", "note.txt"]
    assert ignored == [Path("image.png")]


def test_ingestion_normalises_documents_writes_artifacts_and_recovers(
    tmp_path: Path, monkeypatch
) -> None:
    (tmp_path / "note.txt").write_text("hello", encoding="utf-8")
    (tmp_path / "bad.md").write_text("bad", encoding="utf-8")
    monkeypatch.setitem(
        __import__(
            "knowledge_assistant.ingestion.pipeline", fromlist=["EXTRACTORS"]
        ).EXTRACTORS,
        ".md",
        lambda _path: (_ for _ in ()).throw(ValueError("invalid markdown")),
    )

    summary = ingest_workspace(_workspace(tmp_path), _settings())

    assert summary.succeeded == 1
    assert len(summary.failures) == 1
    document = summary.documents[0]
    assert document.text == "hello"
    assert document.checksum == checksum(tmp_path / "note.txt")
    assert summary.artifact_directory == tmp_path.parent / "artifacts" / "ingestion"
    assert (summary.artifact_directory / f"{document.id}.json").is_file()
    assert (summary.artifact_directory / "report.json").is_file()


def test_ingestion_preserves_named_source_root_provenance(tmp_path: Path) -> None:
    course = tmp_path / "course"
    evidence = tmp_path / "evidence"
    course.mkdir()
    evidence.mkdir()
    (course / "guide.txt").write_text("course", encoding="utf-8")
    (evidence / "guide.txt").write_text("evidence", encoding="utf-8")
    workspace = Workspace(
        "example",
        "Example",
        course,
        tmp_path / "artifacts",
        "example",
        True,
        (SourceRoot("course", course), SourceRoot("evidence", evidence)),
    )

    summary = ingest_workspace(workspace, _settings())

    assert {document.source_root for document in summary.documents} == {
        "course",
        "evidence",
    }
    assert {document.source_path for document in summary.documents} == {
        Path("course/guide.txt"),
        Path("evidence/guide.txt"),
    }
    assert len({document.id for document in summary.documents}) == 2


def test_ingestion_records_an_empty_pdf_as_a_non_fatal_failure(tmp_path: Path) -> None:
    (tmp_path / "note.txt").write_text("hello", encoding="utf-8")
    (tmp_path / "empty.pdf").write_bytes(b"")
    settings = DocumentSettings(include=["*.pdf", "*.txt"], exclude=[], recursive=True)

    summary = ingest_workspace(_workspace(tmp_path), settings)

    assert summary.succeeded == 1
    assert len(summary.failures) == 1
    assert summary.failures[0].relative_path == Path("empty.pdf")
    assert "Cannot read an empty file" in summary.failures[0].message


def test_ingestion_records_an_encrypted_pdf_as_a_non_fatal_failure(
    tmp_path: Path,
) -> None:
    from pypdf import PdfWriter

    encrypted = tmp_path / "encrypted.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    writer.encrypt("password")
    with encrypted.open("wb") as file:
        writer.write(file)
    settings = DocumentSettings(include=["*.pdf"], exclude=[], recursive=True)

    summary = ingest_workspace(_workspace(tmp_path), settings)

    assert summary.succeeded == 0
    assert len(summary.failures) == 1
    assert summary.failures[0].relative_path == Path("encrypted.pdf")
    assert "PDF is encrypted" in summary.failures[0].message


def test_markdown_extractor_returns_title_and_text(tmp_path: Path) -> None:
    from knowledge_assistant.ingestion.extractors.markdown import extract_markdown

    path = tmp_path / "note.md"
    path.write_text("# Title\n\nBody", encoding="utf-8")
    assert extract_markdown(path) == ("# Title\n\nBody", {"title": "Title"})


def test_eml_extractor_prefers_plain_text_and_excludes_attachments(
    tmp_path: Path,
) -> None:
    from knowledge_assistant.ingestion.extractors.eml import extract_eml

    message = EmailMessage()
    message["Subject"] = "Volunteer update"
    message["From"] = "Secretary <secretary@example.org>"
    message["To"] = "Trustees <trustees@example.org>"
    message["Date"] = "Tue, 1 Sep 2026 09:30:00 +0000"
    message.set_content("The volunteer interacted with the students.")
    message.add_alternative(
        "<p>The volunteer <strong>interacted</strong>.</p>", subtype="html"
    )
    message.add_attachment(b"not searchable", maintype="application", subtype="pdf")
    path = tmp_path / "message.eml"
    path.write_bytes(message.as_bytes())

    text, metadata = extract_eml(path)

    assert "Volunteer update" in text
    assert "interacted with the students" in text
    assert "not searchable" not in text
    assert metadata["title"] == "Volunteer update"
    assert metadata["author"] == "Secretary <secretary@example.org>"
    assert metadata["body_format"] == "plain"


def test_cli_ingest_reports_summary(tmp_path: Path, capsys) -> None:
    documents = tmp_path / "documents"
    documents.mkdir()
    (documents / "note.txt").write_text("hello", encoding="utf-8")
    config = tmp_path / "config.yaml"
    source = Path(__file__).parents[1] / "config" / "config.example.yaml"
    content = source.read_text(encoding="utf-8").replace(
        "path: ./knowledge", f"path: {documents.as_posix()}"
    )
    config.write_text(content, encoding="utf-8")

    assert main(["--config", str(config), "ingest", "--root", "documents"]) == 0
    output = capsys.readouterr().out
    assert "1 documents discovered" in output
    assert "Succeeded: 1" in output
    assert (
        str(tmp_path.parent / "workspaces" / "example" / "artifacts" / "ingestion")
        in output
    )


def test_cli_ingest_rejects_unknown_source_root(tmp_path: Path, capsys) -> None:
    config = tmp_path / "config" / "config.yaml"
    config.parent.mkdir()
    config.write_text(
        (Path(__file__).parents[1] / "config" / "config.example.yaml").read_text(
            encoding="utf-8"
        ),
        encoding="utf-8",
    )

    assert main(["--config", str(config), "ingest", "--root", "missing"]) == 2
    assert "unknown document source root" in capsys.readouterr().err
    assert not (tmp_path / "workspaces" / "example" / "artifacts").exists()


def test_cli_ingest_does_not_access_prompt_arguments(monkeypatch) -> None:
    class IngestArguments(SimpleNamespace):
        def __getattribute__(self, name: str):
            if name == "prompt_command":
                raise AssertionError("ingest command accessed prompt arguments")
            return super().__getattribute__(name)

    args = IngestArguments(
        command="ingest",
        config=Path(__file__).parents[1] / "config" / "config.example.yaml",
        env=Path(__file__).parents[1] / ".env",
    )
    parser = SimpleNamespace(parse_args=lambda _argv: args)
    monkeypatch.setattr(main_module, "build_parser", lambda: parser)
    monkeypatch.setattr(main_module, "_ingest", lambda received_args, _manager: 0)

    assert main_module.main(["ingest"]) == 0
