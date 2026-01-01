"""Main CLI entry point for csb."""

import typer
from rich.console import Console, Group
from rich.prompt import Confirm
from rich.live import Live
from rich.spinner import Spinner
from rich.text import Text
from rich.panel import Panel
from pathlib import Path
from collections import deque

from csb.devcontainer import DevContainer, CommandResult
from csb.mcp import MCP_SERVERS
from csb.config import Config
from csb.exceptions import CsbError
from csb.cli_mcp import mcp_app
from csb.cli_claude import claude_app
from csb.claude_context import ClaudeContext, ClaudeContextConfig

console = Console()

# Number of output lines to show in the scrolling window
OUTPUT_WINDOW_LINES = 12


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


app = typer.Typer(
    name="csb",
    help="Claude Sandbox CLI - Run Claude Code in isolated devcontainers",
    no_args_is_help=True,
)

# Register subcommand groups
app.add_typer(mcp_app, name="mcp")
app.add_typer(claude_app, name="claude")


@app.command()
@handle_csb_errors
def init(
    path: Path = typer.Argument(
        Path("."),
        help="Project directory to initialize",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="Overwrite existing .devcontainer/",
    ),
    mcp: str = typer.Option(
        None,
        "--mcp",
        "-m",
        help="Comma-separated list of MCP servers (non-interactive mode)",
    ),
    dockerfile: Path = typer.Option(
        None,
        "--dockerfile",
        "-d",
        help="Path to custom Dockerfile (copied into .devcontainer/)",
    ),
    with_claude_context: bool = typer.Option(
        None,
        "--with-claude-context/--no-claude-context",
        help="Include Claude context from parent directories (CLAUDE.md, skills, agents, commands)",
    ),
):
    """Initialize a new Claude sandbox in the current project.

    Examples:
        csb init                                    # Interactive mode
        csb init --mcp filesystem,github            # Non-interactive mode
        csb init -m firecrawl,notion                # Short form
        csb init --dockerfile ./my-dockerfile       # Custom Dockerfile
        csb init --with-claude-context              # Include parent CLAUDE.md, skills, etc.
    """
    project_path = path.resolve()
    devcontainer_path = project_path / ".devcontainer"

    if devcontainer_path.exists() and not force:
        console.print(
            "[yellow]Warning:[/] .devcontainer/ already exists. Use --force to overwrite."
        )
        raise typer.Exit(1)

    # Validate dockerfile path if provided
    dockerfile_path = None
    if dockerfile:
        dockerfile_path = dockerfile.resolve()
        if not dockerfile_path.exists():
            console.print(f"[red]Error:[/] Dockerfile not found: {dockerfile_path}")
            raise typer.Exit(1)
        if not dockerfile_path.is_file():
            console.print(f"[red]Error:[/] Not a file: {dockerfile_path}")
            raise typer.Exit(1)

    console.print(f"\n[bold]Initializing Claude sandbox in:[/] {project_path}\n")

    # Determine MCP servers - interactive or from --mcp flag
    if mcp:
        # Non-interactive mode: parse comma-separated list
        selected_servers = [s.strip() for s in mcp.split(",") if s.strip()]
        invalid_servers = [s for s in selected_servers if s not in MCP_SERVERS]
        if invalid_servers:
            console.print(f"[red]Error:[/] Unknown MCP servers: {', '.join(invalid_servers)}")
            console.print(f"[dim]Available: {', '.join(MCP_SERVERS.keys())}[/]")
            raise typer.Exit(1)
        console.print(f"[dim]Using MCP servers: {', '.join(selected_servers)}[/]\n")
    else:
        cfg = Config()
        default_list = cfg.get("default_mcp_servers", ["filesystem"])
        if not isinstance(default_list, list):
            default_list = ["filesystem"]
        default_mcp_servers = set(default_list)
        invalid_defaults = [s for s in default_mcp_servers if s not in MCP_SERVERS]
        if invalid_defaults:
            console.print(
                f"[yellow]Warning:[/] Ignoring unknown default MCP servers in config: "
                f"{', '.join(sorted(invalid_defaults))}"
            )
            default_mcp_servers = {s for s in default_mcp_servers if s in MCP_SERVERS}

        # Interactive MCP server selection
        console.print("[bold]Available MCP servers:[/]\n")
        for name, server in MCP_SERVERS.items():
            console.print(f"  [cyan]{name}[/] - {server['description']}")

        console.print()
        selected_servers = []
        for name in MCP_SERVERS:
            if Confirm.ask(
                f"Enable [cyan]{name}[/]?",
                default=name in default_mcp_servers,
            ):
                selected_servers.append(name)

    # Check for required env vars
    console.print("\n[bold]Environment variables:[/]\n")
    env_vars = {}
    for server_name in selected_servers:
        server = MCP_SERVERS[server_name]
        for env_var in server.get("required_env", []):
            if env_var not in env_vars:
                console.print(f"  [yellow]{env_var}[/] required for {server_name}")
                env_vars[env_var] = True

    if env_vars:
        console.print(
            "\n[dim]Make sure these are set in your shell before running `csb start`[/]"
        )

    # Claude context discovery
    claude_context_config = None
    ctx = ClaudeContext(project_path)

    # Check for parent Claude context
    parent_contexts = ctx.discover_parent_contexts()
    global_context = ctx.discover_global_context()

    if parent_contexts or global_context:
        # Determine whether to include Claude context
        if with_claude_context is None and not mcp:
            # Interactive mode - ask user
            console.print("\n[bold]Claude Context Discovery:[/]\n")

            if global_context:
                items = []
                if global_context.claude_md:
                    items.append("CLAUDE.md")
                if global_context.skills_dir:
                    items.append("skills/")
                if global_context.agents_dir:
                    items.append("agents/")
                if global_context.commands_dir:
                    items.append("commands/")
                console.print(f"  [cyan]~/.claude/[/]: {', '.join(items)} [dim](always mounted)[/]")

            if parent_contexts:
                for pctx in parent_contexts:
                    items = []
                    if pctx.claude_md:
                        items.append("CLAUDE.md")
                    if pctx.skills_dir:
                        items.append("skills/")
                    if pctx.agents_dir:
                        items.append("agents/")
                    if pctx.commands_dir:
                        items.append("commands/")
                    if pctx.rules_dir:
                        items.append("rules/")
                    console.print(f"  [yellow]Parent {pctx.relative_depth}:[/] {pctx.source_path}")
                    console.print(f"      Found: {', '.join(items)}")

                console.print()
                with_claude_context = Confirm.ask(
                    "Include parent Claude context in sandbox?",
                    default=True,
                )

        if with_claude_context:
            claude_context_config = ClaudeContextConfig(
                include_global=True,
                auto_discover_parents=True,
            )
            # Sync the contexts
            copied = ctx.sync(claude_context_config)
            if copied:
                console.print(f"\n[green]Synced {len(copied)} Claude context items[/]")

    # Create devcontainer
    dc = DevContainer(project_path)
    if dc.needs_runtime_update():
        console.print("[dim]Updating sandbox config for runtime settings/MCP...[/]")
        dc.update()
    dc.create(selected_servers, dockerfile_path=dockerfile_path, claude_context=claude_context_config)

    console.print(f"\n[green]Created .devcontainer/ with {len(selected_servers)} MCP servers[/]")
    if dockerfile_path:
        console.print(f"[dim]Using custom Dockerfile: {dockerfile_path}[/]")
    if claude_context_config:
        console.print("[dim]Claude context from parent directories included[/]")
    console.print("\nNext steps:")
    console.print("  1. Set required environment variables")
    console.print("  2. Run [cyan]csb start[/] to launch the sandbox")


