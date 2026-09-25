"""Loading, byte-level identity, and governance checks for QA benchmarks."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from knowledge_assistant.qa_evaluation.models import QABenchmark

REPOSITORY_CATEGORY_MINIMUMS = {
    "direct_fact": 5,
    "document_discovery": 3,
    "metadata_filtered": 3,
    "temporal": 2,
    "cross_document": 3,
    "evidence_comparison": 3,
    "unanswerable": 3,
    "conflicting": 2,
}


class BenchmarkValidationError(ValueError):
    """Raised before any retrieval or model call when a benchmark is invalid."""


@dataclass(frozen=True, slots=True)
class LoadedBenchmark:
    """A validated benchmark plus its exact byte identity."""

    path: Path
    benchmark: QABenchmark
    checksum: str
    category_counts: dict[str, int]


def load_benchmark(
    path: str | Path, *, repository_acceptance: bool | None = None
) -> LoadedBenchmark:
    """Load strict JSON and compute SHA-256 from the exact bytes read."""
    benchmark_path = Path(path).expanduser().resolve()
    try:
        content = benchmark_path.read_bytes()
        raw = json.loads(content)
        benchmark = QABenchmark.model_validate(raw)
    except OSError as error:
        raise BenchmarkValidationError(f"unable to read benchmark: {error}") from error
    except json.JSONDecodeError as error:
        raise BenchmarkValidationError(
            f"benchmark is not valid JSON: {error}"
        ) from error
    except ValidationError as error:
        raise BenchmarkValidationError(f"invalid QA benchmark: {error}") from error

    acceptance = (
        benchmark.benchmark_id == "m2.4-qa-acceptance"
        if repository_acceptance is None
        else repository_acceptance
    )
    counts = Counter(case.category for case in benchmark.cases)
    if acceptance:
        _validate_repository_acceptance(benchmark, counts)
    return LoadedBenchmark(
        path=benchmark_path,
        benchmark=benchmark,
        checksum=hashlib.sha256(content).hexdigest(),
        category_counts=dict(sorted(counts.items())),
    )


def _validate_repository_acceptance(
    benchmark: QABenchmark, counts: Counter[str]
) -> None:
    count = len(benchmark.cases)
    if not 20 <= count <= 30:
        raise BenchmarkValidationError(
            "repository acceptance benchmark must contain 20-30 cases"
        )
    if count < 25:
        raise BenchmarkValidationError(
            "repository acceptance benchmark must contain at least 25 cases"
        )
    missing = [
        f"{category}={counts[category]} (requires {minimum})"
        for category, minimum in REPOSITORY_CATEGORY_MINIMUMS.items()
        if counts[category] < minimum
    ]
    if missing:
        raise BenchmarkValidationError(
            "repository category coverage is incomplete: " + ", ".join(missing)
        )
    for case in benchmark.cases:
        if case.category == "metadata_filtered" and not case.filters:
            raise BenchmarkValidationError(
                f"metadata-filtered case '{case.id}' must define filters"
            )
        if case.category == "unanswerable" and case.answerability != "unanswerable":
            raise BenchmarkValidationError(
                f"unanswerable case '{case.id}' has incompatible answerability"
            )
        if case.category == "conflicting" and case.answerability != "conflicting":
            raise BenchmarkValidationError(
                f"conflicting case '{case.id}' has incompatible answerability"
            )
