"""Create a validated multi-root workspace from the command line."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from knowledge_assistant.utilities import (
    WorkspaceUtilityError,
    create_workspace,
    parse_document_root,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Create a multi-root workspace.")
    parser.add_argument("name")
    parser.add_argument(
        "--config",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "config" / "config.yaml",
    )
    parser.add_argument("--description")
    parser.add_argument("--collection")
    parser.add_argument("--document-root", action="append", required=True)
    parser.add_argument("--disabled", action="store_true")
    parser.add_argument("--yes", action="store_true")
    args = parser.parse_args(argv)
    try:
        artifacts = create_workspace(
            args.config,
            args.name,
            [parse_document_root(value) for value in args.document_root],
            description=args.description,
            collection=args.collection,
            enabled=not args.disabled,
            confirm=args.yes,
        )
    except WorkspaceUtilityError as error:
        print(error, file=sys.stderr)
        return 2
    print(f"Created workspace '{args.name}'.")
    print(f"Artefact directory: {artifacts}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