@app.command()
@handle_csb_errors
def start(
    path: Path = typer.Argument(
        Path("."),
        help="Project directory",
    ),
    rebuild: bool = typer.Option(
        False,
        "--rebuild",
        "-r",
        help="Rebuild the container (removes existing container first)",
    ),
    no_cache: bool = typer.Option(
        False,
        "--no-cache",
        help="Force full image rebuild without using Docker cache (implies --rebuild)",
    ),
):
    """Start the Claude sandbox and open Claude Code.

    Examples:
        csb start                      # Start or resume container
        csb start --rebuild            # Remove container and rebuild
        csb start --rebuild --no-cache # Full rebuild, no Docker cache
    """
    project_path = path.resolve()
    devcontainer_path = project_path / ".devcontainer"

    if not devcontainer_path.exists():
        console.print("[red]Error:[/] No .devcontainer/ found. Run `csb init` first.")
        raise typer.Exit(1)

    # --no-cache implies --rebuild
    if no_cache:
        rebuild = True

    dc = DevContainer(project_path)

    if no_cache:
        status_text = "Rebuilding container (no cache)..."
    elif rebuild:
        status_text = "Rebuilding container..."
    else:
        status_text = "Starting container..."

    # Use scrolling output window with spinner
    output_lines = deque(maxlen=OUTPUT_WINDOW_LINES)
    all_output = []
    result = None

    def make_display():
        spinner = Spinner("dots", text=Text(f" {status_text}", style="bold blue"))
        if output_lines:
            output_text = Text("\n".join(output_lines), style="dim")
            panel = Panel(output_text, title="Build Output", border_style="dim", padding=(0, 1))
            return Group(spinner, panel)
        return spinner

    with Live(make_display(), console=console, refresh_per_second=10) as live:
        for item in dc.up_with_output(rebuild=rebuild, no_cache=no_cache):
            if isinstance(item, CommandResult):
                result = item
            else:
                # It's a line of output
                output_lines.append(item)
                all_output.append(item)
                live.update(make_display())

    if not result or not result.success:
        console.print("\n[red]Error starting container[/]")
        if all_output:
            console.print(Panel(
                "\n".join(all_output[-30:]),  # Show last 30 lines on error
                title="Build Output",
                border_style="red",
            ))
        raise typer.Exit(1)

    console.print("[green]Container running![/]")
    console.print("\n[bold]Launching Claude Code...[/]\n")

    # Exec into container and run Claude
    dc.exec_claude()


