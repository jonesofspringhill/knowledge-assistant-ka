"""Load, validate, match, and persist evidence-library control metadata."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import yaml
from pydantic import ValidationError

from knowledge_assistant.config import DocumentSettings
from knowledge_assistant.evidence.models import (
    ClaimReview,
    DocumentAssociation,
    EvidenceLibrary,
    EvidenceManifest,
    EvidenceModule,
    MetadataIssue,
    MetadataSummary,
    ModuleRecord,
    ResearchPolicy,
)
from knowledge_assistant.ingestion.pipeline import discover_documents
from knowledge_assistant.managers.workspace_manager import SourceRoot, Workspace

SUPPORTED_SCHEMA_VERSIONS = {"1.0"}


class EvidenceLibraryError(ValueError):
    """Raised when evidence metadata is invalid or violates workspace safety."""


def _load_json(path: Path, model_type):
    try:
        return model_type.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValidationError) as error:
        raise EvidenceLibraryError(
            f"Invalid control record '{path}': {error}"
        ) from error


def _load_policy(path: Path) -> ResearchPolicy:
    try:
        return ResearchPolicy.model_validate(
            yaml.safe_load(path.read_text(encoding="utf-8"))
        )
    except (OSError, yaml.YAMLError, ValidationError) as error:
        raise EvidenceLibraryError(
            f"Invalid research policy '{path}': {error}"
        ) from error


def _resolved(path: Path, parent: Path) -> Path:
    candidate = path.expanduser()
    return (candidate if candidate.is_absolute() else parent / candidate).resolve()


def _match_root(path: Path, roots: tuple[SourceRoot, ...]) -> tuple[SourceRoot, Path]:
    matches: list[tuple[SourceRoot, Path]] = []
    resolved = path.resolve()
    normalised = Path(os.path.normcase(str(resolved)))
    for root in roots:
        resolved_root = root.path.resolve()
        root_path = Path(os.path.normcase(str(resolved_root)))
        try:
            normalised.relative_to(root_path)
            matches.append((root, resolved.relative_to(resolved_root)))
        except ValueError:
            continue
    if len(matches) != 1:
        detail = (
            "outside every configured document root" if not matches else "ambiguous"
        )
        raise EvidenceLibraryError(f"Evidence path '{path}' is {detail}")
    return matches[0]


def _association(
    workspace: Workspace,
    module: ModuleRecord,
    path: Path,
    role: str,
    *,
    source=None,
) -> DocumentAssociation:
    root, relative = _match_root(path, workspace.sources)
    return DocumentAssociation(
        workspace=workspace.name,
        source_root=root.name,
        relative_path=relative,
        source_path=Path(root.name) / relative,
        document_role=role,
        module_id=module.module_id,
        module_title=module.title,
        module_status=module.status,
        source_id=source.id if source else None,
        source_title=source.title if source else None,
        organisation=source.organisation if source else None,
        authority_type=source.authority_type if source else None,
        source_url=str(source.url) if source and source.url else None,
        subtopic_ids=[item.id for item in module.subtopics],
        topics=list(source.relevant_topics) if source else [],
    )


def load_evidence_library(workspace: Workspace) -> EvidenceLibrary | None:
    """Validate configured control records and match them to workspace roots."""
    settings = workspace.evidence_library
    if settings is None:
        return None
    manifest = _load_json(settings.manifest, EvidenceManifest)
    if manifest.schema_version not in SUPPORTED_SCHEMA_VERSIONS:
        raise EvidenceLibraryError(
            f"Unsupported manifest schema '{manifest.schema_version}'; supported: "
            + ", ".join(sorted(SUPPORTED_SCHEMA_VERSIONS))
        )
    policy = _load_policy(settings.policy)
    modules: list[EvidenceModule] = []
    associations: list[DocumentAssociation] = []
    reviews: list[ClaimReview] = []
    issues: list[MetadataIssue] = []
    missing = 0
    referenced: set[tuple[str, str]] = set()
    for entry in sorted(manifest.modules, key=lambda item: item.module_id.casefold()):
        record_path = _resolved(entry.record_file, settings.manifest.parent)
        record = _load_json(record_path, ModuleRecord)
        if record.module_id.casefold() != entry.module_id.casefold():
            raise EvidenceLibraryError(
                f"Module identity mismatch in '{record_path}': "
                f"{entry.module_id} != {record.module_id}"
            )
        if record.status not in policy.module_statuses:
            raise EvidenceLibraryError(
                f"Module '{record.module_id}' has disallowed status '{record.status}'"
            )
        if entry.status is not None and entry.status != record.status:
            raise EvidenceLibraryError(
                f"Module status mismatch for '{record.module_id}': "
                f"{entry.status} != {record.status}"
            )
        if entry.source_count is not None and entry.source_count != len(record.sources):
            raise EvidenceLibraryError(
                f"Source count mismatch for '{record.module_id}': "
                f"{entry.source_count} != {len(record.sources)}"
            )
        invalid = sorted(
            {item.assessment for item in record.claim_reviews}
            - set(policy.claim_assessments)
        )
        if invalid:
            raise EvidenceLibraryError(
                f"Module '{record.module_id}' has disallowed assessment(s): "
                + ", ".join(invalid)
            )
        if policy.download_statuses is not None:
            invalid_downloads = sorted(
                {
                    item.download_status
                    for item in record.sources
                    if item.download_status is not None
                }
                - set(policy.download_statuses)
            )
            if invalid_downloads:
                raise EvidenceLibraryError(
                    f"Module '{record.module_id}' has disallowed download status(es): "
                    + ", ".join(invalid_downloads)
                )
        course_path = _resolved(record.course_document, record_path.parent)
        if entry.course_document is not None:
            manifest_course = _resolved(entry.course_document, settings.manifest.parent)
            if manifest_course != course_path:
                raise EvidenceLibraryError(
                    f"Course paths disagree for module '{record.module_id}': "
                    f"'{manifest_course}' != '{course_path}'"
                )
        course_association = _association(
            workspace, record, course_path, "course_module"
        )
        associations.append(course_association)
        referenced.add(
            (
                course_association.source_root.casefold(),
                course_association.relative_path.as_posix().casefold(),
            )
        )
        if not course_path.is_file():
            missing += 1
            issues.append(
                MetadataIssue(
                    severity=settings.missing_referenced_document,
                    code="missing_referenced_document",
                    message=f"Missing referenced document: {course_association.source_path}",
                )
            )
        module_reviews = [
            ClaimReview(
                module_id=record.module_id,
                subtopic_id=item.subtopic_id,
                assessment=item.assessment,
                notes=item.notes,
                record_file=record_path,
            )
            for item in record.claim_reviews
        ]
        reviews.extend(module_reviews)
        resolved_sources = []
        for source in sorted(record.sources, key=lambda item: item.id.casefold()):
            if source.local_file is None:
                resolved_sources.append(source)
                continue
            source_path = _resolved(source.local_file, record_path.parent)
            association = _association(
                workspace, record, source_path, "authoritative_source", source=source
            )
            associations.append(association)
            resolved_sources.append(
                source.model_copy(update={"local_file": association.source_path})
            )
            referenced.add(
                (
                    association.source_root.casefold(),
                    association.relative_path.as_posix().casefold(),
                )
            )
            if not source_path.is_file():
                missing += 1
                issues.append(
                    MetadataIssue(
                        severity=settings.missing_referenced_document,
                        code="missing_referenced_document",
                        message=f"Missing referenced document: {association.source_path}",
                    )
                )
        modules.append(
            EvidenceModule(
                module_id=record.module_id,
                title=record.title,
                status=record.status,
                course_document=course_association.source_path,
                course_pdf_pages=record.course_pdf_pages,
                subtopics=record.subtopics,
                sources=resolved_sources,
                claim_reviews=module_reviews,
                record_file=record_path,
            )
        )
    unmatched = 0
    for root in workspace.sources:
        if not root.path.is_dir():
            continue
        try:
            files, _ = discover_documents(
                root.path, root.settings or DocumentSettings(include=["*"])
            )
        except OSError as error:
            raise EvidenceLibraryError(
                f"Unable to scan source root '{root.name}' for metadata: {error}"
            ) from error
        for path in files:
            logical_path = path.relative_to(root.path).as_posix()
            key = (root.name.casefold(), logical_path.casefold())
            if key not in referenced:
                unmatched += 1
                if settings.unmatched_document != "ignore":
                    issues.append(
                        MetadataIssue(
                            severity=settings.unmatched_document,
                            code="unmatched_document",
                            message=f"Unmatched document: {root.name}/{logical_path}",
                        )
                    )
    fatal = [item.message for item in issues if item.severity == "fatal"]
    if fatal:
        raise EvidenceLibraryError("; ".join(fatal))
    associations.sort(
        key=lambda item: (
            item.source_root.casefold(),
            item.relative_path.as_posix().casefold(),
            item.module_id.casefold(),
            item.source_id or "",
        )
    )
    reviews.sort(
        key=lambda item: (item.module_id.casefold(), item.subtopic_id.casefold())
    )
    source_count = sum(len(item.sources) for item in modules)
    local_count = sum(
        source.local_file is not None for module in modules for source in module.sources
    )
    return EvidenceLibrary(
        schema_version=manifest.schema_version,
        workspace=workspace.name,
        manifest_path=settings.manifest,
        policy_path=settings.policy,
        policy=policy,
        modules=modules,
        document_associations=associations,
        claim_reviews=reviews,
        validation_issues=issues,
        summary=MetadataSummary(
            modules=len(modules),
            subtopics=sum(len(item.subtopics) for item in modules),
            source_references=source_count,
            local_source_references=local_count,
            remote_only_references=source_count - local_count,
            claim_reviews=len(reviews),
            missing_references=missing,
            unmatched_documents=unmatched,
            associations=len(associations),
        ),
    )


def write_control_artifact(library: EvidenceLibrary, directory: Path) -> Path:
    """Atomically replace the validated, workspace-scoped control artefact."""
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / "evidence-library.json"
    descriptor, temporary = tempfile.mkstemp(
        prefix=".evidence-", suffix=".json", dir=directory
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as file:
            file.write(library.model_dump_json(indent=2) + "\n")
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary, destination)
    except Exception:
        Path(temporary).unlink(missing_ok=True)
        raise
    return destination


class EvidenceLibraryService:
    """Read-only provider-independent access to validated claim reviews."""

    def __init__(self, library: EvidenceLibrary) -> None:
        self.library = library

    @classmethod
    def from_artifact(cls, path: Path) -> EvidenceLibraryService:
        return cls(_load_json(path, EvidenceLibrary))

    def claim_reviews(
        self, module_id: str, subtopic_id: str | None = None
    ) -> tuple[ClaimReview, ...]:
        return tuple(
            review
            for review in self.library.claim_reviews
            if review.module_id.casefold() == module_id.casefold()
            and (
                subtopic_id is None
                or review.subtopic_id.casefold() == subtopic_id.casefold()
            )
        )
