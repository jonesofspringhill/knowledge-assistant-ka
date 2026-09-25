"""Sequential execution and deterministic metrics for full-pipeline QA runs."""

from __future__ import annotations

import hashlib
import math
import platform
import re
import subprocess
import time
import uuid
from collections import Counter
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from statistics import fmean, median
from typing import Any

from knowledge_assistant.config import Settings
from knowledge_assistant.managers.prompt_manager import PromptManager
from knowledge_assistant.managers.workspace_manager import Workspace
from knowledge_assistant.qa_evaluation.benchmark import LoadedBenchmark
from knowledge_assistant.qa_evaluation.models import (
    AutomaticMetrics,
    CaseMeasures,
    CaseResult,
    CitationDiagnostics,
    EvidenceRecord,
    GateOutcome,
    LatencyStatistics,
    QACase,
    QARunReport,
    RateMetric,
    SourceExpectation,
)
from knowledge_assistant.question_answering.models import QuestionAnswerResult
from knowledge_assistant.question_answering.service import (
    QuestionAnsweringError,
    TextGenerator,
    answer_question,
)
from knowledge_assistant.retrieval.models import SearchResult
from knowledge_assistant.retrieval.pipeline import search_workspace

CITATION_PATTERN = re.compile(r"\[S(\d+)\]")
CONTROL_RECORD_TYPES = {
    "control",
    "control_metadata",
    "evidence_library_control",
    "policy",
    "manifest",
}


class RecordingSearcher:
    """Record the one retrieval operation performed through the M2.3 boundary."""

    def __init__(self, delegate: Callable[..., tuple[list[SearchResult], float]]):
        self.delegate = delegate
        self.calls = 0
        self.results: list[SearchResult] = []
        self.latency = 0.0

    def __call__(self, *args: Any, **kwargs: Any) -> tuple[list[SearchResult], float]:
        self.calls += 1
        results, latency = self.delegate(*args, **kwargs)
        self.results = list(results)
        self.latency = latency
        return results, latency


def run_qa_evaluation(
    loaded: LoadedBenchmark,
    workspace: Workspace,
    settings: Settings,
    *,
    run_kind: str,
    repeats: int = 1,
    repository_root: Path | None = None,
    answerer: Callable[..., QuestionAnswerResult] = answer_question,
    searcher: Callable[..., tuple[list[SearchResult], float]] = search_workspace,
    embedder: Callable[[list[str]], list[list[float]]] | None = None,
    generator: TextGenerator | None = None,
    progress: Callable[[int, int, CaseResult], None] | None = None,
) -> QARunReport:
    """Invoke M2.3 exactly once per case/repeat and retain privacy-safe evidence."""
    if run_kind not in {"baseline", "candidate"}:
        raise ValueError("run kind must be baseline or candidate")
    if repeats <= 0:
        raise ValueError("repeat count must be greater than zero")

    root = (repository_root or Path(__file__).resolve().parents[3]).resolve()
    prompt_manager = PromptManager(settings.prompts)
    prompt_name = settings.question_answering.prompt_name
    template = prompt_manager.get(prompt_name)
    prompt_checksum = hashlib.sha256(template.encode()).hexdigest()
    started = datetime.now(UTC)
    run_id = f"{started.strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"
    case_results: list[CaseResult] = []
    partial = False
    total = len(loaded.benchmark.cases) * repeats
    sequence = 0

    try:
        for repeat_index in range(1, repeats + 1):
            for case in loaded.benchmark.cases:
                sequence += 1
                outcome = _run_case(
                    case,
                    repeat_index,
                    workspace,
                    settings,
                    prompt_manager,
                    answerer=answerer,
                    searcher=searcher,
                    embedder=embedder,
                    generator=generator,
                    repository_root=root,
                )
                case_results.append(outcome)
                if progress:
                    progress(sequence, total, outcome)
    except KeyboardInterrupt:
        if not case_results:
            raise
        partial = True

    finished = datetime.now(UTC)
    metrics = aggregate_metrics(case_results, settings.retrieval.top_k)
    return QARunReport(
        run_id=run_id,
        run_kind=run_kind,
        partial=partial,
        benchmark={
            "id": loaded.benchmark.benchmark_id,
            "version": loaded.benchmark.benchmark_version,
            "schema_version": loaded.benchmark.schema_version,
            "checksum": loaded.checksum,
            "path": _logical_path(loaded.path, root),
            "case_count": len(loaded.benchmark.cases),
        },
        application={
            "name": settings.application.name,
            "version": settings.application.version,
        },
        git=_git_record(root),
        environment={
            "python": platform.python_version(),
            "operating_system": platform.platform(),
        },
        workspace={"name": workspace.name, "collection": workspace.collection},
        embedding={
            "provider": settings.embedding.provider,
            "model": settings.embedding.model,
            "version": settings.embedding.version,
        },
        llm={
            "provider": settings.llm.provider,
            "configured_model": settings.llm.model,
            "reported_models": sorted(
                {case.model for case in case_results if case.model is not None}
            ),
        },
        prompt={"name": prompt_name, "checksum": prompt_checksum},
        retrieval={
            "top_k": settings.retrieval.top_k,
            "threshold": settings.retrieval.similarity_threshold,
            "filters": "per-case",
            "rerank": settings.retrieval.rerank,
            "cache_policy": settings.retrieval.cache_policy,
        },
        context={
            "maximum_tokens": settings.question_answering.max_context_tokens,
            "reserved_output_tokens": (
                settings.question_answering.reserved_output_tokens
            ),
            "effective_budget_tokens": (
                settings.question_answering.max_context_tokens
                - settings.question_answering.reserved_output_tokens
            ),
            "estimator": "characters_divided_by_four_ceiling_v1",
        },
        generation={
            "temperature": settings.llm.temperature,
            "top_p": settings.llm.top_p,
            "max_tokens": settings.llm.max_tokens,
            "timeout_seconds": settings.llm.timeout_seconds,
            "warm_up_status": "unknown",
        },
        repeats=repeats,
        started_at=started.isoformat(),
        finished_at=finished.isoformat(),
        cases=case_results,
        automatic_metrics=metrics,
        automatic_gates=automatic_gate_outcomes(metrics, case_results, partial),
    )


