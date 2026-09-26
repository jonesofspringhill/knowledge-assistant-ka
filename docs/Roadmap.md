# Project Roadmap

**Version:** 0.1  
**Status:** Initial Development Roadmap  
**Date:** 2026-07-21

---

## 1. Purpose

This roadmap defines the planned evolution of the `ka` knowledge and agent
platform.

The project will progress incrementally from a local document question-answering
system into a provider-neutral knowledge analysis and agent-assisted decision
support platform.

Each milestone should deliver a usable capability before moving to the next stage.

---

## 2. Development Philosophy

The project will follow these principles:

- Build a useful system early.
- Avoid unnecessary complexity.
- Preserve architectural flexibility.
- Maintain traceability to source information.
- Keep private data separate from software.
- Add intelligence progressively.

The initial focus is reliability and usability rather than advanced AI capabilities.

---

## 3. Milestone Overview

| Milestone | Capability | Status      |
|---|---|-------------|
| M0 | Project foundation | Complete    |
| M1 | Local retrieval foundation | Complete    |
| M2 | Local grounded question answering | In Progress |
| M3 | Knowledge extraction and agent-tool contract | In Progress |
| M4 | Agreement and contradiction analysis | Planned     |
| M5 | Agent workflows | Planned     |
| M6 | Decision support platform | Future      |

---

## 4. Milestone M0 — Project Foundation

### Objective

Establish the engineering foundation required for long-term development.

### Deliverables

- GitHub repository.
- Python project structure.
- Virtual environment.
- Documentation set.
- Coding standards.
- Test framework.
- Continuous integration.

### Completion Criteria

The project can be cloned, installed, tested, and extended by another developer.

---

## 5. Milestone M1 — Local Document Question Answering

### Objective

Create a local RAG-based assistant capable of answering questions from a document collection.

### Capabilities

- Load documents from a directory.
- Extract text.
- Split documents into chunks.
- Generate embeddings.
- Store vectors.
- Retrieve relevant context.
- Query local LLM.
- Provide source citations.

### Initial Technologies

- Python.
- LlamaIndex.
- ChromaDB.
- A configurable local or hosted model adapter.
- Local embedding model.

### Completion Criteria

Example:

Input:

> What decisions were made about the project budget?

Output:

- Answer generated from documents.
- Supporting source documents identified.

---

## 6. Milestone M2 — Retrieval Improvement

### Objective

Improve answer quality and reliability.

### Capabilities

- Safe multi-workspace refresh and named document roots (M2.1, complete).
- Evidence metadata and exact retrieval filters (M2.2, complete).
- Grounded single-question answers with bounded context, citations and explicit
  insufficient-evidence handling (M2.3, complete; real-workspace validation
  pending).
- Versioned full-pipeline QA evaluation, fixed gates, human review and immutable
  baseline/candidate comparison (M2.4, implemented; clean baseline pending).
- Retrieval, context or prompt refinement only when evaluation evidence
  identifies a weakness.

### Completion Criteria

The system reliably identifies relevant information from a mixed document
collection and produces grounded cited answers that pass the frozen M2.4
automatic and human-review gates without an unapproved M1 retrieval regression.

---

## 7. Milestone M3 — Knowledge Extraction

### Objective

Move from document retrieval to structured understanding.

M3.0 first establishes a provider-neutral, workspace-scoped tool contract so
that later extraction and agent workflows consume KA capabilities rather than
bypassing provenance and workspace isolation.

### Capabilities

Extract:

- People.
- Organisations.
- Projects.
- Meetings.
- Decisions.
- Actions.
- Claims.
- Evidence.

### New Components

- Agent-tool registry, JSON schemas, authority checks and audit trail (M3.0,
  in progress).
- Metadata database.
- Entity extraction.
- Relationship storage.

### Completion Criteria

The system can answer:

> What decisions have been made and who owns the resulting actions?

---

## 8. Milestone M4 — Agreement and Contradiction Analysis

### Objective

Identify relationships between statements across documents.

### Capabilities

- Compare claims.
- Identify supporting evidence.
- Detect contradictions.
- Detect superseded information.
- Build timelines.
- Track decision changes.

Examples:

> Which documents disagree about the budget?

> Which decisions have changed since January?

### Completion Criteria

The system can explain conflicting information with references to evidence.

---

## 9. Milestone M5 — Agent Workflows

### Objective

Introduce autonomous multi-step assistance.

### Capabilities

Agents can:

- Retrieve information.
- Analyse evidence.
- Create summaries.
- Prepare reports.
- Track actions.
- Support planning activities.

Example:

> Prepare the agenda for the next project meeting.

Possible workflow:

1. Find previous meeting notes.
2. Identify outstanding actions.
3. Review recent correspondence.
4. Summarise issues.
5. Produce agenda draft.

---

## 10. Milestone M6 — Decision Support Platform

### Objective

Provide structured assistance for complex planning and operational decisions.

### Capabilities

- Compare options.
- Identify assumptions.
- Assess risks.
- Summarise evidence.
- Present alternatives.
- Track consequences.

The system remains an assistant and does not replace human judgement.

---

## 11. Future Knowledge workspaces

The platform should support multiple workspaces.

Potential workspaces:

### Community and Volunteer Work

Examples:

- Meeting records.
- Funding applications.
- Policies.
- Volunteer coordination.
- Event planning.

### Sport and Training

Examples:

- Training logs.
- Performance data.
- Coaching notes.
- Competition preparation.

### Research

Examples:

- Papers.
- Notes.
- Literature reviews.
- Technical documentation.

---

## 12. Future Integrations

Potential future integrations:

- Obsidian knowledge bases.
- NAS document repositories.
- Calendar systems.
- Task management systems.
- Fitness platforms.
- Web sources.
- Email systems.

---

## 13. Review Points

Architecture should be reviewed after:

- First working RAG system.
- Introduction of knowledge graph.
- Introduction of agents.
- Any move from single-user to multi-user operation.

---

## 14. Current Priority

The immediate development goal is:

> Record and review the clean M2.4 QA baseline, then refine only measured
> retrieval or answer-quality weaknesses.

All future capabilities should build on this foundation.
