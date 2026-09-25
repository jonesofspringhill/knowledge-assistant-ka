"""Reusable extraction results, independent of source paths and evidence metadata."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections.abc import Callable
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, ValidationError

# Increment when extractor behaviour changes. Package versions also invalidate caches.
EXTRACTOR_REVISION = "1"
_PACKAGES = {".pdf": "pypdf", ".docx": "python-docx"}


def checksum(path: Path) -> str:
    """Hash source bytes without modifying them."""
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


class ExtractionRecord(BaseModel):
    """Only format-derived content is shared; source/evidence identities are rebuilt."""

    model_config = ConfigDict(extra="forbid")
    fingerprint: str
    checksum: str
    text: str
    metadata: dict[str, Any]


class ExtractionCache:
    """Reuse extraction by content hash; always verify source bytes on each run."""

    def __init__(self, directory: Path, *, force: bool = False) -> None:
        self.directory = directory
        self.force = force
        self.extracted = 0
        self.reused = 0

    def extract(
        self, path: Path, extractor: Callable[..., tuple[str, dict]]
    ) -> ExtractionRecord:
        """Return verified cached text, or extract and atomically cache it."""
        before = path.stat()
        digest = checksum(path)
        suffix = path.suffix.lower()
        package = _PACKAGES.get(suffix)
        try:
            dependency = version(package) if package else "stdlib"
        except PackageNotFoundError:
            dependency = "unavailable"
        fingerprint = f"{EXTRACTOR_REVISION}:{suffix}:{dependency}"
        key = hashlib.sha256(f"{fingerprint}:{digest}".encode()).hexdigest()
        target = self.directory / f"{key}.json"
        record = None
        if not self.force:
            try:
                candidate = ExtractionRecord.model_validate_json(
                    target.read_text(encoding="utf-8")
                )
                if (
                    candidate.fingerprint == fingerprint
                    and candidate.checksum == digest
                ):
                    record = candidate
            except (OSError, ValueError, ValidationError):
                pass
        cached = record is not None
        if record is None:
            text, metadata = extractor(path)
            record = ExtractionRecord(
                fingerprint=fingerprint, checksum=digest, text=text, metadata=metadata
            )
            # Do not associate extracted text with a hash of different source bytes.
            if checksum(path) != digest:
                raise ValueError("source changed during extraction; retry ingestion")
        after = path.stat()
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise ValueError("source changed during ingestion; retry ingestion")
        if cached:
            self.reused += 1
        else:
            self.directory.mkdir(parents=True, exist_ok=True)
            temporary: Path | None = None
            try:
                with tempfile.NamedTemporaryFile(
                    mode="w", encoding="utf-8", dir=self.directory, delete=False
                ) as output:
                    temporary = Path(output.name)
                    json.dump(record.model_dump(), output, ensure_ascii=False)
                os.replace(temporary, target)
            finally:
                if temporary is not None:
                    temporary.unlink(missing_ok=True)
            self.extracted += 1
        return record
