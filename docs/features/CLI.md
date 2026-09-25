# ka command-line interface

## Purpose

The Knowledge Assistant CLI provides the primary operational interface for managing workspaces, configuring the system, running analysis tasks, and interacting with knowledge collections.

The CLI should be suitable for:

* initial setup,
* system administration,
* diagnostics,
* document processing,
* automation,
* future integration with other systems.

The CLI should remain usable even after graphical or web interfaces are introduced.

---

## Design Principles

The CLI should be:

### Clear

Commands should be easy to discover and understand.

Example:

```text
ka --help
```

should provide a useful overview.

---

### Consistent

Commands should follow predictable patterns.

Examples:

```text
ka workspace list

ka workspace info

ka config show

ka doctor
```

---

### Safe

Commands that modify data should:

* explain what will happen,
* avoid destructive actions by default,
* request confirmation where appropriate.

---

### Scriptable

Commands should support automation.

Where appropriate, provide:

* meaningful exit codes,
* machine-readable output formats,
* predictable behaviour.

Future support:

```text
--format json
```

---

## Command Structure

The CLI should use a hierarchical command structure.

General pattern:

```text
ka <resource> <action>
```

Examples:

```text
ka workspace list

ka workspace create

ka config show

ka prompt list
```

Actions that do not naturally fit a resource model may exist as standalone commands:

```text
ka doctor

ka version
```

---

## Core Commands

### System

#### version

Display application information.

Example:

```text
ka version
```

Displays:

* application version
* Python version
* environment
* active workspace

---

#### doctor

Perform a system health check.

Example:

```text
ka doctor
```

Checks:

* configuration
* environment
* workspace
* prompts
* Ollama connectivity
* models
* storage

---

## Workspace Management

### list

Display available workspaces.

Example:

```text
ka workspace list
```

---

### info

Display workspace details.

Example:

```text
ka workspace info
```

Displays:

* name
* description
* document location
* vector store
* configuration

---

### create

Create a new workspace.

Example:

```text
ka workspace create research
```

Creates:

* workspace configuration
* directory structure
* default prompts

---

### use

Select the active workspace.

Example:

```text
ka workspace use example
```

---

## Configuration

### show

Display active configuration.

Example:

```text
ka config show
```

Sensitive information must not be displayed.

---

### validate

Check configuration correctness.

Example:

```text
ka config validate
```

---

## Prompts

### list

Display available prompt templates.

Example:

```text
ka prompt list
```

---

### show

Display a prompt template.

Example:

```text
ka prompt show question_answer
```

---

## Document synchronisation

### sync

`sync` is the normal end-to-end operation. It discovers changed documents,
extracts and chunks them, creates embeddings, and updates the vector store.
Unchanged extractions are reused from the workspace cache.

```text
ka sync
ka sync --force
ka sync --rebuild-index
```

`--force` refreshes document extraction; `--rebuild-index` recreates the
vector index. The command does not modify source documents.

---

### stats

Display knowledge base statistics.

Example:

```text
ka stats
```

Displays:

* documents
* chunks
* embeddings
* last update

---

## Question Answering

### ask

Ask one question against the active workspace using retrieved evidence.

Example:

```text
ka ask "What funding limits apply?"
```

Options include `--top-k`, `--threshold`, repeated `--filter KEY=VALUE`, and
`--verbose`. The command returns exit code 0 for an answer or successful
insufficient-evidence result, 2 for usage, configuration or model failures,
and does not modify configuration.

---

### search

Perform document retrieval without generating an answer.

Example:

```text
ka search "roof repairs"
```

Useful for debugging retrieval quality.

### qa-evaluate

Evaluate the complete grounded question-answer pipeline without changing the
retrieval-only `evaluate` command.

```text
ka qa-evaluate validate <benchmark.json>
ka qa-evaluate run <benchmark.json> --workspace evaluation --kind baseline
ka qa-evaluate review-template <raw-report.json>
ka qa-evaluate score <raw-report.json> --reviews <review.json>
ka qa-evaluate baseline <scored-report.json>
ka qa-evaluate compare <baseline.json> <candidate.scored.json>
```

`run` executes cases sequentially, supports `--repeat`, and always exits `1`
after writing the immutable raw report because human review is mandatory. Score,
baseline and compare exit `0` only when their applicable gates pass, `1` for a
valid non-passing result, and `2` for invalid input or operational setup errors.
A failing clean baseline can be designated only with `--accept-failing` and a
non-empty `--reason`.

---

## Analysis Commands

Future commands.

### summarise

Generate summaries.

### agreement

Identify areas of agreement.

### contradiction

Identify conflicting information.

---

## Output Standards

All commands should:

* provide clear status messages,
* identify errors clearly,
* avoid unnecessary technical detail for normal users.

Example:

```text
PASS Configuration loaded

WARNING No documents indexed

READY
```

---

## Error Handling

Errors should:

* explain what happened,
* suggest corrective action,
* avoid exposing internal exceptions unless requested.

Example:

Poor:

```text
FileNotFoundError: /abc/config.yaml
```

Better:

```text
Configuration file not found.

Expected:
config/config.yaml

Run:
ka config validate
```

---

## Future Extensions

Potential additions:

* interactive mode,
* JSON output,
* progress indicators,
* web dashboard,
* scheduled operations,
* agent control commands.
