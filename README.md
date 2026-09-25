# ka

A local, model- and tool-independent knowledge platform for document ingestion,
evidence retrieval, grounded answers, and future agent workflows.

Use `ka` as the short command; `knowledge-assistant` remains supported.
See [incremental ingestion](docs/features/KA-Incremental-Ingestion.md)
for extraction caching, `ka ingest --force`, and the next development increments.

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -e ".[dev]"
ka config validate
# After pointing the example workspace at a document folder:
ka sync
```

`ka sync` runs ingest, chunk, embed, index, and index verification in order.
Configure local document roots in `config/config.yaml` before the first run.

- [Documentation home](docs/index.md)
- [Getting started](docs/getting-started.md)
- [Build and publish documentation](docs/documentation-workflow.md)
- [Development guide](docs/Development.md)

The project is portable: source documents, caches and vector indexes remain local
runtime data and are not committed to Git.
