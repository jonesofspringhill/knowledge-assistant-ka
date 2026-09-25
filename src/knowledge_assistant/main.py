"""Command-line interface for the Knowledge Assistant."""

from __future__ import annotations

import argparse
import json
import os
import platform
import sys
from collections.abc import Sequence
from pathlib import Path

import yaml

from knowledge_assistant.chunking import chunk_workspace
from knowledge_assistant.config import ConfigurationError
from knowledge_assistant.evidence.service import (
    EvidenceLibraryError,
    load_evidence_library,
    write_control_artifact,
)
from knowledge_assistant.ingestion import ingest_workspace
from knowledge_assistant.managers import (
    ConfigManager,
    PromptManager,
    PromptNotFoundError,
    WorkspaceManager,
    WorkspaceNotFoundError,
)
from knowledge_assistant.qa_evaluation.cli import (
    add_qa_evaluation_parser,
    handle_qa_evaluation,
    qa_action_needs_configuration,
)
from knowledge_assistant.question_answering import (
    QuestionAnsweringError,
    answer_question,
)
from knowledge_assistant.retrieval import (
    evaluate_workspace,
    generate_embeddings,
    index_workspace,
    search_workspace,
    verify_index,
)
from knowledge_assistant.utilities import WorkspaceUtilityError, run_workspace_pipeline


def _repository_root() -> Path:
    return Path(__file__).resolve().parents[2]


