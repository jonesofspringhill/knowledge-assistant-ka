"""Run the ingestion-to-index pipeline for one explicitly selected workspace."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from knowledge_assistant.utilities import (
    WorkspaceUtilityError,
    run_workspace_pipeline,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run a workspace pipeline.")
    parser.add_argument("workspace")
    root = Path(__file__).resolve().parents[1]
    parser.add_argument("--config", type=Path, default=root / "config" / "config.yaml")
    parser.add_argument("--env", type=Path, default=root / ".env")
    parser.add_argument("--root", help="Ingest only this named source root.")
    parser.add_argument("--rebuild-index", action="store_true")
    args = parser.parse_args(argv)
    try:
        summary = run_workspace_pipeline(
            args.config,
            args.env if args.env.is_file() else None,
            args.workspace,
            root=args.root,
            rebuild_index=args.rebuild_index,
        )
    except WorkspaceUtilityError as error:
        print(error, file=sys.stderr)
        return error.exit_code
    print(f"Workspace: {summary.workspace}")
    print(f"Scope: {summary.scope}")
    if getattr(summary, "metadata_schema", None):
        print(f"Manifest schema: {summary.metadata_schema}")
        print(f"Evidence associations: {summary.metadata_associations}")
        print(f"Control reviews: {summary.control_reviews}")
        for warning in summary.metadata_warnings:
            print(f"WARNING {warning}", file=sys.stderr)
        print(f"Control artefact: {summary.control_artifact}")
    print("\nRoots")
    for outcome in summary.root_outcomes:
        print(
            f"  {outcome.name}  {outcome.status.upper()}  "
            f"discovered={outcome.discovered} processed={outcome.processed} "
            f"failed={outcome.failed} added_or_updated={outcome.added_or_updated} "
            f"retained={outcome.retained} removed={outcome.removed}"
        )
        if outcome.status == "unavailable":
            print(
                f"WARNING Source root '{outcome.name}' ({outcome.path}) is "
                "unavailable; existing records were retained.",
                file=sys.stderr,
            )
    print(
        "\nReconciliation: "
        f"added_or_updated={summary.added_or_updated} retained={summary.retained} "
        f"failed={summary.failed} documents_removed={summary.documents_removed}"
    )
    print(f"Ingestion artefacts: {summary.ingestion_artifacts}")
    print(f"Chunk artefacts: {summary.chunk_artifacts}")
    print(f"Embedding artefacts: {summary.embedding_artifacts}")
    print(f"Chunks removed: {summary.chunks_removed}")
    print(f"Embeddings removed: {summary.embeddings_removed}")
    print(f"Vectors removed: {summary.vectors_removed}")
    print(f"Verified index size: {summary.index_size}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
