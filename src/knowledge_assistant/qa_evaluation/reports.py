"""Immutable reports, human scoring, baselines, and candidate comparison."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import uuid
from datetime import UTC, datetime
from pathlib import Path
from statistics import fmean
from typing import Any

from pydantic import ValidationError

from knowledge_assistant.qa_evaluation.models import (
    GateOutcome,
    HumanMetrics,
    QARunReport,
    RateMetric,
    ReviewEntry,
    ReviewFile,
    ScoredReport,
)


class ReviewValidationError(ValueError):
    """Raised when review input does not match its immutable raw run."""


class ComparisonError(ValueError):
    """Raised when two scored reports cannot be compared honestly."""


def write_run_artifacts(
    report: QARunReport, workspace_artifacts: Path
) -> tuple[Path, Path, Path]:
    """Atomically create the raw JSON, Markdown summary, and review template."""
    directory = workspace_artifacts / "evaluations" / "qa" / str(report.benchmark["id"])
    raw = directory / f"{report.run_id}.json"
    summary = directory / f"{report.run_id}.md"
    review = directory / f"{report.run_id}.review.json"
    _write_json(raw, report.model_dump(mode="json"))
    _write_text(summary, render_run_markdown(report))
    write_review_template(report, review)
    return raw, summary, review


def write_review_template(report: QARunReport, output: str | Path) -> Path:
    """Create blank semantic review input bound to one run and benchmark."""
    entries = [
        ReviewEntry(
            case_id=case.case_id,
            repeat_index=case.repeat_index,
            question=case.question,
            answer=case.answer,
            supplied_sources=case.context_sources,
            expected_facts=case.expected_facts,
            forbidden_claims=case.forbidden_claims,
            notes=case.review_notes,
        )
        for case in report.cases
        if case.status != "operational_failure"
    ]
    template = ReviewFile(
        run_id=report.run_id,
        benchmark_checksum=str(report.benchmark["checksum"]),
        reviews=entries,
    )
    path = Path(output)
    _write_json(path, template.model_dump(mode="json"))
    return path


def score_review(
    raw_report_path: str | Path, review_path: str | Path
) -> tuple[ScoredReport, Path, Path]:
    """Validate completed human input and write a separate scored artefact."""
    raw_path = Path(raw_report_path).resolve()
    review_input = Path(review_path).resolve()
    raw_bytes = raw_path.read_bytes()
    review_bytes = review_input.read_bytes()
    try:
        report = QARunReport.model_validate_json(raw_bytes)
        review = ReviewFile.model_validate_json(review_bytes)
    except (ValidationError, ValueError) as error:
        raise ReviewValidationError(f"invalid report or review: {error}") from error
    _validate_completed_review(report, review)
    human = _human_metrics(report, review)
    structural = _structural_gates(report, review)
    human_gates = _human_gates(report, review, human)
    automatic = list(report.automatic_gates)
    all_passed = all(
        gate.passed is True for gate in structural + automatic + human_gates
    )
    scored = ScoredReport(
        raw_report_checksum=hashlib.sha256(raw_bytes).hexdigest(),
        review_checksum=hashlib.sha256(review_bytes).hexdigest(),
        run=report,
        review={
            "review_schema_version": review.review_schema_version,
            "rubric_version": review.rubric_version,
            "reviewer": review.reviewer,
            "reviewed_at": review.reviewed_at,
            "entries": [
                {
                    "case_id": item.case_id,
                    "repeat_index": item.repeat_index,
                    "correctness": item.correctness,
                    "grounding": item.grounding,
                    "citation_coverage": item.citation_coverage,
                    "uncertainty_handling": item.uncertainty_handling,
                    "satisfied_fact_ids": item.satisfied_fact_ids,
                    "missed_fact_ids": item.missed_fact_ids,
                    "observed_forbidden_claims": item.observed_forbidden_claims,
                    "unsupported_material_claims": item.unsupported_material_claims,
                    "disposition": item.disposition,
                    "disposition_note": item.disposition_note,
                }
                for item in review.reviews
            ],
        },
        human_metrics=human,
        structural_gates=structural,
        automatic_gates=automatic,
        human_gates=human_gates,
        all_gates_passed=all_passed,
    )
    stem = raw_path.with_suffix("")
    json_path = stem.with_name(stem.name + ".scored.json")
    markdown_path = stem.with_name(stem.name + ".scored.md")
    _write_json(json_path, scored.model_dump(mode="json"))
    _write_text(markdown_path, render_scored_markdown(scored))
    return scored, json_path, markdown_path


def designate_baseline(
    scored_path: str | Path,
    *,
    accept_failing: bool = False,
    reason: str = "",
) -> tuple[dict[str, Any], Path]:
    """Point a designation record at an existing immutable clean-worktree run."""
    path = Path(scored_path).resolve()
    scored_bytes = path.read_bytes()
    try:
        scored = ScoredReport.model_validate_json(scored_bytes)
    except ValidationError as error:
        raise ReviewValidationError(f"invalid scored report: {error}") from error
    if scored.run.partial:
        raise ReviewValidationError("a partial run cannot be designated as baseline")
    if bool(scored.run.git.get("dirty")):
        raise ReviewValidationError(
            "a dirty-worktree run cannot be designated as baseline"
        )
    if not str(scored.run.git.get("commit") or "").strip():
        raise ReviewValidationError(
            "a baseline requires a resolvable Git commit identifier"
        )
    if not scored.all_gates_passed:
        if not accept_failing:
            raise ReviewValidationError(
                "the run fails gates; use --accept-failing with a recorded reason"
            )
        if not reason.strip():
            raise ReviewValidationError(
                "a failing baseline requires a non-empty recorded reason"
            )
    designation = {
        "designation_schema_version": "1.0",
        "benchmark_id": scored.run.benchmark["id"],
        "benchmark_version": scored.run.benchmark["version"],
        "benchmark_checksum": scored.run.benchmark["checksum"],
        "workspace": scored.run.workspace["name"],
        "run_id": scored.run.run_id,
        "scored_report": path.name,
        "scored_report_checksum": hashlib.sha256(scored_bytes).hexdigest(),
        "accepted": scored.all_gates_passed,
        "reason": reason.strip(),
        "designated_at": datetime.now(UTC).isoformat(),
    }
    historical = path.parent / f"{scored.run.run_id}.baseline.json"
    active = path.parent / "baseline.json"
    _write_json(historical, designation)
    _write_json(active, designation, overwrite=True)
    return designation, active


def compare_scored_reports(
    baseline_path: str | Path, candidate_path: str | Path
) -> tuple[dict[str, Any], Path, Path]:
    """Compare compatible scored reports and enforce fixed regression gates."""
    baseline_file = Path(baseline_path).resolve()
    candidate_file = Path(candidate_path).resolve()
    baseline = _load_scored_or_designation(baseline_file)
    candidate = _load_scored_or_designation(candidate_file)
    incompatibilities = _compatibility_errors(baseline, candidate)
    if incompatibilities:
        raise ComparisonError("incompatible reports: " + "; ".join(incompatibilities))

    values = _comparison_values(baseline, candidate)
    regression_gates: list[dict[str, Any]] = []
    for name, item in values.items():
        base = item["baseline"]
        current = item["candidate"]
        allowed = 0.10 if name.startswith("mean_") else 0.02
        if name == "median_end_to_end_latency":
            passed = base in {None, 0} or current is None or current <= base * 1.25
            requirement = "no more than 25% slower"
        elif base is None or current is None:
            passed = False
            requirement = "both values must be measured"
        elif name in {"false_abstention_rate", "unsupported_answer_rate"}:
            passed = current <= base + allowed
            requirement = f"no increase greater than {allowed:.2f}"
        else:
            passed = current >= base - allowed
            requirement = f"no decrease greater than {allowed:.2f}"
        regression_gates.append(
            {
                "name": name,
                "passed": passed,
                "requirement": requirement,
                "baseline": base,
                "candidate": current,
                "change": None if base is None or current is None else current - base,
            }
        )

    baseline_failures = _case_failures(baseline)
    candidate_failures = _case_failures(candidate)
    report = {
        "comparison_schema_version": "1.0",
        "created_at": datetime.now(UTC).isoformat(),
        "benchmark": baseline.run.benchmark,
        "baseline_run_id": baseline.run.run_id,
        "candidate_run_id": candidate.run.run_id,
        "setting_differences": _setting_differences(baseline, candidate),
        "metrics": values,
        "regression_gates": regression_gates,
        "fixed_cases": sorted(baseline_failures - candidate_failures),
        "regressed_cases": sorted(candidate_failures - baseline_failures),
        "candidate_quality_gates_passed": candidate.all_gates_passed,
        "candidate_passed": candidate.all_gates_passed
        and all(item["passed"] for item in regression_gates),
    }
    directory = candidate_file.parent / "comparisons"
    identity = f"{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"
    json_path = directory / f"{identity}.json"
    markdown_path = directory / f"{identity}.md"
    _write_json(json_path, report)
    _write_text(markdown_path, render_comparison_markdown(report))
    return report, json_path, markdown_path


def render_run_markdown(report: QARunReport) -> str:
    """Render a concise privacy-safe automatic run summary."""
    lines = [
        f"# QA Evaluation Run {report.run_id}",
        "",
        f"- Benchmark: `{report.benchmark['id']}` {report.benchmark['version']}",
        f"- Checksum: `{report.benchmark['checksum']}`",
        f"- Workspace: `{report.workspace['name']}`",
        f"- Kind: `{report.run_kind}`",
        (
            f"- Git: `{report.git.get('commit') or 'unavailable'}` "
            f"({'dirty' if report.git.get('dirty') else 'clean'})"
        ),
        f"- Complete: `{'no' if report.partial else 'yes'}`",
        "",
        "## Automatic metrics",
        "",
    ]
    for name, metric in report.automatic_metrics.model_dump().items():
        if isinstance(metric, dict) and "value" in metric:
            lines.append(
                f"- {name}: `{metric['value']}` ({metric['numerator']}/{metric['denominator']})"
            )
    lines.extend(["", "## Gates", ""])
    lines.extend(
        f"- {'PASS' if gate.passed else 'FAIL'} {gate.name}: {gate.actual} ({gate.requirement})"
        for gate in report.automatic_gates
    )
    lines.extend(["", "Human review: **pending**", ""])
    return "\n".join(lines)


def render_scored_markdown(scored: ScoredReport) -> str:
    """Render automatic and reviewed gate outcomes."""
    lines = [
        f"# Scored QA Evaluation {scored.run.run_id}",
        "",
        f"Final result: **{'PASS' if scored.all_gates_passed else 'FAIL'}**",
        "",
        "## Human metrics",
        "",
    ]
    for name, value in scored.human_metrics.model_dump().items():
        lines.append(f"- {name}: `{value}`")
    lines.extend(["", "## Gates", ""])
    for gate in scored.structural_gates + scored.automatic_gates + scored.human_gates:
        lines.append(
            f"- {'PASS' if gate.passed else 'FAIL'} {gate.name}: "
            f"{gate.actual} ({gate.requirement})"
        )
    return "\n".join(lines) + "\n"


def render_comparison_markdown(comparison: dict[str, Any]) -> str:
    """Render setting differences, metric changes, and per-case regressions."""
    lines = [
        "# QA Evaluation Comparison",
        "",
        f"Baseline: `{comparison['baseline_run_id']}`",
        f"Candidate: `{comparison['candidate_run_id']}`",
        f"Result: **{'PASS' if comparison['candidate_passed'] else 'FAIL'}**",
        "",
        "## Metrics",
        "",
        "| Metric | Baseline | Candidate | Change | Gate |",
        "| --- | ---: | ---: | ---: | --- |",
    ]
    gates = {item["name"]: item for item in comparison["regression_gates"]}
    for name, values in comparison["metrics"].items():
        gate = gates[name]
        lines.append(
            f"| {name} | {values['baseline']} | {values['candidate']} | "
            f"{gate['change']} | {'PASS' if gate['passed'] else 'FAIL'} |"
        )
    lines.extend(
        [
            "",
            "## Cases",
            "",
            "- Fixed: " + (", ".join(comparison["fixed_cases"]) or "none"),
            "- Regressed: " + (", ".join(comparison["regressed_cases"]) or "none"),
            "",
            "## Setting differences",
            "",
            "```json",
            json.dumps(comparison["setting_differences"], indent=2),
            "```",
            "",
        ]
    )
    return "\n".join(lines)


def _validate_completed_review(report: QARunReport, review: ReviewFile) -> None:
    if review.run_id != report.run_id:
        raise ReviewValidationError("review run_id does not match the raw report")
    if review.benchmark_checksum != report.benchmark["checksum"]:
        raise ReviewValidationError("review benchmark checksum does not match")
    if not review.reviewer.strip() or not review.reviewed_at:
        raise ReviewValidationError("reviewer and reviewed_at are required")
    try:
        datetime.fromisoformat(review.reviewed_at)
    except ValueError as error:
        raise ReviewValidationError(
            "reviewed_at must be an ISO-8601 timestamp"
        ) from error
    completed = {
        (case.case_id, case.repeat_index): case
        for case in report.cases
        if case.status != "operational_failure"
    }
    supplied = {(item.case_id, item.repeat_index): item for item in review.reviews}
    if set(completed) != set(supplied):
        missing = sorted(set(completed) - set(supplied))
        extra = sorted(set(supplied) - set(completed))
        raise ReviewValidationError(
            f"review case mismatch; missing={missing}, extra={extra}"
        )
    for key, case in completed.items():
        item = supplied[key]
        immutable = (
            item.question == case.question
            and item.answer == case.answer
            and item.supplied_sources == case.context_sources
            and item.expected_facts == case.expected_facts
            and item.forbidden_claims == case.forbidden_claims
            and item.notes == case.review_notes
        )
        if not immutable:
            raise ReviewValidationError(f"review changed immutable input for {key}")
        required = [
            item.correctness,
            item.grounding,
            item.citation_coverage,
            item.uncertainty_handling,
            item.disposition,
        ]
        if any(value is None for value in required):
            raise ReviewValidationError(f"review is incomplete for {key}")
        known = {fact.id for fact in item.expected_facts}
        recorded = set(item.satisfied_fact_ids) | set(item.missed_fact_ids)
        if known != recorded or set(item.satisfied_fact_ids) & set(
            item.missed_fact_ids
        ):
            raise ReviewValidationError(
                f"fact outcomes must partition expected facts for {key}"
            )


def _human_metrics(report: QARunReport, review: ReviewFile) -> HumanMetrics:
    cases = {(case.case_id, case.repeat_index): case for case in report.cases}
    answerable = [
        item
        for item in review.reviews
        if cases[(item.case_id, item.repeat_index)].answerability == "answerable"
    ]
    uncertainty = [
        item
        for item in review.reviews
        if cases[(item.case_id, item.repeat_index)].answerability
        in {"unanswerable", "conflicting"}
    ]
    unsupported = [item for item in review.reviews if item.unsupported_material_claims]
    return HumanMetrics(
        mean_correctness=_mean([item.correctness for item in answerable]),
        minimum_answerable_correctness=min(
            (item.correctness for item in answerable if item.correctness is not None),
            default=None,
        ),
        mean_grounding=_mean([item.grounding for item in review.reviews]),
        mean_citation_coverage=_mean(
            [item.citation_coverage for item in review.reviews]
        ),
        unsupported_claim_case_rate=_rate(len(unsupported), len(review.reviews)),
        uncertainty_handling_pass_rate=_rate(
            sum((item.uncertainty_handling or 0) >= 3 for item in uncertainty),
            len(uncertainty),
        ),
    )


def _structural_gates(report: QARunReport, review: ReviewFile) -> list[GateOutcome]:
    automatic = {gate.name: gate for gate in report.automatic_gates}
    forbidden = sum(len(item.observed_forbidden_claims) for item in review.reviews)
    missing_reproducibility = _missing_reproducibility_fields(report)
    return [
        automatic["citation_validity"],
        automatic["citation_presence"],
        automatic["control_metadata_excluded"],
        automatic["operational_completion"],
        GateOutcome(
            name="critical_unsupported_claims",
            passed=forbidden == 0,
            actual=forbidden,
            requirement="zero observed forbidden/critical claims",
        ),
        GateOutcome(
            name="reproducibility_fields",
            passed=not missing_reproducibility,
            actual=len(missing_reproducibility),
            requirement="all strict report fields present",
            detail=(
                "missing: " + ", ".join(missing_reproducibility)
                if missing_reproducibility
                else "complete"
            ),
        ),
    ]


def _missing_reproducibility_fields(report: QARunReport) -> list[str]:
    groups: dict[str, tuple[dict[str, Any], tuple[str, ...]]] = {
        "benchmark": (
            report.benchmark,
            ("id", "version", "schema_version", "checksum", "path", "case_count"),
        ),
        "application": (report.application, ("name", "version")),
        "git": (report.git, ("dirty",)),
        "environment": (report.environment, ("python", "operating_system")),
        "workspace": (report.workspace, ("name", "collection")),
        "embedding": (report.embedding, ("provider", "model", "version")),
        "llm": (
            report.llm,
            ("provider", "configured_model", "reported_models"),
        ),
        "prompt": (report.prompt, ("name", "checksum")),
        "retrieval": (
            report.retrieval,
            ("top_k", "threshold", "filters", "rerank", "cache_policy"),
        ),
        "context": (
            report.context,
            (
                "maximum_tokens",
                "reserved_output_tokens",
                "effective_budget_tokens",
                "estimator",
            ),
        ),
        "generation": (
            report.generation,
            ("temperature", "top_p", "max_tokens", "timeout_seconds"),
        ),
    }
    missing: list[str] = []
    for group_name, (values, keys) in groups.items():
        for key in keys:
            value = values.get(key)
            if (
                key not in values
                or value is None
                or (isinstance(value, str) and not value.strip())
            ):
                missing.append(f"{group_name}.{key}")
    if not report.run_id.strip():
        missing.append("run_id")
    if not report.started_at.strip():
        missing.append("started_at")
    if not report.finished_at.strip():
        missing.append("finished_at")
    for index, case in enumerate(report.cases):
        for timing in (
            "retrieval_latency_seconds",
            "generation_latency_seconds",
            "end_to_end_latency_seconds",
        ):
            if getattr(case, timing) is None:
                missing.append(f"cases[{index}].{timing}")
    return missing


def _human_gates(
    report: QARunReport, review: ReviewFile, metrics: HumanMetrics
) -> list[GateOutcome]:
    failed_without_note = sum(
        item.disposition == "fail" and not item.disposition_note.strip()
        for item in review.reviews
    )
    return [
        _value_gate("mean_correctness", metrics.mean_correctness, ">=", 3.5),
        _value_gate(
            "minimum_answerable_correctness",
            metrics.minimum_answerable_correctness,
            ">=",
            2,
        ),
        _value_gate("mean_grounding", metrics.mean_grounding, ">=", 3.5),
        _value_gate(
            "mean_citation_coverage", metrics.mean_citation_coverage, ">=", 3.5
        ),
        _value_gate(
            "unsupported_material_claim_rate",
            metrics.unsupported_claim_case_rate.value,
            "<=",
            0.05,
        ),
        _value_gate(
            "uncertainty_handling",
            metrics.uncertainty_handling_pass_rate.value,
            ">=",
            1.0,
        ),
        GateOutcome(
            name="failed_case_dispositions",
            passed=failed_without_note == 0,
            actual=failed_without_note,
            requirement="every failed case has a documented disposition",
        ),
    ]


def _comparison_values(
    baseline: ScoredReport, candidate: ScoredReport
) -> dict[str, dict[str, float | None]]:
    names = [
        "recall_at_5",
        "mean_reciprocal_rank",
        "expected_source_in_context",
        "citation_validity",
        "citation_source_correctness",
        "citation_presence",
        "unanswerable_abstention_accuracy",
        "false_abstention_rate",
        "unsupported_answer_rate",
        "conflicting_uncertainty_presence",
    ]
    values = {
        name: {
            "baseline": getattr(baseline.run.automatic_metrics, name).value,
            "candidate": getattr(candidate.run.automatic_metrics, name).value,
        }
        for name in names
    }
    for name in ("mean_correctness", "mean_grounding", "mean_citation_coverage"):
        values[name] = {
            "baseline": getattr(baseline.human_metrics, name),
            "candidate": getattr(candidate.human_metrics, name),
        }
    values["median_end_to_end_latency"] = {
        "baseline": baseline.run.automatic_metrics.end_to_end_latency.median,
        "candidate": candidate.run.automatic_metrics.end_to_end_latency.median,
    }
    return values


def _compatibility_errors(baseline: ScoredReport, candidate: ScoredReport) -> list[str]:
    checks = {
        "benchmark checksum": (
            baseline.run.benchmark.get("checksum"),
            candidate.run.benchmark.get("checksum"),
        ),
        "workspace": (
            baseline.run.workspace.get("name"),
            candidate.run.workspace.get("name"),
        ),
        "collection": (
            baseline.run.workspace.get("collection"),
            candidate.run.workspace.get("collection"),
        ),
        "evaluation schema": (
            baseline.run.evaluation_schema_version,
            candidate.run.evaluation_schema_version,
        ),
        "scoring schema": (
            baseline.scoring_schema_version,
            candidate.scoring_schema_version,
        ),
        "rubric version": (
            baseline.review.get("rubric_version"),
            candidate.review.get("rubric_version"),
        ),
        "repeat count": (baseline.run.repeats, candidate.run.repeats),
    }
    return [name for name, (left, right) in checks.items() if left != right]


def _setting_differences(
    baseline: ScoredReport, candidate: ScoredReport
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for group in ("embedding", "llm", "prompt", "retrieval", "context", "generation"):
        left = getattr(baseline.run, group)
        right = getattr(candidate.run, group)
        for key in sorted(set(left) | set(right)):
            if left.get(key) != right.get(key):
                result[f"{group}.{key}"] = {
                    "baseline": left.get(key),
                    "candidate": right.get(key),
                }
    return result


def _case_failures(scored: ScoredReport) -> set[str]:
    reviews = {
        (item["case_id"], item["repeat_index"]): item
        for item in scored.review.get("entries", [])
    }
    failed: set[str] = set()
    for case in scored.run.cases:
        key = (case.case_id, case.repeat_index)
        automatic_failure = (
            case.status == "operational_failure"
            or bool(case.citations.invalid_labels)
            or (
                case.answerability == "answerable"
                and not case.measures.citation_present
            )
            or (case.measures.recall_at_5 is False)
            or (case.answerability == "unanswerable" and not case.measures.abstained)
            or (
                case.answerability == "conflicting"
                and not case.measures.conflicting_uncertainty_present
            )
        )
        review_failure = reviews.get(key, {}).get("disposition") == "fail"
        if automatic_failure or review_failure:
            failed.add(f"{case.case_id}#{case.repeat_index}")
    return failed


def _load_scored_or_designation(path: Path) -> ScoredReport:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if raw.get("designation_schema_version") == "1.0":
        target = path.parent / raw["scored_report"]
        content = target.read_bytes()
        if hashlib.sha256(content).hexdigest() != raw["scored_report_checksum"]:
            raise ComparisonError("baseline designation target checksum changed")
    else:
        content = path.read_bytes()
    try:
        return ScoredReport.model_validate_json(content)
    except ValidationError as error:
        raise ComparisonError(f"invalid scored report: {error}") from error


def _mean(values: list[int | None]) -> float | None:
    measured = [value for value in values if value is not None]
    return fmean(measured) if measured else None


def _rate(numerator: int, denominator: int) -> RateMetric:
    return RateMetric(
        value=numerator / denominator if denominator else None,
        numerator=numerator,
        denominator=denominator,
        status="measured" if denominator else "not_applicable",
    )


def _value_gate(
    name: str, value: float | None, operator: str, threshold: float
) -> GateOutcome:
    passed = value is not None and (
        value >= threshold if operator == ">=" else value <= threshold
    )
    return GateOutcome(
        name=name,
        passed=passed,
        actual=value,
        requirement=f"{operator} {threshold}",
        detail="not applicable" if value is None else "",
    )


def _write_json(path: Path, value: Any, *, overwrite: bool = False) -> None:
    _write_text(
        path,
        json.dumps(value, indent=2, ensure_ascii=False) + "\n",
        overwrite=overwrite,
    )


def _write_text(path: Path, value: str, *, overwrite: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not overwrite:
        raise FileExistsError(f"immutable artefact already exists: {path}")
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(value)
            handle.flush()
            os.fsync(handle.fileno())
        if path.exists() and not overwrite:
            raise FileExistsError(f"immutable artefact already exists: {path}")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
