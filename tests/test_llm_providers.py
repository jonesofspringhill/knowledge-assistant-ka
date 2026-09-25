"""Provider registration keeps grounded answers independent from a transport."""

import pytest

from knowledge_assistant.config import EnvironmentSettings, LLMSettings
from knowledge_assistant.llm import (
    LLMInvocationError,
    create_text_generator,
    register_provider,
)


class StubGenerator:
    model = "stub-model"

    def generate(self, prompt: str) -> str:
        return f"generated: {prompt}"


def _settings(provider: str) -> LLMSettings:
    return LLMSettings(
        provider=provider,
        model="stub-model",
        temperature=0,
        top_p=1,
        max_tokens=10,
    )


def test_provider_registry_constructs_a_registered_adapter() -> None:
    name = "test-stub"
    register_provider(
        name, lambda _settings, _environment: StubGenerator(), replace=True
    )
    generator = create_text_generator(_settings(name), EnvironmentSettings())
    assert generator.model == "stub-model"
    assert generator.generate("question") == "generated: question"


def test_provider_registry_reports_unknown_adapter() -> None:
    with pytest.raises(LLMInvocationError, match="No language-model adapter"):
        create_text_generator(_settings("unknown-provider"), EnvironmentSettings())