def build_parser() -> argparse.ArgumentParser:
    """Build the application command-line parser."""
    parser = argparse.ArgumentParser(
        prog="ka", description="Manage Knowledge Assistant (ka)."
    )
    root = _repository_root()
    parser.add_argument("--config", type=Path, default=root / "config" / "config.yaml")
    parser.add_argument("--env", type=Path, default=root / ".env")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("version", help="Display application information.")
    commands.add_parser("doctor", help="Run local installation health checks.")
    ingest = commands.add_parser(
        "ingest", help="Ingest documents from the active workspace."
    )
    ingest.add_argument("--root", help="Ingest only this named source root.")
    ingest.add_argument(
        "--force", action="store_true", help="Extract again, bypassing cached text."
    )
    sync = commands.add_parser(
        "sync", help="Run ingest, chunk, embed, index, and index verification."
    )
    sync.add_argument("--root", help="Sync only this named source root.")
    sync.add_argument(
        "--force", action="store_true", help="Extract again, bypassing cached text."
    )
    sync.add_argument(
        "--rebuild-index", action="store_true", help="Rebuild this workspace index."
    )
    commands.add_parser(
        "chunk", help="Create retrieval chunks from ingested documents."
    )
    embed = commands.add_parser("embed", help="Generate cached chunk embeddings.")
    embed.add_argument(
        "--force", action="store_true", help="Regenerate every embedding."
    )
    index = commands.add_parser(
        "index", help="Synchronise embeddings to the vector index."
    )
    index.add_argument(
        "--rebuild",
        action="store_true",
        help="Remove then rebuild this workspace index.",
    )
    index.add_argument(
        "--verify", action="store_true", help="Verify index count after synchronising."
    )
    search = commands.add_parser("search", help="Perform semantic similarity search.")
    search.add_argument("question")
    search.add_argument("--top-k", type=int)
    search.add_argument("--threshold", type=float)
    search.add_argument("--filter", action="append", default=[], metavar="KEY=VALUE")
    ask = commands.add_parser(
        "ask", help="Answer one question using retrieved local evidence."
    )
    ask.add_argument("question")
    ask.add_argument("--top-k", type=int)
    ask.add_argument("--threshold", type=float)
    ask.add_argument("--filter", action="append", default=[], metavar="KEY=VALUE")
    ask.add_argument(
        "--verbose",
        action="store_true",
        help="Show retrieval and generation diagnostics.",
    )
    evaluate = commands.add_parser(
        "evaluate", help="Run retrieval benchmarks from JSON."
    )
    evaluate.add_argument(
        "benchmarks", type=Path, help="JSON list, or an object with a benchmarks list."
    )
    add_qa_evaluation_parser(commands)

    workspace = commands.add_parser("workspace", help="Manage workspaces.")
    workspace_commands = workspace.add_subparsers(
        dest="workspace_command", required=True
    )
    list_command = workspace_commands.add_parser(
        "list", help="List configured workspaces."
    )
    list_command.add_argument(
        "--all", action="store_true", help="Include disabled workspaces."
    )
    info_command = workspace_commands.add_parser("info", help="Show workspace details.")
    info_command.add_argument(
        "name", nargs="?", help="Workspace name (defaults to active)."
    )
    create_command = workspace_commands.add_parser("create", help="Create a workspace.")
    create_command.add_argument("name")
    create_command.add_argument("--description", help="Workspace description.")
    create_command.add_argument("--documents", type=Path, help="Document directory.")
    create_command.add_argument("--collection", help="Vector collection name.")
    create_command.add_argument(
        "--disabled", action="store_true", help="Create disabled."
    )
    create_command.add_argument("--yes", action="store_true", help="Confirm creation.")
    use_command = workspace_commands.add_parser(
        "use", help="Select the active workspace."
    )
    use_command.add_argument("name")

    config = commands.add_parser("config", help="Inspect and validate configuration.")
    config_commands = config.add_subparsers(dest="config_command", required=True)
    config_commands.add_parser("show", help="Display validated configuration.")
    config_commands.add_parser("validate", help="Validate configuration.")

    metadata = commands.add_parser(
        "metadata", help="Validate and inspect evidence-library metadata."
    )
    metadata_commands = metadata.add_subparsers(dest="metadata_command", required=True)
    validate_metadata = metadata_commands.add_parser(
        "validate", help="Validate evidence-library control records."
    )
    validate_metadata.add_argument(
        "workspace", nargs="?", help="Workspace name (defaults to active)."
    )
    show_metadata = metadata_commands.add_parser(
        "show", help="Show validated evidence associations and control reviews."
    )
    show_metadata.add_argument(
        "workspace", nargs="?", help="Workspace name (defaults to active)."
    )
    show_metadata.add_argument("--module", help="Show only one module.")

    prompt = commands.add_parser("prompt", help="Inspect configured prompts.")
    prompt_commands = prompt.add_subparsers(dest="prompt_command", required=True)
    prompt_commands.add_parser("list", help="List prompt templates.")
    show_prompt = prompt_commands.add_parser("show", help="Display a prompt template.")
    show_prompt.add_argument("name")
    return parser


def _state_path(config_path: Path) -> Path:
    return config_path.resolve().parent / ".knowledge-assistant-state.json"


def _active_workspace(config_path: Path, manager: WorkspaceManager) -> str | None:
    try:
        name = json.loads(_state_path(config_path).read_text(encoding="utf-8")).get(
            "active_workspace"
        )
        if name:
            manager.get(name)
            return name
    except (OSError, ValueError, WorkspaceNotFoundError):
        pass
    workspaces = manager.list()
    return workspaces[0].name if workspaces else None


def _write_active_workspace(config_path: Path, name: str) -> None:
    _state_path(config_path).write_text(
        json.dumps({"active_workspace": name}, indent=2) + "\n", encoding="utf-8"
    )


def _settings(args: argparse.Namespace):
    return ConfigManager(args.config, args.env if args.env.is_file() else None).settings


def _print_workspace(workspace) -> None:
    print(f"Name: {workspace.name}")
    print(f"Description: {workspace.description}")
    print(f"Documents: {workspace.documents}")
    print(f"Collection: {workspace.collection}")
    print(f"Enabled: {'yes' if workspace.enabled else 'no'}")


