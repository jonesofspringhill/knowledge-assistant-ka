"""Loading of configured Markdown prompt templates."""

from pathlib import Path

from knowledge_assistant.config import PromptSettings


class PromptNotFoundError(KeyError):
    """Raised when a requested prompt has no configured template."""


class PromptManager:
    """Read prompt templates declared in application configuration."""

    def __init__(self, prompts: PromptSettings) -> None:
        self._prompts = prompts

    def names(self) -> tuple[str, ...]:
        """Return configured prompt names in configuration order."""
        return tuple(type(self._prompts).model_fields)

    def get(self, name: str) -> str:
        """Return Markdown text for a named configured prompt."""
        if name not in self.names():
            raise PromptNotFoundError(f"Unknown prompt: {name}")
        path: Path = getattr(self._prompts, name)
        try:
            return path.read_text(encoding="utf-8")
        except OSError as error:
            raise RuntimeError(f"Unable to load prompt '{name}': {path}") from error
