"""Validated loading of application configuration and local environment values."""

from __future__ import annotations

import os
from copy import deepcopy
from pathlib import Path
from typing import Any, Literal

import yaml
from dotenv import dotenv_values
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    ValidationError,
    field_validator,
    model_validator,
)


class ConfigurationError(ValueError):
    """Raised when application configuration cannot be read or validated."""


class _StrictModel(BaseModel):
    """Base model that rejects misspelled configuration keys."""

    model_config = ConfigDict(extra="forbid")


class ApplicationSettings(_StrictModel):
    """Application identity and runtime environment."""

    name: str = Field(min_length=1)
    version: str = Field(min_length=1, coerce_numbers_to_str=True)
    environment: str = Field(min_length=1)


class DocumentSettings(_StrictModel):
    """Document discovery options."""

    include: list[str] = Field(min_length=1)
    exclude: list[str] = Field(default_factory=list)
    recursive: bool = True


class SourceRootSettings(_StrictModel):
    """A named source location and its optional discovery-policy overrides."""

    name: str = Field(min_length=1)
    path: Path
    include: list[str] | None = None
    exclude: list[str] | None = None
    recursive: bool | None = None

    @field_validator("name")
    @classmethod
    def normalise_name(cls, name: str) -> str:
        normalised = name.strip()
        if not normalised:
            raise ValueError("must not be blank")
        return normalised


class WorkspaceDocumentSettings(_StrictModel):
    """Named roots and workspace-level defaults for document discovery."""

    unavailable_root: Literal["warn", "fatal"] = "warn"
    defaults: DocumentSettings | None = None
    roots: list[SourceRootSettings] = Field(min_length=1)

    @model_validator(mode="after")
    def roots_must_have_unique_names(self) -> WorkspaceDocumentSettings:
        names = [root.name.casefold() for root in self.roots]
        if len(names) != len(set(names)):
            raise ValueError("document source-root names must be unique")
        return self


class EvidenceLibrarySettings(_StrictModel):
    """External evidence-library control records and matching policies."""

    manifest: Path
    policy: Path
    missing_referenced_document: Literal["warn", "fatal"] = "warn"
    unmatched_document: Literal["ignore", "warn", "fatal"] = "warn"


class WorkspaceSettings(_StrictModel):
    """Configuration for an isolated knowledge workspace."""

    enabled: bool
    description: str = Field(min_length=1)
    documents: Path | WorkspaceDocumentSettings
    evidence_library: EvidenceLibrarySettings | None = None
    artifacts: Path
    collection: str = Field(min_length=1)

    @model_validator(mode="after")
    def roots_must_not_overlap(self) -> WorkspaceSettings:
        if isinstance(self.documents, Path):
            return self
        roots = self.documents.roots
        for index, root in enumerate(roots):
            root_path = Path(os.path.normcase(str(root.path)))
            for other in roots[index + 1 :]:
                other_path = Path(os.path.normcase(str(other.path)))
                try:
                    other_path.relative_to(root_path)
                    overlap = True
                except ValueError:
                    try:
                        root_path.relative_to(other_path)
                        overlap = True
                    except ValueError:
                        overlap = False
                if overlap:
                    raise ValueError(
                        f"document source roots '{root.name}' and '{other.name}' overlap"
                    )
        return self


class PdfLinkDownloadSettings(_StrictModel):
    """Rules for downloading document links embedded in PDFs."""

    allowed_hosts: list[str] = Field(default_factory=list)
    allowed_extensions: list[str] = Field(
        default_factory=lambda: [".pdf", ".txt", ".md"]
    )
    allowed_content_types: list[str] = Field(
        default_factory=lambda: ["application/pdf", "text/plain", "text/markdown"]
    )
    timeout_seconds: float = Field(default=30, gt=0)
    maximum_bytes: int = Field(default=50_000_000, gt=0)

    @field_validator("allowed_hosts")
    @classmethod
    def normalise_hosts(cls, hosts: list[str]) -> list[str]:
        return [host.lower().strip().lstrip(".") for host in hosts if host.strip()]

    @field_validator("allowed_extensions")
    @classmethod
    def normalise_extensions(cls, extensions: list[str]) -> list[str]:
        return [
            extension.lower() if extension.startswith(".") else f".{extension.lower()}"
            for extension in extensions
        ]

    @field_validator("allowed_content_types")
    @classmethod
    def normalise_content_types(cls, content_types: list[str]) -> list[str]:
        return [content_type.lower().strip() for content_type in content_types]


