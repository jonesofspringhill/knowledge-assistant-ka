"""Strict, versioned models for full-pipeline question-answer evaluation."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

SCHEMA_VERSION = "1.0"
REPORT_SCHEMA_VERSION = "1.0"
RUBRIC_VERSION = "1.0"

Category = Literal[
    "direct_fact",
    "document_discovery",
    "metadata_filtered",
    "temporal",
    "cross_document",
    "evidence_comparison",
    "unanswerable",
    "conflicting",
]
Answerability = Literal["answerable", "unanswerable", "conflicting"]
ScalarFilter = str | int | float | bool


class StrictModel(BaseModel):
    """Reject unknown fields so benchmark mistakes fail before invocation."""

    model_config = ConfigDict(extra="forbid")


class SourceExpectation(StrictModel):
    """Stable logical identity of an expected evidence source."""

    source_path: str | None = None
    document_id: str | None = None

    @model_validator(mode="after")
    def exactly_one_identity(self) -> SourceExpectation:
        if (self.source_path is None) == (self.document_id is None):
            raise ValueError("provide exactly one of source_path or document_id")
        if self.source_path is not None:
            normalised = self.source_path.strip().replace("\\", "/")
            if not normalised or normalised.startswith("/") or ":/" in normalised:
                raise ValueError(
                    "source_path must be a non-empty logical relative path"
                )
            self.source_path = normalised
        if self.document_id is not None:
            self.document_id = self.document_id.strip()
            if not self.document_id:
                raise ValueError("document_id must not be blank")
        return self


class ExpectedFact(StrictModel):
    """One benchmark fact scored by a human reviewer."""

    id: str = Field(min_length=1)
    description: str = Field(min_length=1)


class QACase(StrictModel):
    """One stable full-pipeline QA evaluation case."""

    id: str = Field(min_length=1)
    category: Category
    question: str = Field(min_length=1)
    answerability: Answerability
    expected_sources: list[SourceExpectation] = Field(default_factory=list)
    acceptable_sources: list[SourceExpectation] = Field(default_factory=list)
    expected_facts: list[ExpectedFact] = Field(default_factory=list)
    forbidden_claims: list[str] = Field(default_factory=list)
    filters: dict[str, ScalarFilter] = Field(default_factory=dict)
    notes: str = ""

    @model_validator(mode="after")
    def validate_case(self) -> QACase:
        self.id = self.id.strip()
        self.question = self.question.strip()
        if not self.id or not self.question:
            raise ValueError("case id and question must not be blank")
        if any(not key.strip() or "=" in key for key in self.filters):
            raise ValueError("filter keys must be non-empty names without '='")
        fact_ids = [fact.id.casefold() for fact in self.expected_facts]
        if len(fact_ids) != len(set(fact_ids)):
            raise ValueError("expected fact ids must be unique ignoring case")
        if any(not claim.strip() for claim in self.forbidden_claims):
            raise ValueError("forbidden claims must not be blank")
        sources = self.expected_sources + self.acceptable_sources
        identities = [
            (item.source_path or f"document:{item.document_id}").casefold()
            for item in sources
        ]
        if len(identities) != len(set(identities)):
            raise ValueError("source expectations must be unique ignoring case")
        if self.answerability == "answerable" and (
            not self.expected_sources or not self.expected_facts
        ):
            raise ValueError(
                "answerable cases require expected_sources and expected_facts"
            )
        if self.answerability == "unanswerable" and (sources or self.expected_facts):
            raise ValueError(
                "unanswerable cases cannot declare sources or expected facts"
            )
        if self.answerability == "conflicting" and len(self.expected_sources) < 2:
            raise ValueError("conflicting cases require at least two expected sources")
        return self


class QABenchmark(StrictModel):
    """Versioned collection of QA cases."""

    schema_version: Literal["1.0"]
    benchmark_id: str = Field(min_length=1)
    benchmark_version: str = Field(
        min_length=1, pattern=r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$"
    )
    description: str = Field(min_length=1)
    cases: list[QACase] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_case_ids(self) -> QABenchmark:
        ids = [case.id.casefold() for case in self.cases]
        if len(ids) != len(set(ids)):
            raise ValueError("case ids must be unique ignoring case")
        return self


class RateMetric(StrictModel):
    """A rate whose denominator remains explicit and inspectable."""

    value: float | None
    numerator: float
    denominator: int
    status: Literal["measured", "not_applicable"]
    excluded_cases: list[str] = Field(default_factory=list)


class LatencyStatistics(StrictModel):
    """Deterministic latency summary in seconds."""

    count: int
    mean: float | None
    median: float | None
    p95: float | None


class EvidenceRecord(StrictModel):
    """Privacy-safe ranked evidence identity; source text is deliberately absent."""

    rank: int = Field(gt=0)
    chunk_id: str
    document_id: str
    source_path: str
    source_location: str
    similarity: float
    selected_for_context: bool
    expectation_match: Literal["expected", "acceptable", "none"]
    control_metadata: bool = False


class CitationDiagnostics(StrictModel):
    """Resolved answer citation labels for one invocation."""

    labels_found: list[str] = Field(default_factory=list)
    resolved_labels: list[str] = Field(default_factory=list)
    invalid_labels: list[str] = Field(default_factory=list)
    duplicate_labels: list[str] = Field(default_factory=list)
    unused_supplied_labels: list[str] = Field(default_factory=list)
    expected_source_labels: list[str] = Field(default_factory=list)
    acceptable_source_labels: list[str] = Field(default_factory=list)


class CaseMeasures(StrictModel):
    """Deterministic automatic measures for one case/repeat."""

    relevant_source_rank: int | None = None
    recall_at_5: bool | None = None
    recall_at_10: bool | None = None
    reciprocal_rank: float | None = None
    expected_source_in_context: bool | None = None
    citation_valid_count: int = 0
    citation_count: int = 0
    citation_correct_count: int = 0
    citation_correct_denominator: int = 0
    citation_present: bool | None = None
    answered: bool | None = None
    abstained: bool | None = None
    conflicting_uncertainty_present: bool | None = None


class CaseResult(StrictModel):
    """Privacy-safe result of one case/repeat invocation."""

    case_id: str
    repeat_index: int = Field(gt=0)
    category: Category
    answerability: Answerability
    question: str
    filters: dict[str, ScalarFilter] = Field(default_factory=dict)
    expected_facts: list[ExpectedFact] = Field(default_factory=list)
    forbidden_claims: list[str] = Field(default_factory=list)
    review_notes: str = ""
    status: Literal["answered", "insufficient_evidence", "operational_failure"]
    answer: str
    model: str | None = None
    uncertainty: str | None = None
    model_invoked: bool
    operational_error: str | None = None
    evidence: list[EvidenceRecord] = Field(default_factory=list)
    context_sources: list[str] = Field(default_factory=list)
    citations: CitationDiagnostics
    measures: CaseMeasures
    retrieval_latency_seconds: float = 0
    generation_latency_seconds: float = 0
    end_to_end_latency_seconds: float = 0


class AutomaticMetrics(StrictModel):
    """Aggregate automatic metrics for a run or scored report."""

    recall_at_5: RateMetric
    recall_at_10: RateMetric
    mean_reciprocal_rank: RateMetric
    expected_source_in_context: RateMetric
    citation_validity: RateMetric
    citation_source_correctness: RateMetric
    citation_presence: RateMetric
    answerable_answer_rate: RateMetric
    unanswerable_abstention_accuracy: RateMetric
    false_abstention_rate: RateMetric
    unsupported_answer_rate: RateMetric
    conflicting_uncertainty_presence: RateMetric
    completion_rate: RateMetric
    operational_failures: int
    retrieval_latency: LatencyStatistics
    generation_latency: LatencyStatistics
    end_to_end_latency: LatencyStatistics


class GateOutcome(StrictModel):
    """One fixed completion or regression gate."""

    name: str
    passed: bool | None
    actual: float | int | str | None = None
    requirement: str
    detail: str = ""


class QARunReport(StrictModel):
    """Immutable raw measurement report for a full QA run."""

    evaluation_schema_version: Literal["1.0"] = REPORT_SCHEMA_VERSION
    run_id: str
    run_kind: Literal["baseline", "candidate"]
    partial: bool = False
    benchmark: dict[str, Any]
    application: dict[str, Any]
    git: dict[str, Any]
    environment: dict[str, Any]
    workspace: dict[str, Any]
    embedding: dict[str, Any]
    llm: dict[str, Any]
    prompt: dict[str, Any]
    retrieval: dict[str, Any]
    context: dict[str, Any]
    generation: dict[str, Any]
    repeats: int = Field(gt=0)
    started_at: str
    finished_at: str
    cases: list[CaseResult]
    automatic_metrics: AutomaticMetrics
    automatic_gates: list[GateOutcome]
    human_review_status: Literal["pending"] = "pending"


class ReviewEntry(StrictModel):
    """Human semantic review for one case/repeat."""

    case_id: str
    repeat_index: int = Field(gt=0)
    question: str
    answer: str
    supplied_sources: list[str]
    expected_facts: list[ExpectedFact]
    forbidden_claims: list[str]
    notes: str
    correctness: int | None = Field(default=None, ge=0, le=4)
    grounding: int | None = Field(default=None, ge=0, le=4)
    citation_coverage: int | None = Field(default=None, ge=0, le=4)
    uncertainty_handling: int | None = Field(default=None, ge=0, le=4)
    satisfied_fact_ids: list[str] = Field(default_factory=list)
    missed_fact_ids: list[str] = Field(default_factory=list)
    observed_forbidden_claims: list[str] = Field(default_factory=list)
    unsupported_material_claims: list[str] = Field(default_factory=list)
    disposition: Literal["pass", "fail", "needs_discussion"] | None = None
    disposition_note: str = ""


class ReviewFile(StrictModel):
    """Review template or completed human review bound to one exact run."""

    review_schema_version: Literal["1.0"] = SCHEMA_VERSION
    rubric_version: Literal["1.0"] = RUBRIC_VERSION
    run_id: str
    benchmark_checksum: str
    reviewer: str = ""
    reviewed_at: str | None = None
    reviews: list[ReviewEntry]


class HumanMetrics(StrictModel):
    """Aggregated human-review results."""

    mean_correctness: float | None
    minimum_answerable_correctness: int | None
    mean_grounding: float | None
    mean_citation_coverage: float | None
    unsupported_claim_case_rate: RateMetric
    uncertainty_handling_pass_rate: RateMetric


class ScoredReport(StrictModel):
    """Immutable merged result that references, but does not rewrite, raw data."""

    scoring_schema_version: Literal["1.0"] = REPORT_SCHEMA_VERSION
    raw_report_checksum: str
    review_checksum: str
    run: QARunReport
    review: dict[str, Any]
    human_metrics: HumanMetrics
    structural_gates: list[GateOutcome]
    automatic_gates: list[GateOutcome]
    human_gates: list[GateOutcome]
    all_gates_passed: bool