def _run_case(
    case: QACase,
    repeat_index: int,
    workspace: Workspace,
    settings: Settings,
    prompt_manager: PromptManager,
    *,
    answerer: Callable[..., QuestionAnswerResult],
    searcher: Callable[..., tuple[list[SearchResult], float]],
    embedder: Callable[[list[str]], list[list[float]]] | None,
    generator: TextGenerator | None,
    repository_root: Path,
) -> CaseResult:
    recorder = RecordingSearcher(searcher)
    started = time.monotonic()
    try:
        result = answerer(
            workspace,
            settings.chroma.directory,
            settings.retrieval,
            settings.embedding,
            settings.llm,
            settings.environment,
            prompt_manager,
            case.question,
            qa_settings=settings.question_answering,
            filters=case.filters,
            embedder=embedder,
            generator=generator,
            searcher=recorder,
        )
        if recorder.calls != 1:
            raise QuestionAnsweringError(
                f"expected one retrieval call, observed {recorder.calls}"
            )
        elapsed = time.monotonic() - started
        return _case_result(case, repeat_index, result, recorder.results, elapsed)
    except Exception as error:  # noqa: BLE001 - failures are per-case measurements.
        elapsed = time.monotonic() - started
        return CaseResult(
            case_id=case.id,
            repeat_index=repeat_index,
            category=case.category,
            answerability=case.answerability,
            question=case.question,
            filters=case.filters,
            expected_facts=case.expected_facts,
            forbidden_claims=case.forbidden_claims,
            review_notes=case.notes,
            status="operational_failure",
            answer="",
            model_invoked=False,
            operational_error=_safe_error(error, workspace, repository_root),
            citations=CitationDiagnostics(),
            measures=CaseMeasures(),
            retrieval_latency_seconds=recorder.latency,
            end_to_end_latency_seconds=elapsed,
        )


