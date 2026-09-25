# Project Journal

## 2026-09-08 — Documentation site

Added Sphinx with MyST Markdown and the Read the Docs theme, a documentation
homepage, getting-started and configuration pages, and maintenance instructions.
Added strict builds, a GitHub Actions documentation check and a publisher with
a configurable destination. The initial local destination is
the configured documentation publishing destination. M2.4 acceptance remains
pending; this work does not change milestone acceptance status.

## 2026-07-22
Established the project architecture, documentation set, development workflow, configuration strategy, 
prompt management approach and Git repository. Project is now ready to move into implementation using 
Codex.

### Establishing a codex project

Use the following to full access. 

```text
cd <repository-root>

codex --sandbox danger-full-access
```

Best though is to require approval before making 
any changes. The fresh `ka` repository is now created at
`E:\projects\ml\knowledge-assistant`.

```text
codex --sandbox danger-full-access --approve
```

## 2026-07-23

Moved from architecture/design phase into Codex-assisted implementation.

Codex CLI configured for local repository access using danger-full-access mode.

- Check all paths are configurable
- `.env` values are handled correctly
- prompt files are loaded cleanly
- tests have been updated and pass
- Is the public API sensible?

Next:
- Implement configuration subsystem (M1 preparation).

## 2026-07-24

  Changes made today:

  - Expanded the CLI with version, doctor, workspace, config, and prompt subcommands.
  - Added safe workspace creation (--yes) and persisted active-workspace selection.
  - Implemented doctor diagnostics for configuration, environment, workspace, prompts, storage, logging, Ollama
    connectivity, and configured models.

  - Ensured configuration display excludes environment/secrets.
  - Added clear status output and non-zero exit codes for mandatory failures.

• Doctor is now explicitly aligned with ADR-001’s workspace-first model.
  - It continues to resolve the active workspace through WorkspaceManager.
  - Its workspace health result now identifies both the workspace’s document root and isolated vector collection.
  - Disabled workspaces remain failures; missing document directories remain warnings.
  - Added test coverage asserting the selected workspace and collection are reported.


  Files modified:

  - src/knowledge_assistant/main.py
  - tests/test_main.py

  Tests and checks run:

  - pytest — 14 passed
  - ruff check src tests — passed
  - black --fast src tests — formatted successfully
  - git diff --check — passed

### 2026-08-21

M2.3 grounded single-question answering implemented. The `ask` command now
reuses the M1 retrieval interface, builds bounded provenance-preserving context,
loads the configured question-answer prompt, invokes the configured Ollama model,
and presents citations, uncertainty and verbose diagnostics. Automated coverage
includes context deduplication/budgeting, prompt rendering, abstention and
structured citations. Interactive validation against a real indexed workspace
remains to be completed when Ollama and workspace data are available.

Document updates:

| Document | Required change | Priority |
|---|---|---:|
| `docs/features/M2.3-Grounded-Question-Answering.md` | **Create this next.** Define exact CLI behaviour, context builder, prompt contract, citations, abstention, Ollama errors, exit codes and tests. | **Critical** |
| `docs/Architecture.md` | Update any text saying retrieval/RAG is unimplemented. Add the precise M1 retrieval → M2 context → LLM boundary. | **Critical** |
| `docs/features/CLI.md` | Move `ask` from generic “future” status to M2.3 planned status. Record option precedence, filter syntax and eventual exit-code contract. | **High** |
| `docs/Roadmap.md` | Mark M1 complete, M2 in progress, M2.1/M2.2 complete, M2.3 next and M2.4 planned. | **High** |
| `docs/DataModel.md` | Verify the retrieval-result/evidence model contains the minimum provenance required by §4. Do not invent a second QA evidence model unnecessarily. | **High** |
| `docs/features/Retrieval.md` / `Retrieval-Pipeline.md` | Explicitly document score direction, zero-result behaviour, ordering guarantees, filter/root representation and the M1 handoff contract. | **High** |
| `docs/decisions/002-m1-retrieval-boundary.md` | Probably no substantive change; add a short note only if needed pointing to the formal handoff contract now in `M2.md`. | Medium |
| `docs/Development.md` | Add the requirement that M2.4 benchmarks and settings be versioned and that evaluation gates be fixed before tuning. | Medium |
| `docs/ProjectJournal.md` | Record this documentation review and the decision to resolve contracts before coding M2.3. | Medium |
| `docs/ProjectDefinition.md` | Check milestone status wording only; avoid duplicating low-level M2.3 requirements here. | Low |

### 2026-08-24

Implemented the M2.4 question-answer evaluation and evidence-led refinement
framework after the original coding session was interrupted by tool quota.

- Added a frozen 25-case synthetic QA benchmark, matching source fixtures and a
  separate M1 retrieval regression benchmark.
- Added `qa-evaluate validate`, `run`, `review-template`, `score`, `baseline`
  and `compare` without changing the existing `evaluate` command.
- Reused the M2.3 answer service and captured its one retrieval call for ranked
  source, context, citation, abstention, conflict and latency metrics.
- Added strict versioned benchmark, run, review and scored-report models;
  privacy-safe immutable reports; fixed gates; clean-worktree baseline rules;
  and candidate regression comparison.
- Extended the model-output contract with explicit answered or
  insufficient-evidence status while retaining compatibility with earlier
  responses.
- Added a shareable evaluation configuration and ignored local benchmarks,
  evaluation artefacts, test output and workspace state.
- Full automated verification passed with 74 tests, Ruff, Black and diff checks.
  The synthetic ingest-to-index pipeline produced and verified 14 vectors. A
  dirty-worktree 25-case diagnostic completed without operational failures and
  passed every automatic gate: QA Recall@5 and MRR were `1.0`, citation validity
  was `1.0`, citation source correctness was approximately `0.9825`, and all
  unanswerable cases abstained. The separate M1 benchmark recorded Recall@5
  `1.0`, Recall@10 `1.0` and MRR `0.9`.
- The diagnostic is not an official baseline. A clean committed run, human
  rubric review, baseline designation and optional real-workspace validation
  remain operator steps because the current worktree contains the uncommitted
  implementation.
# 2026-09-24 — ka ingestion foundation

Added the `ka` command alias and checksum-based extraction reuse. Cache identity
includes file type, extractor revision and library version. Source provenance and
evidence metadata are refreshed independently. Added regression tests for duplicate
files, unchanged artefacts, forced refresh, same-size edits, corruption, source
mutation and unavailable roots. The fresh repository uses a generic example
workspace. Provider adapters, PDF/OCR improvements and the agent remain follow-on
work; the M2.4 acceptance baseline has not been designated by this change.

