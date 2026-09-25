#!/usr/bin/env python
"""Download configured document links embedded in a PDF into a workspace."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from knowledge_assistant.config import ConfigurationError, load_settings
from knowledge_assistant.utilities.pdf_links import download_pdf_links


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", type=Path, help="PDF whose embedded links are examined")
    parser.add_argument("workspace", help="Configured workspace to receive downloads")
    parser.add_argument("--config", type=Path, default=Path("config/config.yaml"))
    parser.add_argument(
        "--dry-run", action="store_true", help="Report eligible links only"
    )
    parser.add_argument(
        "--overwrite", action="store_true", help="Replace existing downloads"
    )
    args = parser.parse_args()
    try:
        settings = load_settings(args.config)
        workspace = settings.workspaces[args.workspace]
    except (ConfigurationError, KeyError) as error:
        print(f"Configuration error: {error}", file=sys.stderr)
        return 2
    if not workspace.enabled or not args.pdf.is_file():
        print("Workspace is disabled or PDF does not exist.", file=sys.stderr)
        return 2
    results = download_pdf_links(
        args.pdf,
        workspace.documents,
        settings.pdf_link_download,
        dry_run=args.dry_run,
        overwrite=args.overwrite,
    )
    for result in results:
        print(f"{result.status.upper():<14} {result.url}\n  {result.detail}")
    return 1 if any(result.status == "failed" for result in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
