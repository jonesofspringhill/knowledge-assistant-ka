"""Structure-aware, provenance-preserving document chunking."""

from __future__ import annotations

import json
import re
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from knowledge_assistant.config import ChunkingSettings
from knowledge_assistant.ingestion.models import (
    Chunk,
    ChunkingFailure,
    ChunkingSummary,
    Document,
)
from knowledge_assistant.managers.workspace_manager import Workspace

_HEADING = re.compile(r"^(#{1,6})\s+(.+?)(?:\s+#+)?\s*$")
_PARAGRAPHS = re.compile(r"\n\s*\n")
_SENTENCES = re.compile(r"(?<=[.!?])\s+")
_INFERRED_HEADING = re.compile(
    r"^(?:\d+(?:\.\d+)*[.)]?\s+)?[A-Z][A-Za-z0-9 ,&:/()'-]{2,80}[?]?$"
)


@dataclass(frozen=True)
class _Section:
    title: str | None
    text: str
    heading_level: int | None = None
    parent_section: str | None = None


@dataclass
class _Statistics:
    headings_detected: int = 0
    paragraph_splits: int = 0
    sentence_splits: int = 0
    forced_token_splits: int = 0


def chunk_workspace(
    workspace: Workspace, settings: ChunkingSettings
) -> ChunkingSummary:
    """Convert a workspace's ingestion artefacts into inspectable chunk artefacts."""
    started = time.monotonic()
    source = workspace.artifacts / "ingestion"
    output = workspace.artifacts / "chunks"
    documents, failures = _read_documents(source, workspace.name)
    chunks: list[Chunk] = []
    statistics = _Statistics()
    for document in documents:
        try:
            chunks.extend(_chunk_document(document, settings, statistics))
        except (ValueError, TypeError) as error:
            failures.append(
                ChunkingFailure(artifact=document.relative_path, message=str(error))
            )
    removed = _write_artifacts(output, chunks, failures)
    return ChunkingSummary(
        workspace=workspace.name,
        documents_processed=len(documents),
        chunks=chunks,
        failures=failures,
        artifact_directory=output,
        elapsed_seconds=time.monotonic() - started,
        headings_detected=statistics.headings_detected,
        paragraph_splits=statistics.paragraph_splits,
        sentence_splits=statistics.sentence_splits,
        forced_token_splits=statistics.forced_token_splits,
        chunks_removed=removed,
    )


def _read_documents(
    directory: Path, workspace_name: str
) -> tuple[list[Document], list[ChunkingFailure]]:
    """Load individual document artefacts, retaining invalid artefacts as failures."""
    if not directory.is_dir():
        raise FileNotFoundError(
            f"Ingestion artefact directory does not exist: {directory}"
        )
    documents: list[Document] = []
    failures: list[ChunkingFailure] = []
    for path in sorted(directory.glob("*.json")):
        if path.name == "report.json":
            continue
        try:
            document = Document.model_validate_json(path.read_text(encoding="utf-8"))
            if document.workspace != workspace_name:
                raise ValueError(
                    f"Artefact belongs to workspace '{document.workspace}', not "
                    f"'{workspace_name}'"
                )
            documents.append(document)
        except (OSError, ValidationError, ValueError) as error:
            failures.append(ChunkingFailure(artifact=path.name, message=str(error)))
    return documents, failures


def _chunk_document(
    document: Document,
    settings: ChunkingSettings,
    statistics: _Statistics | None = None,
) -> list[Chunk]:
    statistics = statistics or _Statistics()
    sections = _sections(document, settings.detect_headings, statistics)
    parts = [
        part
        for section in sections
        for part in _split_section(section, settings.maximum_size, statistics)
    ]
    grouped = _merge_small_parts(parts, settings)
    total = len(grouped)
    return [
        Chunk(
            chunk_id=str(
                uuid.uuid5(uuid.NAMESPACE_URL, f"{document.id}:{index}:{text}")
            ),
            document_id=document.id,
            workspace=document.workspace,
            document_title=document.title,
            section_title=section_title,
            chunk_index=index,
            chunk_count=total,
            source_filename=document.filename,
            relative_path=document.relative_path,
            source_root=document.source_root,
            page=_page(document),
            heading_level=_heading_level(section_title),
            parent_section=_parent_section(section_title),
            chunk_quality=_chunk_quality(text),
            checksum=document.checksum,
            text=text,
            metadata=document.metadata,
        )
        for index, (section_title, text) in enumerate(grouped, start=1)
    ]


def _sections(
    document: Document, detect_headings: bool, statistics: _Statistics
) -> list[_Section]:
    """Recognise Markdown heading hierarchy; otherwise retain the whole document."""
    if not detect_headings:
        return (
            [_Section(document.title, document.text.strip())]
            if document.text.strip()
            else []
        )
    hierarchy: list[str] = []
    title: str | None = document.title
    body: list[str] = []
    sections: list[_Section] = []
    lines = document.text.splitlines()
    for index, line in enumerate(lines):
        match = _HEADING.match(line)
        inferred = detect_headings and not match and _is_inferred_heading(lines, index)
        if not match and not inferred:
            body.append(line)
            continue
        if body or title:
            text = "\n".join(body).strip()
            if text:
                sections.append(_Section(title, text))
        level = len(match.group(1)) if match else 1
        heading = match.group(2).strip() if match else line.strip()
        hierarchy = hierarchy[: level - 1] + [heading]
        title = " > ".join(hierarchy)
        statistics.headings_detected += 1
        body = []
    text = "\n".join(body).strip()
    if text:
        sections.append(_Section(title, text))
    return sections