def _create_workspace(args: argparse.Namespace) -> int:
    config_path = args.config.resolve()
    try:
        raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        print(f"Unable to read configuration: {error}", file=sys.stderr)
        return 2
    if not isinstance(raw, dict) or not isinstance(raw.get("workspaces"), dict):
        print("Configuration has no valid workspaces section.", file=sys.stderr)
        return 2
    if args.name in raw["workspaces"]:
        print(f"Workspace '{args.name}' already exists.", file=sys.stderr)
        return 2
    if not args.yes:
        print("Creation requires --yes. No files were changed.", file=sys.stderr)
        return 2
    base = config_path.parent.parent
    documents = args.documents or Path("knowledge") / args.name
    absolute_documents = documents if documents.is_absolute() else (base / documents)
    raw["workspaces"][args.name] = {
        "enabled": not args.disabled,
        "description": args.description or f"{args.name} knowledge workspace",
        "documents": str(documents).replace("\\", "/"),
        "artifacts": f"workspaces/{args.name}/artifacts",
        "collection": args.collection or args.name,
    }
    try:
        absolute_documents.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            yaml.safe_dump(raw, sort_keys=False, allow_unicode=True), encoding="utf-8"
        )
    except OSError as error:
        print(f"Unable to create workspace: {error}", file=sys.stderr)
        return 2
    print(f"Created workspace '{args.name}'.")
    print(f"Document directory: {absolute_documents}")
    return 0


def _ingest(args: argparse.Namespace, manager: WorkspaceManager) -> int:
    """Ingest documents from the active enabled workspace."""
    name = _active_workspace(args.config, manager)
    if name is None:
        print("No active workspace configured.", file=sys.stderr)
        return 2
    workspace = manager.get(name)
    if not workspace.enabled:
        print(f"Workspace '{name}' is disabled.", file=sys.stderr)
        return 2
    print(f"Workspace: {workspace.name}\n")
    print("Scanning documents...")
    try:
        evidence_library = load_evidence_library(workspace)
        if evidence_library:
            write_control_artifact(evidence_library, workspace.artifacts / "metadata")
        summary = ingest_workspace(
            workspace,
            _settings(args).documents,
            roots={args.root} if args.root else None,
            evidence_library=evidence_library,
            force=args.force,
        )
    except (EvidenceLibraryError, OSError, ValueError) as error:
        print(f"Unable to ingest documents: {error}", file=sys.stderr)
        return 2
    print(f"\n{summary.discovered} documents discovered")
    print("\nProcessing...")
    print(f"\nSucceeded: {summary.succeeded}")
    print(f"Extractions performed: {summary.extractions_performed}")
    print(f"Extractions reused:    {summary.extractions_reused}")
    print(f"Failed:    {len(summary.failures)}")
    for outcome in summary.root_outcomes:
        print(
            f"  Root {outcome.name}: {outcome.status.upper()} "
            f"discovered={outcome.discovered} processed={outcome.processed} "
            f"failed={outcome.failed} retained={outcome.retained} "
            f"removed={outcome.removed}"
        )
        if outcome.status == "unavailable":
            print(
                f"WARNING Source root '{outcome.name}' ({outcome.path}) is "
                "unavailable; existing records were retained.",
                file=sys.stderr,
            )
    for failure in summary.failures:
        print(f"  {failure.source_root}/{failure.relative_path}: {failure.message}")
    print(f"\nIntermediate artefacts written to:\n\n{summary.artifact_directory}")
    print(f"\nElapsed time: {summary.elapsed_seconds:.1f} seconds")
    return 0 if not summary.failures else 1