@app.command()
@handle_csb_errors
def stop(
    path: Path = typer.Argument(
        Path("."),
        help="Project directory",
    ),
):
    """Stop the running Claude sandbox."""
    project_path = path.resolve()
    dc = DevContainer(project_path)

    with console.status("[bold blue]Stopping container..."):
        result = dc.down()

    if result.success:
        console.print("[green]Container stopped.[/]")
    else:
        console.print(f"[red]Error:[/] {result.error}")
        raise typer.Exit(1)


@app.command()
@handle_csb_errors
def remove(
    path: Path = typer.Argument(
        Path("."),
        help="Project directory",
    ),
    image: bool = typer.Option(
        False,
        "--image",
        "-i",
        help="Also remove the Docker image",
    ),
    all: bool = typer.Option(
        False,
        "--all",
        "-a",
        help="Remove container, image, AND .devcontainer/ directory",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="Skip confirmation prompts",
    ),
):
    """Remove the sandbox container (and optionally more).

    By default, only removes the container. Use flags for more aggressive cleanup:
    - --image: Also removes the Docker image
    - --all: Removes container, image, and .devcontainer/ directory

    Examples:
        csb remove                # Remove container only
        csb remove --image        # Remove container and image
        csb remove --all          # Full cleanup (container + image + configs)
        csb remove --all --force  # Full cleanup without confirmation
    """
    project_path = path.resolve()
    devcontainer_path = project_path / ".devcontainer"

    dc = DevContainer(project_path)

    # Determine what we're removing
    remove_image = image or all
    remove_configs = all

    # Confirm if removing configs (destructive)
    if remove_configs and not force:
        if not Confirm.ask(
            "[yellow]This will delete .devcontainer/ and all configuration. Continue?[/]",
            default=False,
        ):
            console.print("[dim]Cancelled.[/]")
            raise typer.Exit(0)

    # Stop container if running
    if dc.is_running():
        with console.status("[bold blue]Stopping container..."):
            dc.down()
        console.print("[green]✓[/] Container stopped")

    # Remove container
    with console.status("[bold blue]Removing container..."):
        result = dc.remove_container()

    if result.success:
        console.print("[green]✓[/] Container removed")
    elif "not found" in result.error.lower() or "no container" in result.error.lower():
        console.print("[dim]✓ No container to remove[/]")
    else:
        console.print(f"[yellow]Warning:[/] {result.error}")

    # Remove image if requested
    if remove_image:
        with console.status("[bold blue]Removing image..."):
            result = dc.remove_image()

        if result.success:
            console.print("[green]✓[/] Image removed")
        elif "not found" in result.error.lower() or "no image" in result.error.lower():
            console.print("[dim]✓ No image to remove[/]")
        else:
            console.print(f"[yellow]Warning:[/] {result.error}")

    # Remove configs if requested
    if remove_configs and devcontainer_path.exists():
        import shutil
        shutil.rmtree(devcontainer_path)
        console.print("[green]✓[/] .devcontainer/ removed")

    console.print("\n[green]Cleanup complete![/]")
    if remove_configs:
        console.print("[dim]Run `csb init` to create a new sandbox.[/]")


