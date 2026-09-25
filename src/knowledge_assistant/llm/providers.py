"""Registry that keeps application services independent of model transports."""

from __future__ import annotations

from collections.abc import Callable

from knowledge_assistant.config import EnvironmentSettings, LLMSettings
from knowledge_assistant.llm.base import LLMInvocationError, TextGenerator

ProviderFactory = Callable[[LLMSettings, EnvironmentSettings], TextGenerator]
_PROVIDERS: dict[str, ProviderFactory] = {}


def register_provider(
    name: str, factory: ProviderFactory, *, replace: bool = False
) -> None:
    """Register one named adapter without coupling the application to its SDK."""
    key = name.strip().casefold()
    if not key:
        raise ValueError("provider name must not be blank")
    if key in _PROVIDERS and not replace:
        raise ValueError(f"provider '{name}' is already registered")
    _PROVIDERS[key] = factory


def create_text_generator(
    settings: LLMSettings, environment: EnvironmentSettings
) -> TextGenerator:
    """Resolve the configured provider and give a useful error for unavailable ones."""
    try:
        factory = _PROVIDERS[settings.provider.casefold()]
    except KeyError as error:
        choices = ", ".join(sorted(_PROVIDERS)) or "none"
        raise LLMInvocationError(
            f"No language-model adapter is registered for '{settings.provider}'. "
            f"Available providers: {choices}."
        ) from error
    return factory(settings, environment)


def registered_providers() -> tuple[str, ...]:
    """Return registered provider names for diagnostics and tests."""
    return tuple(sorted(_PROVIDERS))