def _chunk(args: argparse.Namespace, manager: WorkspaceManager) -> int:
    """Create chunks from ingestion artefacts in the active enabled workspace."""
    name = _active_workspace(args.config, manager)
    if name is None:
        print("No active workspace configured.", file=sys.stderr)
        return 2
    workspace = manager.get(name)
    if not workspace.enabled:
        print(f"Workspace '{name}' is disabled.", file=sys.stderr)
        return 2
    print(f"Workspace: {workspace.name}\n")
    print("Reading ingested documents...")
    try:
        summary = chunk_workspace(workspace, _settings(args).chunking)
    except OSError as error:
        print(f"Unable to chunk documents: {error}", file=sys.stderr)
        return 2
    print(f"\n{summary.documents_processed} documents loaded")
    print("\nGenerating chunks...")
    print(f"\n{summary.chunks_created} chunks created")
    print(f"\nAverage size: {summary.average_size:.0f} words")
    print(f"Largest chunk: {summary.largest_size} words")
    print(f"Smallest chunk: {summary.smallest_size} words")
    print(f"Headings detected: {summary.headings_detected}")
    print(f"Paragraph splits: {summary.paragraph_splits}")
    print(f"Sentence splits: {summary.sentence_splits}")
    print(f"Forced token splits: {summary.forced_token_splits}")
    for failure in summary.failures:
        print(f"  {failure.artifact}: {failure.message}")
    print(f"\nChunk artefacts written to:\n\n{summary.artifact_directory}")
    print(f"\nElapsed time: {summary.elapsed_seconds:.1f} seconds")
    return 0 if not summary.failures else 1


def _sync(args: argparse.Namespace) -> int:
    """Run the complete verified pipeline for the active workspace."""
    try:
        settings = _settings(args)
        manager = WorkspaceManager(settings.workspaces)
        name = _active_workspace(args.config, manager)
        if name is None:
            raise WorkspaceUtilityError("No active workspace configured.")
        summary = run_workspace_pipeline(
            args.config,
            args.env if args.env.is_file() else None,
            name,
            root=args.root,
            rebuild_index=args.rebuild_index,
            force_extraction=args.force,
        )
    except (ConfigurationError, WorkspaceUtilityError) as error:
        print(f"Unable to sync workspace: {error}", file=sys.stderr)
        return getattr(error, "exit_code", 2)
    print(f"Workspace: {summary.workspace}")
    print(f"Scope: {summary.scope}")
    print(f"Documents added or updated: {summary.added_or_updated}")
    print(f"Documents retained: {summary.retained}")
    print(f"Chunks removed: {summary.chunks_removed}")
    print(f"Embeddings removed: {summary.embeddings_removed}")
    print(f"Vectors removed: {summary.vectors_removed}")
    print(f"Verified index size: {summary.index_size}")
    return 0


def _workspace_for_retrieval(args: argparse.Namespace, manager: WorkspaceManager):
    name = _active_workspace(args.config, manager)
    if name is None:
        raise WorkspaceNotFoundError("No active workspace configured")
    workspace = manager.get(name)
    if not workspace.enabled:
        raise WorkspaceNotFoundError(f"Workspace '{name}' is disabled")
    return workspace


def _embed(args: argparse.Namespace, manager: WorkspaceManager) -> int:
    try:
        workspace = _workspace_for_retrieval(args, manager)
        summary = generate_embeddings(
            workspace, _settings(args).embedding, force=args.force
        )
    except (OSError, WorkspaceNotFoundError) as error:
        print(f"Unable to generate embeddings: {error}", file=sys.stderr)
        return 2
    print(f"Workspace: {workspace.name}")
    print(f"Chunks processed: {summary.chunks_processed}")
    print(f"Embeddings generated: {summary.embeddings_generated}")
    print(f"Embeddings reused: {summary.embeddings_reused}")
    print(f"Embedding time: {summary.elapsed_seconds:.3f} seconds")
    print(f"Embedding artefacts: {summary.artifact_directory}")
    for failure in summary.failures:
        print(f"  {failure.artifact}: {failure.message}", file=sys.stderr)
    return 0 if not summary.failures else 1