def _case_result(
    case: QACase,
    repeat_index: int,
    result: QuestionAnswerResult,
    ranked: list[SearchResult],
    elapsed: float,
) -> CaseResult:
    context_ids = {item.chunk_id for item in result.evidence}
    evidence = [
        EvidenceRecord(
            rank=rank,
            chunk_id=item.chunk_id,
            document_id=item.document_id,
            source_path=item.source_path.as_posix(),
            source_location=item.source_location,
            similarity=item.similarity,
            selected_for_context=item.chunk_id in context_ids,
            expectation_match=_expectation_match(item, case),
            control_metadata=_is_control_record(item),
        )
        for rank, item in enumerate(ranked, 1)
    ]
    relevant = [item.rank for item in evidence if item.expectation_match != "none"]
    relevant_rank = min(relevant) if relevant else None
    supplied = {citation.label: citation for citation in result.citations}
    by_chunk = {item.chunk_id: item for item in ranked}
    found = [f"S{number}" for number in CITATION_PATTERN.findall(result.answer)]
    counts = Counter(found)
    unique_found = list(dict.fromkeys(found))
    resolved = [label for label in unique_found if label in supplied]
    invalid = [label for label in unique_found if label not in supplied]
    correct_expected: list[str] = []
    correct_acceptable: list[str] = []
    for label in resolved:
        item = by_chunk.get(supplied[label].chunk_id)
        match = _expectation_match(item, case) if item else "none"
        if match == "expected":
            correct_expected.append(label)
        elif match == "acceptable":
            correct_acceptable.append(label)
    has_expectation = bool(case.expected_sources or case.acceptable_sources)
    answerable = case.answerability == "answerable"
    conflicting = case.answerability == "conflicting"
    diagnostics = CitationDiagnostics(
        labels_found=found,
        resolved_labels=resolved,
        invalid_labels=invalid,
        duplicate_labels=[label for label, count in counts.items() if count > 1],
        unused_supplied_labels=[
            label for label in supplied if label not in unique_found
        ],
        expected_source_labels=correct_expected,
        acceptable_source_labels=correct_acceptable,
    )
    measures = CaseMeasures(
        relevant_source_rank=relevant_rank,
        recall_at_5=(
            (relevant_rank is not None and relevant_rank <= 5)
            if has_expectation
            else None
        ),
        recall_at_10=(
            (relevant_rank is not None and relevant_rank <= 10)
            if has_expectation
            else None
        ),
        reciprocal_rank=(
            (1 / relevant_rank) if relevant_rank else (0 if has_expectation else None)
        ),
        expected_source_in_context=(
            any(
                item.selected_for_context and item.expectation_match != "none"
                for item in evidence
            )
            if answerable
            else None
        ),
        citation_valid_count=sum(label in supplied for label in found),
        citation_count=len(found),
        citation_correct_count=sum(
            label in set(correct_expected + correct_acceptable) for label in found
        ),
        citation_correct_denominator=(
            sum(label in supplied for label in found) if has_expectation else 0
        ),
        citation_present=bool(resolved) if answerable else None,
        answered=result.status == "answered" if answerable else None,
        abstained=(
            result.status == "insufficient_evidence"
            if case.answerability == "unanswerable"
            else None
        ),
        conflicting_uncertainty_present=(
            (
                result.status == "insufficient_evidence"
                or bool((result.uncertainty or "").strip())
            )
            if conflicting
            else None
        ),
    )
    return CaseResult(
        case_id=case.id,
        repeat_index=repeat_index,
        category=case.category,
        answerability=case.answerability,
        question=case.question,
        filters=case.filters,
        expected_facts=case.expected_facts,
        forbidden_claims=case.forbidden_claims,
        review_notes=case.notes,
        status=result.status,
        answer=result.answer,
        model=result.model,
        uncertainty=result.uncertainty,
        model_invoked=result.model is not None,
        evidence=evidence,
        context_sources=[path.as_posix() for path in result.context_sources],
        citations=diagnostics,
        measures=measures,
        retrieval_latency_seconds=result.retrieval_latency_seconds,
        generation_latency_seconds=result.generation_latency_seconds,
        end_to_end_latency_seconds=elapsed,
    )


