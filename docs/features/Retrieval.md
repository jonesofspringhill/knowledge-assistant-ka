# Embedding, Indexing, and Retrieval

**Identifier:** M1.3–M1.4

**Status:** Implemented

**Related Milestone:** M1 – Local Retrieval Assistant

---

## Purpose

The Retrieval subsystem transforms semantically chunked documents into a searchable knowledge base capable of returning the most relevant information for a user query.

The subsystem shall generate embeddings, maintain a vector index, perform similarity search and provide objective evaluation of retrieval quality.

The output of this subsystem becomes the provenance-preserving context supplied
to M2 Question Answering and later Agent workflows.

---

## Design Goals

The implementation shall optimise for retrieval quality, reproducibility and maintainability.

The retrieval pipeline shall:

* preserve provenance
* support incremental updates
* avoid unnecessary recomputation
* remain model-independent where practical
* separate embedding generation from vector indexing
* provide measurable retrieval quality

---

## Scope

This feature includes:

* embedding generation
* embedding persistence
* vector database management
* similarity search
* retrieval evaluation
* CLI integration
* statistics generation

---

## Out of Scope

This feature does not include:

* LLM prompting
* answer generation
* summarisation
* contradiction detection
* planning
* autonomous agents

---

## Processing Pipeline

```text
Chunk Artefacts
        │
        ▼
Generate Embeddings
        │
        ▼
Persist Embeddings
        │
        ▼
Build Vector Index
        │
        ▼
Similarity Search
        │
        ▼
Evaluation
```

---

## Functional Requirements

### FR1 – Input

Read chunk artefacts produced by the Chunking subsystem.

Only valid chunk artefacts shall be processed.

---

### FR2 – Embedding Generation

Generate embeddings using the configured embedding model.

The implementation shall:

* preserve metadata
* associate each embedding with its chunk
* record embedding model
* record embedding version
* support incremental regeneration

---

### FR3 – Incremental Processing

Embeddings shall only be regenerated when:

* chunk checksum changes
* embedding model changes
* embedding version changes
* regeneration is explicitly requested

---

### FR4 – Embedding Storage

Embeddings shall be stored beneath:

```text
workspaces/<workspace>/artifacts/embeddings/
```

The storage format should remain independent of any specific vector database.

---

### FR5 – Vector Database

The implementation shall support ChromaDB.

Each vector shall retain:

* chunk identifier
* document identifier
* workspace
* checksum
* text
* metadata

The implementation should permit future support for alternative vector databases.

---

### FR6 – Index Management

The vector database shall support:

* creation
* update
* deletion
* rebuild
* verification

---

### FR7 – Similarity Search

The system shall retrieve the most relevant chunks for a supplied query.

Search shall support:

* configurable Top-K
* configurable similarity threshold
* metadata filtering
* workspace isolation

CLI filters use `--filter KEY=VALUE`. Top-level provenance fields can be filtered
directly, for example `--filter document_id=document-1` or
`--filter section_title=Grants`. Chunk metadata can be filtered either as
`--filter metadata.topic=funding` or, when the key is not a top-level retrieval
field, `--filter topic=funding`.

---

### FR8 – Provenance

Every retrieved result shall retain sufficient provenance for later citation.

Results shall include:

* document title
* section title
* relative path
* source location
* chunk identifier
* similarity score
* chunk text

---

### FR9 – Retrieval Quality

The implementation shall optimise for semantic relevance rather than purely numerical similarity.

The objective is to retrieve the smallest set of chunks capable of answering the user's question.

---

### FR10 – Statistics

The implementation shall report:

* chunks processed
* embeddings generated
* embeddings reused
* index size
* indexing time
* search latency

---

## Commands

The subsystem introduces:

```text
knowledge-assistant embed
```

Generate embeddings.

---

```text
knowledge-assistant index
```

Create or update the vector database.

---

```text
knowledge-assistant search
```

Perform semantic similarity search.

---

```text
knowledge-assistant evaluate
```

Execute retrieval benchmarks.

---

## Search Output

Typical output:

```text
Question

What grants have we applied for?

Results

1.
Sponsored Grant Application
Similarity 0.94

2.
Funding Pipeline
Similarity 0.91

3.
Board Minutes July
Similarity 0.87
```

Search output shall include provenance.

---

## Metadata

Each indexed vector should retain:

```text
chunk_id
document_id
workspace
document_title
section_title
relative_path
checksum
embedding_model
embedding_version
created
text
metadata
```

---

## Evaluation

Evaluation shall use benchmark questions whose expected answers are known.

Each benchmark shall include:

* question
* expected documents
* expected sections
* expected keywords
* optional similarity threshold

This M1 evaluation boundary remains retrieval-only. M2.4 uses the separate
`qa-evaluate` hierarchy to measure the full question -> retrieval -> context ->
LLM -> cited-answer path. Its recording adapter observes the same single search
call consumed by M2.3; it must not issue a second search or redefine the M1
`evaluate` metrics.

---

## Evaluation Metrics

The implementation should report:

* Recall@5
* Recall@10
* Mean Reciprocal Rank (MRR)
* Average similarity
* Search latency
* Index size

These metrics should be retained between runs to allow comparison.

---

## Incremental Updates

The implementation shall avoid regenerating embeddings unnecessarily.

The following changes shall trigger regeneration:

* modified chunk
* deleted chunk
* changed embedding model
* changed embedding configuration

---

## Configuration

Typical configurable values include:

* embedding model
* vector database backend
* Top-K
* similarity threshold
* maximum context length
* batch size
* parallelism
* cache policy

All values shall be configurable through the project configuration system.

---

## Validation

Retrieval quality shall be assessed using real project questions.

A retrieval shall be considered successful when the expected document appears within the configured Top-K results.

---

## Error Handling

Failures affecting individual chunks shall not terminate the indexing process.

Errors shall be summarised after completion.

---

## Acceptance Criteria

The feature is complete when:

* embeddings are generated
* embeddings are cached
* vector database is populated
* similarity search operates correctly
* provenance is preserved
* evaluation framework executes successfully
* evaluation dataset exists at `evaluation/retrieval_benchmarks.example.json`
* CLI integration is complete
* documentation is updated
* tests pass

---

## Future Enhancements

Potential future improvements include:

* hybrid keyword/vector retrieval
* reranking
* cross-encoder scoring
* metadata-aware retrieval
* document-type-aware retrieval
* temporal filtering
* multi-workspace search
* contradiction-aware retrieval
* graph-based retrieval
* adaptive query expansion

---

### M2.2 evidence filters and results

Portable embedding cache equivalence includes chunk metadata as well as text,
checksum, model, and version. Search accepts exact `document_role`, `module_id`,
and `source_id` filters through the existing `--filter KEY=VALUE` interface;
combined filters use logical AND against one complete association, including
documents with multiple associations. Results retain the full public evidence
metadata and CLI output labels role, module, organisation, and source URL when
present. Control records never enter embeddings or the vector collection.

## Revision History

| Version | Date       | Author  | Summary                                    |
| ------- | ---------- | ------- | ------------------------------------------ |
| 1.0     | 2026-08-04 | Project | Initial retrieval subsystem specification. |
| 1.1     | 2026-08-24 | Codex | Documented the separate M2.4 full-pipeline evaluation boundary and single-search reuse contract. |