class ChunkingSettings(_StrictModel):
    """Text chunking options."""

    size: int = Field(gt=0)
    maximum_size: int = Field(default=1000, gt=0)
    minimum_size: int = Field(ge=0)
    overlap: int = Field(ge=0)
    strategy: str = Field(min_length=1)
    detect_headings: bool = True

    @field_validator("overlap")
    @classmethod
    def overlap_must_be_smaller_than_size(cls, overlap: int, info: Any) -> int:
        """Ensure each chunk retains some non-overlapping content."""
        size = info.data.get("size")
        if size is not None and overlap >= size:
            raise ValueError("must be smaller than chunking.size")
        return overlap

    @field_validator("minimum_size")
    @classmethod
    def minimum_size_must_not_exceed_size(cls, minimum_size: int, info: Any) -> int:
        size = info.data.get("size")
        if size is not None and minimum_size > size:
            raise ValueError("must not exceed chunking.size")
        return minimum_size

    @field_validator("maximum_size")
    @classmethod
    def maximum_size_must_not_be_smaller_than_target(
        cls, maximum_size: int, info: Any
    ) -> int:
        size = info.data.get("size")
        if size is not None and maximum_size < size:
            raise ValueError("must not be smaller than chunking.size")
        return maximum_size


class EmbeddingSettings(_StrictModel):
    """Embedding provider settings."""

    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    batch_size: int = Field(gt=0)
    version: str = Field(default="1", min_length=1)


class LLMSettings(_StrictModel):
    """Language-model generation settings."""

    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    thinking: bool | Literal["low", "medium", "high"] | None = None
    temperature: float = Field(ge=0, le=2)
    top_p: float = Field(gt=0, le=1)
    max_tokens: int = Field(gt=0)
    timeout_seconds: float = Field(default=120, gt=0)


class QuestionAnsweringSettings(_StrictModel):
    """Context and prompt settings for grounded single-question answering."""

    max_context_tokens: int = Field(default=4096, gt=0)
    reserved_output_tokens: int = Field(default=1024, gt=0)
    prompt_name: str = Field(default="question_answer", min_length=1)

    @model_validator(mode="after")
    def output_must_fit_context(self) -> QuestionAnsweringSettings:
        if self.reserved_output_tokens >= self.max_context_tokens:
            raise ValueError(
                "reserved_output_tokens must be smaller than max_context_tokens"
            )
        return self


class RetrievalSettings(_StrictModel):
    """Retrieval query settings."""

    top_k: int = Field(gt=0)
    similarity_threshold: float = Field(ge=0, le=1)
    max_context_length: int = Field(default=6000, ge=0)
    rerank: bool
    cache_policy: str = Field(default="reuse", min_length=1)


class StorageSettings(_StrictModel):
    """Vector-storage provider selection."""

    provider: str = Field(min_length=1)


class ChromaSettings(_StrictModel):
    """ChromaDB persistence settings."""

    directory: Path


class AnalysisSettings(_StrictModel):
    """Optional knowledge-analysis features."""

    detect_people: bool
    detect_decisions: bool
    detect_actions: bool
    detect_claims: bool
    detect_contradictions: bool


class PromptSettings(_StrictModel):
    """Locations of Markdown prompt templates."""

    question_answer: Path
    summarise: Path
    contradiction: Path
    planning: Path


class LoggingSettings(_StrictModel):
    """Application logging settings."""

    level: str = Field(min_length=1)
    console: bool
    file: Path

    @field_validator("level")
    @classmethod
    def validate_level(cls, level: str) -> str:
        """Normalise and validate standard Python logging levels."""
        normalised = level.upper()
        if normalised not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ValueError("must be a standard logging level")
        return normalised


class EnvironmentSettings(_StrictModel):
    """Values supplied exclusively by a local ``.env`` file."""

    ollama_host: HttpUrl | None = None
    openai_api_key: str | None = Field(default=None, repr=False)
    anthropic_api_key: str | None = Field(default=None, repr=False)
    huggingface_token: str | None = Field(default=None, repr=False)
    qdrant_host: str | None = None
    qdrant_port: int | None = Field(default=None, gt=0, le=65535)
    nas_host: str | None = None
    nas_username: str | None = Field(default=None, repr=False)
    nas_password: str | None = Field(default=None, repr=False)