def aggregate_metrics(cases: list[CaseResult], top_k: int) -> AutomaticMetrics:
    """Aggregate rates without converting empty denominators into success."""
    completed = [case for case in cases if case.status != "operational_failure"]
    relevant = [case for case in completed if case.measures.recall_at_5 is not None]
    answerable = [case for case in completed if case.answerability == "answerable"]
    unanswerable = [case for case in completed if case.answerability == "unanswerable"]
    conflicting = [case for case in completed if case.answerability == "conflicting"]
    citations = sum(case.measures.citation_count for case in completed)
    valid_citations = sum(case.measures.citation_valid_count for case in completed)
    correct_denominator = sum(
        case.measures.citation_correct_denominator for case in completed
    )
    correct_citations = sum(case.measures.citation_correct_count for case in completed)
    return AutomaticMetrics(
        recall_at_5=_boolean_rate(relevant, "recall_at_5"),
        recall_at_10=(
            _boolean_rate(relevant, "recall_at_10")
            if top_k >= 10
            else _not_applicable([case.case_id for case in relevant])
        ),
        mean_reciprocal_rank=_numeric_mean(
            [case.measures.reciprocal_rank for case in relevant],
            [case.case_id for case in cases if case not in relevant],
        ),
        expected_source_in_context=_boolean_rate(
            answerable, "expected_source_in_context"
        ),
        citation_validity=_rate(valid_citations, citations),
        citation_source_correctness=_rate(correct_citations, correct_denominator),
        citation_presence=_boolean_rate(answerable, "citation_present"),
        answerable_answer_rate=_boolean_rate(answerable, "answered"),
        unanswerable_abstention_accuracy=_boolean_rate(unanswerable, "abstained"),
        false_abstention_rate=_boolean_rate(answerable, "answered", invert=True),
        unsupported_answer_rate=_boolean_rate(unanswerable, "abstained", invert=True),
        conflicting_uncertainty_presence=_boolean_rate(
            conflicting, "conflicting_uncertainty_present"
        ),
        completion_rate=_rate(len(completed), len(cases)),
        operational_failures=len(cases) - len(completed),
        retrieval_latency=_latencies(
            [case.retrieval_latency_seconds for case in completed]
        ),
        generation_latency=_latencies(
            [
                case.generation_latency_seconds
                for case in completed
                if case.model_invoked
            ]
        ),
        end_to_end_latency=_latencies(
            [case.end_to_end_latency_seconds for case in completed]
        ),
    )


def automatic_gate_outcomes(
    metrics: AutomaticMetrics, cases: list[CaseResult], partial: bool
) -> list[GateOutcome]:
    """Apply the fixed pre-tuning structural and automatic thresholds."""
    control_count = sum(
        item.control_metadata for case in cases for item in case.evidence
    )
    return [
        _minimum_gate("citation_validity", metrics.citation_validity, 1.0),
        _minimum_gate("citation_presence", metrics.citation_presence, 1.0),
        GateOutcome(
            name="control_metadata_excluded",
            passed=control_count == 0,
            actual=control_count,
            requirement="zero control-metadata evidence records",
        ),
        GateOutcome(
            name="operational_completion",
            passed=metrics.operational_failures == 0 and not partial,
            actual=metrics.operational_failures,
            requirement="zero operational failures and a complete run",
            detail="partial run" if partial else "",
        ),
        _minimum_gate("recall_at_5", metrics.recall_at_5, 0.90),
        _minimum_gate("mean_reciprocal_rank", metrics.mean_reciprocal_rank, 0.80),
        _minimum_gate(
            "expected_source_in_context", metrics.expected_source_in_context, 0.90
        ),
        _minimum_gate(
            "unanswerable_abstention_accuracy",
            metrics.unanswerable_abstention_accuracy,
            0.90,
        ),
        _maximum_gate("false_abstention_rate", metrics.false_abstention_rate, 0.10),
        _minimum_gate(
            "citation_source_correctness",
            metrics.citation_source_correctness,
            0.95,
        ),
        _minimum_gate(
            "conflicting_uncertainty_presence",
            metrics.conflicting_uncertainty_presence,
            1.0,
        ),
    ]


def _boolean_rate(
    cases: list[CaseResult], field: str, *, invert: bool = False
) -> RateMetric:
    values = [getattr(case.measures, field) for case in cases]
    applicable = [value for value in values if value is not None]
    if invert:
        applicable = [not value for value in applicable]
    excluded = [
        case.case_id for case, value in zip(cases, values, strict=True) if value is None
    ]
    return _rate(sum(applicable), len(applicable), excluded)


