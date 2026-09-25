# Project Definition Document (PDD)

**Version:** 0.1
**Status:** Initial Architecture Definition
**Date:** 2026-07-21

---

## 1. Purpose

The Knowledge Assistant project aims to develop a local, extensible AI-assisted knowledge management and decision support platform.

The initial capability will be a local document question-answering system based on Retrieval-Augmented Generation (RAG). The longer-term goal is to evolve this into a knowledge analysis and agent-assisted planning system capable of supporting research, operations, and decision-making.

The system will prioritise:

- Local processing and data privacy.
- Traceable answers supported by source documents.
- Extensibility across different knowledge workspaces.
- Human-controlled decision-making.
- Maintainable, modular software architecture.

---

## 2. Vision

The long-term vision is a personal knowledge assistant that can:

- Understand collections of documents and information sources.
- Retrieve relevant evidence when answering questions.
- Identify relationships between information sources.
- Detect agreement, disagreement, uncertainty, and changes over time.
- Assist with planning, preparation, reporting, and operational activities.

The system should become a reusable platform rather than a single-purpose application.

Potential workspaces include:

- Personal projects.
- Community and volunteer organisations.
- Sports and training analysis.
- Research activities.
- Technical documentation.
- Planning and operational support.

---

## 3. Initial Scope

### Phase 1: Document Question Answering

The first implementation will provide:

- Document ingestion from a specified directory.
- Text extraction from common document formats.
- Document chunking.
- Embedding generation.
- Vector-based retrieval.
- Local LLM question answering.
- Source citation in responses.

Initial supported document types:

- PDF
- Microsoft Word documents
- Plain text
- Markdown
- Email formats where practical

The system will initially operate on a single local document repository.

---

## 4. Future Capabilities

### Phase 2: Knowledge Extraction and Analysis

The system will extract structured information from documents.

Potential entities:

- People
- Organisations
- Projects
- Meetings
- Decisions
- Actions
- Risks
- Claims
- Evidence
- Dates
- Locations

The system will support analysis such as:

- Agreement identification.
- Contradiction detection.
- Timeline reconstruction.
- Decision history.
- Outstanding action tracking.
- Evidence comparison.

---

### Phase 3: Agent-Assisted Workflows

The system will support agentic workflows where AI components perform multi-step tasks.

Examples:

- Preparing meeting briefings.
- Producing project summaries.
- Identifying outstanding actions.
- Reviewing documents against objectives.
- Creating planning documents.
- Performing research tasks.

Agents must remain:

- Evidence-based.
- Transparent.
- Traceable to source information.
- Under human supervision.

---

## 5. Design Principles

### 5.1 Local First

Sensitive information should remain under user control.

Preferred operation:

- Local LLM inference.
- Local document storage.
- Local embeddings.
- Local vector databases.

External services may be considered where beneficial, but should not be required.

---

### 5.2 Modular Architecture

The system should be composed of replaceable components.

Examples:

- LLM providers can change.
- Embedding models can change.
- Vector databases can change.
- User interfaces can change.

Business logic should not depend on a specific technology choice.

---

### 5.3 Separation of Data and Software

The software repository must not contain private documents.

The system will separate:

```
Software
    |
    +-- source code
    +-- documentation
    +-- tests


Knowledge Data
    |
    +-- documents
    +-- embeddings
    +-- indexes
```

---

### 5.4 Traceability

AI-generated answers must be supported by evidence.

Responses should identify:

- Source document.
- Relevant section or page where possible.
- Confidence or uncertainty where appropriate.

---

### 5.5 Human Control

The system assists human reasoning but does not replace human judgement.

Agents may:

- gather information,
- summarise,
- compare,
- suggest options.

Humans remain responsible for:

- decisions,
- approvals,
- actions.

---

## 6. Target Architecture

High-level architecture:

```
Documents
    |
    v
Ingestion Pipeline
    |
    +----------------+
    |                |
    v                v
Vector Store     Metadata Store
    |                |
    +----------------+
             |
             v
      Retrieval Layer
             |
             v
          LLM Layer
             |
             v
       User Interface
```

Future extension:

```
Knowledge Graph
        |
        v
Analysis Engine
        |
        v
Agent Framework
```

---

## 7. Technology Direction

Initial technology choices:

| Area | Technology |
|---|---|
| Language | Python |
| Development environment | PyCharm |
| Version control | GitHub |
| LLM runtime | Ollama |
| Retrieval framework | LlamaIndex |
| Vector database | ChromaDB |
| Testing | pytest |
| Formatting | Black/Ruff |
| Configuration | YAML/environment variables |

These choices may change as the project develops.

---

## 8. Security Model

The system must protect private information.

Requirements:

- No documents committed to Git.
- No credentials stored in source code.
- Configuration separated from secrets.
- Local data storage by default.
- Clear separation between public software and private knowledge.

Sensitive directories must be excluded through `.gitignore`.

---

## 9. Development Approach

The project will follow incremental development.

Each phase should produce a usable capability.

Development cycle:

1. Define requirement.
2. Design component.
3. Implement.
4. Test.
5. Review.
6. Commit.
7. Document architectural decisions.

AI coding assistants may be used, but all architectural decisions remain documented.

---

## 10. Development Roadmap

### Milestone 0 — Foundation

Deliverables:

- GitHub repository.
- Project structure.
- Documentation.
- Development environment.
- Testing framework.

Status:

In progress.

---

### Milestone 1 — Local RAG Assistant

Deliverables:

- Document ingestion.
- Vector indexing.
- Local embeddings.
- Ollama integration.
- Question answering.
- Source citations.

---

### Milestone 2 — Knowledge Layer

Deliverables:

- Entity extraction.
- Metadata enrichment.
- Claim extraction.
- Relationship modelling.

---

### Milestone 3 — Analysis Layer

Deliverables:

- Agreement detection.
- Contradiction detection.
- Timeline generation.
- Decision tracking.

---

### Milestone 4 — Agent Layer

Deliverables:

- Workflow execution.
- Planning support.
- Reporting assistance.
- Workspace-specific assistants.

---

## 11. Success Criteria

The project will be considered successful when it can:

1. Answer questions from a private document collection.
2. Provide evidence for its answers.
3. Operate locally.
4. Support multiple knowledge workspaces.
5. Identify relationships between information sources.
6. Assist with planning and operational tasks while maintaining human oversight.

---

## 12. Open Questions

The following decisions remain open:

- Choice of final vector database.
- Knowledge graph technology.
- Web interface technology.
- Multi-user support requirements.
- Integration with external systems.
- Long-term storage strategy.
- Deployment location (desktop, NAS, or hybrid).
-
