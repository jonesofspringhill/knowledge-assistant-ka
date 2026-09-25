# Workspaces

A workspace separates a document collection and its derived artifacts from
other collections. Configuration defines the source paths, collection name,
enabled state and artifacts directory for each workspace.

## Inspect and select

```powershell
knowledge-assistant workspace list
knowledge-assistant workspace list --all
knowledge-assistant workspace info
knowledge-assistant workspace use WORKSPACE_NAME
```

Select a configured, enabled workspace before ingestion or queries. Run
`workspace info` again to confirm the active source and artifact locations.

## Create

Use `knowledge-assistant workspace create --help` to inspect the current
creation options, including document directory and collection name. Review
the proposed workspace settings before confirming creation.

## Processing and refresh

The active workspace is used by `ingest`, `chunk`, `embed`, `index`, `search`
and `ask`. Named source roots support scoped ingestion with `ingest --root`.
See [ingestion](Ingestion.md) and [retrieval](Retrieval.md) for processing and
refresh behaviour. Keep source documents separate from generated artifacts.

See [configuration](../configuration.md) for the example workspace structure.
