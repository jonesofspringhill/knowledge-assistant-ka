"""Application service for grounded single-question answering."""

from __future__ import annotations

import hashlib
import re
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal

from knowledge_assistant.config import (
    EmbeddingSettings,
    EnvironmentSettings,
    LLMSettings,
    QuestionAnsweringSettings,
    RetrievalSettings,
)
from knowledge_assistant.llm import (
    LLMInvocationError,
    TextGenerator,
    create_text_generator,
)
from knowledge_assistant.managers.prompt_manager import PromptManager
from knowledge_assistant.managers.workspace_manager import Workspace
from knowledge_assistant.question_answering.context import (
    ContextBudgetError,
    build_context,
)
from knowledge_assistant.question_answering.models import (
    Citation,
    QuestionAnswerResult,
)
from knowledge_assistant.retrieval.models import SearchResult
from knowledge_assistant.retrieval.pipeline import search_workspace


class QuestionAnsweringError(RuntimeError):
    """Raised for a user-actionable question-answering failure."""


_STATUS = re.compile(r"(?im)^\s*Status\s*:\s*(ANSWERED|INSUFFICIENT_EVIDENCE)\s*$")
_UNCERTAINTY = re.compile(
    r"(?ims)^\s*Uncertainty\s*:\s*(.*?)"
    r"(?=^\s*(?:Reasoning|Status|Answer|Evidence)\s*:|\Z)"
)
_NO_UNCERTAINTY = re.compile(
    r"(?is)^\s*(?:<none>|none|no uncertainty|n/?a)(?:\.|\s|$)"
)
_CONFLICT_EVIDENCE = re.compile(
    r"(?is)(?:"
    r"\b(?:different|conflicting|inconsistent|incompatible|superseded|older)\b"
    r".{0,100}\b(?:date|deadline|value|figure|amount|version|statement)\b"
    r"|\b(?:confirm|verify|clarify|check)\b"
    r".{0,80}\b(?:date|deadline|value|figure|amount)\b"
    r")"
)


def _structured_output(
    answer: str,
) -> tuple[Literal["answered", "insufficient_evidence"], str | None]:
    """Read exact fields requested by the versioned prompt, never free prose."""
    status_match = _STATUS.search(answer)
    status: Literal["answered", "insufficient_evidence"] = (
        "insufficient_evidence"
        if status_match and status_match.group(1) == "INSUFFICIENT_EVIDENCE"
        else "answered"  # Backward-compatible with pre-M2.4 prompt templates.
    )
    uncertainty_match = _UNCERTAINTY.search(answer)
    uncertainty = uncertainty_match.group(1).strip() if uncertainty_match else ""
    if not uncertainty or _NO_UNCERTAINTY.match(uncertainty):
        uncertainty = ""
    return status, uncertainty or None


def _apply_conflict_evidence_guard(
    answer: str,
    status: Literal["answered", "insufficient_evidence"],
    uncertainty: str | None,
    evidence: list[SearchResult],
) -> tuple[str, Literal["answered", "insufficient_evidence"], str | None]:
    """Prevent an unqualified answer when supplied evidence requires confirmation.

    This deliberately narrow check is a final safety net for explicit retrieval
    evidence such as "confirm the deadline" or "an older form gives a different
    date".  The model remains responsible for ordinary evidence assessment.
    """
    if status != "answered" or uncertainty:
        return answer, status, uncertainty
    labels = [
        f"[S{index}]"
        for index, item in enumerate(evidence, 1)
        if _CONFLICT_EVIDENCE.search(item.text)
    ]
    if not labels:
        return answer, status, uncertainty
    cited = " ".join(labels)
    uncertainty = (
        "The supplied evidence explicitly describes a differing or unconfirmed "
        "value."
    )
    guarded_answer = (
        "Status: INSUFFICIENT_EVIDENCE\n\n"
        "Answer:\nThe supplied evidence does not establish an authoritative "
        f"answer because it records a differing or unconfirmed value {cited}.\n\n"
        f"Evidence:\n{cited}\n\n"
        f"Uncertainty:\n{uncertainty}\n\n"
        "Reasoning:\nAn evidence-conflict safeguard prevented a single value "
        "from being presented as authoritative."
    )
    return (
        guarded_answer,
        "insufficient_evidence",
        uncertainty,
    )