def _index(args: argparse.Namespace, manager: WorkspaceManager) -> int:
    try:
        workspace = _workspace_for_retrieval(args, manager)
        settings = _settings(args)
        summary = index_workspace(
            workspace, settings.chroma.directory, rebuild=args.rebuild
        )
        verified = (
            verify_index(workspace, settings.chroma.directory) if args.verify else None
        )
    except (OSError, WorkspaceNotFoundError, ValueError) as error:
        print(f"Unable to update index: {error}", file=sys.stderr)
        return 2
    print(f"Workspace: {workspace.name}")
    print(f"Vectors indexed: {summary.indexed}")
    print(f"Vectors deleted: {summary.deleted}")
    print(f"Index size: {summary.index_size}")
    print(f"Indexing time: {summary.elapsed_seconds:.3f} seconds")
    if verified:
        valid, expected, actual = verified
        print(f"Verification: {'PASS' if valid else 'FAIL'} ({actual}/{expected})")
        if not valid:
            return 1
    return 0 if not summary.failures else 1


def _filter_value(value: str) -> str | int | float | bool:
    lower = value.lower()
    if lower == "true":
        return True
    if lower == "false":
        return False
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        return value


def _filters(values: list[str]) -> dict[str, str | int | float | bool]:
    result = {}
    for value in values:
        key, separator, content = value.partition("=")
        if not separator or not key.strip() or not content.strip():
            raise ValueError("filters must use KEY=VALUE")
        if key in result:
            raise ValueError(f"duplicate filter key: {key}")
        result[key] = _filter_value(content)
    return result


def _ask(args: argparse.Namespace, manager: WorkspaceManager) -> int:
    """Answer one question from retrieved evidence."""
    try:
        workspace = _workspace_for_retrieval(args, manager)
        settings = _settings(args)
        result = answer_question(
            workspace,
            settings.chroma.directory,
            settings.retrieval,
            settings.embedding,
            settings.llm,
            settings.environment,
            PromptManager(settings.prompts),
            args.question,
            qa_settings=settings.question_answering,
            top_k=args.top_k,
            threshold=args.threshold,
            filters=_filters(args.filter),
        )
    except (
        OSError,
        WorkspaceNotFoundError,
        ValueError,
        IndexError,
        QuestionAnsweringError,
    ) as error:
        print(f"Unable to answer question: {error}", file=sys.stderr)
        return 2

    print(f"Question\n\n{result.question}\n\nAnswer\n\n{result.answer}")
    if result.citations:
        print("\nSources")
        for citation in result.citations:
            print(f"{citation.label}. {citation.source}")
    if result.uncertainty:
        print(f"\nUncertainty\n\n{result.uncertainty}")
    if args.verbose:
        print("\nDiagnostics")
        print(f"Workspace: {result.workspace}")
        print(f"Model: {result.model or settings.llm.model}")
        print(
            f"Prompt: {result.prompt_name or settings.question_answering.prompt_name}"
        )
        print(f"Prompt checksum: {result.prompt_checksum or '-'}")
        print(f"Top-K: {result.retrieval_parameters['top_k']}")
        print(f"Threshold: {result.retrieval_parameters['threshold']}")
        print(f"Filters: {result.retrieval_parameters['filters'] or '-'}")
        print(f"Retrieved evidence: {len(result.evidence)}")
        print(f"Context budget: {result.context_budget_tokens} tokens")
        print(f"Estimated context: {result.context_estimated_tokens} tokens")
        print(f"Retrieval latency: {result.retrieval_latency_seconds:.3f} seconds")
        print(f"Generation latency: {result.generation_latency_seconds:.3f} seconds")
        for evidence in result.evidence:
            print(f"  {evidence.chunk_id}: similarity={evidence.similarity:.3f}")
    return 0


def _preview(text: str, length: int = 700) -> str:
    collapsed = " ".join(text.split())
    return collapsed if len(collapsed) <= length else collapsed[: length - 3] + "..."


