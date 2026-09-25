"""Normalised models produced by the document-ingestion pipeline."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field


class Document(BaseModel):
    """A source document represented independently of its original format."""

    model_config = ConfigDict(frozen=True)

    id: str
    checksum: str
    filename: str
    relative_path: Path
    workspace: str
    source_root: str = "default"
    file_type: str
    file_size: int = Field(ge=0)
    created_at: datetime
    modified_at: datetime
    title: str | None = None
    author: str | None = None
    page_count: int | None = Field(default=None, ge=0)
    text: str
    metadata: dict[str, Any] = Field(default_factory=dict)

    @computed_field
    @property
    def source_path(self) -> Path:
        """Return the stable, root-qualified provenance path."""
        return Path(self.source_root) / self.relative_path


class IngestionFailure(BaseModel):
    """A non-fatal failure encountered while importing one document."""

    relative_path: Path
    message: str
    source_root: str = "default"


class RootOutcome(BaseModel):
    """Structured result for one configured source root in an ingestion run."""

    name: str
    path: Path
    selected: bool
    status: Literal["unselected", "scanned", "unavailable", "failed"]
    discovered: int = Field(default=0, ge=0)
    processed: int = Field(default=0, ge=0)
    failed: int = Field(default=0, ge=0)
    added_or_updated: int = Field(default=0, ge=0)
    retained: int = Field(default=0, ge=0)
    removed: int = Field(default=0, ge=0)
    message: str | None = None


class IngestionSummary(BaseModel):
    """The outcome of one workspace ingestion run."""

    workspace: str
    discovered: int
    processed: int
    documents: list[Document]
    failures: list[IngestionFailure]
    ignored: list[Path]
    root_outcomes: list[RootOutcome] = Field(default_factory=list)
    artifact_directory: Path
    elapsed_seconds: float = Field(ge=0)
    extractions_performed: int = Field(default=0, ge=0)
    extractions_reused: int = Field(default=0, ge=0)

    @property
    def succeeded(self) -> int:
        """Return the number of documents successfully normalised."""
        return len(self.documents)


class Chunk(BaseModel):
    """A retrievable, provenance-preserving part of an ingested document."""

    chunk_id: str
    document_id: str
    workspace: str
    document_title: str | None = None
    section_title: str | None = None
    chunk_index: int = Field(ge=1)
    chunk_count: int = Field(ge=1)
    source_filename: str
    relative_path: Path
    source_root: str = "default"
    page: int | None = Field(default=None, ge=1)
    heading_level: int | None = Field(default=None, ge=1)
    parent_section: str | None = None
    chunk_quality: str = "complete"
    checksum: str
    text: str
    metadata: dict[str, Any] = Field(default_factory=dict)

    @computed_field
    @property
    def source_path(self) -> Path:
        """Return the stable, root-qualified provenance path."""
        return Path(self.source_root) / self.relative_path

    @property
    def word_count(self) -> int:
        """Return a portable approximation of chunk size for reporting."""
        return len(self.text.split())


class ChunkingFailure(BaseModel):
    """A non-fatal failure while turning an ingestion artefact into chunks."""

    artifact: Path
    message: str


class ChunkingSummary(BaseModel):
    """The outcome of chunking all ingestion artefacts in one workspace."""

    workspace: str
    documents_processed: int
    chunks: list[Chunk]
    failures: list[ChunkingFailure]
    artifact_directory: Path
    elapsed_seconds: float = Field(ge=0)
    headings_detected: int = Field(default=0, ge=0)
    paragraph_splits: int = Field(default=0, ge=0)
    sentence_splits: int = Field(default=0, ge=0)
    forced_token_splits: int = Field(default=0, ge=0)
    chunks_removed: int = Field(default=0, ge=0)

    @property
    def chunks_created(self) -> int:
        return len(self.chunks)

    @property
    def average_size(self) -> float:
        return (
            sum(chunk.word_count for chunk in self.chunks) / len(self.chunks)
            if self.chunks
            else 0
        )

    @property
    def largest_size(self) -> int:
        return max((chunk.word_count for chunk in self.chunks), default=0)

    @property
    def smallest_size(self) -> int:
        return min((chunk.word_count for chunk in self.chunks), default=0)
