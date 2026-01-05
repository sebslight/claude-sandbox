"""Cleanup subcommand group for csb CLI."""

import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.tree import Tree
from rich.prompt import Confirm
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich import box
from pathlib import Path

from csb.cleanup import (
    generate_cleanup_report,
    get_all_csb_containers,
    get_all_csb_images,
    get_dangling_images,
    find_orphaned_devcontainers,
    remove_container,
    remove_image,
    remove_orphaned_directory,
    prune_dangling_images,
    get_docker_disk_usage,
    CleanupReport,
)
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


cleanup_app = typer.Typer(
    name="cleanup",
    help="Clean up unused containers, images, and orphaned configurations",
    no_args_is_help=False,  # Allow running without subcommand for interactive mode
    invoke_without_command=True,
)


def _render_cleanup_report(report: CleanupReport, include_running: bool = False) -> None:
    """Render the cleanup report with Rich formatting."""
    console.print()

    # Create main tree
    tree = Tree(
        "[bold]CSB Disk Usage Report[/]",
        guide_style="dim",
    )

    # Containers section
    if report.containers:
        containers_branch = tree.add("[bold cyan]Containers[/]")
        for container in report.containers:
            status_color = "green" if container.is_running else "dim"
            removable = "" if container.is_running else " [yellow]← removable[/]"
            containers_branch.add(
                f"[{status_color}]{container.name}[/] ({container.status}) "
                f"[dim]{container.size_human}[/]{removable}"
            )
    else:
        tree.add("[dim]Containers: none found[/]")

    # Images section
    if report.images:
        images_branch = tree.add("[bold cyan]Images[/]")
        for image in report.images:
            in_use_marker = "[green](in use)[/]" if image.in_use else "[yellow]← removable[/]"
            images_branch.add(
                f"{image.full_name} [dim]{image.size_human}[/] {in_use_marker}"
            )
    else:
        tree.add("[dim]Images: none found[/]")

    # Dangling images section
    if report.dangling_images:
        dangling_branch = tree.add("[bold cyan]Dangling Images[/]")
        total_dangling = sum(d.size_bytes for d in report.dangling_images)
        dangling_branch.add(
            f"[dim]{len(report.dangling_images)} dangling image(s)[/] "
            f"[dim]{report.dangling_images[0].size_human if len(report.dangling_images) == 1 else _format_bytes(total_dangling)}[/] "
            f"[yellow]← removable[/]"
        )

    # Orphaned directories section
    if report.orphaned_dirs:
        orphans_branch = tree.add("[bold cyan]Orphaned .devcontainer/ dirs[/]")
        for orphan in report.orphaned_dirs:
            orphans_branch.add(
                f"[dim]{orphan.project_path}[/] "
                f"[dim]{orphan.size_human}[/] [yellow]← removable[/]"
            )
    else:
        tree.add("[dim]Orphaned directories: none found[/]")

    console.print(tree)
    console.print()

    # Summary panel
    if report.has_reclaimable:
        summary = f"[bold green]Total reclaimable: {report.total_reclaimable_human}[/]"
        console.print(Panel(summary, box=box.ROUNDED, padding=(0, 2)))
    else:
        console.print("[dim]Nothing to clean up.[/]")


def _format_bytes(size_bytes: int) -> str:
    """Format bytes as human-readable string."""
    if size_bytes < 0:
        return "0 B"
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if abs(size_bytes) < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} PB"


