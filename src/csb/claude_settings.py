"""Generate container-safe Claude settings from host settings."""

from __future__ import annotations

import json
import shlex
from pathlib import Path


def _wrap_absolute_command(command: str) -> str:
    """Wrap absolute-path commands so missing binaries don't raise errors."""
    stripped = command.strip()
    if not stripped.startswith("/"):
        return command

    try:
        parts = shlex.split(stripped)
    except ValueError:
        return command

    if not parts:
        return command

    binary = parts[0]
    if not binary.startswith("/"):
        return command

    return f'test -x "{binary}" || exit 0; {command}'


def sanitize_settings(settings: dict) -> dict:
    """Return a sanitized copy of settings for container use."""
    hooks = settings.get("hooks")
    if not isinstance(hooks, dict):
        return settings

    for hook_group in hooks.values():
        if not isinstance(hook_group, list):
            continue
        for entry in hook_group:
            if not isinstance(entry, dict):
                continue
            hook_list = entry.get("hooks")
            if not isinstance(hook_list, list):
                continue
            for hook in hook_list:
                if not isinstance(hook, dict):
                    continue
                if hook.get("type") != "command":
                    continue
                command = hook.get("command")
                if isinstance(command, str):
                    hook["command"] = _wrap_absolute_command(command)

    return settings


def generate_runtime_settings(output_path: Path, source_path: Path | None = None) -> dict:
    """Write a container-safe settings.json based on host settings."""
    if source_path is None:
        source_path = Path.home() / ".claude" / "settings.json"

    settings = {}
    if source_path.exists():
        try:
            settings = json.loads(source_path.read_text())
        except json.JSONDecodeError:
            settings = {}

    sanitized = sanitize_settings(settings)
    output_path.write_text(json.dumps(sanitized, indent=2))
    return sanitized
