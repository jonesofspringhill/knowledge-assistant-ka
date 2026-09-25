"""Markdown document extraction."""

from pathlib import Path

from knowledge_assistant.ingestion.extractors.text import extract_text


def extract_markdown(path: Path) -> tuple[str, dict[str, str | int | None]]:
    """Extract Markdown text and use its first level-one heading as a title."""
    text, metadata = extract_text(path)
    title = next(
        (line[2:].strip() for line in text.splitlines() if line.startswith("# ")),
        None,
    )
    return text, {**metadata, "title": title}
