# Feature: M1.4 Retrieval and Query Pipeline

**Status:** Implemented

## Overview

Milestone M1.4 introduces the retrieval layer of Knowledge Assistant.

The purpose of this feature is to transform a user question into a ranked set of relevant knowledge chunks while preserving document provenance and metadata.

This milestone completes the transition from document processing to knowledge discovery.

## Objective

Implement a reliable retrieval pipeline:

```
User Question
      |
      v
Query Processing
      |
      v
Embedding Generation
      |
      v
Vector Search
      |
      v
Ranking and Filtering
      |
      v
Context Results
```

The output of retrieval will become the input context for future LLM-based answer generation.

---

## Scope

### Included

#### Query Processing

The system shall:

* accept natural-language questions
* generate query embeddings using the configured embedding model
* pass queries to the vector search layer

#### Vector Retrieval

The system shall:

* search the knowledge index
* retrieve candidate chunks
* rank results by similarity score
* support configurable result limits

#### Filtering

The system shall support:

* similarity threshold filtering
* metadata filtering
* document-type filtering where available

#### Result Formatting

Returned results shall include:

* chunk identifier
* document identifier
* document title
* source location
* chunk text
* similarity score
* metadata

---

## User Interface

The CLI command:

```
knowledge-assistant search "<question>"
```

shall provide access to retrieval.

Example:

```
knowledge-assistant search \
"What grants were available in 2024?"
```

Optional parameters:

```
--top-k
--threshold
--filter
```

Example:

```
knowledge-assistant search \
"What grants were available?" \
--top-k 10 \
--threshold 0.35
```

---

## Configuration

Retrieval settings shall be configurable.

Example:

```yaml
retrieval:
  top_k: 5
  similarity_threshold: 0.35
  max_context_length: 6000
```

Configuration values shall not be embedded in application code.

---

## Architecture

The retrieval layer shall remain independent of the underlying vector database.

Target architecture:

```
retrieval/
    models.py
    retriever.py
    scoring.py

vectorstore/
    chroma.py

main.py
```

Implemented architecture:

* `retrieval.models` defines portable embedding, index, vector candidate and final search-result models.
* `retrieval.retriever` owns query embedding, similarity filtering, ranking conversion and context-length limiting.
* `retrieval.scoring` normalises vector distances into public similarity scores.
* `vectorstore.chroma` owns ChromaDB collection access, metadata flattening and filter translation.
* `retrieval.pipeline` remains the application-service facade for embedding generation, indexing, search and evaluation.
* `main.py` exposes `embed`, `index`, `search` and `evaluate` commands.

---

## Evaluation

A retrieval evaluation dataset shall be created.

Each test case shall contain:

* question
* expected document(s)
* expected topic
* acceptable ranking position

Metrics:

| Metric                  | Purpose                    |
| ----------------------- | -------------------------- |
| Recall@5                | Relevant document found    |
| Recall@10               | Broader retrieval coverage |
| Mean Reciprocal Rank    | Ranking quality            |
| Latency                 | Performance                |
| Similarity distribution | Threshold tuning           |

---

## Acceptance Criteria

M1.4 is complete when:

* [x] CLI search retrieves relevant chunks
* [x] Results preserve provenance
* [x] Similarity scores are displayed
* [x] Retrieval parameters are configurable
* [x] Metadata filtering works
* [x] Evaluation dataset exists
* [x] Retrieval quality can be measured

---

## Dependencies

Requires:

* M1.1 ingestion pipeline
* M1.2 chunking pipeline
* M1.3 embedding/index pipeline

Enables:

* M2 question answering
* RAG workflows
* conversational knowledge assistant