@cleanup_app.callback()
@handle_csb_errors
def cleanup_main(
    ctx: typer.Context,
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        "-n",
        help="Show what would be removed without removing anything",
    ),
    all_containers: bool = typer.Option(
        False,
        "--all",
        "-a",
        help="Include running containers (requires confirmation)",
    ),
    images_only: bool = typer.Option(
        False,
        "--images",
        "-i",
        help="Only clean up images",
    ),
    containers_only: bool = typer.Option(
        False,
        "--containers",
        "-c",
        help="Only clean up containers",
    ),
    orphans_only: bool = typer.Option(
        False,
        "--orphans",
        "-o",
        help="Only clean up orphaned .devcontainer/ directories",
    ),
    dangling_only: bool = typer.Option(
        False,
        "--dangling",
        "-d",
        help="Only clean up dangling images",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="Skip confirmation prompts",
    ),
    search_path: list[Path] = typer.Option(
        None,
        "--search-path",
        "-s",
        help="Additional paths to search for orphaned devcontainers",
    ),
):
    """Clean up unused CSB containers, images, and orphaned configurations.

    By default, shows a report and prompts for confirmation before removing
    stopped containers, unused images, and orphaned .devcontainer/ directories.

    Examples:
        csb cleanup                    # Interactive cleanup
        csb cleanup --dry-run          # Show what would be removed
        csb cleanup --force            # Remove without confirmation
        csb cleanup --containers       # Only remove stopped containers
        csb cleanup --images           # Only remove unused images
        csb cleanup --orphans          # Only remove orphaned directories
        csb cleanup --dangling         # Only remove dangling images
        csb cleanup --all              # Include running containers
    """
    # If a subcommand was invoked, don't run the main cleanup
    if ctx.invoked_subcommand is not None:
        return

    # Determine what to include
    include_all = not any([images_only, containers_only, orphans_only, dangling_only])

    with Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]{task.description}"),
        console=console,
        transient=True,
    ) as progress:
        progress.add_task("Scanning for cleanup targets...", total=None)

        # Generate report based on flags
        report = CleanupReport()

        if include_all or containers_only:
            report.containers = get_all_csb_containers(include_running=all_containers)

        if include_all or images_only:
            report.images = get_all_csb_images()

        if include_all or orphans_only:
            search_paths = list(search_path) if search_path else None
            report.orphaned_dirs = find_orphaned_devcontainers(search_paths=search_paths)

        if include_all or dangling_only:
            report.dangling_images = get_dangling_images()

    # Display report
    _render_cleanup_report(report, include_running=all_containers)

    if not report.has_reclaimable:
        raise typer.Exit(0)

    if dry_run:
        console.print("\n[dim]Dry run - no changes made.[/]")
        raise typer.Exit(0)

    # Confirm before proceeding
    if not force:
        if all_containers and any(c.is_running for c in report.containers):
            console.print(
                "\n[yellow]Warning:[/] This will stop and remove running containers!"
            )

        if not Confirm.ask("\nProceed with cleanup?", default=False):
            console.print("[dim]Cancelled.[/]")
            raise typer.Exit(0)

    console.print()

    # Perform cleanup
    removed_count = 0
    error_count = 0

    # Remove containers
    if include_all or containers_only:
        for container in report.containers:
            if container.is_running and not all_containers:
                continue

            with console.status(f"Removing container {container.name[:30]}..."):
                success, message = remove_container(
                    container.id, force=container.is_running
                )

            if success:
                console.print(f"[green]✓[/] Removed container: {container.name}")
                removed_count += 1
            else:
                console.print(f"[red]✗[/] Failed to remove {container.name}: {message}")
                error_count += 1

    # Remove images
    if include_all or images_only:
        for image in report.images:
            if image.in_use:
                continue

            with console.status(f"Removing image {image.full_name[:40]}..."):
                success, message = remove_image(image.id)

            if success:
                console.print(f"[green]✓[/] Removed image: {image.full_name}")
                removed_count += 1
            else:
                console.print(f"[red]✗[/] Failed to remove {image.full_name}: {message}")
                error_count += 1

    # Remove dangling images
    if include_all or dangling_only:
        if report.dangling_images:
            with console.status("Pruning dangling images..."):
                success, message, reclaimed = prune_dangling_images()

            if success:
                console.print(f"[green]✓[/] {message}")
                removed_count += 1
            else:
                console.print(f"[red]✗[/] {message}")
                error_count += 1

    # Remove orphaned directories
    if include_all or orphans_only:
        for orphan in report.orphaned_dirs:
            with console.status(f"Removing {orphan.path}..."):
                success, message = remove_orphaned_directory(orphan.path)

            if success:
                console.print(f"[green]✓[/] Removed: {orphan.project_path}/.devcontainer/")
                removed_count += 1
            else:
                console.print(f"[red]✗[/] {message}")
                error_count += 1

    # Summary
    console.print()
    if error_count == 0:
        console.print(
            f"[green]Cleanup complete![/] Removed {removed_count} item(s), "
            f"reclaimed ~{report.total_reclaimable_human}"
        )
    else:
        console.print(
            f"[yellow]Cleanup finished with {error_count} error(s).[/] "
            f"Removed {removed_count} item(s)."
        )


