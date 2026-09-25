from pathlib import Path

import pytest

from knowledge_assistant.managers import (
    ConfigManager,
    PromptManager,
    PromptNotFoundError,
    WorkspaceManager,
    WorkspaceNotFoundError,
)


def settings():
    root = Path(__file__).parents[1]
    return ConfigManager(root / "config" / "config.example.yaml").settings


def test_config_manager_loads_workspace_settings() -> None:
    assert settings().workspaces["example"].collection == "example"


def test_prompt_manager_loads_configured_prompt() -> None:
    manager = PromptManager(settings().prompts)
    assert "question_answer" in manager.names()
    assert "Knowledge Assistant" in manager.get("question_answer")
    with pytest.raises(PromptNotFoundError):
        manager.get("missing")


def test_workspace_manager_lists_enabled_and_finds_named_workspace() -> None:
    manager = WorkspaceManager(settings().workspaces)
    assert [workspace.name for workspace in manager.list()] == ["example"]
    assert manager.get("example").documents.name == "knowledge"
    with pytest.raises(WorkspaceNotFoundError):
        manager.get("missing")
