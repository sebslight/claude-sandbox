"""CLI commands for managing Claude context (CLAUDE.md, skills, agents, commands)."""

import typer
from rich.console import Console
from pathlib import Path

from csb.devcontainer import DevContainer
from csb.claude_context import ClaudeContext, ClaudeContextConfig
from csb.exceptions import CsbError

console = Console()

claude_app = typer.Typer(
    name="claude",
    help="Manage Claude context (CLAUDE.md, skills, agents, commands)",
    no_args_is_help=True,
)


def handle_csb_errors(func):
    """Decorator to handle CsbError exceptions gracefully."""
    import functools

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except CsbError as e:
            console.print(f"[red]Error:[/] {e}")
            raise typer.Exit(1)

    return wrapper


@claude_app.command("list")
@handle_csb_errors
def list_context(
    path: Path = typer.Argument(
        Path("."),
        help="Project directory",
    ),
):
    """List Claude context that will be included in the sandbox.

    Shows global ~/.claude/ content, discovered parent contexts,
    and what has been copied to .devcontainer/claude-context/.
    """
    project_path = path.resolve()
    devcontainer_path = project_path / ".devcontainer"

    # Load config if exists
    csb_json_path = devcontainer_path / "csb.json"
    if csb_json_path.exists():
        import json
        csb_config = json.loads(csb_json_path.read_text())
        config = ClaudeContextConfig.from_dict(csb_config.get("claude_context", {}))
    else:
        config = ClaudeContextConfig()

    ctx = ClaudeContext(project_path)
    info = ctx.list_contexts(config)

    # Global context
    console.print("\n[bold]Global Context (~/.claude/)[/]")
    if info["global"]:
        global_ctx = info["global"]
        items = []
        if global_ctx.get("claude_md"):
            items.append("CLAUDE.md")
        if global_ctx.get("rules_dir"):
            items.append("rules/")
        if global_ctx.get("skills_dir"):
            items.append("skills/")
        if global_ctx.get("agents_dir"):
            items.append("agents/")
        if global_ctx.get("commands_dir"):
            items.append("commands/")
        console.print(f"  [green]✓[/] Mounted: {', '.join(items)}")
    else:
        console.print("  [dim]No global Claude context found[/]")

    # Parent contexts
    console.print("\n[bold]Parent Contexts[/]")
    if info["parents"]:
        for parent in info["parents"]:
            depth = parent["relative_depth"]
            source = parent["source_path"]
            items = []
            if parent.get("claude_md"):
                items.append("CLAUDE.md")
            if parent.get("rules_dir"):
                items.append("rules/")
            if parent.get("skills_dir"):
                items.append("skills/")
            if parent.get("agents_dir"):
                items.append("agents/")
            if parent.get("commands_dir"):
                items.append("commands/")

            status = "[green]✓[/]" if info["copied"] else "[yellow]![/]"
            console.print(f"  {status} Level {depth}: {source}")
            console.print(f"      Found: {', '.join(items)}")

        # Sync status - only show if there are parents to sync
        console.print("\n[bold]Sync Status[/]")
        context_dir = devcontainer_path / "claude-context"
        if context_dir.exists() and info["copied"]:
            console.print("  [green]✓[/] Context copied to .devcontainer/claude-context/")
            console.print(f"      {len(info['copied'])} items synced")
        else:
            console.print("  [yellow]![/] Not synced - run [cyan]csb claude sync[/] to copy parent contexts")
    else:
        console.print("  [dim]No parent Claude context found[/]")

    console.print()


@claude_app.command("sync")
@handle_csb_errors
def sync_context(
    path: Path = typer.Argument(
        Path("."),
        help="Project directory",
    ),
):
    """Sync Claude context from parent directories.

    Copies CLAUDE.md, skills, agents, commands, and rules from parent
    directories into .devcontainer/claude-context/ so they're available
    in the container.
    """
    project_path = path.resolve()
    devcontainer_path = project_path / ".devcontainer"

    if not devcontainer_path.exists():
        console.print("[red]Error:[/] No .devcontainer/ found. Run `csb init` first.")
        raise typer.Exit(1)

    # Load config
    import json
    csb_json_path = devcontainer_path / "csb.json"
    if csb_json_path.exists():
        csb_config = json.loads(csb_json_path.read_text())
        config = ClaudeContextConfig.from_dict(csb_config.get("claude_context", {}))
    else:
        config = ClaudeContextConfig()
        csb_config = {}

    ctx = ClaudeContext(project_path)

    with console.status("[bold blue]Discovering Claude context..."):
        copied = ctx.sync(config)

    if copied:
        console.print(f"\n[green]Synced {len(copied)} items:[/]")
        for dest, source in copied.items():
            console.print(f"  [dim]{source}[/] → [cyan]{dest}[/]")

        # Update csb.json with sources
        csb_config["claude_context"] = config.to_dict()
        csb_config["claude_context_sources"] = copied
        csb_json_path.write_text(json.dumps(csb_config, indent=2))

        # Check if container is running
        dc = DevContainer(project_path)
        if dc.get_container_id():
            console.print("\n[yellow]Container is running.[/] Run [cyan]csb claude refresh[/] to apply changes.")
        else:
            console.print("\n[dim]Changes will be applied on next `csb start`[/]")
    else:
        console.print("\n[dim]No parent Claude context found to sync.[/]")
        # Only mention global context if it exists and is enabled
        global_claude = Path.home() / ".claude"
        if config.include_global and global_claude.exists() and any(global_claude.iterdir()):
            console.print("[dim]Your global ~/.claude/ context is already mounted automatically.[/]")


