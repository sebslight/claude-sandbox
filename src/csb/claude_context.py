"""Claude Code context management - handles CLAUDE.md, skills, agents, commands discovery and sync."""

import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class DiscoveredContext:
    """Represents discovered Claude context from a location."""

    source_path: Path
    relative_depth: int  # 0 = project, 1 = parent, 2 = grandparent, etc.
    claude_md: Path | None = None
    claude_local_md: Path | None = None
    rules_dir: Path | None = None
    skills_dir: Path | None = None
    agents_dir: Path | None = None
    commands_dir: Path | None = None

    def has_content(self) -> bool:
        """Check if any Claude content was found."""
        return any([
            self.claude_md,
            self.claude_local_md,
            self.rules_dir,
            self.skills_dir,
            self.agents_dir,
            self.commands_dir,
        ])

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "source_path": str(self.source_path),
            "relative_depth": self.relative_depth,
            "claude_md": str(self.claude_md) if self.claude_md else None,
            "claude_local_md": str(self.claude_local_md) if self.claude_local_md else None,
            "rules_dir": str(self.rules_dir) if self.rules_dir else None,
            "skills_dir": str(self.skills_dir) if self.skills_dir else None,
            "agents_dir": str(self.agents_dir) if self.agents_dir else None,
            "commands_dir": str(self.commands_dir) if self.commands_dir else None,
        }


@dataclass
class ClaudeContextConfig:
    """Configuration for Claude context inclusion."""

    include_global: bool = True
    global_components: list[str] = field(
        default_factory=lambda: ["CLAUDE.md", "agents", "commands", "skills", "rules", "settings.json"]
    )
    auto_discover_parents: bool = True
    parent_max_depth: int = 3
    extra_paths: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "global": {
                "include": self.include_global,
                "components": self.global_components,
            },
            "parents": {
                "auto_discover": self.auto_discover_parents,
                "max_depth": self.parent_max_depth,
            },
            "extra": self.extra_paths,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ClaudeContextConfig":
        """Create from dictionary."""
        if not data:
            return cls()

        global_config = data.get("global", {})
        parents_config = data.get("parents", {})

        return cls(
            include_global=global_config.get("include", True),
            global_components=global_config.get(
                "components",
                ["CLAUDE.md", "agents", "commands", "skills", "rules", "settings.json"],
            ),
            auto_discover_parents=parents_config.get("auto_discover", True),
            parent_max_depth=parents_config.get("max_depth", 3),
            extra_paths=data.get("extra", []),
        )


