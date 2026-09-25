"""Application configuration lifecycle management."""

from pathlib import Path

from knowledge_assistant.config import Settings, load_settings


class ConfigManager:
    """Load and expose the validated application configuration."""

    def __init__(
        self, config_path: str | Path, env_path: str | Path | None = None
    ) -> None:
        self._config_path = Path(config_path)
        self._env_path = Path(env_path) if env_path is not None else None
        self._settings: Settings | None = None

    def load(self) -> Settings:
        """Load configuration and retain validated settings."""
        self._settings = load_settings(self._config_path, self._env_path)
        return self._settings

    @property
    def settings(self) -> Settings:
        """Return settings, loading them on first access."""
        return self._settings if self._settings is not None else self.load()
