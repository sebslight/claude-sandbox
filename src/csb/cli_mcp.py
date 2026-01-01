"""MCP subcommand group for csb CLI."""

import typer
from rich.console import Console
from rich.table import Table
from pathlib import Path

from csb.devcontainer import DevContainer
from csb.mcp import MCP_SERVERS
from csb.exceptions import CsbError

console = Console()


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


mcp_app = typer.Typer(
    name="mcp",
    help="Manage MCP servers in the sandbox",
    no_args_is_help=True,
)


@mcp_app.command("add")
@handle_csb_errors
def add_server(
    server: str = typer.Argument(
        ...,
        help="MCP server name to add",
    ),
    path: Path = typer.Option(
        Path("."),
        "--path",
        "-p",
        help="Project directory",
    ),
):
    """Add a built-in MCP server to the sandbox.

    Examples:
        csb mcp add github
        csb mcp add firecrawl
    """
    project_path = path.resolve()
    devcontainer_path = project_path / ".devcontainer"

    if not devcontainer_path.exists():
        console.print("[red]Error:[/] No .devcontainer/ found. Run `csb init` first.")
        raise typer.Exit(1)

    if server not in MCP_SERVERS:
        console.print(f"[red]Error:[/] Unknown MCP server: {server}")
        console.print(f"[dim]Available: {', '.join(MCP_SERVERS.keys())}[/]")
        console.print("[dim]For custom servers, use `csb mcp add-custom`[/]")
        raise typer.Exit(1)

    dc = DevContainer(project_path)
    added = dc.add_mcp_server(server)

    if added:
        server_info = MCP_SERVERS[server]
        console.print(f"[green]Added MCP server:[/] {server}")
        if server_info.get("required_env"):
            console.print(
                f"[yellow]Required env vars:[/] {', '.join(server_info['required_env'])}"
            )
        console.print("[dim]Run `csb start --rebuild` to apply changes[/]")
    else:
        console.print(f"[yellow]Server already configured:[/] {server}")


@mcp_app.command("add-custom")
@handle_csb_errors
def add_custom_server(
    name: str = typer.Argument(
        ...,
        help="Name for the custom MCP server",
    ),
    command: str = typer.Option(
        ...,
        "--command",
        "-c",
        help="Command to run the server (e.g., 'npx', 'node', 'python')",
    ),
    args: str = typer.Option(
        "",
        "--args",
        "-a",
        help="Comma-separated arguments for the command",
    ),
    env: str = typer.Option(
        "",
        "--env",
        "-e",
        help="Comma-separated env vars (e.g., 'API_KEY,SECRET_TOKEN')",
    ),
    path: Path = typer.Option(
        Path("."),
        "--path",
        "-p",
        help="Project directory",
    ),
):
    """Add a custom MCP server to the sandbox.

    Examples:
        csb mcp add-custom myserver -c npx -a "-y,my-mcp-server"
        csb mcp add-custom dbserver -c node -a "server.js" -e "DB_URL,DB_PASSWORD"
    """
    project_path = path.resolve()
    devcontainer_path = project_path / ".devcontainer"

    if not devcontainer_path.exists():
        console.print("[red]Error:[/] No .devcontainer/ found. Run `csb init` first.")
        raise typer.Exit(1)

    # Parse args
    args_list = [a.strip() for a in args.split(",") if a.strip()] if args else []

    # Parse env vars
    env_dict = None
    if env:
        env_vars = [e.strip() for e in env.split(",") if e.strip()]
        env_dict = {var: f"${{{var}}}" for var in env_vars}

    dc = DevContainer(project_path)
    added = dc.add_custom_mcp_server(name, command, args_list, env_dict)

    if added:
        console.print(f"[green]Added custom MCP server:[/] {name}")
        console.print(f"  Command: {command} {' '.join(args_list)}")
        if env_dict:
            console.print(
                f"  [yellow]Required env vars:[/] {', '.join(env_dict.keys())}"
            )
        console.print("[dim]Run `csb start --rebuild` to apply changes[/]")
    else:
        console.print(f"[yellow]Server already exists:[/] {name}")


@mcp_app.command("remove")
@handle_csb_errors
def remove_server(
    server: str = typer.Argument(
        ...,
        help="MCP server name to remove",
    ),
    path: Path = typer.Option(
        Path("."),
        "--path",
        "-p",
        help="Project directory",
    ),
):
    """Remove an MCP server from the sandbox.

    Examples:
        csb mcp remove github
        csb mcp remove my-custom-server
    """
    project_path = path.resolve()
    devcontainer_path = project_path / ".devcontainer"

    if not devcontainer_path.exists():
        console.print("[red]Error:[/] No .devcontainer/ found. Run `csb init` first.")
        raise typer.Exit(1)

    dc = DevContainer(project_path)
    removed = dc.remove_mcp_server(server)

    if removed:
        console.print(f"[green]Removed MCP server:[/] {server}")
        console.print("[dim]Run `csb start --rebuild` to apply changes[/]")
    else:
        console.print(f"[yellow]Server not found:[/] {server}")


@mcp_app.command("list")
@handle_csb_errors
def list_servers(
    path: Path = typer.Option(
        Path("."),
        "--path",
        "-p",
        help="Project directory",
    ),
):
    """List available and configured MCP servers.

    Shows all built-in servers and their status (configured or not),
    plus any custom servers that have been added.

    Examples:
        csb mcp list
        csb mcp list --path /path/to/project
    """
    project_path = path.resolve()
    devcontainer_path = project_path / ".devcontainer"

    # Get configured servers if devcontainer exists
    configured_servers = set()
    custom_servers = {}

    if devcontainer_path.exists():
        dc = DevContainer(project_path)
        config = dc.get_csb_config()
        if config:
            configured_servers = set(config.get("mcp_servers", []))
            custom_servers = config.get("custom_mcp_servers", {})

    # Display built-in servers
    console.print("\n[bold]Built-in MCP servers:[/]\n")

    table = Table(show_header=True, header_style="bold")
    table.add_column("Name", style="cyan")
    table.add_column("Status")
    table.add_column("Description")
    table.add_column("Required Env")

    for name, server in MCP_SERVERS.items():
        status = (
            "[green]✓ configured[/]"
            if name in configured_servers
            else "[dim]available[/]"
        )
        env_vars = ", ".join(server.get("required_env", [])) or "-"
        table.add_row(name, status, server["description"], env_vars)

    console.print(table)

    # Display custom servers if any
    if custom_servers:
        console.print("\n[bold]Custom MCP servers:[/]\n")

        custom_table = Table(show_header=True, header_style="bold")
        custom_table.add_column("Name", style="cyan")
        custom_table.add_column("Command")
        custom_table.add_column("Required Env")

        for name, server in custom_servers.items():
            cmd = f"{server['command']} {' '.join(server.get('args', []))}"
            env_vars = ", ".join(server.get("required_env", [])) or "-"
            custom_table.add_row(name, cmd, env_vars)

        console.print(custom_table)

    if not devcontainer_path.exists():
        console.print(
            "\n[dim]No .devcontainer/ found. Run `csb init` to get started.[/]"
        )

    console.print()
