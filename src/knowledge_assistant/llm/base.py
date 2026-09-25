"""Provider-neutral contracts for language-model adapters."""

from __future__ import annotations

from typing import Protocol


class LLMInvocationError(RuntimeError):
    """Raised when a configured language-model adapter cannot complete a request."""


class TextGenerator(Protocol):
    """Smallest contract required by grounded answers and future agent tools."""

    @property
    def model(self) -> str:
        """Return the configured model identifier."""

    def generate(self, prompt: str) -> str:
        """Generate text from a fully rendered prompt."""
