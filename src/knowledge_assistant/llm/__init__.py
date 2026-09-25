"""Language-model contracts and registered adapters."""

from knowledge_assistant.llm.base import LLMInvocationError, TextGenerator
from knowledge_assistant.llm.ollama import OllamaLLM
from knowledge_assistant.llm.providers import (
    create_text_generator,
    register_provider,
    registered_providers,
)

register_provider("ollama", OllamaLLM)

__all__ = [
    "LLMInvocationError",
    "OllamaLLM",
    "TextGenerator",
    "create_text_generator",
    "register_provider",
    "registered_providers",
]
