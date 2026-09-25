# System Architecture Document

The CLI is also available as `ka`. Ingestion now has a local content-addressed
extraction cache ahead of document normalisation; evidence associations and source
identity are rebuilt on each run. See
[ka incremental ingestion](features/KA-Incremental-Ingestion.md) for cache
invalidation, privacy, transfer and remaining implementation work.

**Version:** 0.1
**Status:** Initial Architecture Definition
**Date:** 2026-07-21

---

## 1. Introduction

This document defines the high-level architecture of the `ka` knowledge and agent
platform. `ka` preserves stable application contracts while adapters provide
models, embedding services, vector stores and agent tools.

The architecture is designed to support progressive evolution from:

1. Document question answering.
2. Knowledge extraction and analysis.
3. Agent-assisted workflows and decision support.

The architecture separates:

- Document management.
- Information retrieval.
- Knowledge representation.
- Reasoning.
- User interaction.

The system should remain modular so individual technologies can be replaced without major redesign.

---

## 2. Architectural Principles

### 2.1 Layered Design

The system is organised into layers.

```text
+------------------------------------------------+
| User Interface                                 |
+------------------------------------------------+
| Application Services                          |
+------------------------------------------------+
| Retrieval and Reasoning                        |
+------------------------------------------------+
| Knowledge Storage                              |
+------------------------------------------------+
| Document Processing                           |
+------------------------------------------------+
| Source Documents                              |
+------------------------------------------------+
```

Each layer should have clear responsibilities and minimal dependencies on other layers.

---

### 2.2 Separation of Concerns

The following responsibilities must remain separate:

| Component | Responsibility |
|---|---|
| Ingestion | Read and process source documents |
| Chunking | Divide text into retrieval units |
| Embeddings | Convert text into vector representations |
| Storage | Persist searchable information |
| Retrieval | Find relevant information |
| LLM Interface | Generate responses |
| Analysis | Extract and compare knowledge |
| Agents | Perform workflows |

---

## 3. System Overview

The initial system:

```text
                 Documents

                    |
                    v

            Document Ingestion

                    |
                    v

              Text Chunks

                    |
          +---------+---------+
          |                   |
          v                   v

     Embeddings          Metadata

          |                   |
          v                   v

       Vector Store      Metadata Store

                 \       /

                  Retrieval

                      |

                      v

                 Context Builder

                      |

                      v

                    LLM

                      |

                      v

                  Response
```

---

## 4. Component Architecture

### 4.1 Document Ingestion Layer

Purpose:

Convert external documents into a common internal representation.

Responsibilities:

- Discover documents.
- Load files.
- Extract text.
- Extract basic metadata.
- Handle unsupported formats gracefully.
- Record processing status.

Input:

```text
PDF
DOCX
TXT
MD
EML
```

Output:

```python
Document
{
    id,
    filename,
    source,
    text,
    metadata
}
```

---

## 4.2 Chunking Layer

Purpose:

Split documents into retrieval-sized sections.

Responsibilities:

- Preserve context.
- Maintain document references.
- Add chunk metadata.

Example:

```python
Chunk
{
    document_id,
    chunk_id,
    text,
    page,
    section
}
```

Initial configuration:

```text
Chunk size:
800 tokens

Overlap:
100 tokens
```

These values should be configurable.

---

## 4.3 Embedding Layer

Purpose:

Create vector representations for semantic retrieval.

Responsibilities:

- Generate embeddings.
- Support configurable embedding models.
- Store embedding metadata.

Initial model:

```text
nomic-embed-text
```

The embedding interface should not depend on a specific model.

---

## 4.4 Vector Storage Layer

Purpose:

Store and retrieve semantic representations.

Current default implementation:

```text
ChromaDB
```

Responsibilities:

- Store embeddings.
- Perform similarity searches.
- Return ranked results.
- Preserve metadata.

Interface:

```python
search(
    query,
    top_k
)
```

Returns:

```python
[
    {
        text,
        metadata,
        score
    }
]
```

---

## 4.5 Retrieval Layer

Purpose:

Select relevant information to answer a query.

Responsibilities:

- Convert user questions into retrieval queries.
- Search vector store.
- Filter results.
- Construct context.

Future capabilities:

- Metadata filtering.
- Hybrid search.
- Re-ranking.
- Multi-query retrieval.

---

## 4.6 LLM Interface Layer

Purpose:

Provide a consistent interface to language models.

Initial implementation:

```text
Ollama
```

Responsibilities:

- Send prompts.
- Manage model selection.
- Control generation parameters.
- Return responses.

Interface:

```python
generate(
    prompt,
    context
)
```

