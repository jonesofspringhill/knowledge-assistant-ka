# Getting started

## Install

Use Python 3.12 or newer. From the repository root on Windows:

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -e ".[dev]"
```

If they do not already exist, copy `config/config.example.yaml` to
`config/config.yaml` and `.env.example` to `.env`. Preserve existing local
settings. Set the workspace document path to a small collection of non-private
Markdown, text or PDF files. See [configuration](configuration.md) and
[workspaces](features/Workspace.md).

Install and start Ollama, and make the embedding and answer models selected in
your configuration available locally. Application commands requiring models
need that service; building this documentation does not.

## Check the setup

```powershell
.venv\Scripts\knowledge-assistant --help
.venv\Scripts\knowledge-assistant config validate
.venv\Scripts\knowledge-assistant workspace list
.venv\Scripts\knowledge-assistant doctor
```

Resolve configuration or model errors before processing documents. The
[doctor guide](features/Doctor.md) explains the diagnostics.

## Process and query the active workspace

These commands write derived artifacts for the configured active workspace.
Check the selected workspace and source directory first.

```powershell
.venv\Scripts\knowledge-assistant workspace info
.venv\Scripts\knowledge-assistant ingest
.venv\Scripts\knowledge-assistant chunk
.venv\Scripts\knowledge-assistant embed
.venv\Scripts\knowledge-assistant index --verify
.venv\Scripts\knowledge-assistant search "What does this collection describe?"
.venv\Scripts\knowledge-assistant ask "What does this collection describe?"
```

Search returns retrieved evidence; ask generates a grounded answer with source
references, or reports insufficient evidence. Inspect citations against the
source documents. See [grounded answering](features/M2.3-Grounded-Single-Question-Answering.md)
for limitations and [retrieval](features/Retrieval.md) for refresh and filtering.

The command sequence matches the current CLI parser. End-to-end results depend
on your configured documents and local models; the documentation build does
not execute this pipeline or certify M2 acceptance.