@app.command()
@handle_csb_errors
def shell(
    path: Path = typer.Argument(
        Path("."),
        help="Project directory",
    ),
):
    """Open a shell in the running sandbox."""
    project_path = path.resolve()
    dc = DevContainer(project_path)
    dc.exec_shell()


@app.command()
@handle_csb_errors
def logs(
    path: Path = typer.Argument(
        Path("."),
        help="Project directory",
    ),
    follow: bool = typer.Option(
        False,
        "--follow",
        "-f",
        help="Follow log output (like tail -f)",
    ),
    tail: int = typer.Option(
        None,
        "--tail",
        "-n",
        help="Number of lines to show from the end",
    ),
):
    """Show container logs.

    Examples:
        csb logs              # Show all logs
        csb logs -f           # Follow log output
        csb logs -n 50        # Show last 50 lines
        csb logs -f -n 100    # Follow, starting from last 100 lines
    """
    project_path = path.resolve()
    dc = DevContainer(project_path)

    if not dc.is_running():
        console.print("[yellow]Container is not running.[/]")
        raise typer.Exit(1)

    dc.logs(follow=follow, tail=tail)


@app.command()
@handle_csb_errors
def status(
    path: Path = typer.Argument(
        Path("."),
        help="Project directory",
    ),
):
    """Show the status of the sandbox."""
    project_path = path.resolve()
    dc = DevContainer(project_path)

    running = dc.is_running()
    devcontainer_exists = (project_path / ".devcontainer").exists()

    console.print(f"\n[bold]Project:[/] {project_path}")
    console.print(f"[bold]Devcontainer:[/] {'[green]configured[/]' if devcontainer_exists else '[yellow]not initialized[/]'}")
    console.print(f"[bold]Container:[/] {'[green]running[/]' if running else '[dim]stopped[/]'}")


@app.command()
@handle_csb_errors
def update(
    path: Path = typer.Argument(
        Path("."),
        help="Project directory",
    ),
):
    """Regenerate config files from saved configuration.

    This command reads the csb.json file and regenerates devcontainer.json
    and .mcp.json based on the saved MCP server selections.

    NOTE: The Dockerfile is NOT regenerated. To update the Dockerfile,
    run `csb init --force` (optionally with --dockerfile).

    Useful when:
    - The csb CLI has been updated with new features
    - You manually edited csb.json and want to apply changes
    """
    project_path = path.resolve()
    devcontainer_path = project_path / ".devcontainer"

    if not devcontainer_path.exists():
        console.print("[red]Error:[/] No .devcontainer/ found. Run `csb init` first.")
        raise typer.Exit(1)

    dc = DevContainer(project_path)
    config = dc.get_csb_config()

    if not config:
        console.print("[red]Error:[/] No csb.json found. This project may have been")
        console.print("initialized with an older version. Run `csb init --force` to recreate.")
        raise typer.Exit(1)

    mcp_servers = config.get("mcp_servers", [])
    custom_servers = config.get("custom_mcp_servers", {})

    console.print(f"\n[bold]Updating sandbox in:[/] {project_path}")
    console.print(f"[dim]MCP servers: {', '.join(mcp_servers)}[/]")
    if custom_servers:
        console.print(f"[dim]Custom servers: {', '.join(custom_servers.keys())}[/]")

    dc.update()

    console.print("\n[green]Devcontainer files regenerated![/]")
    console.print("[dim]Run `csb start --rebuild` to apply changes to running container[/]")


@app.command()
def config():
    """Show global csb configuration."""
    cfg = Config()
    console.print(f"\n[bold]Config location:[/] {cfg.config_path}")
    console.print("\n[bold]Current settings:[/]")
    for key, value in cfg.get_all().items():
        console.print(f"  {key}: {value}")


if __name__ == "__main__":
    app()
