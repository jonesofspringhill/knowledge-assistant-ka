"""Read-only access to configured knowledge workspaces."""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from knowledge_assistant.config import (
    DocumentSettings,
    EvidenceLibrarySettings,
    SourceRootSettings,
    WorkspaceDocumentSettings,
    WorkspaceSettings,
)


class WorkspaceNotFoundError(KeyError):
    """Raised when a configured workspace cannot be found."""


@dataclass(frozen=True, slots=True)
class SourceRoot:
    """A configured source root with its effective discovery policy."""

    name: str
    path: Path
    settings: DocumentSettings | None = None


@dataclass(frozen=True, slots=True)
class Workspace:
    """An isolated configured collection of source documents."""

    name: str
    description: str
    documents: Path
    artifacts: Path
    collection: str
    enabled: bool
    sources: tuple[SourceRoot, ...] = ()
    unavailable_root: Literal["warn", "fatal"] = "warn"
    legacy_documents: bool = False
    evidence_library: EvidenceLibrarySettings | None = None


class WorkspaceManager:
    """Provide workspace selection without accessing source documents."""

    def __init__(self, workspaces: dict[str, WorkspaceSettings]) -> None:
        self._workspaces = workspaces

    def list(self, *, include_disabled: bool = False) -> tuple[Workspace, ...]:
        """Return configured workspaces, optionally including disabled ones."""
        return tuple(
            self._make(name, setting)
            for name, setting in self._workspaces.items()
            if include_disabled or setting.enabled
        )

    def get(self, name: str) -> Workspace:
        """Return a workspace by configured name."""
        try:
            return self._make(name, self._workspaces[name])
        except KeyError as error:
            raise WorkspaceNotFoundError(f"Unknown workspace: {name}") from error

    @staticmethod
    def _make(name: str, setting: WorkspaceSettings) -> Workspace:
        sources = _sources(setting.documents)
        canonical = isinstance(setting.documents, WorkspaceDocumentSettings)
        return Workspace(
            name,
            setting.description,
            sources[0].path,
            setting.artifacts,
            setting.collection,
            setting.enabled,
            sources,
            setting.documents.unavailable_root if canonical else "fatal",
            not canonical,
            setting.evidence_library,
        )


def _sources(documents: Path | WorkspaceDocumentSettings) -> tuple[SourceRoot, ...]:
    if isinstance(documents, Path):
        return (SourceRoot("default", documents),)
    defaults = documents.defaults or DocumentSettings(include=["*"])
    return tuple(
        SourceRoot(root.name, root.path, _effective_settings(defaults, root))
        for root in documents.roots
    )


def _effective_settings(
    defaults: DocumentSettings, root: SourceRootSettings
) -> DocumentSettings:
    return DocumentSettings(
        include=root.include if root.include is not None else defaults.include,
        exclude=root.exclude if root.exclude is not None else defaults.exclude,
        recursive=root.recursive if root.recursive is not None else defaults.recursive,
    )
