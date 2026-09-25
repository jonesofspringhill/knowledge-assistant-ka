# Data Model Document

Ingestion also persists `ExtractionRecord` cache entries containing a source
checksum, extractor fingerprint, extracted text and format metadata. These are
independent of document identity and evidence associations. `IngestionSummary`
adds `extractions_performed` and `extractions_reused` counters. See
[ka incremental ingestion](features/KA-Incremental-Ingestion.md).

**Version:** 0.1  
**Status:** Initial Data Model Definition  
**Date:** 2026-07-21

---

## 1. Purpose

This document defines the data structures used by the Knowledge Assistant platform.

The model supports the evolution from:

1. Document retrieval and question answering.
2. Knowledge extraction.
3. Agreement and contradiction analysis.
4. Agent-assisted planning and decision support.

The data model separates:

- Original source information.
- Extracted knowledge.
- Relationships between knowledge items.
- AI-generated interpretations.

---

## 2. Design Principles

### 2.1 Source Evidence Must Be Preserved

The original document content is authoritative.

Extracted information must always maintain a reference back to:

- source document,
- location within document,
- extraction method,
- confidence level.

No derived information should exist without traceability.

---

### 2.2 Derived Knowledge Is Not Source Truth

The system distinguishes between:

#### Source

Information directly contained in a document.

Example:

> "The committee agreed to defer expenditure until April."

#### Interpretation

AI-generated understanding.

Example:

> "The committee postponed spending decisions."

Interpretations may be wrong and must remain linked to evidence.

---

## 3. Core Entities

### 3.1 Document

Represents an original source file.

Example:

- PDF report.
- Email.
- Meeting minutes.
- Spreadsheet.
- Web page.

Structure:

```text
Document
{
    id,
    filename,
    path,
    document_type,
    created_date,
    modified_date,
    author,
    source_system,
    metadata
}
```

---

### 3.2 Document Chunk

A searchable section of a document.

Used by the RAG system.

Structure:

```text
Chunk
{
    id,
    document_id,
    text,
    position,
    page_number,
    section,
    embedding_reference
}
```

Relationship:

```text
Document
    |
    contains
    |
Chunk
```

---

## 4. Knowledge Entities

These entities represent extracted understanding.

---

### 4.1 Person

Represents an individual.

Examples:

- author,
- participant,
- owner,
- decision maker.

Structure:

```text
Person
{
    id,
    name,
    organisation,
    roles
}
```

---

### 4.2 Organisation

Represents a group or organisation.

Examples:

- company,
- charity,
- committee,
- supplier.

Structure:

```text
Organisation
{
    id,
    name,
    type
}
```

---

### 4.3 Project

Represents a body of related activity.

Structure:

```text
Project
{
    id,
    name,
    description,
    status
}
```

---

### 4.4 Event

Represents something occurring at a specific time.

Examples:

- meeting,
- training session,
- competition,
- deadline.

Structure:

```text
Event
{
    id,
    name,
    date,
    location,
    participants
}
```

---

### 4.5 Meeting

Specialised event.

Structure:

```text
Meeting
{
    id,
    date,
    attendees,
    agenda,
    minutes_reference
}
```

---

## 5. Decision Model

A decision represents an agreed choice.

Structure:

```text
Decision
{
    id,
    description,
    date,
    status,
    owner,
    evidence
}
```

Example:

```text
Decision:

Purchase new equipment

Date:

15 March

Evidence:

Board meeting minutes page 4
```

---

## 6. Action Model

Represents work resulting from decisions.

Structure:

```text
Action
{
    id,
    description,
    owner,
    due_date,
    status,
    evidence
}
```

Possible statuses:

```text
Open
In Progress
Complete
Blocked
Cancelled
```

---

## 7. Claim Model

A claim represents a statement extracted from a document.

This is the basis for contradiction detection.

Structure:

```text
Claim
{
    id,
    subject,
    predicate,
    object,
    source,
    confidence,
    timestamp
}
```

Example:

```text
Subject:
Budget

Predicate:
will increase

Object:
10 percent

Source:
Finance report
```

---

## 8. Evidence Model

Evidence links knowledge back to source material.

Structure:

```text
Evidence
{
    id,
    document_id,
    chunk_id,
    quote,
    confidence
}
```

Relationship:

```text
Claim
   |
supported_by
   |
Evidence
   |
derived_from
   |
Document
```

---

## 9. Relationship Model

Knowledge is represented through relationships.

Examples:

```text
Person
    authored
        Document


Person
    attended
        Meeting


Meeting
    created
        Decision


Decision
    generated
        Action


Claim
    supported_by
        Evidence
```

---

## 10. Contradiction and Agreement Model

The system will eventually compare claims.

Relationship types:

```text
Supports

Contradicts

Extends

Updates

Supersedes

Uncertain
```

Example:

```text
Claim A:

"Budget approved in March"


Claim B:

"Budget approval postponed until April"


Relationship:

Claim A
    contradicted_by
Claim B
```

---

## 11. Timeline Model

Time is critical when interpreting changing information.

Objects may have:

- creation date,
- event date,
- effective date,
- expiry date.

Example:

```text
January:

Supplier A selected.


March:

Supplier B selected.
```

The system should determine whether:

- this is a contradiction,
- or a later replacement decision.

---

## 12. Metadata Model

All objects should support metadata.

Example:

```text
Metadata
{
    created,
    modified,
    source,
    confidence,
    tags,
    workspace
}
```

The `workspace` field supports multiple knowledge areas.

Examples:

```text
sport

volunteering

personal

research

technical
```

---

## 13. Storage Strategy

Initial implementation:

```text
Vector Database

    Stores:
        chunks
        embeddings
        metadata
```

Future implementation:

```text
Knowledge Graph

    Stores:
        entities
        relationships
        claims
        decisions
```

Relational storage may also be used for:

- configuration,
- user preferences,
- workflow state.

---

## 14. Initial RAG Data Model

The first implementation only requires:

```text
Document

    |
    |
Chunk

    |
    |
Embedding

    |
    |
Vector Store
```

The richer model will be introduced incrementally.

---

## 15. Future Extensions

Potential additions:

- Task management integration.
- Calendar integration.
- Sensor and activity data.
- Financial records.
- Web sources.
- Multimedia documents.
- OCR-derived information.

The model should support new knowledge types without redesigning existing components.

---

## 16. M2.4 Evaluation Data Model

QA evaluation data is an audit model, not source truth and not part of the
vector collection.

```text
QABenchmark
  +-- QACase (question, category, answerability, filters)
        +-- expected/acceptable logical sources
        +-- expected facts and forbidden claims

QARunReport
  +-- benchmark checksum and pinned settings
  +-- CaseResult per case and repeat
        +-- ranked evidence identities (no chunk text)
        +-- context source identities
        +-- citation diagnostics and automatic measures
  +-- aggregate metrics and automatic gates

ReviewFile -- exact run/checksum binding and rubric entries
     |
     v
ScoredReport -- raw/review checksums, human metrics and all gates
     |
     +-- BaselineDesignation
     +-- ComparisonReport
```

Logical `source_path` or `document_id` values identify expected evidence. Case
filters are recorded on every result. Raw reports preserve the question and
model answer for review, but exclude source text, rendered prompts, credentials
and private absolute paths. Later scoring and comparison create new artefacts
rather than modifying prior measurements.