class ClaudeContext:
    """Manages Claude Code context discovery, copying, and synchronization."""

    CONTEXT_DIR_NAME = "claude-context"
    SETUP_SCRIPT_NAME = "setup-claude-context.sh"

    def __init__(self, project_path: Path):
        self.project_path = project_path
        self.devcontainer_path = project_path / ".devcontainer"
        self.context_path = self.devcontainer_path / self.CONTEXT_DIR_NAME

    def discover_parent_contexts(self, max_depth: int = 3) -> list[DiscoveredContext]:
        """Discover Claude context in parent directories.

        Args:
            max_depth: Maximum number of parent levels to traverse

        Returns:
            List of DiscoveredContext objects, ordered by depth (closest first)
        """
        contexts = []
        current = self.project_path.parent
        depth = 1
        home_dir = Path.home()

        while depth <= max_depth and current != current.parent:
            # Skip home directory - its .claude/ is already mounted as global context
            if current == home_dir:
                current = current.parent
                depth += 1
                continue

            context = self._scan_directory(current, depth)
            if context.has_content():
                contexts.append(context)
            current = current.parent
            depth += 1

        return contexts

    def discover_global_context(self) -> DiscoveredContext | None:
        """Discover Claude context in ~/.claude/."""
        claude_home = Path.home() / ".claude"
        if not claude_home.exists():
            return None

        context = DiscoveredContext(
            source_path=claude_home,
            relative_depth=-1,  # -1 indicates global
        )

        # Check for each component
        if (claude_home / "CLAUDE.md").exists():
            context.claude_md = claude_home / "CLAUDE.md"
        if (claude_home / "rules").is_dir():
            context.rules_dir = claude_home / "rules"
        if (claude_home / "skills").is_dir():
            context.skills_dir = claude_home / "skills"
        if (claude_home / "agents").is_dir():
            context.agents_dir = claude_home / "agents"
        if (claude_home / "commands").is_dir():
            context.commands_dir = claude_home / "commands"

        return context if context.has_content() else None

    def _scan_directory(self, path: Path, depth: int) -> DiscoveredContext:
        """Scan a directory for Claude context files."""
        if path.is_file():
            context = DiscoveredContext(source_path=path, relative_depth=depth)
            if path.name == "CLAUDE.md":
                context.claude_md = path
            elif path.name == "CLAUDE.local.md":
                context.claude_local_md = path
            return context

        context = DiscoveredContext(source_path=path, relative_depth=depth)

        # Check for CLAUDE.md in root
        if (path / "CLAUDE.md").exists():
            context.claude_md = path / "CLAUDE.md"

        # Check for CLAUDE.local.md
        if (path / "CLAUDE.local.md").exists():
            context.claude_local_md = path / "CLAUDE.local.md"

        # Check for .claude/ directory contents
        claude_dir = path / ".claude"
        if claude_dir.is_dir():
            # Also check for CLAUDE.md inside .claude/
            if (claude_dir / "CLAUDE.md").exists():
                context.claude_md = claude_dir / "CLAUDE.md"

            if (claude_dir / "rules").is_dir():
                context.rules_dir = claude_dir / "rules"
            if (claude_dir / "skills").is_dir():
                context.skills_dir = claude_dir / "skills"
            if (claude_dir / "agents").is_dir():
                context.agents_dir = claude_dir / "agents"
            if (claude_dir / "commands").is_dir():
                context.commands_dir = claude_dir / "commands"

        return context

    def copy_contexts(
        self,
        contexts: list[DiscoveredContext],
        config: ClaudeContextConfig,
    ) -> dict:
        """Copy discovered contexts to .devcontainer/claude-context/.

        Args:
            contexts: List of discovered contexts to copy
            config: Configuration specifying what to include

        Returns:
            Dictionary mapping target paths to source paths (for csb.json)
        """
        # Clean and recreate context directory
        if self.context_path.exists():
            shutil.rmtree(self.context_path)
        self.context_path.mkdir(parents=True)

        copied_sources = {}

        # Create subdirectories for organization
        parents_dir = self.context_path / "parents"
        parents_dir.mkdir()

        for context in contexts:
            if context.relative_depth == -1:
                # Global context - we don't copy this, it's mounted
                continue

            # Create directory for this parent level
            parent_dir = parents_dir / f"level-{context.relative_depth}"
            parent_dir.mkdir(exist_ok=True)

            # Copy CLAUDE.md
            if context.claude_md:
                dest = parent_dir / "CLAUDE.md"
                shutil.copy2(context.claude_md, dest)
                copied_sources[str(dest.relative_to(self.devcontainer_path))] = str(
                    context.claude_md
                )

            # Copy CLAUDE.local.md (if exists and user wants it)
            if context.claude_local_md:
                dest = parent_dir / "CLAUDE.local.md"
                shutil.copy2(context.claude_local_md, dest)
                copied_sources[str(dest.relative_to(self.devcontainer_path))] = str(
                    context.claude_local_md
                )

            # Copy directories
            for dir_name, source_dir in [
                ("rules", context.rules_dir),
                ("skills", context.skills_dir),
                ("agents", context.agents_dir),
                ("commands", context.commands_dir),
            ]:
                if source_dir and source_dir.is_dir():
                    dest_dir = parent_dir / dir_name
                    shutil.copytree(source_dir, dest_dir)
                    copied_sources[str(dest_dir.relative_to(self.devcontainer_path))] = str(
                        source_dir
                    )

        # Generate setup script for container
        self._generate_setup_script(contexts, config)

        return copied_sources

    def _generate_setup_script(
        self,
        contexts: list[DiscoveredContext],
        config: ClaudeContextConfig,
    ) -> None:
        """Generate shell script to set up Claude context in container."""
        script_path = self.context_path / self.SETUP_SCRIPT_NAME

        lines = [
            "#!/bin/bash",
            "# Auto-generated by csb - sets up Claude context in container",
            "set -e",
            "",
            "CLAUDE_HOME=\"/home/claude/.claude\"",
            "CONTEXT_DIR=\"/workspace/.devcontainer/claude-context\"",
            "",
            "# Ensure directories exist",
            "mkdir -p \"$CLAUDE_HOME/rules\"",
            "mkdir -p \"$CLAUDE_HOME/skills\"",
            "mkdir -p \"$CLAUDE_HOME/agents\"",
            "mkdir -p \"$CLAUDE_HOME/commands\"",
            "",
        ]

        # Copy parent CLAUDE.md files and create imports
        parent_claude_mds = []
        for context in contexts:
            if context.relative_depth > 0 and context.claude_md:
                parent_claude_mds.append(f"level-{context.relative_depth}/CLAUDE.md")

        if parent_claude_mds:
            lines.extend([
                "# Create parent context imports in a way Claude can find them",
                "# We create a .claude/parents/ directory with symlinks",
                "mkdir -p \"$CLAUDE_HOME/parents\"",
                "",
            ])
            for md_path in parent_claude_mds:
                level = md_path.split("/")[0]
                lines.append(
                    f'ln -sf "$CONTEXT_DIR/parents/{md_path}" "$CLAUDE_HOME/parents/{level}-CLAUDE.md"'
                )
            lines.append("")

        # Symlink parent skills, agents, commands into global directories
        lines.extend([
            "# Symlink parent skills, agents, commands into Claude's directories",
            "for level_dir in \"$CONTEXT_DIR/parents/level-\"*; do",
            "    if [ -d \"$level_dir\" ]; then",
            "        level_name=$(basename \"$level_dir\")",
            "        ",
            "        # Symlink skills",
            "        if [ -d \"$level_dir/skills\" ]; then",
            "            for skill in \"$level_dir/skills/\"*; do",
            "                [ -d \"$skill\" ] && ln -sf \"$skill\" \"$CLAUDE_HOME/skills/$(basename $skill)-$level_name\"",
            "            done",
            "        fi",
            "        ",
            "        # Symlink agents",
            "        if [ -d \"$level_dir/agents\" ]; then",
            "            for agent in \"$level_dir/agents/\"*.md; do",
            "                [ -f \"$agent\" ] && ln -sf \"$agent\" \"$CLAUDE_HOME/agents/$(basename $agent .md)-$level_name.md\"",
            "            done",
            "        fi",
            "        ",
            "        # Symlink commands",
            "        if [ -d \"$level_dir/commands\" ]; then",
            "            for cmd in \"$level_dir/commands/\"*.md; do",
            "                [ -f \"$cmd\" ] && ln -sf \"$cmd\" \"$CLAUDE_HOME/commands/$(basename $cmd .md)-$level_name.md\"",
            "            done",
            "        fi",
            "        ",
            "        # Symlink rules",
            "        if [ -d \"$level_dir/rules\" ]; then",
            "            for rule in \"$level_dir/rules/\"*.md; do",
            "                [ -f \"$rule\" ] && ln -sf \"$rule\" \"$CLAUDE_HOME/rules/$(basename $rule .md)-$level_name.md\"",
            "            done",
            "        fi",
            "    fi",
            "done",
            "",
            "echo 'Claude context setup complete!'",
        ])

        script_path.write_text("\n".join(lines))
        script_path.chmod(0o755)

    def sync(self, config: ClaudeContextConfig) -> dict:
        """Re-sync contexts from their sources.

        Returns:
            Dictionary of what was synced
        """
        contexts = []

        if config.auto_discover_parents:
            contexts.extend(self.discover_parent_contexts(config.parent_max_depth))

        # Add extra paths
        for extra_path in config.extra_paths:
            path = Path(extra_path).expanduser()
            if path.exists():
                # Treat extra paths as depth 100+ to distinguish them
                context = self._scan_directory(path, 100 + len(contexts))
                if context.has_content():
                    contexts.append(context)

        return self.copy_contexts(contexts, config)

    def list_contexts(self, config: ClaudeContextConfig) -> dict:
        """List all Claude contexts that would be included.

        Returns:
            Dictionary with 'global', 'parents', 'extra' keys
        """
        result = {
            "global": None,
            "parents": [],
            "extra": [],
            "copied": {},
        }

        # Global context
        if config.include_global:
            global_ctx = self.discover_global_context()
            if global_ctx:
                result["global"] = global_ctx.to_dict()

        # Parent contexts
        if config.auto_discover_parents:
            parents = self.discover_parent_contexts(config.parent_max_depth)
            result["parents"] = [p.to_dict() for p in parents]

        # Check what's already copied
        if self.context_path.exists():
            csb_json = self.devcontainer_path / "csb.json"
            if csb_json.exists():
                csb_config = json.loads(csb_json.read_text())
                result["copied"] = csb_config.get("claude_context_sources", {})

        return result

    def refresh_in_container(self, container_id: str) -> bool:
        """Run the context setup script in a running container.

        Args:
            container_id: Docker container ID

        Returns:
            True if successful
        """
        import subprocess

        script_path = f"/workspace/.devcontainer/{self.CONTEXT_DIR_NAME}/{self.SETUP_SCRIPT_NAME}"

        try:
            result = subprocess.run(
                ["docker", "exec", container_id, "bash", script_path],
                capture_output=True,
                text=True,
                timeout=30,
            )
            return result.returncode == 0
        except Exception:
            return False
