# Document Chunking

**Identifier:** M1.2

**Status:** Implemented

**Related Milestone:** M1 – Local Retrieval Assistant

---

## Purpose

The Document Chunking subsystem transforms normalised Document artefacts into semantically meaningful chunks suitable for embedding generation and retrieval.

The primary objective is **high-quality retrieval**, not simply dividing documents into smaller pieces.

Chunking shall maximise semantic coherence, preserve document structure, maintain provenance and produce chunks that can be understood independently.

---

## Design Goals

The implementation shall optimise for retrieval quality rather than chunk count.

Every generated chunk should:

* represent a coherent unit of meaning
* discuss a single primary subject where practical
* remain understandable when retrieved independently
* preserve sufficient context for later reasoning
* retain complete provenance
* preserve document hierarchy wherever possible

The implementation should favour semantic integrity over strict adherence to target chunk sizes.

---

## Scope

This feature includes:

* Reading ingested document artefacts
* Semantic chunk generation
* Structural analysis
* Heading detection
* Metadata propagation
* Chunk quality assessment
* Statistics generation
* Intermediate artefact generation
* CLI integration

---

## Out of Scope

This feature does not include:

* Embedding generation
* Vector database construction
* Question answering
* Retrieval
* OCR
* Summarisation
* Contradiction detection
* Duplicate detection

---

## User Stories

As a user I can convert documents into semantically meaningful chunks suitable for searching.

As a developer I can inspect chunk artefacts before embedding generation.

As an administrator I can trace every chunk back to its originating document.

---

## Processing Hierarchy

Chunk boundaries shall be determined using the highest available semantic structure.

The preferred hierarchy is:

1. Document
2. Major Heading
3. Section Heading
4. Paragraph
5. Sentence
6. Token Limit (last resort)

The implementation shall only move to the next level when the current level cannot satisfy the target chunk size.

---

## Heading Detection

Where explicit document structure exists (Markdown headings, DOCX heading styles etc.) it shall be used.

Where structure is unavailable (for example many PDFs), the implementation should infer headings using heuristics.

Possible indicators include:

* short standalone lines
* Title Case
* numbered headings
* trailing question marks
* repeated formatting
* surrounding whitespace
* common heading phrases
* PDF font information (where available)

Heading detection is heuristic and does not need to be perfect.

---

## Functional Requirements

### FR1 – Input

Read Document artefacts produced by the ingestion pipeline.

---

### FR2 – Semantic Structure

The implementation shall identify logical document structure before chunk generation.

Logical structure includes:

* titles
* headings
* sections
* paragraphs
* lists
* tables

---

### FR3 – Chunk Size

Target chunk size:

* approximately 400–700 words

Recommended maximum:

* approximately 1000 words

These limits are guidance rather than strict requirements.

Semantic integrity should take precedence over exact size.

---

### FR4 – Oversized Sections

Oversized sections shall be divided using the following order:

1. Paragraph boundaries
2. Sentence boundaries
3. Token count

This order shall not be reversed.

---

### FR5 – Small Sections

Small adjacent sections may be merged where doing so improves retrieval quality.

Section headings should be preserved within merged chunks.

---

### FR6 – Chunk Quality

Each generated chunk should:

* preserve complete paragraphs
* preserve lists
* preserve tables where practical
* avoid ending mid-sentence
* include the relevant section heading
* avoid mixing unrelated topics

---

### FR7 – Semantic Anchors

Where present, the implementation should preserve together:

* decisions
* action items
* recommendations
* objectives
* risks
* budgets
* responsibilities
* dates
* resolutions

These represent high-value retrieval units.

---

### FR8 – Metadata

Every chunk shall retain:

* chunk identifier
* document identifier
* workspace
* document title
* section title
* chunk number
* total chunk count
* source filename
* relative path
* checksum
* page information (where available)
* original document metadata

Future metadata may include:

* heading level
* parent section
* chunk quality
* language

---

### FR9 – Provenance

Every chunk shall remain traceable to:

* the original document
* the document location
* the approximate document position
* the original metadata

This information shall later support citations.

---