class Settings(_StrictModel):
    """Complete, validated application configuration."""

    application: ApplicationSettings
    workspaces: dict[str, WorkspaceSettings] = Field(min_length=1)
    documents: DocumentSettings
    pdf_link_download: PdfLinkDownloadSettings = Field(
        default_factory=PdfLinkDownloadSettings
    )
    chunking: ChunkingSettings
    embedding: EmbeddingSettings
    llm: LLMSettings
    question_answering: QuestionAnsweringSettings = Field(
        default_factory=QuestionAnsweringSettings
    )
    retrieval: RetrievalSettings
    storage: StorageSettings
    chroma: ChromaSettings
    analysis: AnalysisSettings
    prompts: PromptSettings
    logging: LoggingSettings
    environment: EnvironmentSettings = Field(
        default_factory=EnvironmentSettings, exclude=True
    )


def load_settings(
    config_path: str | Path, env_path: str | Path | None = None
) -> Settings:
    """Load validated YAML configuration and local environment values.

    Relative paths in YAML are resolved against the directory that contains the
    ``config`` directory. Environment values are read only from ``env_path``;
    process environment variables are deliberately not consulted.
    """
    configuration_file = Path(config_path).expanduser().resolve()
    if not configuration_file.is_file():
        raise ConfigurationError(
            f"Configuration file does not exist: {configuration_file}"
        )

    try:
        with configuration_file.open(encoding="utf-8") as file:
            raw_config = yaml.safe_load(file)
    except (OSError, yaml.YAMLError) as error:
        raise ConfigurationError(f"Unable to read configuration: {error}") from error

    if not isinstance(raw_config, dict):
        raise ConfigurationError("Configuration root must be a YAML mapping")

    raw_config["environment"] = _load_environment(env_path)
    return validate_settings_mapping(raw_config, configuration_file.parent.parent)


def validate_settings_mapping(config: dict[str, Any], base_directory: Path) -> Settings:
    """Validate an in-memory configuration without writing it to disk."""
    candidate = deepcopy(config)
    _resolve_configured_paths(candidate, base_directory)
    try:
        return Settings.model_validate(candidate)
    except ValidationError as error:
        raise ConfigurationError(f"Invalid configuration: {error}") from error


def _load_environment(env_path: str | Path | None) -> dict[str, str]:
    """Read declared local environment values without modifying ``os.environ``."""
    if env_path is None:
        return {}

    environment_file = Path(env_path).expanduser().resolve()
    if not environment_file.is_file():
        raise ConfigurationError(f"Environment file does not exist: {environment_file}")

    values = dotenv_values(environment_file)
    mapping = {
        "OLLAMA_HOST": "ollama_host",
        "OPENAI_API_KEY": "openai_api_key",
        "ANTHROPIC_API_KEY": "anthropic_api_key",
        "HUGGINGFACE_TOKEN": "huggingface_token",
        "QDRANT_HOST": "qdrant_host",
        "QDRANT_PORT": "qdrant_port",
        "NAS_HOST": "nas_host",
        "NAS_USERNAME": "nas_username",
        "NAS_PASSWORD": "nas_password",
    }
    return {
        target: values[source]
        for source, target in mapping.items()
        if values.get(source)
    }


def _resolve_configured_paths(config: dict[str, Any], base_directory: Path) -> None:
    """Resolve known YAML paths without altering absolute document locations."""
    for workspace in config.get("workspaces", {}).values():
        if isinstance(workspace, dict):
            documents = workspace.get("documents")
            if isinstance(documents, dict):
                for root in documents.get("roots", []):
                    if isinstance(root, dict) and "path" in root:
                        root["path"] = _resolve_path(root["path"], base_directory)
            elif "documents" in workspace:
                workspace["documents"] = _resolve_path(documents, base_directory)
            if "artifacts" in workspace:
                workspace["artifacts"] = _resolve_path(
                    workspace["artifacts"], base_directory
                )
            evidence_library = workspace.get("evidence_library")
            if isinstance(evidence_library, dict):
                for key in ("manifest", "policy"):
                    if key in evidence_library:
                        evidence_library[key] = _resolve_path(
                            evidence_library[key], base_directory
                        )

    for section, keys in {
        "chroma": ("directory",),
        "prompts": ("question_answer", "summarise", "contradiction", "planning"),
        "logging": ("file",),
    }.items():
        settings = config.get(section)
        if isinstance(settings, dict):
            for key in keys:
                if key in settings:
                    settings[key] = _resolve_path(settings[key], base_directory)


def _resolve_path(value: Any, base_directory: Path) -> Path:
    """Convert a configured path to an absolute path."""
    path = Path(value).expanduser()
    return path if path.is_absolute() else (base_directory / path).resolve()
