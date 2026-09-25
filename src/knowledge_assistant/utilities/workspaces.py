"""Safe workspace creation and pipeline orchestration utilities."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import yaml

from knowledge_assistant.chunking import chunk_workspace
from knowledge_assistant.config import (
    ConfigurationError,
    load_settings,
    validate_settings_mapping,
)
from knowledge_assistant.evidence.service import (
    EvidenceLibraryError,
    load_evidence_library,
    write_control_artifact,
)
from knowledge_assistant.ingestion import RootOutcome, ingest_workspace
from knowledge_assistant.managers import WorkspaceManager, WorkspaceNotFoundError
from knowledge_assistant.retrieval import (
    generate_embeddings,
    index_workspace,
    verify_index,
)


class WorkspaceUtilityError(ValueError):
    """Raised when a workspace utility cannot complete safely."""

    def __init__(self, message: str, *, exit_code: int = 2) -> None:
        super().__init__(message)
        self.exit_code = exit_code


@dataclass(frozen=True, slots=True)
class PipelineSummary:
    """Concise result of a workspace pipeline run."""

    workspace: str
    scope: str
    root_outcomes: tuple[RootOutcome, ...]
    added_or_updated: int
    retained: int
    failed: int
    documents_removed: int
    chunks_removed: int
    embeddings_removed: int
    vectors_removed: int
    ingestion_artifacts: Path
    chunk_artifacts: Path
    embedding_artifacts: Path
    index_size: int
    metadata_schema: str | None = None
    metadata_associations: int = 0
    control_reviews: int = 0
    metadata_warnings: tuple[str, ...] = ()
    control_artifact: Path | None = None


def parse_document_root(value: str) -> tuple[str, Path]:
    """Parse ``name=path`` source-root syntax used by the public utilities."""
    name, separator, raw_path = value.partition("=")
    if not separator or not name.strip() or not raw_path.strip():
        raise WorkspaceUtilityError(
            "document roots must use the form name=path, for example evidence=D:/docs"
        )
    return name.strip(), Path(raw_path.strip())


def create_workspace(
    config_path: Path,
    name: str,
    roots: list[tuple[str, Path]],
    *,
    description: str | None = None,
    collection: str | None = None,
    enabled: bool = True,
    confirm: bool = False,
) -> Path:
    """Add a validated multi-root workspace and create only its artefact root."""
    if not confirm:
        raise WorkspaceUtilityError("workspace creation requires --yes")
    if not name.strip() or not roots:
        raise WorkspaceUtilityError(
            "a workspace name and at least one document root are required"
        )
    try:
        raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        raise WorkspaceUtilityError(f"unable to read configuration: {error}") from error
    if not isinstance(raw, dict) or not isinstance(raw.get("workspaces"), dict):
        raise WorkspaceUtilityError("configuration has no valid workspaces section")
    if name in raw["workspaces"]:
        raise WorkspaceUtilityError(f"workspace '{name}' already exists")
    defaults = raw.get("documents")
    if not isinstance(defaults, dict):
        raise WorkspaceUtilityError("configuration has no valid document defaults")
    raw["workspaces"][name] = {
        "enabled": enabled,
        "description": description or f"{name} knowledge workspace",
        "documents": {
            "unavailable_root": "warn",
            "defaults": defaults,
            "roots": [
                {"name": root_name, "path": str(path)} for root_name, path in roots
            ],
        },
        "artifacts": f"workspaces/{name}/artifacts",
        "collection": collection or name,
    }
    try:
        settings = validate_settings_mapping(raw, config_path.resolve().parent.parent)
    except ConfigurationError as error:
        raise WorkspaceUtilityError(str(error)) from error
    workspace = WorkspaceManager(settings.workspaces).get(name)
    try:
        config_path.write_text(
            yaml.safe_dump(raw, sort_keys=False, allow_unicode=True), encoding="utf-8"
        )
        workspace.artifacts.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        raise WorkspaceUtilityError(f"unable to create workspace: {error}") from error
    return workspace.artifacts


def run_workspace_pipeline(
    config_path: Path,
    env_path: Path | None,
    workspace_name: str,
    *,
    root: str | None = None,
    rebuild_index: bool = False,
    force_extraction: bool = False,
    embedder: Callable[[list[str]], list[list[float]]] | None = None,
) -> PipelineSummary:
    """Run ingestion through verified indexing without changing active workspace."""
    try:
        settings = load_settings(config_path, env_path)
    except ConfigurationError as error:
        raise WorkspaceUtilityError(str(error)) from error
    try:
        workspace = WorkspaceManager(settings.workspaces).get(workspace_name)
    except WorkspaceNotFoundError as error:
        raise WorkspaceUtilityError(str(error)) from error
    if not workspace.enabled:
        raise WorkspaceUtilityError(f"workspace '{workspace_name}' is disabled")
    selected_roots = {root} if root else None
    try:
        evidence_library = load_evidence_library(workspace)
        control_artifact = (
            write_control_artifact(evidence_library, workspace.artifacts / "metadata")
            if evidence_library
            else None
        )
    except (EvidenceLibraryError, OSError) as error:
        raise WorkspaceUtilityError(
            f"evidence metadata validation failed: {error}", exit_code=2
        ) from error
    try:
        ingestion = ingest_workspace(
            workspace,
            settings.documents,
            roots=selected_roots,
            evidence_library=evidence_library,
            force=force_extraction,
        )
    except (OSError, ValueError) as error:
        raise WorkspaceUtilityError(str(error), exit_code=2) from error
    if ingestion.failures:
        detail = ingestion.failures[0]
        raise WorkspaceUtilityError(
            f"ingestion failed for root '{detail.source_root}' at "
            f"'{detail.relative_path}': {detail.message}",
            exit_code=1,
        )
    try:
        chunking = chunk_workspace(workspace, settings.chunking)
    except OSError as error:
        raise WorkspaceUtilityError(f"chunking failed: {error}", exit_code=1) from error
    if chunking.failures:
        raise WorkspaceUtilityError("chunking completed with failures", exit_code=1)
    try:
        embeddings = generate_embeddings(
            workspace, settings.embedding, embedder=embedder
        )
    except OSError as error:
        raise WorkspaceUtilityError(
            f"embedding failed: {error}", exit_code=1
        ) from error
    if embeddings.failures:
        raise WorkspaceUtilityError("embedding completed with failures", exit_code=1)
    try:
        indexing = index_workspace(
            workspace, settings.chroma.directory, rebuild=rebuild_index
        )
    except Exception as error:
        raise WorkspaceUtilityError(f"indexing failed: {error}", exit_code=1) from error
    if indexing.failures:
        raise WorkspaceUtilityError("indexing completed with failures", exit_code=1)
    try:
        verified, expected, actual = verify_index(workspace, settings.chroma.directory)
    except Exception as error:
        raise WorkspaceUtilityError(
            f"index verification failed: {error}", exit_code=1
        ) from error
    if not verified:
        raise WorkspaceUtilityError(
            f"index verification failed: expected {expected} vectors, found {actual}",
            exit_code=1,
        )
    outcomes = tuple(ingestion.root_outcomes)
    return PipelineSummary(
        workspace=workspace.name,
        scope=root or "all",
        root_outcomes=outcomes,
        added_or_updated=sum(item.added_or_updated for item in outcomes),
        retained=sum(item.retained for item in outcomes),
        failed=sum(item.failed for item in outcomes),
        documents_removed=sum(item.removed for item in outcomes),
        chunks_removed=chunking.chunks_removed,
        embeddings_removed=embeddings.embeddings_removed,
        vectors_removed=indexing.deleted,
        ingestion_artifacts=ingestion.artifact_directory,
        chunk_artifacts=chunking.artifact_directory,
        embedding_artifacts=embeddings.artifact_directory,
        index_size=indexing.index_size,
        metadata_schema=(evidence_library.schema_version if evidence_library else None),
        metadata_associations=(
            evidence_library.summary.associations if evidence_library else 0
        ),
        control_reviews=(
            evidence_library.summary.claim_reviews if evidence_library else 0
        ),
        metadata_warnings=(
            tuple(item.message for item in evidence_library.validation_issues)
            if evidence_library
            else ()
        ),
        control_artifact=control_artifact,
    )