def _search(args: argparse.Namespace, manager: WorkspaceManager) -> int:
    try:
        workspace = _workspace_for_retrieval(args, manager)
        settings = _settings(args)
        results, latency = search_workspace(
            workspace,
            settings.chroma.directory,
            settings.retrieval,
            settings.embedding,
            args.question,
            top_k=args.top_k,
            threshold=args.threshold,
            filters=_filters(args.filter),
        )
    except (OSError, WorkspaceNotFoundError, ValueError, IndexError) as error:
        print(f"Unable to search: {error}", file=sys.stderr)
        return 2
    print(f"Question\n\n{args.question}\n\nResults")
    for number, result in enumerate(results, 1):
        print(
            f"\n{number}.\n{result.document_title or result.document_id}\nSimilarity {result.similarity:.2f}"
        )
        print(
            f"Section: {result.section_title or '-'}\n"
            f"Source: {result.source_location}\n"
            f"Chunk: {result.chunk_id}\n\n"
            f"{_preview(result.text)}"
        )
        evidence = result.metadata.get("evidence")
        if isinstance(evidence, dict):
            associations = evidence.get("associations", [])
            if associations:
                first = associations[0]
                print(
                    f"Role: {first.get('document_role', '-')}\n"
                    f"Module: {first.get('module_id', '-')} - "
                    f"{first.get('module_title', '-')}"
                )
                if first.get("organisation"):
                    print(f"Organisation: {first['organisation']}")
                if first.get("source_url"):
                    print(f"Source URL: {first['source_url']}")
    print(f"\nSearch latency: {latency:.3f} seconds")
    return 0


def _metadata(args: argparse.Namespace, manager: WorkspaceManager) -> int:
    name = args.workspace or _active_workspace(args.config, manager)
    if name is None:
        print("No active workspace configured.", file=sys.stderr)
        return 2
    try:
        workspace = manager.get(name)
        library = load_evidence_library(workspace)
    except (EvidenceLibraryError, WorkspaceNotFoundError) as error:
        print(f"Metadata validation failed: {error}", file=sys.stderr)
        return 2
    if library is None:
        print(
            f"Workspace '{name}' has no evidence-library configuration.",
            file=sys.stderr,
        )
        return 2
    if args.metadata_command == "validate":
        summary = library.summary
        print(f"Workspace: {name}")
        print(f"Manifest schema: {library.schema_version}")
        print(f"Modules: {summary.modules}")
        print(f"Subtopics: {summary.subtopics}")
        print(f"Source references: {summary.source_references}")
        print(f"Local source references: {summary.local_source_references}")
        print(f"Remote-only references: {summary.remote_only_references}")
        print(f"Claim reviews: {summary.claim_reviews}")
        print(f"Missing referenced documents: {summary.missing_references}")
        print(f"Unmatched documents: {summary.unmatched_documents}")
        for issue in library.validation_issues:
            print(f"WARNING {issue.message}")
        print("VALID")
        return 0
    selected = [
        item
        for item in library.modules
        if not args.module or item.module_id.casefold() == args.module.casefold()
    ]
    if not selected:
        print(f"Unknown evidence module: {args.module}", file=sys.stderr)
        return 2
    for module in selected:
        print(f"{module.module_id} - {module.title}")
        print(f"Status: {module.status}")
        print(f"Course document: {module.course_document.as_posix()}")
        print(f"Subtopics: {len(module.subtopics)}")
        print("\nAuthoritative sources")
        for source in module.sources:
            location = (
                source.local_file.as_posix() if source.local_file else "remote-only"
            )
            print(f"  {source.id:<28} {location}")
        print("\nClaim reviews")
        for review in module.claim_reviews:
            print(
                f"  {review.subtopic_id:<12} {review.assessment:<12} " f"{review.notes}"
            )
        print()
    return 0


