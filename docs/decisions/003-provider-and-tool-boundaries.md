# 003 — Provider and tool boundaries

**Status:** Accepted  
**Date:** 2026-09-25

## Context

`ka` is intended to support local models, OpenAI-compatible services, hosted
models and future agent tools. Retrieval quality, document provenance and tool
safety must not depend on one runtime's request format.

## Decision

Application services depend on narrow contracts:

- `TextGenerator` generates from an already assembled prompt.
- A named provider registry maps configuration to a model adapter.
- Retrieval remains independent from answer generation.
- Future tools declare a name, typed input and output, side-effect class, and
  evidence/provenance returned with their result.
- Agent workflows orchestrate those contracts and record chosen tools, inputs,
  outputs and cited evidence.

Ollama is the first registered provider. New adapters must be opt-in through
configuration and must not require changes to ingestion, chunking, retrieval or
the grounded-answer service.

## Consequences

The platform can compare answer models against identical retrieved evidence. It
can also keep sensitive workspaces local while allowing a separately authorised
workspace to use a hosted adapter. Provider-specific features remain inside an
adapter and must declare any loss of portability.
