"""Tests for M2.4 full-pipeline QA evaluation and immutable artefacts."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from knowledge_assistant.config import load_settings
from knowledge_assistant.main import main
from knowledge_assistant.managers.workspace_manager import Workspace
from knowledge_assistant.qa_evaluation.benchmark import (
    BenchmarkValidationError,
    load_benchmark,
)
from knowledge_assistant.qa_evaluation.evaluator import run_qa_evaluation
from knowledge_assistant.qa_evaluation.models import ScoredReport
from knowledge_assistant.qa_evaluation.reports import (
    ComparisonError,
    ReviewValidationError,
    compare_scored_reports,
    designate_baseline,
    score_review,
    write_run_artifacts,
)
from knowledge_assistant.retrieval.models import SearchResult

ROOT = Path(__file__).parents[1]
BENCHMARK = ROOT / "benchmarks" / "qa" / "m2.4-acceptance-v1.json"
EVALUATION_CONFIG = ROOT / "config" / "qa-evaluation.yaml"


class GeneratorStub:
    model = "deterministic-test-model"

    def __init__(self, answer: str = "The maximum is GBP 10,000. [S1]") -> None:
        self.answer = answer
        self.prompts: list[str] = []

    def generate(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return self.answer


def _workspace(tmp_path: Path) -> Workspace:
    return Workspace(
        name="evaluation",
        description="Synthetic",
        documents=tmp_path / "documents",
        artifacts=tmp_path / "artifacts",
        collection="evaluation",
        enabled=True,
    )


def _result() -> SearchResult:
    return SearchResult(
        chunk_id="chunk-1",
        document_id="document-1",
        document_title="Community Funding Guide",
        section_title="Grant limits",
        source_filename="funding-guide.md",
        source_root="documents",
        relative_path=Path("funding-guide.md"),
        source_path=Path("documents/funding-guide.md"),
        source_location="documents/funding-guide.md section Grant limits",
        similarity=0.95,
        text="The Community Renewal Grant pays up to GBP 10,000.",
    )


def _one_case_benchmark(tmp_path: Path) -> Path:
    path = tmp_path / "benchmark.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "benchmark_id": "unit-qa",
                "benchmark_version": "1.0.0",
                "description": "Unit benchmark",
                "cases": [
                    {
                        "id": "direct-001",
                        "category": "direct_fact",
                        "question": "What is the maximum grant?",
                        "answerability": "answerable",
                        "expected_sources": [
                            {"source_path": "documents/funding-guide.md"}
                        ],
                        "acceptable_sources": [],
                        "expected_facts": [
                            {
                                "id": "grant-limit",
                                "description": "The maximum is GBP 10,000.",
                            }
                        ],
                        "forbidden_claims": [],
                        "filters": {"source_root": "documents"},
                        "notes": "Unit case",
                    }
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return path


def _run(tmp_path: Path, *, answer: str = "The maximum is GBP 10,000. [S1]"):
    loaded = load_benchmark(_one_case_benchmark(tmp_path))
    settings = load_settings(EVALUATION_CONFIG)
    calls = 0

    def searcher(*args, **kwargs):
        nonlocal calls
        calls += 1
        return [_result()], 0.02

    generator = GeneratorStub(answer)
    report = run_qa_evaluation(
        loaded,
        _workspace(tmp_path),
        settings,
        run_kind="baseline",
        searcher=searcher,
        generator=generator,
        repository_root=ROOT,
    )
    return report, generator, calls


def _complete_review(path: Path) -> None:
    content = json.loads(path.read_text(encoding="utf-8"))
    content["reviewer"] = "test-reviewer"
    content["reviewed_at"] = "2026-08-24T12:00:00Z"
    for item in content["reviews"]:
        item.update(
            {
                "correctness": 4,
                "grounding": 4,
                "citation_coverage": 4,
                "uncertainty_handling": 4,
                "satisfied_fact_ids": [fact["id"] for fact in item["expected_facts"]],
                "missed_fact_ids": [],
                "disposition": "pass",
            }
        )
    path.write_text(json.dumps(content, indent=2) + "\n", encoding="utf-8")


def test_repository_benchmark_is_frozen_shareable_and_has_required_coverage() -> None:
    loaded = load_benchmark(BENCHMARK)

    assert len(loaded.benchmark.cases) == 25
    assert len(loaded.checksum) == 64
    assert loaded.category_counts == {
        "conflicting": 2,
        "cross_document": 3,
        "direct_fact": 5,
        "document_discovery": 3,
        "evidence_comparison": 4,
        "metadata_filtered": 3,
        "temporal": 2,
        "unanswerable": 3,
    }
    assert all(
        not expectation.source_path.startswith(("C:/", "D:/", "E:/"))
        for case in loaded.benchmark.cases
        for expectation in case.expected_sources + case.acceptable_sources
        if expectation.source_path
    )


def test_benchmark_checksum_uses_exact_bytes_and_strict_models(tmp_path: Path) -> None:
    original = _one_case_benchmark(tmp_path)
    first = load_benchmark(original)
    original.write_bytes(original.read_bytes() + b"\n")
    second = load_benchmark(original)
    assert first.checksum != second.checksum

    raw = json.loads(original.read_text(encoding="utf-8"))
    raw["cases"][0]["unexpected"] = True
    original.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(BenchmarkValidationError, match="unexpected"):
        load_benchmark(original)


def test_case_ids_are_unique_ignoring_case(tmp_path: Path) -> None:
    path = _one_case_benchmark(tmp_path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    duplicate = dict(raw["cases"][0])
    duplicate["id"] = "DIRECT-001"
    raw["cases"].append(duplicate)
    path.write_text(json.dumps(raw), encoding="utf-8")

    with pytest.raises(BenchmarkValidationError, match="unique ignoring case"):
        load_benchmark(path)


def test_validate_cli_does_not_require_configuration_or_model(capsys) -> None:
    result = main(
        [
            "--config",
            "missing-config.yaml",
            "qa-evaluate",
            "validate",
            str(BENCHMARK),
        ]
    )
    output = capsys.readouterr().out
    assert result == 0
    assert "Cases: 25" in output
    assert "VALID" in output


def test_run_reuses_one_answer_question_retrieval_and_excludes_raw_evidence(
    tmp_path: Path,
) -> None:
    report, generator, calls = _run(tmp_path)

    assert calls == 1
    assert len(generator.prompts) == 1
    case = report.cases[0]
    assert case.status == "answered"
    assert case.filters == {"source_root": "documents"}
    assert case.evidence[0].expectation_match == "expected"
    assert case.measures.recall_at_5 is True
    assert case.measures.reciprocal_rank == 1
    assert case.citations.resolved_labels == ["S1"]
    serialised = report.model_dump_json()
    assert "The Community Renewal Grant pays up" not in serialised
    assert "fully rendered prompt" not in serialised


def test_not_applicable_gates_are_neutral_not_automatic_failures(
    tmp_path: Path,
) -> None:
    report, _, _ = _run(tmp_path)
    conflict_gate = next(
        gate
        for gate in report.automatic_gates
        if gate.name == "conflicting_uncertainty_presence"
    )

    assert conflict_gate.passed is None
    assert conflict_gate.detail == "not applicable"

    raw, _, review = write_run_artifacts(report, tmp_path / "workspace")
    _complete_review(review)
    scored, _, _ = score_review(raw, review)
    assert scored.all_gates_passed is True


def test_citation_diagnostics_handle_duplicates_and_invalid_labels(
    tmp_path: Path,
) -> None:
    report, _, _ = _run(tmp_path, answer="Fact [S1], repeated [S1], invalid [S9].")
    case = report.cases[0]

    assert case.citations.labels_found == ["S1", "S1", "S9"]
    assert case.citations.duplicate_labels == ["S1"]
    assert case.citations.invalid_labels == ["S9"]
    assert report.automatic_metrics.citation_validity.value == pytest.approx(2 / 3)


def test_empty_retrieval_abstains_without_generation(tmp_path: Path) -> None:
    loaded = load_benchmark(_one_case_benchmark(tmp_path))
    settings = load_settings(EVALUATION_CONFIG)
    generator = GeneratorStub()

    report = run_qa_evaluation(
        loaded,
        _workspace(tmp_path),
        settings,
        run_kind="candidate",
        searcher=lambda *args, **kwargs: ([], 0.01),
        generator=generator,
        repository_root=ROOT,
    )

    assert report.cases[0].status == "insufficient_evidence"
    assert report.cases[0].model_invoked is False
    assert generator.prompts == []
    assert report.automatic_metrics.false_abstention_rate.value == 1


def test_operational_failure_is_recorded_and_run_continues(tmp_path: Path) -> None:
    loaded = load_benchmark(_one_case_benchmark(tmp_path))
    settings = load_settings(EVALUATION_CONFIG)

    def broken(*args, **kwargs):
        raise RuntimeError(f"index unavailable at {tmp_path}")

    report = run_qa_evaluation(
        loaded,
        _workspace(tmp_path),
        settings,
        run_kind="candidate",
        repeats=2,
        searcher=broken,
        generator=GeneratorStub(),
        repository_root=ROOT,
    )

    assert len(report.cases) == 2
    assert report.automatic_metrics.operational_failures == 2
    assert str(tmp_path) not in report.cases[0].operational_error


def test_run_artifacts_are_immutable_and_review_is_exactly_bound(
    tmp_path: Path,
) -> None:
    report, _, _ = _run(tmp_path)
    raw, summary, review = write_run_artifacts(report, tmp_path / "workspace")
    assert raw.is_file() and summary.is_file() and review.is_file()
    with pytest.raises(FileExistsError):
        write_run_artifacts(report, tmp_path / "workspace")

    _complete_review(review)
    scored, scored_path, scored_markdown = score_review(raw, review)
    assert scored_path.is_file() and scored_markdown.is_file()
    assert scored.human_metrics.mean_correctness == 4
    with pytest.raises(FileExistsError):
        score_review(raw, review)


def test_incomplete_or_mismatched_review_is_rejected(tmp_path: Path) -> None:
    report, _, _ = _run(tmp_path)
    raw, _, review = write_run_artifacts(report, tmp_path / "workspace")
    with pytest.raises(ReviewValidationError, match="reviewer"):
        score_review(raw, review)

    content = json.loads(review.read_text(encoding="utf-8"))
    content["run_id"] = "another-run"
    review.write_text(json.dumps(content), encoding="utf-8")
    with pytest.raises(ReviewValidationError, match="run_id"):
        score_review(raw, review)


def test_baseline_requires_clean_worktree_and_failing_reason(tmp_path: Path) -> None:
    report, _, _ = _run(tmp_path)
    raw, _, review = write_run_artifacts(report, tmp_path / "workspace")
    _complete_review(review)
    scored, scored_path, _ = score_review(raw, review)
    with pytest.raises(ReviewValidationError, match="dirty-worktree"):
        designate_baseline(scored_path, accept_failing=True, reason="initial")

    content = scored.model_dump(mode="json")
    content["run"]["git"]["dirty"] = False
    content["run"]["git"]["commit"] = None
    clean_path = scored_path.with_name("clean.scored.json")
    clean_path.write_text(json.dumps(content), encoding="utf-8")
    with pytest.raises(ReviewValidationError, match="Git commit"):
        designate_baseline(clean_path, accept_failing=True, reason="measurement")

    content["run"]["git"]["commit"] = "a" * 40
    content["all_gates_passed"] = False
    clean_path.write_text(json.dumps(content), encoding="utf-8")
    with pytest.raises(ReviewValidationError, match="recorded reason"):
        designate_baseline(clean_path, accept_failing=True)
    designation, active = designate_baseline(
        clean_path, accept_failing=True, reason="pre-refinement measurement"
    )
    assert active.name == "baseline.json"
    assert designation["run_id"] == report.run_id


def test_scoring_fails_reproducibility_gate_when_required_setting_is_missing(
    tmp_path: Path,
) -> None:
    report, _, _ = _run(tmp_path)
    raw, _, review = write_run_artifacts(report, tmp_path / "workspace")
    content = json.loads(raw.read_text(encoding="utf-8"))
    del content["prompt"]["checksum"]
    raw.write_text(json.dumps(content), encoding="utf-8")
    _complete_review(review)

    scored, _, _ = score_review(raw, review)

    gate = next(
        item
        for item in scored.structural_gates
        if item.name == "reproducibility_fields"
    )
    assert gate.passed is False
    assert "prompt.checksum" in gate.detail


def test_comparison_allows_candidate_settings_and_requires_comparable_run_shape(
    tmp_path: Path,
) -> None:
    report, _, _ = _run(tmp_path)
    raw, _, review = write_run_artifacts(report, tmp_path / "workspace")
    _complete_review(review)
    scored, scored_path, _ = score_review(raw, review)
    candidate = scored.model_copy(deep=True)
    candidate.run.run_id = "candidate-run"
    candidate.run.prompt["name"] = "candidate-prompt"
    candidate.run.prompt["checksum"] = "compatible-new-version"
    candidate.run.llm["configured_model"] = "candidate-model"
    candidate_path = scored_path.with_name("candidate.scored.json")
    candidate_path.write_text(candidate.model_dump_json(), encoding="utf-8")

    comparison, comparison_path, _ = compare_scored_reports(scored_path, candidate_path)
    assert comparison_path.is_file()
    assert comparison["regressed_cases"] == []
    assert "prompt.name" in comparison["setting_differences"]
    assert "prompt.checksum" in comparison["setting_differences"]
    assert "llm.configured_model" in comparison["setting_differences"]

    incompatible = ScoredReport.model_validate(candidate.model_dump())
    incompatible.run.repeats = 2
    incompatible_path = scored_path.with_name("incompatible.scored.json")
    incompatible_path.write_text(incompatible.model_dump_json(), encoding="utf-8")
    with pytest.raises(ComparisonError, match="repeat count"):
        compare_scored_reports(scored_path, incompatible_path)


def test_m1_evaluate_parser_contract_remains_separate() -> None:
    from knowledge_assistant.main import build_parser

    parser = build_parser()
    m1 = parser.parse_args(["evaluate", "benchmark.json"])
    m2 = parser.parse_args(["qa-evaluate", "validate", "qa.json"])
    assert m1.command == "evaluate"
    assert not hasattr(m1, "qa_action")
    assert m2.command == "qa-evaluate"
    assert m2.qa_action == "validate"
