# Task: Implement the `doctor` Command

## Objective

Implement a new command-line command:

```text
knowledge-assistant doctor
```

The purpose of this command is to perform a health check of the local Knowledge Assistant installation and provide clear diagnostic information before any document ingestion or question answering is attempted.

This command should become the primary diagnostic tool for the application.

---

## Requirements

Implement a new CLI command:

```text
knowledge-assistant doctor
```

The command should perform a series of independent checks.

Each check should report one of:

* PASS
* WARNING
* FAIL

The command should continue running even if one check fails.

---

## Checks

### 1. Application

Display:

* application name
* application version
* Python version
* operating system

---

### 2. Configuration

Verify that:

* config.yaml can be loaded
* configuration validates successfully
* required sections are present

Display the active configuration file.

---

### 3. Environment

Verify that:

* .env exists (if expected)
* required environment variables are available

Do not display secrets.

Only report whether required values exist.

---

### 4. Workspace

Verify:

* active workspace
* workspace configuration
* document directory exists
* prompt directory exists

Report document path.

---

### 5. Prompt Templates

Verify:

* all configured prompts exist
* Markdown files load correctly

List available prompts.

---

### 6. Ollama

Attempt to connect to the configured Ollama server.

Report:

* reachable or not
* configured host

If reachable:

list available models.

Do not fail if Ollama is unavailable.

---

### 7. Embedding Model

Verify that the configured embedding model is available.

If not available, report a warning.

---

### 8. LLM

Verify that the configured language model exists.

Report the configured model.

---

### 9. Storage

Verify that:

* storage directory exists
* vector database directory is accessible

Do not require that an index already exists.

---

### 10. Logging

Verify:

* log directory exists
* log file is writable

---

## Output

Produce clear human-readable output.

Example only:

```text
Knowledge Assistant Doctor

PASS   Configuration loaded
PASS   Workspace "kingshill"
PASS   Prompt templates loaded
PASS   Ollama reachable
PASS   qwen3:8b available
PASS   nomic-embed-text available
WARNING  Vector database not yet created
PASS   Logging configured

Overall Status

READY
```

If failures exist:

```text
Overall Status

NOT READY
```

---

## Design Constraints

Follow the existing project architecture.

Specifically:

* configuration must be loaded through the configuration subsystem
* prompt templates through the PromptManager
* workspace information through the WorkspaceManager

Do not duplicate configuration loading logic.

---

## Testing

Add unit tests where practical.

Mock external services such as Ollama where appropriate.

The command should return:

* exit code 0 when all mandatory checks pass
* non-zero exit code if mandatory components fail

---

## Documentation

Update:

* CLI help
* milestone progress
* ProjectJournal.md (if appropriate)

Do not modify unrelated files.