@claude_app.command("refresh")
@handle_csb_errors
def refresh_context(
    path: Path = typer.Argument(
        Path("."),
        help="Project directory",
    ),
):
    """Refresh Claude context in the container.

    This command:
    1. Re-syncs context from source directories (like `csb claude sync`)
    2. If container is running, runs the setup script inside it

    Use this when you've updated CLAUDE.md, skills, agents, or commands
    in parent directories and want the container to pick up changes.
    """
    project_path = path.resolve()
    devcontainer_path = project_path / ".devcontainer"

    if not devcontainer_path.exists():
        console.print("[red]Error:[/] No .devcontainer/ found. Run `csb init` first.")
        raise typer.Exit(1)

    # Load config
    import json
    csb_json_path = devcontainer_path / "csb.json"
    if csb_json_path.exists():
        csb_config = json.loads(csb_json_path.read_text())
        config = ClaudeContextConfig.from_dict(csb_config.get("claude_context", {}))
    else:
        config = ClaudeContextConfig()
        csb_config = {}

    ctx = ClaudeContext(project_path)
    dc = DevContainer(project_path)

    # Step 1: Re-sync from sources
    with console.status("[bold blue]Syncing Claude context..."):
        copied = ctx.sync(config)

    if copied:
        console.print(f"[green]✓[/] Synced {len(copied)} items from sources")

        # Update csb.json
        csb_config["claude_context"] = config.to_dict()
        csb_config["claude_context_sources"] = copied
        csb_json_path.write_text(json.dumps(csb_config, indent=2))
    else:
        console.print("[dim]No parent context to sync[/]")

    # Step 2: If container is running, refresh inside it
    container_id = dc.get_container_id()
    if container_id:
        with console.status("[bold blue]Refreshing context in container..."):
            success = ctx.refresh_in_container(container_id)

        if success:
            console.print("[green]✓[/] Context refreshed in running container")
            console.print()
            console.print("[dim]CLAUDE.md changes will be picked up on your next prompt.[/]")
            console.print("[dim]Skills/agents/commands are symlinked and available immediately.[/]")
        else:
            console.print("[yellow]![/] Could not refresh in container - try restarting with `csb start`")
    else:
        console.print("[dim]Container not running - context will be set up on next start[/]")


@claude_app.command("add")
@handle_csb_errors
def add_source(
    source: str = typer.Argument(
        ...,
        help="Path to Claude context source (file or directory)",
    ),
    path: Path = typer.Option(
        Path("."),
        "--project",
        "-p",
        help="Project directory",
    ),
):
    """Add an extra Claude context source.

    Add a CLAUDE.md file, skills directory, or other Claude context
    from anywhere on your system.

    Examples:
        csb claude add ~/my-org/CLAUDE.md
        csb claude add ~/my-org/.claude/skills/
        csb claude add /path/to/shared-agents/
    """
    project_path = path.resolve()
    devcontainer_path = project_path / ".devcontainer"

    if not devcontainer_path.exists():
        console.print("[red]Error:[/] No .devcontainer/ found. Run `csb init` first.")
        raise typer.Exit(1)

    source_path = Path(source).expanduser().resolve()
    if not source_path.exists():
        console.print(f"[red]Error:[/] Path not found: {source_path}")
        raise typer.Exit(1)

    # Load and update config
    import json
    csb_json_path = devcontainer_path / "csb.json"
    if csb_json_path.exists():
        csb_config = json.loads(csb_json_path.read_text())
    else:
        csb_config = {}

    claude_context = csb_config.get("claude_context", {})
    extra = claude_context.get("extra", [])

    source_str = str(source_path)
    if source_str in extra:
        console.print(f"[yellow]Already added:[/] {source_path}")
        return

    extra.append(source_str)
    claude_context["extra"] = extra
    csb_config["claude_context"] = claude_context
    csb_json_path.write_text(json.dumps(csb_config, indent=2))

    console.print(f"[green]Added:[/] {source_path}")
    console.print("[dim]Run `csb claude sync` to copy into container context[/]")


@claude_app.command("remove")
@handle_csb_errors
def remove_source(
    source: str = typer.Argument(
        ...,
        help="Path to remove from extra sources",
    ),
    path: Path = typer.Option(
        Path("."),
        "--project",
        "-p",
        help="Project directory",
    ),
):
    """Remove an extra Claude context source."""
    project_path = path.resolve()
    devcontainer_path = project_path / ".devcontainer"
    csb_json_path = devcontainer_path / "csb.json"

    if not csb_json_path.exists():
        console.print("[red]Error:[/] No csb.json found.")
        raise typer.Exit(1)

    import json
    csb_config = json.loads(csb_json_path.read_text())
    claude_context = csb_config.get("claude_context", {})
    extra = claude_context.get("extra", [])

    source_path = Path(source).expanduser().resolve()
    source_str = str(source_path)

    if source_str not in extra:
        console.print(f"[yellow]Not found in extra sources:[/] {source}")
        return

    extra.remove(source_str)
    claude_context["extra"] = extra
    csb_config["claude_context"] = claude_context
    csb_json_path.write_text(json.dumps(csb_config, indent=2))

    console.print(f"[green]Removed:[/] {source_path}")
    console.print("[dim]Run `csb claude sync` to update container context[/]")