@cleanup_app.command("report")
@handle_csb_errors
def report(
    all_containers: bool = typer.Option(
        False,
        "--all",
        "-a",
        help="Include running containers in report",
    ),
    search_path: list[Path] = typer.Option(
        None,
        "--search-path",
        "-s",
        help="Additional paths to search for orphaned devcontainers",
    ),
    json_output: bool = typer.Option(
        False,
        "--json",
        "-j",
        help="Output as JSON",
    ),
):
    """Show detailed disk usage report without removing anything.

    This is equivalent to `csb cleanup --dry-run` but with more detail.

    Examples:
        csb cleanup report              # Show full report
        csb cleanup report --all        # Include running containers
        csb cleanup report --json       # Output as JSON for scripting
    """
    with Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]{task.description}"),
        console=console,
        transient=True,
    ) as progress:
        progress.add_task("Analyzing disk usage...", total=None)

        search_paths = list(search_path) if search_path else None
        report = generate_cleanup_report(
            include_running=all_containers,
            search_paths=search_paths,
        )

    if json_output:
        import json

        output = {
            "containers": [
                {
                    "id": c.id[:12],
                    "name": c.name,
                    "status": c.status,
                    "size_bytes": c.size_bytes,
                    "size_human": c.size_human,
                    "project_path": str(c.project_path),
                    "removable": c.is_removable,
                }
                for c in report.containers
            ],
            "images": [
                {
                    "id": i.id[:12],
                    "name": i.full_name,
                    "size_bytes": i.size_bytes,
                    "size_human": i.size_human,
                    "in_use": i.in_use,
                }
                for i in report.images
            ],
            "dangling_images": [
                {
                    "id": d.id[:12],
                    "size_bytes": d.size_bytes,
                    "size_human": d.size_human,
                }
                for d in report.dangling_images
            ],
            "orphaned_directories": [
                {
                    "path": str(o.path),
                    "project_path": str(o.project_path),
                    "size_bytes": o.size_bytes,
                    "size_human": o.size_human,
                }
                for o in report.orphaned_dirs
            ],
            "summary": {
                "total_reclaimable_bytes": report.total_reclaimable_bytes,
                "total_reclaimable_human": report.total_reclaimable_human,
            },
        }
        console.print_json(json.dumps(output))
    else:
        _render_cleanup_report(report, include_running=all_containers)

        # Show additional Docker disk usage info
        console.print()
        docker_usage = get_docker_disk_usage()
        if any(docker_usage.values()):
            usage_table = Table(
                title="Overall Docker Disk Usage",
                box=box.SIMPLE,
                show_header=True,
                header_style="bold",
            )
            usage_table.add_column("Type")
            usage_table.add_column("Size", justify="right")

            for type_name, size_bytes in docker_usage.items():
                if size_bytes > 0:
                    usage_table.add_row(
                        type_name.replace("_", " ").title(),
                        _format_bytes(size_bytes),
                    )

            console.print(usage_table)