def answer_question(
    workspace: Workspace,
    chroma_directory: Path,
    retrieval_settings: RetrievalSettings,
    embedding_settings: EmbeddingSettings,
    llm_settings: LLMSettings,
    environment: EnvironmentSettings,
    prompt_manager: PromptManager,
    question: str,
    *,
    qa_settings: QuestionAnsweringSettings | None = None,
    top_k: int | None = None,
    threshold: float | None = None,
    filters: dict[str, Any] | None = None,
    embedder: Callable[[list[str]], list[list[float]]] | None = None,
    generator: TextGenerator | None = None,
    searcher: Callable[..., tuple[list[SearchResult], float]] = search_workspace,
) -> QuestionAnswerResult:
    """Retrieve evidence and generate one grounded answer."""
    question = question.strip()
    if not question:
        raise QuestionAnsweringError("question must not be empty")
    if top_k is not None and top_k <= 0:
        raise QuestionAnsweringError("top-k must be greater than zero")
    if threshold is not None and not 0 <= threshold <= 1:
        raise QuestionAnsweringError("threshold must be between 0 and 1")
    settings = qa_settings or QuestionAnsweringSettings()
    effective_top_k = top_k or retrieval_settings.top_k
    effective_threshold = (
        retrieval_settings.similarity_threshold if threshold is None else threshold
    )
    try:
        results, retrieval_latency = searcher(
            workspace,
            chroma_directory,
            retrieval_settings,
            embedding_settings,
            question,
            top_k=top_k,
            threshold=threshold,
            filters=filters,
            embedder=embedder,
        )
    except Exception as error:
        raise QuestionAnsweringError(f"Unable to retrieve evidence: {error}") from error

    parameters = {
        "top_k": effective_top_k,
        "threshold": effective_threshold,
        "filters": filters or {},
    }
    base = {
        "question": question,
        "workspace": workspace.name,
        "retrieval_parameters": parameters,
        "context_budget_tokens": settings.max_context_tokens
        - settings.reserved_output_tokens,
        "retrieval_latency_seconds": retrieval_latency,
    }
    if not results:
        return QuestionAnswerResult(
            answer="The available evidence is insufficient to answer this question reliably.",
            status="insufficient_evidence",
            uncertainty="No evidence matched the effective retrieval filters and threshold.",
            **base,
        )

    prompt_name = settings.prompt_name
    try:
        template = prompt_manager.get(prompt_name)
        selection = build_context(
            question,
            results,
            template,
            max_context_tokens=settings.max_context_tokens,
            reserved_output_tokens=settings.reserved_output_tokens,
        )
    except (ContextBudgetError, KeyError, RuntimeError) as error:
        raise QuestionAnsweringError(
            f"Unable to construct answer context: {error}"
        ) from error

    prompt = template.format(
        question=question,
        context=selection.context,
        sources="\n".join(selection.sources),
    )
    generation_started = time.monotonic()
    try:
        model = generator or create_text_generator(llm_settings, environment)
        answer = model.generate(prompt)
    except LLMInvocationError as error:
        raise QuestionAnsweringError(str(error)) from error
    generation_latency = time.monotonic() - generation_started
    status, uncertainty = _structured_output(answer)
    answer, status, uncertainty = _apply_conflict_evidence_guard(
        answer, status, uncertainty, list(selection.evidence)
    )
    citations = [
        Citation(
            label=f"S{index}",
            source=selection.sources[index - 1].removeprefix(f"[S{index}] "),
            chunk_id=result.chunk_id,
            document_id=result.document_id,
            source_location=result.source_location,
        )
        for index, result in enumerate(selection.evidence, 1)
    ]
    return QuestionAnswerResult(
        answer=answer,
        status=status,
        evidence=list(selection.evidence),
        citations=citations,
        model=getattr(model, "model", llm_settings.model),
        prompt_name=prompt_name,
        prompt_checksum=hashlib.sha256(template.encode()).hexdigest(),
        context_estimated_tokens=selection.estimated_tokens,
        generation_latency_seconds=generation_latency,
        context_sources=[result.source_path for result in selection.evidence],
        uncertainty=uncertainty,
        **base,
    )
