"""Ollama-backed language-model adapter."""

from __future__ import annotations

from typing import Any

from ollama import Client

from knowledge_assistant.config import EnvironmentSettings, LLMSettings
from knowledge_assistant.llm.base import LLMInvocationError


class OllamaLLM:
    """Generate text through the configured Ollama chat model."""

    def __init__(self, settings: LLMSettings, environment: EnvironmentSettings) -> None:
        self.settings = settings
        self.environment = environment

    @property
    def model(self) -> str:
        """Return the configured model identifier."""
        return self.settings.model

    def generate(self, prompt: str) -> str:
        """Generate one response, retrying one transient empty response."""
        host = (
            str(self.environment.ollama_host) if self.environment.ollama_host else None
        )
        try:
            client = Client(host=host, timeout=self.settings.timeout_seconds)
            for _attempt in range(2):
                response: Any = client.chat(
                    model=self.settings.model,
                    messages=[{"role": "user", "content": prompt}],
                    options={
                        "temperature": self.settings.temperature,
                        "top_p": self.settings.top_p,
                        "num_predict": self.settings.max_tokens,
                    },
                )
                content = _response_content(response)
                if content:
                    return content
        except Exception as error:
            raise LLMInvocationError(
                f"Unable to invoke Ollama model '{self.settings.model}': {error}"
            ) from error
        raise LLMInvocationError(
            f"Ollama model '{self.settings.model}' returned an empty response twice."
        )


def _response_content(response: Any) -> str:
    if isinstance(response, dict):
        message = response.get("message")
        if isinstance(message, dict):
            content = message.get("content")
        else:
            content = None
    else:
        message = getattr(response, "message", None)
        content = getattr(message, "content", None)
    return str(content).strip() if content is not None else ""
