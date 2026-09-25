"""Structure-aware document chunking services."""

from knowledge_assistant.chunking.pipeline import chunk_workspace
from knowledge_assistant.ingestion.models import Chunk, ChunkingSummary

__all__ = ["Chunk", "ChunkingSummary", "chunk_workspace"]