def _evaluate(args: argparse.Namespace, manager: WorkspaceManager) -> int:
    try:
        workspace = _workspace_for_retrieval(args, manager)
        raw = json.loads(args.benchmarks.read_text(encoding="utf-8"))
        benchmarks = raw.get("benchmarks", []) if isinstance(raw, dict) else raw
        if not isinstance(benchmarks, list):
            raise TypeError("benchmark file must contain a JSON list")
        settings = _settings(args)
        report = evaluate_workspace(
            workspace,
            settings.chroma.directory,
            settings.retrieval,
            settings.embedding,
            benchmarks,
        )
        output = workspace.artifacts / "evaluations"
        output.mkdir(parents=True, exist_ok=True)
        (output / "latest.json").write_text(
            json.dumps(report, indent=2) + "\n", encoding="utf-8"
        )
    except (KeyError, OSError, TypeError, ValueError, WorkspaceNotFoundError) as error:
        print(f"Unable to evaluate retrieval: {error}", file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2))
    return 0


def _doctor(args: argparse.Namespace) -> int:
    """Run independent local checks and return non-zero only for mandatory failures."""
    print("Knowledge Assistant Doctor\n")
    failed = False
    try:
        settings = _settings(args)
        print(f"PASS   Configuration loaded ({args.config.resolve()})")
    except ConfigurationError:
        print("FAIL   Configuration could not be loaded")
        print("       Run: knowledge-assistant config validate")
        for check in (
            "Environment",
            "Workspace",
            "Prompt templates",
            "Storage",
            "Logging",
        ):
            print(f"FAIL   {check}: unavailable because configuration is invalid")
        print("\nOverall Status\n\nNOT READY")
        return 2
    print(f"Application: {settings.application.name} {settings.application.version}")
    print(f"Python: {platform.python_version()} ({platform.system()})")
    print(
        f"{'PASS' if args.env.is_file() else 'WARNING':<7}"
        f"Environment file: {args.env.resolve()}"
    )
    print(
        f"{'PASS' if settings.environment.ollama_host else 'WARNING':<7}"
        "Ollama host is "
        + ("configured" if settings.environment.ollama_host else "not configured")
    )
    manager = WorkspaceManager(settings.workspaces)
    active = _active_workspace(args.config, manager)
    if active is None:
        print("FAIL   No enabled workspace configured")
        failed = True
    else:
        workspace = manager.get(active)
        if not workspace.enabled:
            print(f'FAIL   Workspace "{active}" is disabled')
            failed = True
        elif workspace.documents.is_dir():
            print(
                f'PASS   Workspace "{active}" '
                f"(documents: {workspace.documents}; collection: {workspace.collection})"
            )
        else:
            print(
                f'WARNING Workspace "{active}" document directory is missing: '
                f"{workspace.documents} (collection: {workspace.collection})"
            )
    prompt_manager = PromptManager(settings.prompts)
    try:
        for name in prompt_manager.names():
            prompt_manager.get(name)
        print("PASS   Prompt templates loaded: " + ", ".join(prompt_manager.names()))
    except RuntimeError as error:
        print(f"FAIL   Prompt templates: {error}")
        failed = True
    prompt_directories = {
        getattr(settings.prompts, name).parent for name in prompt_manager.names()
    }
    for directory in sorted(prompt_directories):
        print(
            f"{'PASS' if directory.is_dir() else 'FAIL':<7}"
            f"Prompt directory: {directory}"
        )
        failed = failed or not directory.is_dir()
    if not settings.chroma.directory.exists():
        print(f"WARNING Storage directory not yet created: {settings.chroma.directory}")
    elif settings.chroma.directory.is_dir() and os.access(
        settings.chroma.directory, os.R_OK | os.W_OK
    ):
        print(f"PASS   Storage directory accessible: {settings.chroma.directory}")
    else:
        print(
            f"FAIL   Storage directory is not accessible: {settings.chroma.directory}"
        )
        failed = True
    try:
        if not settings.logging.file.parent.is_dir():
            raise OSError("log directory does not exist")
        with settings.logging.file.open("a", encoding="utf-8"):
            pass
        print(f"PASS   Logging writable: {settings.logging.file}")
    except OSError as error:
        print(f"FAIL   Logging: {error}")
        failed = True
    host = (
        str(settings.environment.ollama_host)
        if settings.environment.ollama_host
        else "not configured"
    )
    try:
        from ollama import Client

        models = Client(host=host).list().models
        names = [model.model for model in models]
        print(f"PASS   Ollama reachable: {host}")
        print("PASS   Available models: " + (", ".join(names) if names else "none"))
        for model, label in (
            (settings.embedding.model, "Embedding model"),
            (settings.llm.model, "LLM"),
        ):
            print(f"{'PASS' if model in names else 'WARNING':<7}{label}: {model}")
    except Exception:  # noqa: BLE001 - network/client errors are optional diagnostics.
        print(f"WARNING Ollama unavailable: {host}")
    print("\nOverall Status\n\n" + ("NOT READY" if failed else "READY"))
    return 2 if failed else 0


