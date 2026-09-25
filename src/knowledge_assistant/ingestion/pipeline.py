"""Discovery, normalisation, and artefact writing for workspace documents."""

from __future__ import annotations

import json
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

from pydantic import ValidationError

from knowledge_assistant.config import DocumentSettings
from knowledge_assistant.evidence.models import EvidenceLibrary
from knowledge_assistant.ingestion.cache import ExtractionCache, checksum
from knowledge_assistant.ingestion.extractors import EXTRACTORS
from knowledge_assistant.ingestion.models import (
    Document,
    IngestionFailure,
    IngestionSummary,
    RootOutcome,
)
from knowledge_assistant.managers.workspace_manager import SourceRoot, Workspace


def discover_documents(
    root: Path, settings: DocumentSettings
) -> tuple[list[Path], list[Path]]:
    """Return supported files and ignored files below a workspace document root."""
    if not root.is_dir():
        raise FileNotFoundError(f"Document directory does not exist: {root}")
    candidates = root.rglob("*") if settings.recursive else root.glob("*")
    supported: list[Path] = []
    ignored: list[Path] = []
    excluded = {item.strip("/\\") for item in settings.exclude}
    for path in sorted(candidate for candidate in candidates if candidate.is_file()):
        relative = path.relative_to(root)
        if any(part in excluded for part in relative.parts[:-1]):
            continue
        included = any(relative.match(pattern) for pattern in settings.include)
        if path.suffix.lower() in EXTRACTORS and included:
            supported.append(path)
        else:
            ignored.append(relative)
    return supported, ignored


def ingest_workspace(
    workspace: Workspace,
    settings: DocumentSettings,
    *,
    roots: set[str] | None = None,
    evidence_library: EvidenceLibrary | None = None,
    force: bool = False,
) -> IngestionSummary:
    """Ingest and safely reconcile selected roots in one workspace."""
    started = time.monotonic()
    source_roots = workspace.sources or (SourceRoot("default", workspace.documents),)
    selected = _selected_root_names(source_roots, roots)
    unavailable = [
        root
        for root in source_roots
        if root.name in selected and not root.path.is_dir()
    ]
    if unavailable and (
        workspace.legacy_documents or workspace.unavailable_root == "fatal"
    ):
        details = ", ".join(f"'{root.name}' ({root.path})" for root in unavailable)
        raise FileNotFoundError(f"Unavailable document source root(s): {details}")

    artifact_directory = workspace.artifacts / "ingestion"
    cache = ExtractionCache(workspace.artifacts / "extraction-cache", force=force)
    existing = _read_existing_documents(artifact_directory, workspace.name)
    documents: list[Document] = []
    failures: list[IngestionFailure] = []
    ignored: list[Path] = []
    outcomes: list[RootOutcome] = []
    removed_ids: set[str] = set()

    for source_root in source_roots:
        previous = {
            identifier: document
            for identifier, document in existing.items()
            if document.source_root == source_root.name
        }
        if source_root.name not in selected:
            outcomes.append(
                RootOutcome(
                    name=source_root.name,
                    path=source_root.path,
                    selected=False,
                    status="unselected",
                    retained=len(previous),
                )
            )
            continue
        if source_root in unavailable:
            outcomes.append(
                RootOutcome(
                    name=source_root.name,
                    path=source_root.path,
                    selected=True,
                    status="unavailable",
                    retained=len(previous),
                    message="source root is unavailable; existing records were retained",
                )
            )
            continue
        try:
            files, root_ignored = discover_documents(
                source_root.path, source_root.settings or settings
            )
        except OSError as error:
            failures.append(
                IngestionFailure(
                    source_root=source_root.name,
                    relative_path=Path("."),
                    message=f"unable to scan {source_root.path}: {error}",
                )
            )
            outcomes.append(
                RootOutcome(
                    name=source_root.name,
                    path=source_root.path,
                    selected=True,
                    status="failed",
                    failed=1,
                    retained=len(previous),
                    message=str(error),
                )
            )
            continue

        ignored.extend(Path(source_root.name) / path for path in root_ignored)
        current_ids = {
            _document_id(
                workspace.name, source_root.name, path.relative_to(source_root.path)
            )
            for path in files
        }
        added_or_updated = retained = processed = failed = 0
        for path in files:
            relative = path.relative_to(source_root.path)
            identifier = _document_id(workspace.name, source_root.name, relative)
            try:
                document = _normalise(
                    path,
                    relative,
                    workspace,
                    source_root.name,
                    evidence_library=evidence_library,
                    cache=cache,
                )
                documents.append(document)
                processed += 1
                old = previous.get(identifier)
                if (
                    old is None
                    or old.checksum != document.checksum
                    or old.metadata != document.metadata
                ):
                    added_or_updated += 1
                else:
                    retained += 1
            except Exception as error:  # noqa: BLE001
                failures.append(
                    IngestionFailure(
                        source_root=source_root.name,
                        relative_path=relative,
                        message=str(error),
                    )
                )
                failed += 1
                if identifier in previous:
                    retained += 1
        stale = set(previous) - current_ids
        removed_ids.update(stale)
        outcomes.append(
            RootOutcome(
                name=source_root.name,
                path=source_root.path,
                selected=True,
                status="scanned",
                discovered=len(files),
                processed=processed,
                failed=failed,
                added_or_updated=added_or_updated,
                retained=retained,
                removed=len(stale),
            )
        )

    _write_artifacts(
        artifact_directory, documents, failures, ignored, outcomes, removed_ids, cache
    )
    return IngestionSummary(
        workspace=workspace.name,
        discovered=sum(outcome.discovered for outcome in outcomes),
        processed=sum(outcome.processed for outcome in outcomes),
        documents=documents,
        failures=failures,
        ignored=ignored,
        root_outcomes=outcomes,
        artifact_directory=artifact_directory,
        elapsed_seconds=time.monotonic() - started,
        extractions_performed=cache.extracted,
        extractions_reused=cache.reused,
    )


