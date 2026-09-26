"""Tests for validated configuration loading."""

from pathlib import Path

import pytest
import yaml

from knowledge_assistant.config import ConfigurationError, load_settings


def test_load_settings_validates_repository_configuration() -> None:
    """The checked-in configuration can be loaded with local environment values."""
    root = Path(__file__).parents[1]

    settings = load_settings(
        root / "config" / "config.yaml", root / ".env.example", include_local=False
    )

    assert settings.llm.model == "qwen3:8b"
    assert settings.chunking.overlap == 100
    assert settings.pdf_link_download.allowed_extensions == [".pdf", ".txt", ".md"]
    assert settings.chroma.directory == root / "artifacts" / "chroma"
    assert settings.workspaces["example"].artifacts == (
        root / "workspaces" / "example" / "artifacts"
    )
    assert settings.prompts.question_answer == root / "prompts" / "question_answer.md"
    assert str(settings.environment.ollama_host) == "http://localhost:11434/"


def test_load_settings_merges_a_local_overlay(tmp_path: Path) -> None:
    config = tmp_path / "config" / "config.yaml"
    config.parent.mkdir()
    config.write_text(
        (Path(__file__).parents[1] / "config" / "config.example.yaml").read_text(
            encoding="utf-8"
        ),
        encoding="utf-8",
    )
    config.with_name("config.local.yaml").write_text(
        """llm:
  model: local-test-model
workspaces:
  example:
    documents:
      roots:
        - name: documents
          path: ./private-documents
""",
        encoding="utf-8",
    )

    settings = load_settings(config)

    assert settings.llm.model == "local-test-model"
    assert settings.workspaces["example"].documents.roots[0].path == (
        tmp_path / "private-documents"
    )


def test_evidence_library_configuration_is_optional_and_strict(tmp_path: Path) -> None:
    source = Path("config/config.example.yaml").read_text(encoding="utf-8")
    config = tmp_path / "config" / "config.yaml"
    config.parent.mkdir()
    config.write_text(source, encoding="utf-8")
    assert load_settings(config).workspaces["example"].evidence_library is None

    raw = yaml.safe_load(source)
    raw["workspaces"]["example"]["evidence_library"] = {
        "manifest": "metadata/manifest.json",
        "policy": "metadata/policy.yaml",
        "missing_referenced_document": "fatal",
        "unmatched_document": "ignore",
    }
    config.write_text(yaml.safe_dump(raw), encoding="utf-8")
    evidence = load_settings(config).workspaces["example"].evidence_library
    assert evidence is not None
    assert evidence.missing_referenced_document == "fatal"

    raw["workspaces"]["example"]["evidence_library"]["unmatched_document"] = "guess"
    config.write_text(yaml.safe_dump(raw), encoding="utf-8")
    with pytest.raises(ConfigurationError, match="unmatched_document"):
        load_settings(config)


def test_load_settings_rejects_invalid_chunk_overlap(tmp_path: Path) -> None:
    """Invalid relationships between configuration values are reported."""
    config_file = tmp_path / "config" / "config.yaml"
    config_file.parent.mkdir()
    config_file.write_text(
        (Path(__file__).parents[1] / "config" / "config.example.yaml")
        .read_text(encoding="utf-8")
        .replace("overlap: 100", "overlap: 800"),
        encoding="utf-8",
    )

    with pytest.raises(ConfigurationError, match="smaller than chunking.size"):
        load_settings(config_file)


def test_load_settings_supports_named_roots_and_inherited_policies(
    tmp_path: Path,
) -> None:
    config_file = tmp_path / "config" / "config.yaml"
    config_file.parent.mkdir()
    source = (Path(__file__).parents[1] / "config" / "config.example.yaml").read_text(
        encoding="utf-8"
    )
    config_file.write_text(
        source.replace(
            """        - name: documents
          path: ./knowledge""",
            """        - name: course
          path: ./course
        - name: evidence
          path: ./evidence
          recursive: false""",
        ),
        encoding="utf-8",
    )

    settings = load_settings(config_file)
    documents = settings.workspaces["example"].documents

    assert documents.roots[0].path == tmp_path / "course"
    assert documents.roots[1].recursive is False


def test_load_settings_rejects_overlapping_source_roots(tmp_path: Path) -> None:
    config_file = tmp_path / "config" / "config.yaml"
    config_file.parent.mkdir()
    source = (Path(__file__).parents[1] / "config" / "config.example.yaml").read_text(
        encoding="utf-8"
    )
    config_file.write_text(
        source.replace(
            """        - name: documents
          path: ./knowledge""",
            """        - name: all
          path: ./knowledge
        - name: nested
          path: ./knowledge/nested""",
        ),
        encoding="utf-8",
    )

    with pytest.raises(ConfigurationError, match="overlap"):
        load_settings(config_file)


def test_load_settings_does_not_read_process_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Service values are accepted only from the explicitly supplied .env file."""
    root = Path(__file__).parents[1]
    monkeypatch.setenv("OLLAMA_HOST", "https://process.example")

    settings = load_settings(root / "config" / "config.example.yaml")

    assert settings.environment.ollama_host is None

    environment_file = tmp_path / ".env"
    environment_file.write_text(
        "OLLAMA_HOST=http://localhost:11434\n", encoding="utf-8"
    )
    settings = load_settings(root / "config" / "config.example.yaml", environment_file)

    assert str(settings.environment.ollama_host) == "http://localhost:11434/"
