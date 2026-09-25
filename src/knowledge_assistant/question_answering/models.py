"""Structured results for grounded question answering."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from knowledge_assistant.retrieval.models import SearchResult


class Citation(BaseModel):
    """A user-facing citation tied to one supplied retrieval result."""

    label: str
    source: str
    chunk_id: str
    document_id: str
    source_location: str


class QuestionAnswerResult(BaseModel):
    """Machine-usable answer result behind the human-readable CLI output."""

    question: str
    answer: str
    status: Literal["answered", "insufficient_evidence"]
    citations: list[Citation] = Field(default_factory=list)
    evidence: list[SearchResult] = Field(default_factory=list)
    uncertainty: str | None = None
    workspace: str
    model: str | None = None
    prompt_name: str | None = None
    prompt_checksum: str | None = None
    retrieval_parameters: dict[str, Any] = Field(default_factory=dict)
    context_budget_tokens: int = 0
    context_estimated_tokens: int = 0
    retrieval_latency_seconds: float = 0
    generation_latency_seconds: float = 0
    context_sources: list[Path] = Field(default_factory=list)