### FR10 – Output

Chunk artefacts shall be written beneath:

```text
workspaces/<workspace>/artifacts/chunks/
```

JSON shall be used for the initial implementation.

---

### FR11 – Statistics

The command shall report:

* documents processed
* chunks generated
* average chunk size
* smallest chunk
* largest chunk
* heading detections
* paragraph splits
* sentence splits
* forced token splits
* elapsed time

---

### FR12 – Error Handling

Processing shall continue if an individual document cannot be chunked.

Errors shall be summarised after processing.

---

## Chunk Model

Each chunk should contain at least:

```text
chunk_id
document_id
workspace
document_title
section_title
chunk_index
chunk_count
page
source_filename
relative_path
checksum
text
metadata
```

Future optional fields:

```text
heading_level
parent_section
chunk_quality
entities
topics
```

---

## Processing Workflow

```text
Document Artefacts
        │
        ▼
Read Document
        │
        ▼
Detect Structure
        │
        ▼
Infer Headings
        │
        ▼
Build Sections
        │
        ▼
Merge Small Sections
        │
        ▼
Split Large Sections
        │
        ▼
Generate Chunk Objects
        │
        ▼
Validate Chunk Quality
        │
        ▼
Write Chunk Artefacts
```

---

## Validation

Chunk quality shall be assessed by retrieval usefulness rather than only by size.

A chunk should be considered successful if a human reviewer believes it could answer a focused question without requiring extensive neighbouring context.

Typical questions include:

* Who approved this proposal?
* What funding limits apply?
* Which actions remain outstanding?
* What evidence supports this recommendation?

---

## Document-Type Awareness

The implementation may apply specialised strategies for different document types including:

* board minutes
* agendas
* manager reports
* funding applications
* policies
* financial reports
* correspondence

Different document classes naturally contain different semantic boundaries.

---

## Configuration

Typical configurable values include:

* target chunk size
* maximum chunk size
* minimum chunk size
* overlap strategy
* overlap amount
* heading detection options
* document-type strategies

All values shall be configurable through the project configuration system.

---

## Command Line Interface

The feature introduces:

```text
knowledge-assistant chunk
```

Example output:

```text
Workspace: kingshill

Reading ingested documents...

49 documents loaded

Generating chunks...

683 chunks created

Average size: 520 words

Largest chunk: 742 words

Smallest chunk: 182 words

Headings detected: 587

Paragraph splits: 61

Sentence splits: 8

Forced token splits: 0

Chunk artefacts written to:

workspaces/kingshill/artifacts/chunks/

Elapsed time: 4.1 seconds
```

---

## Acceptance Criteria

This feature is complete when:

* Documents are converted into semantic chunks.
* Chunk hierarchy is preserved.
* Metadata is retained.
* Provenance is retained.
* Chunk quality satisfies manual review.
* Chunk artefacts are written.
* CLI integration is complete.
* Tests pass.
* Documentation is updated.

---

## Testing

The implementation shall include tests covering:

* heading detection
* section detection
* paragraph preservation
* sentence fallback
* oversized sections
* metadata propagation
* provenance preservation
* chunk numbering
* CLI behaviour
* error handling

---

## Future Enhancements

Potential future improvements include:

* language-aware chunking
* semantic boundary detection
* adaptive chunk sizing
* table-aware chunking
* OCR-aware chunking
* entity extraction
* topic classification
* action-item detection
* contradiction markers
* duplicate chunk detection
* incremental chunk regeneration

---

### M2.2 metadata propagation

Chunks copy the complete extractor and evidence namespaces from their source
document. Control manifests, module records, policy, and claim-review notes are
not ingestion documents and therefore cannot produce chunks. Association
changes flow to chunk artefacts while root-scoped retention continues to obey
M2.1.

## Revision History

| Version | Date       | Author  | Summary                                                                                                           |
| ------- | ---------- | ------- | ----------------------------------------------------------------------------------------------------------------- |
| 2.0     | 2026-07-30 | Project | Expanded semantic chunking specification with retrieval-oriented design goals and hierarchical chunking strategy. |
