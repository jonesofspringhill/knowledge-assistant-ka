"""Tests for the public command-line interface."""

from pathlib import Path

import ollama
import yaml

from knowledge_assistant.main import main


def _config() -> str:
    return str(Path(__file__).parents[1] / "config" / "config.example.yaml")


def test_import() -> None:
    assert callable(main)


def test_workspace_list_includes_default_workspace(capsys) -> None:
    assert main(["--config", _config(), "workspace", "list"]) == 0
    assert "example:" in capsys.readouterr().out


def test_workspace_info_uses_active_workspace(capsys) -> None:
    assert main(["--config", _config(), "workspace", "info"]) == 0
    assert "Name: example" in capsys.readouterr().out


def test_prompt_commands_list_and_show_configured_prompts(capsys) -> None:
    assert main(["--config", _config(), "prompt", "list"]) == 0
    assert "question_answer" in capsys.readouterr().out
    assert main(["--config", _config(), "prompt", "show", "question_answer"]) == 0
    assert "Knowledge Assistant" in capsys.readouterr().out


def test_config_validate_and_version(capsys) -> None:
    assert main(["--config", _config(), "config", "validate"]) == 0
    assert "PASS Configuration valid" in capsys.readouterr().out
    assert main(["--config", _config(), "version"]) == 0
    assert "Active workspace: example" in capsys.readouterr().out


def test_workspace_create_requires_explicit_confirmation(
    tmp_path: Path, capsys
) -> None:
    config = tmp_path / "config" / "config.yaml"
    config.parent.mkdir()
    config.write_text(Path(_config()).read_text(encoding="utf-8"), encoding="utf-8")

    assert main(["--config", str(config), "workspace", "create", "research"]) == 2
    assert "requires --yes" in capsys.readouterr().err
    assert (
        main(["--config", str(config), "workspace", "create", "research", "--yes"]) == 0
    )
    assert (tmp_path / "knowledge" / "research").is_dir()
    assert "research:" in config.read_text(encoding="utf-8")


def test_doctor_reports_ready_with_mocked_ollama(
    tmp_path: Path, capsys, monkeypatch
) -> None:
    source = Path(_config())
    configuration = yaml.safe_load(source.read_text(encoding="utf-8"))
    documents = tmp_path / "documents"
    storage = tmp_path / "storage"
    logs = tmp_path / "logs"
    documents.mkdir()
    storage.mkdir()
    logs.mkdir()
    configuration["workspaces"]["example"]["documents"] = str(documents)
    configuration["chroma"]["directory"] = str(storage)
    configuration["logging"]["file"] = str(logs / "knowledge_assistant.log")
    for name in configuration["prompts"]:
        configuration["prompts"][name] = str(
            source.parent.parent / configuration["prompts"][name]
        )
    config = tmp_path / "config.yaml"
    config.write_text(yaml.safe_dump(configuration), encoding="utf-8")

    class Client:
        def __init__(self, host: str) -> None:
            self.host = host

        def list(self):
            return type(
                "Response",
                (),
                {
                    "models": [
                        type("Model", (), {"model": "nomic-embed-text"})(),
                        type("Model", (), {"model": "qwen3:8b"})(),
                    ]
                },
            )()

    monkeypatch.setattr(ollama, "Client", Client)

    assert main(["--config", str(config), "doctor"]) == 0
    output = capsys.readouterr().out
    assert 'PASS   Workspace "example"' in output
    assert "collection: example" in output
    assert "PASS   Ollama reachable" in output
    assert "PASS   Available models: nomic-embed-text, qwen3:8b" in output
    assert "READY" in output


def test_doctor_reports_invalid_configuration_without_traceback(
    tmp_path: Path, capsys
) -> None:
    config = tmp_path / "missing.yaml"

    assert main(["--config", str(config), "doctor"]) == 2
    output = capsys.readouterr().out
    assert "FAIL   Configuration could not be loaded" in output
    assert "NOT READY" in output
