"""Microsoft Word document extraction using python-docx."""

from pathlib import Path


def extract_docx(path: Path) -> tuple[str, dict[str, str | int | None]]:
    """Extract paragraph text and core Word-document properties."""
    try:
        from docx import Document as WordDocument
    except ImportError as error:  # pragma: no cover
        raise RuntimeError("DOCX support requires the 'python-docx' package") from error

    document = WordDocument(path)
    properties = document.core_properties
    return "\n".join(paragraph.text for paragraph in document.paragraphs), {
        "title": properties.title or None,
        "author": properties.author or None,
    }
