# Codex Development Instructions

## Purpose

This document provides guidance for AI-assisted development of the Knowledge Assistant project.

Read this document before implementing any feature.

The project architecture is defined by:

* ProjectDefinition.md
* Architecture.md
* DataModel.md
* Development.md
* Roadmap.md

These documents define the intended design. Do not depart from them without clearly documenting and justifying the change.

---

## Project Mission

Develop a private, extensible knowledge platform that evolves through the following stages:

1. Document ingestion.
2. Retrieval-Augmented Generation (RAG).
3. Structured knowledge extraction.
4. Agreement and contradiction analysis.
5. Agent-assisted planning and decision support.

The system is intended to support multiple knowledge workspaces, including community projects, research, sport, and personal knowledge management.

---

## Current Milestone

Current milestone:

**M2 – Local grounded question answering** (M2.4 baseline acceptance pending; see milestones/M2.md).

Do not begin implementing future capabilities until the current milestone has been completed and tested.

---

## Engineering Principles

* Prefer simple, maintainable solutions.
* Implement one feature at a time.
* Keep modules small and focused.
* Separate responsibilities clearly.
* Preserve architectural flexibility.
* Ensure all behaviour is configurable where appropriate.

---

## Architectural Rules

The following rules are mandatory unless explicitly revised.

* Configuration is loaded only through the configuration subsystem.
* Prompt text is stored in Markdown files.
* Secrets are loaded only from `.env`.
* No hard-coded file paths.
* No hard-coded model names.
* No direct access to vector databases outside the storage layer.
* No direct Ollama calls outside the LLM interface.
* Source documents remain immutable.
* Derived knowledge must retain references to source evidence.

---

## Coding Standards

* Python 3.12+
* Use Pydantic for configuration models.
* Use Black for formatting.
* Use Ruff for linting.
* Use pytest for testing.
* Use type hints for public interfaces.
* Write clear docstrings for public classes and functions.

---

## Testing Requirements

Every significant feature should include:

* Unit tests.
* Appropriate error handling.
* Configuration validation.
* Documentation updates where required.

All tests should pass before considering a task complete.

---

## Documentation

Update documentation whenever implementation changes the design.

Examples:

* Architecture changes → Architecture.md
* New entities → DataModel.md
* New configuration → config documentation
* New milestone progress → milestone document and ProjectJournal.md

---

## Preferred Development Workflow

For every task:

1. Understand the requirement.
2. Review relevant documentation.
3. Design the solution.
4. Implement incrementally.
5. Write tests.
6. Run tests.
7. Update documentation.
8. Commit logically.

---

## Commit Guidelines

Each commit should represent one logical piece of work.

Good examples:

* Implement configuration loader
* Add prompt manager
* Introduce document chunk model

Avoid combining unrelated changes into a single commit.

---

## When in Doubt

Prefer asking for clarification over making architectural assumptions.

Preserve simplicity wherever possible.
