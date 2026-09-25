# Development Guide

**Version:** 0.1  
**Status:** Initial Development Definition  
**Date:** 2026-07-21

---

## 1. Purpose

This document defines the development practices, tools, and workflows used to build and maintain the Knowledge Assistant platform.

The objectives are:

- Maintain a high-quality, maintainable codebase.
- Support collaborative development.
- Enable effective use of AI coding assistants.
- Ensure changes are traceable and reversible.
- Encourage incremental development.

---

## 2. Development Environment

### 2.1 Operating Environment

Primary development environment:

- Windows 11
- PyCharm
- Python virtual environment
- GitHub repository

The system should also remain compatible with:

- Linux
- WSL2
- Local server/NAS deployment

---

## 3. Python Environment

### 3.1 Python Version

The initial target version is:

```text
Python 3.12+
```

The project should avoid unnecessary dependence on operating-system-specific features.

---

### 3.2 Virtual Environment

Each developer should use an isolated environment.

Example:

```powershell
python -m venv .venv
```

Activate:

```powershell
.venv\Scripts\activate
```

The virtual environment must not be committed to Git.

---

## 4. Dependency Management

Dependencies should be explicitly declared.

Initial options:

- `pyproject.toml`
- uv package manager

Preferred approach:

```text
pyproject.toml
```

All dependencies must be version controlled.

Example:

```toml
dependencies = [
    "llama-index",
    "chromadb",
    "pytest"
]
```

---

## 5. Code Quality Standards

### 5.1 Formatting

Code formatting:

```text
Black
```

The project should use automatic formatting rather than manual style decisions.

---

### 5.2 Linting

Linting:

```text
Ruff
```

Ruff should check:

- unused imports,
- style issues,
- common errors,
- code quality problems.

---

### 5.3 Type Hints

Python type hints should be used for public functions.

Example:

```python
def load_document(path: str) -> Document:
    ...
```

Type hints improve:

- readability,
- IDE support,
- AI-assisted development.

---

## 6. Project Structure

The project follows a modular structure.

```text
src/
    knowledge_assistant/

        ingestion/

        storage/

        retrieval/

        llm/

        analysis/

        agents/

        ui/
```

Each module should have a clearly defined purpose.

---

## 7. Coding Principles

### 7.1 Small Components

Prefer small, focused modules.

Avoid large classes that combine unrelated responsibilities.

---

### 7.2 Explicit Interfaces

Components should communicate through defined interfaces.

Example:

The retrieval layer should not know whether storage uses:

- ChromaDB,
- FAISS,
- another vector database.

---

### 7.3 Configuration Driven

Values that may change should be configurable.

Examples:

- model names,
- document paths,
- chunk sizes,
- retrieval parameters.

Avoid:

```python
MODEL = "qwen3"
```

Prefer:

```yaml
llm:
    model: qwen3
```

---

## 8. Testing Strategy

Testing is required for all significant functionality.

Testing framework:

```text
pytest
```

---

### 8.1 Unit Tests

Test individual components.

Examples:

```text
test_document_loader.py

test_chunker.py

test_metadata.py
```

---

### 8.2 Integration Tests

Test complete workflows.

Examples:

```text
Document

    ->

Ingestion

    ->

Index

    ->

Query

    ->

Answer
```

---

### 8.3 Test Data

Tests should use:

- synthetic documents,
- small sample datasets,
- predictable examples.

Private documents must not be included in tests.

### 8.4 QA Evaluation Discipline

The committed M2.4 acceptance benchmark and source fixtures must remain
shareable and versioned. Benchmark identity uses the exact file checksum.
Evaluation schemas, rubric version, prompt checksum, model, embedding,
retrieval, context and generation settings must be recorded with each run.

Quality and regression gates are fixed before viewing tuning results. A baseline
must come from a committed clean worktree; dirty or partial runs are diagnostic
only. Prompt, model or retrieval candidates may be compared when the benchmark,
workspace, collection, repeat count and evaluation/rubric schemas remain
compatible. Private benchmarks belong under `benchmarks/qa/local/`, and runtime
reports belong in ignored workspace artefacts.

---

## 9. Git Workflow

### 9.1 Main Branch

The `main` branch represents stable code.

Changes should be made through feature branches.

---

### 9.2 Branch Naming

Use descriptive branch names.

Examples:

```text
feature/pdf-ingestion

feature/chroma-storage

feature/ollama-interface

bugfix/document-parser
```

---

### 9.3 Commit Messages

Commit messages should describe the change.

Good:

```text
Add PDF document loader

Implement Chroma vector store interface
```

Avoid:

```text
Changes

Fix stuff

Update
```

---

## 10. Pull Request Process

Even for solo development, changes should follow a review process.

A pull request should include:

- Purpose of change.
- Implementation summary.
- Tests performed.
- Any design decisions.

This supports future collaboration.

---

## 11. AI-Assisted Development

AI coding assistants may be used to accelerate development.

However:

- Architecture decisions must be documented.
- Generated code must be reviewed.
- Tests must accompany functionality.
- Security implications must be considered.
- Dependencies must be justified.

AI assistants should work from:

- ProjectDefinition.md
- Architecture.md
- DataModel.md
- Development.md

---

## 12. Codex Development Workflow

Tasks given to Codex should be specific.

Preferred:

> Implement the PDF document loader described in Architecture.md. Add unit tests. Follow Development.md coding standards.

Avoid:

> Build a RAG system.

---

## 13. Documentation Requirements

Changes affecting design must update documentation.

Examples:

Adding a new storage technology:

Update:

```text
Architecture.md
DecisionLog.md
```

Adding a new entity:

Update:

```text
DataModel.md
```

---

## 14. Logging and Diagnostics

The application should provide useful diagnostics.

Logs should include:

- processing stages,
- errors,
- document identifiers,
- timing information.

Avoid logging:

- document contents,
- private information,
- credentials.

---

## 15. Error Handling

Errors should:

- provide useful information,
- identify the failing component,
- avoid exposing sensitive data.

The system should fail gracefully where possible.

---

## 16. Security Practices

The project must:

- Never commit secrets.
- Never commit private documents.
- Use environment variables for credentials.
- Validate external inputs.
- Keep dependencies updated.

---

## 17. Release Strategy

Early releases will be informal.

Versioning:

```text
0.x.x
```

until the architecture stabilises.

Future releases may follow semantic versioning:

```text
MAJOR.MINOR.PATCH
```

---

## 18. Current Development Priorities

The immediate priorities are:

1. Review and commit the M2.4 evaluation implementation and frozen benchmark.
2. Run, human-score and designate a clean synthetic baseline.
3. Preserve the M1 retrieval evaluation result as a regression check.
4. Make only evidence-led retrieval, context or prompt refinements.
5. Record the accepted M2.4 result before beginning M3.

Later priorities:

- Knowledge extraction.
- Contradiction detection.
- Agent workflows.
- Decision support.

---

## 19. Definition of Done

A feature is complete when:

- Code is implemented.
- Tests exist.
- Documentation is updated.
- Configuration is externalised.
- Git history clearly describes the change.
- No private data has been committed.

### Documentation site

See [Documentation workflow](documentation-workflow.md) for building, publishing and maintaining the Sphinx site.
