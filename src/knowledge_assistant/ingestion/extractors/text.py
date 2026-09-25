"""Plain-text document extraction."""

from pathlib import Path


def extract_text(path: Path) -> tuple[str, dict[str, str | int | None]]:
    """Extract UTF-8 text, accepting a byte-order mark when present."""
    return path.read_text(encoding="utf-8-sig"), {}
