"""ChromaDB vector-store adapter."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import chromadb

from knowledge_assistant.retrieval.models import EmbeddingRecord, VectorSearchResult

_KEY_PATTERN = re.compile(r"[^A-Za-z0-9_]")


class ChromaVectorStore:
    """Workspace-scoped ChromaDB adapter used behind retrieval services."""

    def __init__(self, directory: Path) -> None:
        self.directory = directory

    def upsert_workspace(
        self,
        workspace_name: str,
        collection_name: str,
        records: list[EmbeddingRecord],
        *,
        rebuild: bool = False,
    ) -> tuple[int, int]:
        collection = self._collection(collection_name, workspace_name)
        if rebuild:
            collection.delete(where={"workspace": workspace_name})
        existing = set(
            collection.get(where={"workspace": workspace_name}, include=[])["ids"]
        )
        active = {record.chunk.chunk_id for record in records}
        stale = sorted(existing - active)
        if stale:
            collection.delete(ids=stale)
        if records:
            collection.upsert(
                ids=[record.chunk.chunk_id for record in records],
                embeddings=[record.embedding for record in records],
                documents=[record.chunk.text for record in records],
                metadatas=[self._metadata(record) for record in records],
            )
        return len(records), len(stale)

    def count_workspace(self, workspace_name: str, collection_name: str) -> int:
        return len(
            self._collection(collection_name, workspace_name).get(
                where={"workspace": workspace_name}, include=[]
            )["ids"]
        )

    def count_collection(self, workspace_name: str, collection_name: str) -> int:
        return self._collection(collection_name, workspace_name).count()

    def search(
        self,
        workspace_name: str,
        collection_name: str,
        query_embedding: list[float],
        *,
        top_k: int,
        filters: dict[str, Any] | None = None,
    ) -> list[VectorSearchResult]:
        collection = self._collection(collection_name, workspace_name)
        evidence_filters = {
            key: value
            for key, value in (filters or {}).items()
            if key in {"document_role", "module_id", "source_id"}
        }
        ordinary_filters = {
            key: value
            for key, value in (filters or {}).items()
            if key not in evidence_filters
        }
        count = collection.count()
        if count == 0:
            return []
        response = collection.query(
            query_embeddings=[query_embedding],
            n_results=count if evidence_filters else top_k,
            where=self._where(workspace_name, ordinary_filters),
            include=["documents", "metadatas", "distances"],
        )
        results = [
            VectorSearchResult(
                identifier=identifier,
                text=document,
                metadata=metadata,
                distance=float(distance),
            )
            for identifier, document, metadata, distance in zip(
                response["ids"][0],
                response["documents"][0],
                response["metadatas"][0],
                response["distances"][0],
                strict=True,
            )
        ]
        if evidence_filters:
            results = [
                result
                for result in results
                if self._matches_evidence(result.metadata, evidence_filters)
            ]
        return results[:top_k]

    def _collection(self, collection_name: str, workspace_name: str):
        self.directory.mkdir(parents=True, exist_ok=True)
        return chromadb.PersistentClient(
            path=str(self.directory)
        ).get_or_create_collection(
            name=collection_name, metadata={"workspace": workspace_name}
        )

    def _metadata(self, record: EmbeddingRecord) -> dict[str, str | int | float | bool]:
        chunk = record.chunk
        metadata: dict[str, str | int | float | bool] = {
            "chunk_id": chunk.chunk_id,
            "document_id": chunk.document_id,
            "workspace": chunk.workspace,
            "document_title": chunk.document_title or "",
            "section_title": chunk.section_title or "",
            "source_filename": chunk.source_filename,
            "source_root": chunk.source_root,
            "relative_path": str(chunk.relative_path),
            "source_path": str(chunk.source_path),
            "checksum": chunk.checksum,
            "chunk_index": chunk.chunk_index,
            "chunk_count": chunk.chunk_count,
            "chunk_quality": chunk.chunk_quality,
            "embedding_model": record.embedding_model,
            "embedding_version": record.embedding_version,
            "created": record.created,
            "metadata": json.dumps(chunk.metadata, sort_keys=True),
        }
        if chunk.page is not None:
            metadata["page"] = chunk.page
        if chunk.heading_level is not None:
            metadata["heading_level"] = chunk.heading_level
        if chunk.parent_section:
            metadata["parent_section"] = chunk.parent_section
        for key, value in chunk.metadata.items():
            if isinstance(value, str | int | float | bool):
                metadata[f"metadata_{self._normalise_key(key)}"] = value
        evidence = chunk.metadata.get("evidence")
        if isinstance(evidence, dict):
            associations = evidence.get("associations", [])
            if isinstance(associations, list):
                first = associations[0] if associations else {}
                if isinstance(first, dict):
                    for key in (
                        "document_role",
                        "module_id",
                        "module_title",
                        "source_id",
                        "organisation",
                        "authority_type",
                        "source_url",
                    ):
                        value = first.get(key)
                        if isinstance(value, str):
                            metadata[key] = value
        return metadata

    def _where(self, workspace_name: str, filters: dict[str, Any]) -> dict[str, Any]:
        clauses: list[dict[str, Any]] = [{"workspace": workspace_name}]
        clauses.extend({self._filter_key(key): value} for key, value in filters.items())
        return clauses[0] if len(clauses) == 1 else {"$and": clauses}

    def _matches_evidence(
        self, metadata: dict[str, Any], filters: dict[str, Any]
    ) -> bool:
        try:
            portable = json.loads(str(metadata.get("metadata", "{}")))
        except (TypeError, ValueError):
            return False
        evidence = portable.get("evidence")
        associations = (
            evidence.get("associations", []) if isinstance(evidence, dict) else []
        )
        return any(
            isinstance(association, dict)
            and all(association.get(key) == value for key, value in filters.items())
            for association in associations
        )

    def _filter_key(self, key: str) -> str:
        if key.startswith("metadata."):
            return f"metadata_{self._normalise_key(key.removeprefix('metadata.'))}"
        normalised = self._normalise_key(key)
        top_level = {
            "chunk_id",
            "document_id",
            "document_title",
            "section_title",
            "source_filename",
            "source_root",
            "relative_path",
            "source_path",
            "checksum",
            "chunk_index",
            "chunk_count",
            "chunk_quality",
            "embedding_model",
            "embedding_version",
            "page",
            "heading_level",
            "parent_section",
        }
        return normalised if normalised in top_level else f"metadata_{normalised}"

    def _normalise_key(self, key: str) -> str:
        return _KEY_PATTERN.sub("_", key.strip()).strip("_")
