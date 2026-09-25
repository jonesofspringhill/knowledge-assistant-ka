# Retrieval Pipeline Design Prompt

## Purpose

You are assisting with implementation of Milestone M1.4 of Knowledge Assistant.

The objective is to design and implement a retrieval layer that converts user questions into ranked knowledge chunks.

## Context

Knowledge Assistant currently provides:

* document ingestion
* document extraction
* chunking
* metadata preservation
* embedding generation
* vector indexing

The next requirement is reliable retrieval.

## Task

Design or modify the retrieval subsystem to provide:

1. Query embedding generation
2. Vector similarity search
3. Ranking
4. Filtering
5. Provenance-preserving results

## Requirements

The implementation must:

* follow the existing project architecture
* preserve separation between ingestion, indexing, and retrieval
* avoid embedding database-specific behaviour into business logic
* use configuration rather than constants
* maintain document provenance
* support future integration with LLM answer generation

## Required Outputs

Provide:

1. Architecture changes
2. New modules required
3. Data models required
4. Configuration changes
5. CLI changes
6. Tests required
7. Documentation updates

## Design Questions

Consider:

* How are retrieved chunks represented?
* How are similarity scores normalised?
* How are thresholds selected?
* How are metadata filters applied?
* How can retrieval quality be evaluated?
* How can the vector store be replaced later?

## Constraints

Do not implement answer generation.

Do not introduce unnecessary dependencies.

Prefer small, testable components.

## Acceptance Test

A user should be able to run:

```
knowledge-assistant search "question"
```

and receive ranked, explainable knowledge results.