def _render(title: str | None, text: str) -> str:
    return f"{title}\n\n{text}" if title else text


def _split_section(
    section: _Section, size: int, statistics: _Statistics
) -> list[_Section]:
    """Split only oversized sections, preferring paragraphs then sentences."""
    if len(_render(section.title, section.text).split()) <= size:
        return [section]
    maximum_body_words = max(1, size - len((section.title or "").split()))
    paragraphs = [
        paragraph.strip()
        for paragraph in _PARAGRAPHS.split(section.text)
        if paragraph.strip()
    ]
    parts: list[str] = []
    current: list[str] = []
    current_words = 0
    for paragraph in paragraphs:
        paragraph_parts = _split_paragraph(paragraph, maximum_body_words, statistics)
        if len(paragraph_parts) > 1:
            statistics.paragraph_splits += 1
        for part in paragraph_parts:
            words = len(part.split())
            if current and current_words + words > maximum_body_words:
                parts.append("\n\n".join(current))
                current, current_words = [], 0
            current.append(part)
            current_words += words
    if current:
        parts.append("\n\n".join(current))
    return [
        _Section(section.title, part, section.heading_level, section.parent_section)
        for part in parts
    ]


def _split_paragraph(paragraph: str, size: int, statistics: _Statistics) -> list[str]:
    if len(paragraph.split()) <= size:
        return [paragraph]
    sentences = _SENTENCES.split(paragraph)
    result: list[str] = []
    current: list[str] = []
    words = 0
    for sentence in sentences:
        sentence_words = sentence.split()
        if len(sentence_words) > size:
            if current:
                result.append(" ".join(current))
                current, words = [], 0
            result.extend(
                " ".join(sentence_words[index : index + size])
                for index in range(0, len(sentence_words), size)
            )
            statistics.forced_token_splits += 1
        elif current and words + len(sentence_words) > size:
            result.append(" ".join(current))
            current, words = [sentence], len(sentence_words)
            statistics.sentence_splits += 1
        else:
            current.append(sentence)
            words += len(sentence_words)
    if current:
        result.append(" ".join(current))
    return result


def _merge_small_parts(
    parts: list[_Section], settings: ChunkingSettings
) -> list[tuple[str | None, str]]:
    """Merge adjacent short sections only when their combined text fits the target."""
    chunks: list[tuple[list[str], list[str]]] = []
    for part in parts:
        title = part.title or ""
        rendered = _render(part.title, part.text)
        if chunks:
            titles, texts = chunks[-1]
            candidate = "\n\n".join([*texts, rendered])
            if (
                len(" ".join(texts).split()) < settings.minimum_size
                and len(candidate.split()) <= settings.size
            ):
                titles.append(title)
                texts.append(rendered)
                continue
        chunks.append(([title], [rendered]))
    return [
        (" > ".join(title for title in titles if title) or None, "\n\n".join(texts))
        for titles, texts in chunks
    ]


def _page(document: Document) -> int | None:
    page = document.metadata.get("page")
    return page if isinstance(page, int) and page > 0 else None


def _is_inferred_heading(lines: list[str], index: int) -> bool:
    line = lines[index].strip()
    return (
        bool(_INFERRED_HEADING.fullmatch(line))
        and len(line.split()) <= 12
        and (index == 0 or not lines[index - 1].strip())
        and (index == len(lines) - 1 or not lines[index + 1].strip())
    )


def _heading_level(section_title: str | None) -> int | None:
    return section_title.count(" > ") + 1 if section_title else None


def _parent_section(section_title: str | None) -> str | None:
    if not section_title or " > " not in section_title:
        return None
    return section_title.rsplit(" > ", 1)[0]


def _chunk_quality(text: str) -> str:
    return "complete" if text.rstrip().endswith((".", "!", "?", ":")) else "partial"


def _write_artifacts(
    directory: Path, chunks: list[Chunk], failures: list[ChunkingFailure]
) -> int:
    directory.mkdir(parents=True, exist_ok=True)
    for chunk in chunks:
        (directory / f"{chunk.chunk_id}.json").write_text(
            chunk.model_dump_json(indent=2) + "\n", encoding="utf-8"
        )
    removed = 0
    if not failures:
        active = {chunk.chunk_id for chunk in chunks}
        for path in directory.glob("*.json"):
            if path.name != "report.json" and path.stem not in active:
                path.unlink()
                removed += 1
    report = {
        "chunks_created": len(chunks),
        "chunks_removed": removed,
        "failed": len(failures),
        "failures": [failure.model_dump(mode="json") for failure in failures],
    }
    (directory / "report.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    return removed
