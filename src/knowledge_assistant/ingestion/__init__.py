"""Document ingestion services."""

from knowledge_assistant.ingestion.models import Document, IngestionSummary, RootOutcome
from knowledge_assistant.ingestion.pipeline import ingest_workspace

__all__ = ["Document", "IngestionSummary", "RootOutcome", "ingest_workspace"]
