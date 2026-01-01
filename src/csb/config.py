"""User configuration management."""

import json
from pathlib import Path


class Config:
    """Manages global csb configuration."""

    def __init__(self):
        self.config_dir = Path.home() / ".config" / "csb"
        self.config_path = self.config_dir / "config.json"
        self._ensure_config_dir()

    def _ensure_config_dir(self) -> None:
        """Create config directory if it doesn't exist."""
        self.config_dir.mkdir(parents=True, exist_ok=True)
        if not self.config_path.exists():
            self._write_default_config()

    def _write_default_config(self) -> None:
        """Write default configuration."""
        default = {
            "default_mcp_servers": ["filesystem"],
            "container_runtime": "docker",  # docker, podman, orbstack
        }
        self.config_path.write_text(json.dumps(default, indent=2))

    def get_all(self) -> dict:
        """Get all configuration values."""
        if self.config_path.exists():
            return json.loads(self.config_path.read_text())
        return {}

    def get(self, key: str, default=None):
        """Get a configuration value."""
        return self.get_all().get(key, default)

    def set(self, key: str, value) -> None:
        """Set a configuration value."""
        config = self.get_all()
        config[key] = value
        self.config_path.write_text(json.dumps(config, indent=2))