def main(argv: Sequence[str] | None = None) -> int:
    """Run Knowledge Assistant commands."""
    args = build_parser().parse_args(argv)
    if args.command == "doctor":
        return _doctor(args)
    if args.command == "qa-evaluate" and not qa_action_needs_configuration(args):
        return handle_qa_evaluation(args)
    try:
        settings = _settings(args)
    except ConfigurationError as error:
        print(f"Configuration error: {error}", file=sys.stderr)
        return 2
    manager = WorkspaceManager(settings.workspaces)
    if args.command == "version":
        print(f"{settings.application.name} {settings.application.version}")
        print(f"Python {platform.python_version()}")
        print(f"Environment: {settings.application.environment}")
        print(f"Active workspace: {_active_workspace(args.config, manager) or 'none'}")
        return 0
    if args.command == "workspace":
        if args.workspace_command == "create":
            return _create_workspace(args)
        try:
            if args.workspace_command == "list":
                active = _active_workspace(args.config, manager)
                for workspace in manager.list(include_disabled=args.all):
                    marker = "*" if workspace.name == active else " "
                    print(
                        f"{marker} {workspace.name}: {workspace.description} ({workspace.collection})"
                    )
            elif args.workspace_command == "info":
                name = args.name or _active_workspace(args.config, manager)
                if name is None:
                    raise WorkspaceNotFoundError("No active workspace")
                _print_workspace(manager.get(name))
            else:
                manager.get(args.name)
                _write_active_workspace(args.config, args.name)
                print(f"Active workspace: {args.name}")
        except WorkspaceNotFoundError as error:
            print(error, file=sys.stderr)
            return 2
        return 0
    if args.command == "config":
        if args.config_command == "validate":
            print(f"PASS Configuration valid: {args.config.resolve()}")
        else:
            print(
                yaml.safe_dump(
                    settings.model_dump(mode="json", exclude={"environment"}),
                    sort_keys=False,
                )
            )
        return 0
    if args.command == "metadata":
        return _metadata(args, manager)
    if args.command == "ingest":
        return _ingest(args, manager)
    if args.command == "sync":
        return _sync(args)
    if args.command == "chunk":
        return _chunk(args, manager)
    if args.command == "embed":
        return _embed(args, manager)
    if args.command == "index":
        return _index(args, manager)
    if args.command == "search":
        return _search(args, manager)
    if args.command == "ask":
        return _ask(args, manager)
    if args.command == "evaluate":
        return _evaluate(args, manager)
    if args.command == "qa-evaluate":
        return handle_qa_evaluation(args, settings, manager)
    prompts = PromptManager(settings.prompts)
    try:
        if args.prompt_command == "list":
            print("\n".join(prompts.names()))
        else:
            print(prompts.get(args.name), end="")
    except (PromptNotFoundError, RuntimeError) as error:
        print(error, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
