"""Command-line adapter for QA evaluation operations."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from knowledge_assistant.config import Settings
from knowledge_assistant.managers.workspace_manager import (
    WorkspaceManager,
    WorkspaceNotFoundError,
)
from knowledge_assistant.qa_evaluation.benchmark import (
    BenchmarkValidationError,
    load_benchmark,
)
from knowledge_assistant.qa_evaluation.evaluator import run_qa_evaluation
from knowledge_assistant.qa_evaluation.models import QARunReport
from knowledge_assistant.qa_evaluation.reports import (
    ComparisonError,
    ReviewValidationError,
    compare_scored_reports,
    designate_baseline,
    score_review,
    write_review_template,
    write_run_artifacts,
)


def add_qa_evaluation_parser(commands: Any) -> None:
    """Add the M2.4 hierarchy without modifying the M1 evaluate command."""
    qa = commands.add_parser(
        "qa-evaluate", help="Evaluate the complete grounded question-answer pipeline."
    )
    actions = qa.add_subparsers(dest="qa_action", required=True)
    validate = actions.add_parser("validate", help="Validate a QA benchmark.")
    validate.add_argument("benchmark", type=Path)

    run = actions.add_parser("run", help="Run a QA benchmark sequentially.")
    run.add_argument("benchmark", type=Path)
    run.add_argument("--workspace", required=True)
    run.add_argument("--kind", required=True, choices=("baseline", "candidate"))
    run.add_argument("--repeat", type=int, default=1)
    run.add_argument("--verbose", action="store_true")

    template = actions.add_parser(
        "review-template", help="Create a review template from a raw run."
    )
    template.add_argument("report", type=Path)
    template.add_argument("--output", type=Path)

    score = actions.add_parser("score", help="Score a completed human review.")
    score.add_argument("report", type=Path)
    score.add_argument("--reviews", required=True, type=Path)

    baseline = actions.add_parser(
        "baseline", help="Designate a clean, scored run as baseline."
    )
    baseline.add_argument("report", type=Path)
    baseline.add_argument("--accept-failing", action="store_true")
    baseline.add_argument("--reason", default="")

    compare = actions.add_parser("compare", help="Compare two scored QA runs.")
    compare.add_argument("baseline", type=Path)
    compare.add_argument("candidate", type=Path)


def qa_action_needs_configuration(args: argparse.Namespace) -> bool:
    """Only model execution needs application/workspace configuration."""
    return args.qa_action == "run"


def handle_qa_evaluation(
    args: argparse.Namespace,
    settings: Settings | None = None,
    manager: WorkspaceManager | None = None,
) -> int:
    """Execute one QA evaluation action with documented exit-code semantics."""
    try:
        if args.qa_action == "validate":
            return _validate(args)
        if args.qa_action == "run":
            if settings is None or manager is None:
                raise ValueError("run requires application configuration")
            return _run(args, settings, manager)
        if args.qa_action == "review-template":
            return _review_template(args)
        if args.qa_action == "score":
            scored, json_path, markdown_path = score_review(args.report, args.reviews)
            print(f"Final gates: {'PASS' if scored.all_gates_passed else 'FAIL'}")
            print(f"Scored report: {json_path}")
            print(f"Summary: {markdown_path}")
            return 0 if scored.all_gates_passed else 1
        if args.qa_action == "baseline":
            designation, path = designate_baseline(
                args.report,
                accept_failing=args.accept_failing,
                reason=args.reason,
            )
            print(f"Baseline: {path}")
            print(f"Run: {designation['run_id']}")
            print(f"Accepted: {'yes' if designation['accepted'] else 'no'}")
            return 0 if designation["accepted"] else 1
        comparison, json_path, markdown_path = compare_scored_reports(
            args.baseline, args.candidate
        )
        print(f"Candidate: {'PASS' if comparison['candidate_passed'] else 'FAIL'}")
        print(f"Fixed cases: {len(comparison['fixed_cases'])}")
        print(f"Regressed cases: {len(comparison['regressed_cases'])}")
        print(f"Comparison: {json_path}")
        print(f"Summary: {markdown_path}")
        return 0 if comparison["candidate_passed"] else 1
    except (
        BenchmarkValidationError,
        ComparisonError,
        FileExistsError,
        json.JSONDecodeError,
        OSError,
        ReviewValidationError,
        ValidationError,
        ValueError,
        WorkspaceNotFoundError,
    ) as error:
        print(f"QA evaluation input error: {error}", file=sys.stderr)
        return 2


def _validate(args: argparse.Namespace) -> int:
    loaded = load_benchmark(args.benchmark)
    benchmark = loaded.benchmark
    print(f"Benchmark: {benchmark.benchmark_id} {benchmark.benchmark_version}")
    print(f"Schema: {benchmark.schema_version}")
    print(f"Cases: {len(benchmark.cases)}")
    for category, count in loaded.category_counts.items():
        print(f"{category.replace('_', ' ').title()}: {count}")
    print(f"Checksum: {loaded.checksum}")
    print("VALID")
    return 0


def _run(
    args: argparse.Namespace, settings: Settings, manager: WorkspaceManager
) -> int:
    if args.repeat <= 0:
        raise ValueError("repeat count must be greater than zero")
    loaded = load_benchmark(args.benchmark)
    workspace = manager.get(args.workspace)
    if not workspace.enabled:
        raise ValueError(f"workspace '{workspace.name}' is disabled")
    print(f"Workspace: {workspace.name}")
    print(
        f"Benchmark: {loaded.benchmark.benchmark_id} "
        f"{loaded.benchmark.benchmark_version} ({len(loaded.benchmark.cases)} cases)"
    )
    print(f"Model: {settings.llm.model}")

    def progress(index: int, total: int, case: Any) -> None:
        print(f"[{index}/{total}] {case.case_id:<24} {case.status.upper()}")
        if args.verbose and case.answer:
            print(f"  {case.answer}")
        if case.operational_error:
            print(f"  {case.operational_error}", file=sys.stderr)

    report = run_qa_evaluation(
        loaded,
        workspace,
        settings,
        run_kind=args.kind,
        repeats=args.repeat,
        progress=progress,
    )
    raw, _, review = write_run_artifacts(report, workspace.artifacts)
    passed = all(gate.passed is True for gate in report.automatic_gates)
    print(f"Automatic gates: {'PASS' if passed else 'FAIL'}")
    print("Human review: PENDING")
    print(f"Run: {raw}")
    print(f"Review template: {review}")
    return 1


def _review_template(args: argparse.Namespace) -> int:
    report = QARunReport.model_validate_json(args.report.read_bytes())
    output = args.output
    if output is None:
        stem = args.report.with_suffix("")
        output = stem.with_name(stem.name + ".review-template.json")
    path = write_review_template(report, output)
    print(f"Review template: {path}")
    return 0
