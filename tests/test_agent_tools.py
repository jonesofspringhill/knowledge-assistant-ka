"""Contract coverage for workspace-scoped agent tools."""

from __future__ import annotations

import json
from pathlib import Path

from knowledge_assistant.agent_tools import (
    AgentToolRegistry,
    AgentToolRuntime,
    ToolContext,
    build_default_registry,
)
from knowledge_assistant.agent_tools.models import ToolDescriptor, ToolEffect
from knowledge_assistant.config import load_settings
from knowledge_assistant.main import main
from knowledge_assistant.managers import WorkspaceManager

ROOT = Path(__file__).parents[1]


class _StaticTool:
    descriptor = ToolDescriptor(
        name="test.static",
        description="Return a static result for registry tests.",
        effect=ToolEffect.READ_ONLY,
        input_schema={},
        output_schema={},
    )

    def invoke(self, context: ToolContext, arguments: dict[str, object]) -> dict[str, str]:
        del context, arguments
        return {"message": "ok"}


def _runtime(tmp_path: Path) -> AgentToolRuntime:
    settings = load_settings(ROOT / "config" / "config.example.yaml")
    workspace_settings = settings.workspaces["example"].model_copy(
        update={"artifacts": tmp_path / "artifacts"}
    )
    settings = settings.model_copy(
        update={"workspaces": {"example": workspace_settings}}
    )
    return AgentToolRuntime(settings, WorkspaceManager(settings.workspaces))


def test_registry_enforces_tool_allow_list() -> None:
    registry = AgentToolRegistry()
    registry.register(_StaticTool())

    allowed = registry.invoke(
        "test.static",
        ToolContext(workspace="example", allowed_tools={"test.static"}),
        {},
    )
    denied = registry.invoke(
        "test.static", ToolContext(workspace="example", allowed_tools=set()), {}
    )

    assert allowed.status == "ok"
    assert allowed.result == {"message": "ok"}
    assert denied.status == "error"
    assert "not allowed" in (denied.error or "")


def test_workspace_tool_is_scoped_and_audited(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    registry = build_default_registry(runtime)

    result = registry.invoke(
        "knowledge.workspace.describe",
        ToolContext(workspace="example", caller="test-agent", run_id="run-1"),
        {},
    )

    assert result.status == "ok"
    assert result.result == {
        "name": "example",
        "description": "Example local document collection",
        "collection": "example",
        "enabled": True,
        "source_roots": ["documents"],
    }
    audit = tmp_path / "artifacts" / "agent-tools" / "audit.jsonl"
    event = json.loads(audit.read_text(encoding="utf-8"))
    assert event == {
        "run_id": "run-1",
        "caller": "test-agent",
        "workspace": "example",
        "tool": "knowledge.workspace.describe",
        "status": "ok",
        "duration_seconds": event["duration_seconds"],
    }

    invalid = registry.invoke(
        "knowledge.workspace.describe", ToolContext(workspace="example"), {"typo": True}
    )
    assert invalid.status == "error"
    assert "Extra inputs are not permitted" in (invalid.error or "")


def test_default_tool_descriptors_are_machine_readable() -> None:
    registry = build_default_registry(_runtime(Path.cwd() / ".ka-test-output"))

    descriptors = {item.name: item for item in registry.descriptors()}

    assert set(descriptors) == {
        "knowledge.ask",
        "knowledge.search",
        "knowledge.workspace.describe",
    }
    assert descriptors["knowledge.search"].effect == ToolEffect.READ_ONLY
    assert "properties" in descriptors["knowledge.ask"].input_schema


def test_tools_list_cli_emits_registered_contracts(capsys) -> None:
    result = main(
        [
            "--config",
            str(ROOT / "config" / "config.example.yaml"),
            "tools",
            "list",
            "--json",
        ]
    )

    output = json.loads(capsys.readouterr().out)
    assert result == 0
    assert {item["name"] for item in output} == {
        "knowledge.ask",
        "knowledge.search",
        "knowledge.workspace.describe",
    }
