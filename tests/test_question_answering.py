"""Tests for grounded single-question answering."""

from pathlib import Path

import pytest

from knowledge_assistant.config import (
    EmbeddingSettings,
    EnvironmentSettings,
    LLMSettings,
    QuestionAnsweringSettings,
    RetrievalSettings,
)
from knowledge_assistant.managers.workspace_manager import Workspace
from knowledge_assistant.question_answering.context import (
    ContextBudgetError,
    build_context,
)
from knowledge_assistant.question_answering.service import (
    _structured_output,
    answer_question,
)
from knowledge_assistant.retrieval.models import SearchResult


class PromptStub:
    def __init__(self, text: str) -> None:
        self.text = text

    def get(self, name: str) -> str:
        assert name == "question_answer"
        return self.text


class GeneratorStub:
    model = "test-model"

    def __init__(self) -> None:
        self.prompts: list[str] = []

    def generate(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return "The grant limit is £10,000. [S1]"


class StructuredGeneratorStub(GeneratorStub):
    def generate(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return (
            "Status: INSUFFICIENT_EVIDENCE\n\n"
            "Answer:\nThe evidence does not answer the question.\n\n"
            "Evidence:\nNone.\n\n"
            "Uncertainty:\nNo supplied source addresses the requested fact.\n\n"
            "Reasoning:\nThe requested fact is absent."
        )


class ConflictIgnoringGeneratorStub(GeneratorStub):
    def generate(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return (
            "Status: ANSWERED\n\n"
            "Answer:\nThe authoritative deadline is 5 October 2026. [S1]\n\n"
            "Evidence:\n[S1]\n\n"
            "Uncertainty:\nNone. The context explicitly states the deadline.\n\n"
            "Reasoning:\nThe date is stated directly."
        )


def _workspace(tmp_path: Path) -> Workspace:
    return Workspace(
        "example",
        "Example",
        tmp_path / "documents",
        tmp_path / "artifacts",
        "example",
        True,
    )


def _result(text: str, *, chunk_id: str = "chunk-1") -> SearchResult:
    return SearchResult(
        chunk_id=chunk_id,
        document_id="document-1",
        document_title="Funding Guide",
        section_title="Limits",
        source_filename="funding.md",
        relative_path=Path("funding.md"),
        source_path=Path("default/funding.md"),
        source_location="default/funding.md section Limits",
        similarity=0.9,
        text=text,
    )


def _settings() -> tuple[RetrievalSettings, EmbeddingSettings, LLMSettings]:
    return (
        RetrievalSettings(top_k=5, similarity_threshold=0, rerank=False),
        EmbeddingSettings(provider="test", model="embed", batch_size=1),
        LLMSettings(
            provider="ollama",
            model="qwen3:8b",
            temperature=0.2,
            top_p=0.95,
            max_tokens=100,
        ),
    )


def test_context_builder_deduplicates_and_preserves_ranked_whole_chunks() -> None:
    evidence = [_result("A short fact."), _result("A short fact.", chunk_id="chunk-2")]
    selection = build_context(
        "What is the fact?",
        evidence,
        "Question: {question}\nContext: {context}\nSources: {sources}",
        max_context_tokens=100,
        reserved_output_tokens=20,
    )

    assert len(selection.evidence) == 1
    assert "A short fact." in selection.context
    assert selection.sources[0].startswith("[S1]")


def test_context_builder_rejects_evidence_that_cannot_fit() -> None:
    with pytest.raises(ContextBudgetError, match="too small"):
        build_context(
            "Question",
            [_result("x" * 1000)],
            "{question}\n{context}\n{sources}",
            max_context_tokens=20,
            reserved_output_tokens=10,
        )


def test_answer_question_abstains_without_invoking_generator(tmp_path: Path) -> None:
    retrieval, embedding, llm = _settings()
    generator = GeneratorStub()

    def searcher(*args, **kwargs):
        return [], 0.01

    result = answer_question(
        _workspace(tmp_path),
        tmp_path / "chroma",
        retrieval,
        embedding,
        llm,
        EnvironmentSettings(),
        PromptStub("{question}\n{context}\n{sources}"),
        "What is missing?",
        generator=generator,
        searcher=searcher,
    )

    assert result.status == "insufficient_evidence"
    assert result.citations == []
    assert generator.prompts == []


def test_answer_question_preserves_citations_and_prompt_context(tmp_path: Path) -> None:
    retrieval, embedding, llm = _settings()
    generator = GeneratorStub()
    evidence = [_result("The grant limit is £10,000.")]

    def searcher(*args, **kwargs):
        return evidence, 0.02

    result = answer_question(
        _workspace(tmp_path),
        tmp_path / "chroma",
        retrieval,
        embedding,
        llm,
        EnvironmentSettings(),
        PromptStub("Question: {question}\nContext: {context}\nSources: {sources}"),
        "What is the grant limit?",
        qa_settings=QuestionAnsweringSettings(
            max_context_tokens=200, reserved_output_tokens=50
        ),
        generator=generator,
        searcher=searcher,
    )

    assert result.status == "answered"
    assert result.citations[0].label == "S1"
    assert result.citations[0].source == "Funding Guide (Limits)"
    assert "The grant limit" in generator.prompts[0]
    assert "[S1]" in generator.prompts[0]


def test_answer_question_reads_exact_structured_status_and_uncertainty(
    tmp_path: Path,
) -> None:
    retrieval, embedding, llm = _settings()
    generator = StructuredGeneratorStub()

    result = answer_question(
        _workspace(tmp_path),
        tmp_path / "chroma",
        retrieval,
        embedding,
        llm,
        EnvironmentSettings(),
        PromptStub("{question}\n{context}\n{sources}"),
        "What is absent?",
        generator=generator,
        searcher=lambda *args, **kwargs: ([_result("Unrelated evidence.")], 0.01),
    )

    assert result.status == "insufficient_evidence"
    assert result.uncertainty == "No supplied source addresses the requested fact."
    assert result.model == "test-model"


def test_structured_output_does_not_treat_none_with_explanation_as_uncertainty() -> None:
    status, uncertainty = _structured_output(
        "Status: ANSWERED\n\nUncertainty:\nNone. The context is explicit."
    )

    assert status == "answered"
    assert uncertainty is None


def test_answer_question_blocks_unqualified_answer_when_evidence_requires_confirmation(
    tmp_path: Path,
) -> None:
    retrieval, embedding, llm = _settings()
    generator = ConflictIgnoringGeneratorStub()
    evidence = [
        _result(
            "The current form gives 5 October 2026, but KHH should confirm the "
            "deadline because an older indexed form gives a different date."
        )
    ]

    result = answer_question(
        _workspace(tmp_path),
        tmp_path / "chroma",
        retrieval,
        embedding,
        llm,
        EnvironmentSettings(),
        PromptStub("{question}\n{context}\n{sources}"),
        "What is the authoritative deadline?",
        generator=generator,
        searcher=lambda *args, **kwargs: (evidence, 0.01),
    )

    assert result.status == "insufficient_evidence"
    assert result.uncertainty is not None
    assert "evidence-conflict safeguard" in result.answer
    assert "[S1]" in result.answer


def test_unrelated_deadline_conflict_does_not_block_supported_amount(
    tmp_path: Path,
) -> None:
    retrieval, embedding, llm = _settings()
    generator = GeneratorStub()
    evidence = [
        _result(
            "The grant request is £2,500. KHH should confirm the deadline because "
            "an older indexed form gives a different date."
        )
    ]

    result = answer_question(
        _workspace(tmp_path),
        tmp_path / "chroma",
        retrieval,
        embedding,
        llm,
        EnvironmentSettings(),
        PromptStub("{question}\n{context}\n{sources}"),
        "How much does the grant request ask for?",
        generator=generator,
        searcher=lambda *args, **kwargs: (evidence, 0.01),
    )

    assert result.status == "answered"
    assert result.uncertainty is None