The application uses a provider registry. Ollama is currently registered; LM
Studio, OpenAI-compatible, and hosted-model adapters can be added without changing
retrieval or grounded-answer services. Tool contracts follow the same rule: agent
workflows depend on declared tool inputs, outputs, permissions and evidence, not a
vendor-specific tool-calling format.

---

## 4.7 Response Layer

Purpose:

Produce useful user-facing answers.

Responsibilities:

- Format answers.
- Include citations.
- Report uncertainty.
- Identify missing information.

Example:

```text
Answer:

The budget was approved in March.

Sources:

- Meeting_Minutes_03.pdf page 4
- Finance_Report.docx
```

---

## 5. Future Knowledge Layer

The future system will introduce structured knowledge.

Entities:

```text
Person
Organisation
Project
Meeting
Decision
Action
Claim
Evidence
Risk
```

Relationships:

```text
Person
   |
attended
   |
Meeting
   |
created
   |
Decision
   |
assigned
   |
Action
```

This layer supports:

- Agreement analysis.
- Contradiction detection.
- Timeline reconstruction.
- Decision tracking.

---

## 6. Future Agent Architecture

Agents will operate above the knowledge layer.

An agent consists of:

```text
Goal

    |
    v

Planning

    |
    v

Tools

    |
    v

Knowledge Retrieval

    |
    v

Reasoning

    |
    v

Output
```

Example:

Task:

"Prepare project meeting briefing."

Agent actions:

1. Retrieve previous meeting minutes.
2. Find incomplete actions.
3. Search recent correspondence.
4. Identify conflicts.
5. Generate briefing document.

---

## 7. Proposed Source Layout

```text
src/
    knowledge_assistant/

        ingestion/
            loaders.py
            parser.py

        storage/
            vector_store.py
            metadata_store.py

        retrieval/
            retriever.py

        llm/
            ollama.py

        analysis/
            extractor.py

        agents/
            agent.py

        ui/
            cli.py

        config.py
        main.py
```

---

## 8. Configuration

Configuration should be externalised.

Example:

```yaml
llm:
    provider: ollama
    model: qwen3

embedding:
    model: nomic-embed-text

storage:
    vector_database: chromadb

documents:
    directory: ./knowledge
```

Secrets must not be stored in configuration files.

---

## 9. Testing Strategy

Each component should have independent tests.

Examples:

```text
tests/

test_ingestion.py

test_chunking.py

test_embeddings.py

test_storage.py

test_retrieval.py

test_llm_interface.py
```

Tests should use small artificial documents rather than private data.

---

## 10. Deployment Model

Initial deployment:

```text
Desktop Computer

    |
    +-- Python Application
    |
    +-- Ollama
    |
    +-- Vector Database
```

Future options:

```text
Hybrid Deployment

NAS:
    documents
    indexes
    databases

Desktop GPU:
    inference
    agents
```

---

## 11. Architectural Decisions

### Decision 001

Use RAG as the initial architecture.

Reason:

Provides useful capability without requiring model training.

---

### Decision 002

Use local LLM inference.

Reason:

Privacy, control, and suitability for personal knowledge management.

---

### Decision 003

Separate document storage from software repository.

Reason:

Prevent accidental disclosure of private information.

---

## 12. Future Considerations

Potential future enhancements:

- Web interface.
- Multi-user support.
- Authentication.
- Document version tracking.
- Knowledge graph database.
- Automated ingestion.
- Integration with calendars and task systems.
- Mobile access.
- External API access.

### 4.8 Application Management Layer

The current application skeleton provides three read-only management components:

- ConfigManager loads validated YAML and optional .env values through the configuration subsystem.
- PromptManager loads only Markdown prompt files declared by configuration.
- WorkspaceManager selects configured workspaces without reading or ingesting documents.

A workspace is an isolated named document collection with a description, document root,
vector collection name, and enabled state. The CLI can inspect workspaces and prompts.
The M1 pipeline provides ingestion, vector storage and retrieval; M2.3 consumes that
retrieval boundary to build bounded context and invoke the configured local LLM.

### 4.9 Question-Answer Evaluation Layer

M2.4 adds an evaluation adapter around the public M2.3 question-answer service.
It does not implement a second search or answer path. A recording search adapter
captures the single ranked retrieval used by each answer so retrieval, context,
citation, abstention and latency measures all describe the same invocation.

```text
Versioned QA benchmark
        |
        v
M2.3 answer service -- one M1 retrieval --> bounded context --> local LLM
        |
        v
Privacy-safe raw report --> human review --> scored report
        |                                      |
        +-------- baseline/candidate comparison+
```

Raw, scored and comparison reports are immutable. An active baseline is a small
designation record pointing to an immutable scored run. Reports retain logical
source identities and settings but deliberately omit retrieved chunk text and
fully rendered prompts. The `qa-evaluate` command is separate from the M1
retrieval-only `evaluate` command.
