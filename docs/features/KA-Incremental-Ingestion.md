# ka: incremental ingestion

The short command is `ka`. The existing `knowledge-assistant` command and Python
package name remain compatible. Install the project in its existing environment
with `python -m pip install -e . --no-deps` to register both commands.

## First increment (2026-09-24)

Ingestion hashes each source and reuses extracted text when its bytes, file type,
extractor revision and extraction-library version match the extraction cache.
Identical files at different paths share extraction work but keep separate document
identities. The cache is stored under the configured workspace's
`artifacts/extraction-cache/`. It contains private extracted text and should receive
the same protection as the originals.

Every run rebuilds source-path, date and evidence-association metadata. Changing a
policy/manifest therefore updates metadata even when extraction is reused. Cache
entries are validated, written atomically and regenerated when unreadable. Files
changed while being extracted fail individually and retain their previous document
artefact. Unchanged document artefacts are not rewritten. Source files are never
modified. No model or network service is used by ingestion.

```
ka ingest
ka ingest --root recovered-hp
ka ingest --force
```

`--force` bypasses extraction reuse. CLI and JSON reports expose extractions
performed and reused. Input files are still read for hashing, so this saves parsing
time rather than eliminating disk I/O. Deleted-document reconciliation still
follows existing named-root rules. Cache records are retained for future reuse;
cache garbage collection is not yet implemented.

## Workspace setup

The shipped configuration contains a generic `example` workspace pointing to the
local `knowledge/` directory. Add named source roots for each private collection,
such as a recovered machine archive, without placing the files in this repository.
Use `ka workspace info example` to inspect it and `ka workspace use <name>` to
select a configured workspace. No private documents are ingested automatically.

When the recovered files are available, register their folder as a named source
root. Keep source documents outside the code repository. For transfer, copy source
files, workspace artefacts, configuration and prompts; recreate the Python virtual
environment on the destination and update configured paths. Credentials stay in
the destination's local `.env` file.

## Following increments

- Preserve PDF page boundaries and report pages requiring OCR. Benchmark native
  extraction on representative PDFs before selecting a faster backend.
- Add selective OCR with cached results, and DOCX table/heading extraction.
- Extend extraction reuse to incremental chunk generation, then benchmark the
  complete pipeline, including embedding reuse and indexing.
- Add model-provider adapters for LM Studio and OpenAI alongside Ollama. Hold
  retrieved evidence and embeddings fixed for answer-model comparisons; use
  separate collections when comparing embedding models.
- Introduce a bounded search agent with recorded tool calls and cited answers.

These are explicit follow-on tasks, not claims of implemented capability. In
particular, scanned PDFs and legacy `.doc` files still require additional work.
