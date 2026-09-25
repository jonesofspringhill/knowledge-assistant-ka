# Documentation workflow

## Install the documentation tools

Run from the repository root:

```powershell
python -m venv .venv-docs
.venv-docs\Scripts\python -m pip install -r docs/requirements.txt
```

This separate environment does not require the application or Ollama.

## Build and publish

```powershell
.venv-docs\Scripts\python scripts/docs.py build
.venv-docs\Scripts\python scripts/docs.py publish
```

Both commands perform a fresh Sphinx build with warnings treated as errors.
The local result is `docs/_build/html/index.html`. Publishing also copies the
successful build to `E:\public\_html\tech\knowledge-assistant`.

Open that destination's `index.html`, or use your existing web server's URL.
The publishing command copies files; it does not install or configure a web
server. Navigation uses relative links so the site can live below `/tech/`.

To start a temporary laptop-only preview server:

```powershell
python -m http.server 8000 --bind 127.0.0.1 --directory E:\public\_html
```

Then open `http://127.0.0.1:8000/tech/`. Stop the foreground server with Ctrl+C.
The shared `tech/index.html` links to individual projects; add another project
link there when publishing its documentation for the first time.

A future NAS destination can be supplied explicitly:

```powershell
.venv-docs\Scripts\python scripts/docs.py publish --destination "\\YOUR-NAS\YOUR-WEB-SHARE\tech\knowledge-assistant"
```

Replace that example with the actual share. The publisher records owned files
in `.knowledge-assistant-docs.json`; it removes stale files only from that
manifest and refuses to overwrite unowned files. Other projects and the shared
`tech/index.html` are managed separately. Keep documentation destinations
dedicated to generated content.

## Update with each change

- CLI or user-visible behaviour: update the guide and CLI reference.
- Configuration: update the configuration explanation and example YAML.
- Architecture or entities: update architecture, data model and relevant decisions.
- Milestone progress: update the milestone, roadmap, journal and homepage status.

Edit the Markdown sources in Git, never the generated HTML. Include changes in
the same pull request as the implementation. The pull request template asks
for documentation impact, and GitHub Actions builds the site on every pull
request and push to `main`. Configure branch protection to require the
`Documentation / build` check in GitHub if required checks are desired.

Before accepting a milestone, review current behaviour against the guides and
run the quickstart with synthetic documents. A successful site build checks
rendering and references, not factual correctness or model quality.

## Scope and versions

Existing design pages remain part of the site and may describe future work.
Keep that distinction explicit when editing them. Application version comes
from `pyproject.toml`. The local published site represents the last successful
publish, including any local uncommitted documentation changes. Release-tag
snapshots can be added later when needed.