def _numeric_mean(values: list[float | None], excluded: list[str]) -> RateMetric:
    applicable = [value for value in values if value is not None]
    if not applicable:
        return _not_applicable(excluded)
    return RateMetric(
        value=fmean(applicable),
        numerator=sum(applicable),
        denominator=len(applicable),
        status="measured",
        excluded_cases=excluded,
    )


def _rate(
    numerator: float, denominator: int, excluded: list[str] | None = None
) -> RateMetric:
    if denominator == 0:
        return _not_applicable(excluded or [])
    return RateMetric(
        value=numerator / denominator,
        numerator=numerator,
        denominator=denominator,
        status="measured",
        excluded_cases=excluded or [],
    )


def _not_applicable(excluded: list[str]) -> RateMetric:
    return RateMetric(
        value=None,
        numerator=0,
        denominator=0,
        status="not_applicable",
        excluded_cases=excluded,
    )


def _latencies(values: list[float]) -> LatencyStatistics:
    if not values:
        return LatencyStatistics(count=0, mean=None, median=None, p95=None)
    ordered = sorted(values)
    position = 0.95 * (len(ordered) - 1)
    lower = math.floor(position)
    upper = math.ceil(position)
    p95 = ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)
    return LatencyStatistics(
        count=len(values), mean=fmean(values), median=median(values), p95=p95
    )


def _minimum_gate(name: str, metric: RateMetric, minimum: float) -> GateOutcome:
    return GateOutcome(
        name=name,
        passed=metric.value is not None and metric.value >= minimum,
        actual=metric.value,
        requirement=f">= {minimum:.2f}",
        detail="not applicable" if metric.value is None else "",
    )


def _maximum_gate(name: str, metric: RateMetric, maximum: float) -> GateOutcome:
    return GateOutcome(
        name=name,
        passed=metric.value is not None and metric.value <= maximum,
        actual=metric.value,
        requirement=f"<= {maximum:.2f}",
        detail="not applicable" if metric.value is None else "",
    )


def _expectation_match(result: SearchResult | None, case: QACase) -> str:
    if result is None:
        return "none"
    if any(_source_matches(result, expected) for expected in case.expected_sources):
        return "expected"
    if any(_source_matches(result, expected) for expected in case.acceptable_sources):
        return "acceptable"
    return "none"


def _source_matches(result: SearchResult, expected: SourceExpectation) -> bool:
    if expected.document_id is not None:
        return result.document_id.casefold() == expected.document_id.casefold()
    actual = result.source_path.as_posix().lstrip("./").casefold()
    wanted = (expected.source_path or "").lstrip("./").casefold()
    return actual == wanted


def _is_control_record(result: SearchResult) -> bool:
    record_type = str(result.metadata.get("record_type", "")).casefold()
    return record_type in CONTROL_RECORD_TYPES or bool(
        result.metadata.get("control_metadata", False)
    )


def _logical_path(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root).as_posix()
    except ValueError:
        return path.name


def _safe_error(error: Exception, workspace: Workspace, root: Path) -> str:
    message = f"{type(error).__name__}: {' '.join(str(error).split())}"
    replacements = {
        str(root): "<repository>",
        str(workspace.artifacts): "<workspace-artifacts>",
        str(workspace.documents): "<workspace-documents>",
    }
    replacements.update(
        {str(source.path): f"<source:{source.name}>" for source in workspace.sources}
    )
    for value, replacement in sorted(
        replacements.items(), key=lambda item: len(item[0]), reverse=True
    ):
        message = message.replace(value, replacement)
    # A backend exception can mention an arbitrary absolute local path, not only
    # the configured workspace paths above. Reports are meant to be shareable.
    message = re.sub(r"(?<!\w)(?:[A-Za-z]:[\\/]|/)[^\s]+", "<path>", message)
    return message[:1000]


def _git_record(root: Path) -> dict[str, Any]:
    def run(*arguments: str) -> str | None:
        try:
            completed = subprocess.run(
                ["git", *arguments],
                cwd=root,
                check=True,
                capture_output=True,
                text=True,
                timeout=5,
            )
        except (OSError, subprocess.SubprocessError):
            return None
        return completed.stdout.strip()

    commit = run("rev-parse", "HEAD")
    status = run("status", "--porcelain", "--untracked-files=normal")
    return {"commit": commit, "dirty": status is None or bool(status)}
