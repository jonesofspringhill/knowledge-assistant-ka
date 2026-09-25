"""Bounded, provenance-preserving context construction."""

from __future__ import annotations

import math
from dataclasses import dataclass

from knowledge_assistant.retrieval.models import SearchResult


class ContextBudgetError(ValueError):
    """Raised when the configured budget cannot hold any complete evidence item."""


@dataclass(frozen=True, slots=True)
class ContextSelection:
    """Selected evidence and diagnostics for one model invocation."""

    evidence: tuple[SearchResult, ...]
    context: str
    sources: tuple[str, ...]
    estimated_tokens: int
    budget_tokens: int
    truncated: bool = False


def estimate_tokens(text: str) -> int:
    """Conservatively estimate tokens using four characters per token."""
    return max(1, math.ceil(len(text) / 4)) if text else 0


def citation_source(result: SearchResult) -> str:
    """Build a stable citation identity without exposing an absolute path."""
    source = result.document_title or result.source_filename or result.document_id
    details: list[str] = []
    if result.section_title:
        details.append(result.section_title)
    if result.page is not None:
        details.append(f"page {result.page}")
    if result.source_root != "default" or not result.document_title:
        details.append(result.source_location)
    return f"{source} ({'; '.join(details)})" if details else source


def build_context(
    question: str,
    evidence: list[SearchResult],
    prompt_template: str,
    *,
    max_context_tokens: int,
    reserved_output_tokens: int,
) -> ContextSelection:
    """Select ranked whole chunks that fit the complete prompt budget."""
    available = max_context_tokens - reserved_output_tokens
    if available <= 0:
        raise ContextBudgetError(
            "reserved output allowance consumes the context budget"
        )

    selected: list[SearchResult] = []
    blocks: list[str] = []
    sources: list[str] = []
    seen_text: set[str] = set()
    source_counts: dict[str, int] = {}
    for item in evidence:
        base_source = citation_source(item)
        source_counts[base_source] = source_counts.get(base_source, 0) + 1
    for result in evidence:
        if not result.text.strip() or result.text in seen_text:
            continue
        source = citation_source(result)
        if source_counts[source] > 1:
            source = f"{source} ({result.source_location})"
        label = f"S{len(selected) + 1}"
        candidate_block = f"[{label}] {source}\n{result.text.strip()}"
        candidate_blocks = blocks + [candidate_block]
        candidate_sources = sources + [f"[{label}] {source}"]
        candidate_prompt = _render(
            prompt_template,
            question=question,
            context="\n\n".join(candidate_blocks),
            sources="\n".join(candidate_sources),
        )
        if estimate_tokens(candidate_prompt) > available:
            break
        selected.append(result)
        blocks = candidate_blocks
        sources = candidate_sources
        seen_text.add(result.text)

    if not selected:
        raise ContextBudgetError(
            "the context budget is too small to include a complete evidence chunk"
        )
    rendered = _render(
        prompt_template,
        question=question,
        context="\n\n".join(blocks),
        sources="\n".join(sources),
    )
    return ContextSelection(
        evidence=tuple(selected),
        context="\n\n".join(blocks),
        sources=tuple(sources),
        estimated_tokens=estimate_tokens(rendered),
        budget_tokens=available,
        truncated=len(selected) < len([item for item in evidence if item.text.strip()]),
    )


def _render(template: str, *, question: str, context: str, sources: str) -> str:
    try:
        return template.format(question=question, context=context, sources=sources)
    except KeyError as error:
        raise ContextBudgetError(
            f"question-answer prompt has unsupported variable: {error.args[0]}"
        ) from error
