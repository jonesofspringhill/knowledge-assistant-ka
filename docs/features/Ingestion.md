# Document Ingestion

**Identifier:** M1.1

**Status:** Approved

**Related Milestone:** M1 – Local Question Answering

---

## Purpose

The Document Ingestion subsystem is responsible for discovering, loading and normalising 
documents contained within the active workspace.

Its purpose is to transform a heterogeneous collection of source documents into a consistent 
internal representation that can be used by later processing stages including chunking, 
embedding generation, retrieval and question answering.

The ingestion subsystem does **not** perform semantic processing.

---

## Scope

This feature includes:

- Document discovery
- File type recognition
- Text extraction
- Metadata extraction
- Document normalisation
- Intermediate artefact generation
- Progress reporting
- Error reporting

---

## Out of Scope

The following capabilities are explicitly excluded from this milestone:

- Chunk generation
- Embedding generation
- Vector databases
- Retrieval
- Question answering
- OCR
- Email parsing
- Spreadsheet support
- Image analysis

These will be implemented in later milestones.

---

## User Stories

As a user I can ingest the documents within a workspace.

As a user I receive a summary of successful and failed imports.

As a developer I can inspect the intermediate document artefacts before further processing.

As an administrator I can determine whether documents have changed since the previous ingestion.

---

## Functional Requirements

### FR1 – Workspace Discovery

The system shall determine the active workspace using the Workspace Manager.

---

### FR2 – Document Discovery

The system shall recursively search:

```text
workspaces/<workspace>/documents/
```

for supported document types.

---

### FR3 – Supported File Types

The initial implementation shall support:

- PDF
- Microsoft Word (.docx)
- Markdown (.md)
- Plain text (.txt)

Unsupported file types shall be ignored with an informational message.

---

### FR4 – Text Extraction

The system shall extract all available textual content from each supported document.

If text extraction fails for a document, the failure shall be reported while processing continues.

---

### FR5 – Metadata Extraction

Where available, the following metadata shall be extracted:

- filename
- relative path
- file type
- file size
- created timestamp
- modified timestamp
- document title
- document author
- page count (where applicable)

Additional metadata may be added in future releases.

---

### FR6 – Document Identity

Each ingested document shall receive:

- a unique identifier
- a SHA-256 checksum

The checksum shall be used for future change detection.

---

### FR7 – Normalisation

Regardless of source format, every document shall be converted into a common internal Document model.

Subsequent processing stages shall not require knowledge of the original file type.

---

### FR8 – Intermediate Artefacts

The ingestion pipeline shall write structured intermediate artefacts beneath:

```text
workspaces/<workspace>/artifacts/ingestion/
```

The artefacts shall be human-readable and suitable for inspection and debugging.

JSON is acceptable for the initial implementation.

---

### FR9 – Progress Reporting

The CLI shall report:

- documents discovered
- documents processed
- successes
- failures
- elapsed time

---

### FR10 – Error Recovery

Failure to ingest one document shall not terminate the ingestion process.

All failures shall be summarised at completion.

---

## Command Line Interface

The feature shall introduce:

```text
knowledge-assistant ingest
```

Example output:

```text
Workspace: kingshill

Scanning documents...

126 documents discovered

Processing...

PDF         83
DOCX        14
Markdown    21
Text         8

Succeeded: 124
Failed:       2

Intermediate artefacts written to:

workspaces/kingshill/artifacts/ingestion/

Elapsed time: 18.2 seconds
```

---

## Inputs

The ingestion subsystem shall use:

- Active workspace
- Workspace configuration
- Document directory
- Global configuration

No command-line parameters are required for the initial implementation.

---

## Outputs

The subsystem shall produce:

- Normalised Document objects
- Intermediate JSON artefacts
- Processing summary
- Error report
- Checksums

No vector database shall be created during this milestone.

---

## Processing Workflow

```text
Workspace
      │
      ▼
Document Discovery
      │
      ▼
File Identification
      │
      ▼
Text Extraction
      │
      ▼
Metadata Extraction
      │
      ▼
Document Normalisation
      │
      ▼
Intermediate Artefacts
```

---

## Design Constraints

The implementation shall:

- follow the Workspace architecture
- obtain configuration exclusively through the configuration subsystem
- preserve source documents
- avoid hard-coded paths
- avoid hard-coded model names
- separate file-type-specific logic from the remainder of the pipeline

---

## Acceptance Criteria

The feature is complete when:

- Supported documents are discovered recursively.
- Text is extracted successfully from supported document types.
- Metadata is extracted where available.
- SHA-256 checksums are generated.
- A common Document model is produced.
- Intermediate artefacts are written.
- Processing continues after individual failures.
- Unit tests pass.
- CLI help is updated.
- Milestone documentation is updated.

---

## Testing

The implementation shall include tests covering:

- document discovery
- PDF extraction
- DOCX extraction
- Markdown extraction
- text extraction
- metadata extraction
- checksum generation
- error handling
- CLI behaviour

External dependencies should be mocked where practical.

---

## Future Enhancements

Future versions may include:

- OCR for scanned documents
- email (.eml and .msg) ingestion
- spreadsheet support
- HTML ingestion
- archive extraction
- duplicate detection
- incremental ingestion
- parallel processing
- document language detection
- automatic document classification

---

## Documentation

Implementation of this feature may require updates to:

- Milestone M1
- Project Journal
- CLI documentation
- Architecture documentation (if required)

---

## Revision History

| Version | Date | Author | Summary |
|----------|------|--------|---------|
| 1.0 | YYYY-MM-DD | Project | Initial approved specification |
