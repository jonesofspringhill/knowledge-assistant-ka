# Knowledge Assistant

A local knowledge assistant for ingesting documents, retrieving evidence and
answering questions with source citations.

## Current state

M0 and M1 are complete. M2 includes workspace refresh, evidence metadata,
grounded single-question answering and QA evaluation. The recorded M2.4 status
still requires a clean baseline and human acceptance before M3 begins.
Knowledge extraction, contradiction analysis and agent workflows are planned.
See the [M2 acceptance record](milestones/M2.md) for details.

Start with the getting-started guide. Feature pages contain both implementation
details and design proposals; their explicitly deferred capabilities are not
available commands. The roadmap and journal preserve development history.

```{toctree}
:maxdepth: 2
:caption: Using the project

getting-started
features/Workspace
features/Ingestion
features/Chunking
features/Retrieval
features/M2.3-Grounded-Single-Question-Answering
features/Doctor
configuration
features/CLI
```

```{toctree}
:maxdepth: 1
:caption: Architecture and development

Architecture
DataModel
features/Retrieval-Pipeline
features/Retrieval-Design
features/M2.4-Question-Answer-Evaluation-and-Retrieval-Refinement
Development
documentation-workflow
CodingStandards
CodexInstructions
```

```{toctree}
:maxdepth: 1
:caption: Plans and history

Vision
ProjectDefinition
Roadmap
milestones/M0
milestones/M1
milestones/M2
DecisionLog
decisions/001-workspace-model
decisions/002-m1-retrieval-boundary
ProjectJournal
```
