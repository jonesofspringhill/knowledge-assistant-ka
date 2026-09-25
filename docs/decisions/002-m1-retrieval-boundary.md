# ADR-002 M1 Retrieval Boundary

## Status

Accepted — 2026-08-04

## Decision

Milestone M1 ends with reliable, provenance-preserving retrieval. It includes
document ingestion, chunking, embedding generation, vector indexing, semantic
search, filtering, ranking, and retrieval evaluation.

M1 does not include LLM context construction, answer generation, or
source-cited responses. Those capabilities begin in M2.

## Context

Early project documents described M1 as a local RAG question-answering
assistant. Implementation and later feature design established a separately
testable retrieval capability first. Treating retrieval as the M1 endpoint
keeps the milestone measurable and provides a stable foundation for answer
generation.

## Consequences

* M1 is named **Local Retrieval Assistant**.
* M1 acceptance criteria require ranked, explainable results with provenance
  and measurable retrieval quality.
* M2 is named **Local Question Answering** and owns LLM integration, context
  construction, answers, uncertainty handling, and citations.
* Documentation must not describe generated answers as an M1 deliverable.
