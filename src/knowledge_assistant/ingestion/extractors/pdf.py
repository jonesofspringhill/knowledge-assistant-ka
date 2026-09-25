"""PDF document extraction using pypdf."""

from pathlib import Path

from pypdf.errors import PyPdfError


def extract_pdf(path: Path) -> tuple[str, dict[str, str | int | None]]:
    """Extract available PDF text and standard document metadata."""
    try:
        from pypdf import PdfReader
    except ImportError as error:  # pragma: no cover
        raise RuntimeError("PDF support requires the 'pypdf' package") from error

    try:
        reader = PdfReader(path)
        if reader.is_encrypted:
            raise ValueError("PDF is encrypted and cannot be ingested")
        metadata = reader.metadata or {}
        return (
            "\n".join(page.extract_text() or "" for page in reader.pages),
            {
                "title": metadata.title,
                "author": metadata.author,
                "page_count": len(reader.pages),
            },
        )
    except PyPdfError as error:
        raise ValueError(f"Unable to read PDF: {error}") from error