def _selected_root_names(
    source_roots: tuple[SourceRoot, ...], roots: set[str] | None
) -> set[str]:
    configured = {root.name for root in source_roots}
    selected = configured if roots is None else roots
    unknown = selected - configured
    if unknown:
        raise ValueError("unknown document source root: " + ", ".join(sorted(unknown)))
    return selected


def _read_existing_documents(
    directory: Path, workspace_name: str
) -> dict[str, Document]:
    """Load valid prior artefacts for reconciliation without changing them."""
    documents: dict[str, Document] = {}
    if not directory.is_dir():
        return documents
    for path in directory.glob("*.json"):
        if path.name == "report.json":
            continue
        try:
            document = Document.model_validate_json(path.read_text(encoding="utf-8"))
            if document.workspace == workspace_name:
                documents[document.id] = document
        except (OSError, ValidationError):
            continue
    return documents


def _document_id(workspace: str, source_root: str, relative: Path) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"{workspace}:{source_root}:{relative}"))


def _normalise(
    path: Path,
    relative: Path,
    workspace: Workspace,
    source_root: str = "default",
    *,
    evidence_library: EvidenceLibrary | None = None,
    cache: ExtractionCache | None = None,
) -> Document:
    if cache is None:
        text, extracted = EXTRACTORS[path.suffix.lower()](path)
        digest = checksum(path)
    else:
        record = cache.extract(path, EXTRACTORS[path.suffix.lower()])
        text, extracted, digest = record.text, record.metadata, record.checksum
    stat = path.stat()
    metadata = {"extractor": {"source_suffix": path.suffix.lower(), **extracted}}
    if evidence_library is None:
        metadata = {"source_suffix": path.suffix.lower(), **extracted}
    else:
        associations = evidence_library.associations_for(source_root, relative)
        if associations:
            metadata["evidence"] = {
                "associations": [item.model_dump(mode="json") for item in associations],
                "document_roles": sorted({item.document_role for item in associations}),
                "module_ids": sorted({item.module_id for item in associations}),
                "source_ids": sorted(
                    {item.source_id for item in associations if item.source_id}
                ),
            }
    return Document(
        id=_document_id(workspace.name, source_root, relative),
        checksum=digest,
        filename=path.name,
        relative_path=relative,
        workspace=workspace.name,
        source_root=source_root,
        file_type=path.suffix.lower().removeprefix("."),
        file_size=stat.st_size,
        created_at=datetime.fromtimestamp(stat.st_ctime, UTC),
        modified_at=datetime.fromtimestamp(stat.st_mtime, UTC),
        title=extracted.get("title"),
        author=extracted.get("author"),
        page_count=extracted.get("page_count"),
        text=text,
        metadata=metadata,
    )


def _write_artifacts(
    directory: Path,
    documents: list[Document],
    failures: list[IngestionFailure],
    ignored: list[Path],
    root_outcomes: list[RootOutcome],
    removed_ids: set[str],
    cache: ExtractionCache,
) -> None:
    """Write human-readable per-document JSON and a run report."""
    directory.mkdir(parents=True, exist_ok=True)
    for document in documents:
        target = directory / f"{document.id}.json"
        content = document.model_dump_json(indent=2) + "\n"
        if not target.exists() or target.read_text(encoding="utf-8") != content:
            target.write_text(content, encoding="utf-8")
    for identifier in removed_ids:
        (directory / f"{identifier}.json").unlink(missing_ok=True)
    report = {
        "succeeded": len(documents),
        "failed": len(failures),
        "extractions_performed": cache.extracted,
        "extractions_reused": cache.reused,
        "ignored": [str(path) for path in ignored],
        "failures": [failure.model_dump(mode="json") for failure in failures],
        "roots": [outcome.model_dump(mode="json") for outcome in root_outcomes],
    }
    (directory / "report.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
