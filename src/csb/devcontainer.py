"""Wrapper around the devcontainer CLI."""

from __future__ import annotations

import logging
import subprocess
import shutil
import json
from dataclasses import dataclass
from pathlib import Path
from importlib import resources
from typing import TYPE_CHECKING

from csb.mcp import generate_mcp_config, generate_runtime_mcp_config, MCP_SERVERS
from csb.claude_settings import generate_runtime_settings
from csb.exceptions import DevcontainerCliNotFoundError
import csb.templates

if TYPE_CHECKING:
    from csb.claude_context import ClaudeContextConfig


@dataclass
class CommandResult:
    success: bool
    output: str = ""
    error: str = ""


class DevContainer:
    """Manages devcontainer lifecycle for a project."""

    def __init__(self, project_path: Path):
        self.project_path = project_path
        self.devcontainer_path = project_path / ".devcontainer"
        self._ensure_devcontainer_cli()

    def _ensure_devcontainer_cli(self) -> None:
        """Check if devcontainer CLI is installed."""
        if not shutil.which("devcontainer"):
            raise DevcontainerCliNotFoundError()

    def create(
        self,
        mcp_servers: list[str],
        custom_mcp_servers: dict | None = None,
        dockerfile_path: Path | None = None,
        claude_context: ClaudeContextConfig | None = None,
    ) -> None:
        """Create .devcontainer/ with the given MCP servers.

        This is the initial creation - writes all files including Dockerfile.
        For subsequent updates (add/remove MCP servers), use _update_config_files().

        Args:
            mcp_servers: List of built-in MCP server names to enable
            custom_mcp_servers: Dict of custom server configs
            dockerfile_path: Path to custom Dockerfile to copy (uses built-in if None)
            claude_context: Claude context configuration (CLAUDE.md, skills, etc.)
        """
        self.devcontainer_path.mkdir(parents=True, exist_ok=True)

        # Write Dockerfile (only on initial create)
        self._write_dockerfile(dockerfile_path)

        # Write config files (csb.json, devcontainer.json, .mcp.json)
        self._update_config_files(mcp_servers, custom_mcp_servers, claude_context)

    def _write_dockerfile(self, dockerfile_path: Path | None = None) -> None:
        """Write Dockerfile to .devcontainer/.

        Args:
            dockerfile_path: Path to custom Dockerfile to copy. If None, uses built-in.
        """
        if dockerfile_path:
            # Copy custom Dockerfile
            dockerfile_content = dockerfile_path.read_text()
        else:
            # Use built-in template
            template_file = resources.files(csb.templates).joinpath("Dockerfile")
            dockerfile_content = template_file.read_text()

        (self.devcontainer_path / "Dockerfile").write_text(dockerfile_content)

    def _update_config_files(
        self,
        mcp_servers: list[str],
        custom_mcp_servers: dict | None = None,
        claude_context: ClaudeContextConfig | None = None,
    ) -> None:
        """Update config files without touching Dockerfile.

        Writes: csb.json, devcontainer.json, .mcp.json
        Does NOT write: Dockerfile (that's only written on initial create)
        """
        # Write csb.json (tracks configuration for updates)
        csb_config = {
            "version": "1.0",
            "mcp_servers": mcp_servers,
            "custom_mcp_servers": custom_mcp_servers or {},
        }
        if claude_context:
            csb_config["claude_context"] = claude_context.to_dict()

        (self.devcontainer_path / "csb.json").write_text(
            json.dumps(csb_config, indent=2)
        )

        # Write devcontainer.json
        has_context_setup = (
            self.devcontainer_path / "claude-context" / "setup-claude-context.sh"
        ).exists()
        devcontainer_json = self._generate_devcontainer_json(
            mcp_servers, custom_mcp_servers, has_context_setup
        )
        (self.devcontainer_path / "devcontainer.json").write_text(
            json.dumps(devcontainer_json, indent=2)
        )

        # Write .mcp.json
        mcp_config = generate_mcp_config(mcp_servers, custom_mcp_servers)
        (self.devcontainer_path / ".mcp.json").write_text(
            json.dumps(mcp_config, indent=2)
        )

        # Write runtime MCP config (merged with global when Claude context is enabled)
        runtime_mcp_config = generate_runtime_mcp_config(
            mcp_servers,
            custom_mcp_servers,
            merge_global=bool(claude_context and claude_context.include_global),
        )
        (self.devcontainer_path / ".mcp.runtime.json").write_text(
            json.dumps(runtime_mcp_config, indent=2)
        )

        # Write runtime settings.json with container-safe hooks
        generate_runtime_settings(self.devcontainer_path / ".settings.runtime.json")

    def get_csb_config(self) -> dict | None:
        """Read csb.json configuration if it exists."""
        csb_json_path = self.devcontainer_path / "csb.json"
        if csb_json_path.exists():
            try:
                return json.loads(csb_json_path.read_text())
            except json.JSONDecodeError:
                logging.warning(f"Invalid JSON in {csb_json_path}, treating as missing")
                return None
        return None

    def needs_runtime_update(self) -> bool:
        """Check if devcontainer.json includes runtime config mounts."""
        devcontainer_json_path = self.devcontainer_path / "devcontainer.json"
        csb_json_path = self.devcontainer_path / "csb.json"

        if not devcontainer_json_path.exists() or not csb_json_path.exists():
            return False

        try:
            config = json.loads(devcontainer_json_path.read_text())
        except json.JSONDecodeError:
            return True

        mounts = config.get("mounts", [])
        if not isinstance(mounts, list):
            return True

        has_settings = any(".settings.runtime.json" in mount for mount in mounts)
        has_mcp = any(".mcp.runtime.json" in mount for mount in mounts)
        has_workspace_mcp = any("/workspace/.mcp.json" in mount for mount in mounts)
        runtime_settings = self.devcontainer_path / ".settings.runtime.json"
        runtime_mcp = self.devcontainer_path / ".mcp.runtime.json"
        has_runtime = (
            has_settings
            and has_mcp
            and runtime_settings.exists()
            and runtime_mcp.exists()
        )
        has_workspace_folder = config.get("workspaceFolder") == "/workspace"

        post_create = config.get("postCreateCommand", "")
        setup_script = (
            self.devcontainer_path / "claude-context" / "setup-claude-context.sh"
        )
        needs_post_create_guard = (
            isinstance(post_create, str)
            and "claude-context/setup-claude-context.sh" in post_create
            and not setup_script.exists()
        )

        return (
            not has_runtime
            or needs_post_create_guard
            or not has_workspace_mcp
            or not has_workspace_folder
        )

    def update(self) -> None:
        """Regenerate config files based on saved csb.json config.

        Updates devcontainer.json and .mcp.json but NOT the Dockerfile.
        To update the Dockerfile, run `csb init --force` with optional --dockerfile.
        """
        config = self.get_csb_config()
        if not config:
            raise ValueError("No csb.json found. Run `csb init` first.")

        mcp_servers = config.get("mcp_servers", [])
        custom_mcp_servers = config.get("custom_mcp_servers", {})

        # Reconstruct claude_context config if it exists
        claude_context = None
        if "claude_context" in config:
            from csb.claude_context import ClaudeContextConfig

            claude_context = ClaudeContextConfig.from_dict(config["claude_context"])

        self._update_config_files(mcp_servers, custom_mcp_servers, claude_context)

    def add_mcp_server(self, server_name: str) -> bool:
        """Add a built-in MCP server to the configuration.

        Returns True if the server was added, False if it already exists.
        Does not modify the Dockerfile.
        """
        config = self.get_csb_config()
        if not config:
            raise ValueError("No csb.json found. Run `csb init` first.")

        mcp_servers = config.get("mcp_servers", [])
        if server_name in mcp_servers:
            return False

        mcp_servers.append(server_name)

        # Preserve claude_context
        claude_context = None
        if "claude_context" in config:
            from csb.claude_context import ClaudeContextConfig

            claude_context = ClaudeContextConfig.from_dict(config["claude_context"])

        self._update_config_files(
            mcp_servers, config.get("custom_mcp_servers", {}), claude_context
        )
        return True

    def remove_mcp_server(self, server_name: str) -> bool:
        """Remove an MCP server from the configuration.

        Returns True if the server was removed, False if it wasn't found.
        Does not modify the Dockerfile.
        """
        config = self.get_csb_config()
        if not config:
            raise ValueError("No csb.json found. Run `csb init` first.")

        mcp_servers = config.get("mcp_servers", [])
        custom_mcp_servers = config.get("custom_mcp_servers", {})

        removed = False
        if server_name in mcp_servers:
            mcp_servers.remove(server_name)
            removed = True
        if server_name in custom_mcp_servers:
            del custom_mcp_servers[server_name]
            removed = True

        if removed:
            # Preserve claude_context
            claude_context = None
            if "claude_context" in config:
                from csb.claude_context import ClaudeContextConfig

                claude_context = ClaudeContextConfig.from_dict(config["claude_context"])

            self._update_config_files(mcp_servers, custom_mcp_servers, claude_context)

        return removed

    def add_custom_mcp_server(
        self, name: str, command: str, args: list[str], env: dict | None = None
    ) -> bool:
        """Add a custom MCP server to the configuration.

        Returns True if the server was added, False if it already exists.
        Does not modify the Dockerfile.
        """
        config = self.get_csb_config()
        if not config:
            raise ValueError("No csb.json found. Run `csb init` first.")

        custom_mcp_servers = config.get("custom_mcp_servers", {})
        if name in custom_mcp_servers or name in config.get("mcp_servers", []):
            return False

        custom_mcp_servers[name] = {
            "command": command,
            "args": args,
        }
        if env:
            custom_mcp_servers[name]["env"] = env
            custom_mcp_servers[name]["required_env"] = list(env.keys())

        # Preserve claude_context
        claude_context = None
        if "claude_context" in config:
            from csb.claude_context import ClaudeContextConfig

            claude_context = ClaudeContextConfig.from_dict(config["claude_context"])

        self._update_config_files(
            config.get("mcp_servers", []), custom_mcp_servers, claude_context
        )
        return True

    def _generate_devcontainer_json(
        self,
        mcp_servers: list[str],
        custom_mcp_servers: dict | None = None,
        has_context_setup: bool = False,
    ) -> dict:
        """Generate devcontainer.json configuration."""
        # Collect required env vars from selected MCP servers
        env_vars = {}
        for server_name in mcp_servers:
            server = MCP_SERVERS.get(server_name, {})
            for env_var in server.get("required_env", []):
                env_vars[env_var] = f"${{localEnv:{env_var}}}"

        # Add env vars from custom MCP servers
        if custom_mcp_servers:
            for server_config in custom_mcp_servers.values():
                for env_var in server_config.get("required_env", []):
                    env_vars[env_var] = f"${{localEnv:{env_var}}}"

        # Build postCreateCommand - run context setup if it exists
        post_create = (
            "if [ -f /workspace/.devcontainer/claude-context/setup-claude-context.sh ]; then "
            "/workspace/.devcontainer/claude-context/setup-claude-context.sh; fi"
        )

        # postStartCommand - re-run context setup on each start (in case sources changed)
        post_start = (
            "if [ -f /workspace/.devcontainer/claude-context/setup-claude-context.sh ]; then "
            "/workspace/.devcontainer/claude-context/setup-claude-context.sh; "
            "fi; echo 'Claude Sandbox ready! Run: claude --dangerously-skip-permissions'"
        )

        return {
            "name": "Claude Sandbox",
            "build": {
                "dockerfile": "Dockerfile",
            },
            "workspaceFolder": "/workspace",
            "workspaceMount": (
                "source=${localWorkspaceFolder},target=/workspace,"
                "type=bind,consistency=cached"
            ),
            "mounts": [
                "source=${localEnv:HOME}/.claude,target=/home/claude/.claude,type=bind,consistency=cached",
                "source=${localWorkspaceFolder}/.devcontainer/.settings.runtime.json,target=/home/claude/.claude/settings.json,type=bind,consistency=cached",
                "source=${localWorkspaceFolder}/.devcontainer/.mcp.runtime.json,target=/workspace/.mcp.json,type=bind,consistency=cached",
                "source=${localWorkspaceFolder}/.devcontainer/.mcp.runtime.json,target=/home/claude/.claude/.mcp.json,type=bind,consistency=cached",
            ],
            "containerEnv": {
                "ANTHROPIC_API_KEY": "${localEnv:ANTHROPIC_API_KEY}",
                **env_vars,
            },
            "remoteUser": "claude",
            "postCreateCommand": post_create,
            "postStartCommand": post_start,
        }

    def up(self, rebuild: bool = False, no_cache: bool = False) -> CommandResult:
        """Start the devcontainer.

        Args:
            rebuild: If True, removes existing container before starting
            no_cache: If True, forces a full image rebuild without Docker cache
        """
        cmd = [
            "devcontainer",
            "up",
            "--workspace-folder",
            str(self.project_path),
        ]
        if rebuild:
            cmd.append("--remove-existing-container")
        if no_cache:
            cmd.append("--build-no-cache")

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=600,  # 10 minute timeout for no-cache builds
            )
            if result.returncode == 0:
                return CommandResult(success=True, output=result.stdout)
            return CommandResult(success=False, error=result.stderr or result.stdout)
        except subprocess.TimeoutExpired:
            return CommandResult(success=False, error="Container build timed out")
        except Exception as e:
            return CommandResult(success=False, error=str(e))

    def up_with_output(self, rebuild: bool = False, no_cache: bool = False):
        """Start the devcontainer, yielding output lines as they come.

        Args:
            rebuild: If True, removes existing container before starting
            no_cache: If True, forces a full image rebuild without Docker cache

        Yields:
            str: Lines of output from the build process

        Returns:
            CommandResult via the final yield
        """
        cmd = [
            "devcontainer",
            "up",
            "--workspace-folder",
            str(self.project_path),
        ]
        if rebuild:
            cmd.append("--remove-existing-container")
        if no_cache:
            cmd.append("--build-no-cache")

        try:
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,  # Line buffered
            )

            output_lines = []
            for line in process.stdout:
                line = line.rstrip("\n")
                output_lines.append(line)
                yield line

            process.wait()

            if process.returncode == 0:
                yield CommandResult(success=True, output="\n".join(output_lines))
            else:
                yield CommandResult(success=False, error="\n".join(output_lines))

        except Exception as e:
            yield CommandResult(success=False, error=str(e))

    def down(self) -> CommandResult:
        """Stop the devcontainer."""
        try:
            # Find container ID using docker ps with devcontainer label
            # Devcontainers are labeled with devcontainer.local_folder
            workspace_path = str(self.project_path)
            find_cmd = [
                "docker",
                "ps",
                "-q",
                "--filter",
                f"label=devcontainer.local_folder={workspace_path}",
            ]
            result = subprocess.run(
                find_cmd, capture_output=True, text=True, timeout=10
            )

            container_id = result.stdout.strip()
            if not container_id:
                return CommandResult(success=True, output="Container not running")

            # Stop the container
            stop_cmd = ["docker", "stop", container_id]
            stop_result = subprocess.run(
                stop_cmd, capture_output=True, text=True, timeout=30
            )

            if stop_result.returncode == 0:
                return CommandResult(
                    success=True, output=f"Stopped container {container_id[:12]}"
                )
            return CommandResult(success=False, error=stop_result.stderr)
        except subprocess.TimeoutExpired:
            return CommandResult(success=False, error="Timeout stopping container")
        except Exception as e:
            return CommandResult(success=False, error=str(e))

    def remove_container(self) -> CommandResult:
        """Remove the devcontainer (must be stopped first).

        Finds and removes the container associated with this project.
        """
        try:
            workspace_path = str(self.project_path)

            # Find container (including stopped ones) using -a flag
            find_cmd = [
                "docker",
                "ps",
                "-aq",
                "--filter",
                f"label=devcontainer.local_folder={workspace_path}",
            ]
            result = subprocess.run(
                find_cmd, capture_output=True, text=True, timeout=10
            )

            container_id = result.stdout.strip()
            if not container_id:
                return CommandResult(success=False, error="No container found")

            # Remove the container
            rm_cmd = ["docker", "rm", container_id]
            rm_result = subprocess.run(
                rm_cmd, capture_output=True, text=True, timeout=30
            )

            if rm_result.returncode == 0:
                return CommandResult(
                    success=True, output=f"Removed container {container_id[:12]}"
                )
            return CommandResult(success=False, error=rm_result.stderr)
        except subprocess.TimeoutExpired:
            return CommandResult(success=False, error="Timeout removing container")
        except Exception as e:
            return CommandResult(success=False, error=str(e))

    def remove_image(self) -> CommandResult:
        """Remove the Docker image for this project.

        The devcontainer CLI creates images with a specific naming pattern.
        """
        try:
            # Devcontainer images are named based on the project folder
            # Format: vsc-{folder_name}-{hash}
            folder_name = self.project_path.name

            # Find images matching the devcontainer pattern
            find_cmd = [
                "docker",
                "images",
                "-q",
                "--filter",
                f"reference=vsc-{folder_name}-*",
            ]
            result = subprocess.run(
                find_cmd, capture_output=True, text=True, timeout=10
            )

            image_ids = result.stdout.strip().split("\n")
            image_ids = [img for img in image_ids if img]  # Filter empty strings

            if not image_ids:
                return CommandResult(success=False, error="No image found")

            # Remove the images
            rm_cmd = ["docker", "rmi"] + image_ids
            rm_result = subprocess.run(
                rm_cmd, capture_output=True, text=True, timeout=60
            )

            if rm_result.returncode == 0:
                return CommandResult(
                    success=True, output=f"Removed {len(image_ids)} image(s)"
                )
            return CommandResult(success=False, error=rm_result.stderr)
        except subprocess.TimeoutExpired:
            return CommandResult(success=False, error="Timeout removing image")
        except Exception as e:
            return CommandResult(success=False, error=str(e))

    def exec_claude(self) -> None:
        """Execute Claude Code in the container."""
        cmd = [
            "devcontainer",
            "exec",
            "--workspace-folder",
            str(self.project_path),
            "claude",
            "--dangerously-skip-permissions",
        ]
        # Use os.execvp to replace current process
        import os

        os.execvp("devcontainer", cmd)

    def exec_shell(self) -> None:
        """Open a shell in the container."""
        cmd = [
            "devcontainer",
            "exec",
            "--workspace-folder",
            str(self.project_path),
            "zsh",
        ]
        import os

        os.execvp("devcontainer", cmd)

    def is_running(self) -> bool:
        """Check if the container is running."""
        cmd = [
            "devcontainer",
            "exec",
            "--workspace-folder",
            str(self.project_path),
            "true",
        ]
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                timeout=5,
            )
            return result.returncode == 0
        except Exception:
            return False

    def get_container_id(self) -> str | None:
        """Get the container ID for this project."""
        workspace_path = str(self.project_path)
        find_cmd = [
            "docker",
            "ps",
            "-q",
            "--filter",
            f"label=devcontainer.local_folder={workspace_path}",
        ]
        try:
            result = subprocess.run(
                find_cmd, capture_output=True, text=True, timeout=10
            )
            container_id = result.stdout.strip()
            return container_id if container_id else None
        except Exception:
            return None

    def logs(self, follow: bool = False, tail: int | None = None) -> None:
        """Show container logs.

        Args:
            follow: If True, follow log output (like tail -f)
            tail: Number of lines to show from the end
        """
        container_id = self.get_container_id()
        if not container_id:
            raise ValueError("Container not running")

        cmd = ["docker", "logs"]
        if follow:
            cmd.append("-f")
        if tail:
            cmd.extend(["--tail", str(tail)])
        cmd.append(container_id)

        import os

        os.execvp("docker", cmd)
