# ka configuration

Copy `config.example.yaml` to `config.yaml` and set the workspace document paths
for the local machine. Configuration is loaded with
`knowledge_assistant.config.load_settings` and is validated before use. The
`ka` command reads `config/config.yaml` by default.

The YAML file holds non-secret application options. Place credentials and
machine-specific service connection values in the repository-root `.env` file,
copied from `.env.example`. Pass that file explicitly to `load_settings`.

`llm.thinking` is optional. For Ollama models that support a reasoning channel,
set it to `false`, `low`, `medium`, or `high`; `false` is a good default for
concise structured question answering.

Relative YAML paths are resolved from the repository root (the parent of the
`config` directory). This makes paths such as `prompts/question_answer.md` and
`artifacts/chroma` portable across machines. Each workspace's `artifacts` path
stores workspace-isolated runtime outputs, including ingestion artefacts.
Chunking uses word-based `size`, `maximum_size`, and `minimum_size` limits. It
detects explicit and standalone title-case headings when `detect_headings` is
enabled, keeping sections intact whenever possible. Workspace document paths may be
absolute.

`pdf_link_download` configures the PDF-link download utility. It downloads only
HTTP(S) URLs whose host (or subdomain) appears in `allowed_hosts`, and whose final
URL extension or HTTP content type appears in the corresponding allow-list. Leave
`allowed_hosts` empty to disable downloads until trusted sources are explicitly
configured.