@cleanup_app.command("containers")
@handle_csb_errors
def cleanup_containers(
    all_containers: bool = typer.Option(
        False,
        "--all",
        "-a",
        help="Include running containers (will be stopped first)",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="Skip confirmation prompts",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        "-n",
        help="Show what would be removed",
    ),
):
    """Remove stopped CSB containers.

    Examples:
        csb cleanup containers           # Remove stopped containers
        csb cleanup containers --all     # Remove all containers (including running)
        csb cleanup containers --dry-run # Show what would be removed
    """
    containers = get_all_csb_containers(include_running=all_containers)

    if not containers:
        console.print("[dim]No CSB containers found.[/]")
        raise typer.Exit(0)

    # Filter to removable only (unless --all)
    if not all_containers:
        containers = [c for c in containers if c.is_removable]

    if not containers:
        console.print("[dim]No stopped containers to remove.[/]")
        raise typer.Exit(0)

    # Display what we found
    console.print("\n[bold]Containers to remove:[/]\n")
    table = Table(show_header=True, header_style="bold", box=box.SIMPLE)
    table.add_column("Name")
    table.add_column("Status")
    table.add_column("Size", justify="right")
    table.add_column("Project")

    total_size = 0
    for c in containers:
        status_color = "green" if c.is_running else "dim"
        table.add_row(
            c.name[:40],
            f"[{status_color}]{c.status}[/]",
            c.size_human,
            str(c.project_path)[:50],
        )
        total_size += c.size_bytes

    console.print(table)
    console.print(f"\n[bold]Total:[/] {_format_bytes(total_size)}")

    if dry_run:
        console.print("\n[dim]Dry run - no changes made.[/]")
        raise typer.Exit(0)

    if not force:
        if all_containers and any(c.is_running for c in containers):
            console.print(
                "\n[yellow]Warning:[/] Running containers will be forcefully stopped!"
            )
        if not Confirm.ask("\nRemove these containers?", default=False):
            console.print("[dim]Cancelled.[/]")
            raise typer.Exit(0)

    console.print()
    for container in containers:
        success, message = remove_container(container.id, force=container.is_running)
        if success:
            console.print(f"[green]✓[/] {container.name}")
        else:
            console.print(f"[red]✗[/] {container.name}: {message}")

    console.print(f"\n[green]Done![/] Reclaimed ~{_format_bytes(total_size)}")


@cleanup_app.command("images")
@handle_csb_errors
def cleanup_images(
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="Skip confirmation prompts",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        "-n",
        help="Show what would be removed",
    ),
    include_dangling: bool = typer.Option(
        True,
        "--dangling/--no-dangling",
        help="Include dangling images",
    ),
):
    """Remove unused CSB images.

    Only removes images not currently in use by any container.

    Examples:
        csb cleanup images              # Remove unused images
        csb cleanup images --dry-run    # Show what would be removed
        csb cleanup images --no-dangling # Skip dangling images
    """
    images = get_all_csb_images()
    dangling = get_dangling_images() if include_dangling else []

    # Filter to unused only
    unused_images = [i for i in images if not i.in_use]

    if not unused_images and not dangling:
        console.print("[dim]No unused images to remove.[/]")
        raise typer.Exit(0)

    total_size = 0

    # Display what we found
    if unused_images:
        console.print("\n[bold]CSB images to remove:[/]\n")
        table = Table(show_header=True, header_style="bold", box=box.SIMPLE)
        table.add_column("Image")
        table.add_column("Size", justify="right")
        table.add_column("Created")

        for img in unused_images:
            table.add_row(img.full_name, img.size_human, img.created[:19])
            total_size += img.size_bytes

        console.print(table)

    if dangling:
        dangling_size = sum(d.size_bytes for d in dangling)
        total_size += dangling_size
        console.print(
            f"\n[bold]Dangling images:[/] {len(dangling)} ({_format_bytes(dangling_size)})"
        )

    console.print(f"\n[bold]Total:[/] {_format_bytes(total_size)}")

    if dry_run:
        console.print("\n[dim]Dry run - no changes made.[/]")
        raise typer.Exit(0)

    if not force:
        if not Confirm.ask("\nRemove these images?", default=False):
            console.print("[dim]Cancelled.[/]")
            raise typer.Exit(0)

    console.print()

    for img in unused_images:
        success, message = remove_image(img.id)
        if success:
            console.print(f"[green]✓[/] {img.full_name}")
        else:
            console.print(f"[red]✗[/] {img.full_name}: {message}")

    if dangling:
        success, message, _ = prune_dangling_images()
        if success:
            console.print("[green]✓[/] Pruned dangling images")
        else:
            console.print(f"[red]✗[/] {message}")

    console.print(f"\n[green]Done![/] Reclaimed ~{_format_bytes(total_size)}")


@cleanup_app.command("orphans")
@handle_csb_errors
def cleanup_orphans(
    search_path: list[Path] = typer.Option(
        None,
        "--search-path",
        "-s",
        help="Additional paths to search for orphaned devcontainers",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="Skip confirmation prompts",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        "-n",
        help="Show what would be removed",
    ),
):
    """Remove orphaned .devcontainer/ directories.

    Finds CSB-created .devcontainer/ directories that don't have
    a corresponding container and offers to remove them.

    Examples:
        csb cleanup orphans                    # Find and remove orphans
        csb cleanup orphans --dry-run          # Show what would be removed
        csb cleanup orphans -s ~/extra/path    # Search additional paths
    """
    with Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]{task.description}"),
        console=console,
        transient=True,
    ) as progress:
        progress.add_task("Scanning for orphaned directories...", total=None)
        search_paths = list(search_path) if search_path else None
        orphans = find_orphaned_devcontainers(search_paths=search_paths)

    if not orphans:
        console.print("[dim]No orphaned .devcontainer/ directories found.[/]")
        raise typer.Exit(0)

    # Display what we found
    console.print("\n[bold]Orphaned .devcontainer/ directories:[/]\n")
    table = Table(show_header=True, header_style="bold", box=box.SIMPLE)
    table.add_column("Project Path")
    table.add_column("Size", justify="right")

    total_size = 0
    for orphan in orphans:
        table.add_row(str(orphan.project_path), orphan.size_human)
        total_size += orphan.size_bytes

    console.print(table)
    console.print(f"\n[bold]Total:[/] {_format_bytes(total_size)}")

    if dry_run:
        console.print("\n[dim]Dry run - no changes made.[/]")
        raise typer.Exit(0)

    if not force:
        console.print(
            "\n[yellow]Warning:[/] This will permanently delete these directories!"
        )
        if not Confirm.ask("\nRemove these directories?", default=False):
            console.print("[dim]Cancelled.[/]")
            raise typer.Exit(0)

    console.print()

    for orphan in orphans:
        success, message = remove_orphaned_directory(orphan.path)
        if success:
            console.print(f"[green]✓[/] {orphan.project_path}")
        else:
            console.print(f"[red]✗[/] {orphan.project_path}: {message}")

    console.print(f"\n[green]Done![/] Reclaimed ~{_format_bytes(total_size)}")


@cleanup_app.command("dangling")
@handle_csb_errors
def cleanup_dangling(
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="Skip confirmation prompts",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        "-n",
        help="Show what would be removed",
    ),
):
    """Remove dangling Docker images.

    Dangling images are intermediate build layers that are no longer
    referenced by any tagged image.

    Examples:
        csb cleanup dangling              # Remove dangling images
        csb cleanup dangling --dry-run    # Show what would be removed
    """
    dangling = get_dangling_images()

    if not dangling:
        console.print("[dim]No dangling images found.[/]")
        raise typer.Exit(0)

    total_size = sum(d.size_bytes for d in dangling)

    console.print(f"\n[bold]Dangling images:[/] {len(dangling)}")
    console.print(f"[bold]Total size:[/] {_format_bytes(total_size)}")

    if dry_run:
        console.print("\n[dim]Dry run - no changes made.[/]")
        raise typer.Exit(0)

    if not force:
        if not Confirm.ask("\nRemove dangling images?", default=True):
            console.print("[dim]Cancelled.[/]")
            raise typer.Exit(0)

    success, message, reclaimed = prune_dangling_images()

    if success:
        console.print(f"\n[green]✓[/] {message}")
        console.print(f"[green]Done![/] Reclaimed ~{_format_bytes(reclaimed)}")
    else:
        console.print(f"\n[red]✗[/] {message}")
        raise typer.Exit(1)
