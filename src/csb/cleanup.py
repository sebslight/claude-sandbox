"""Core cleanup functionality for csb.

This module provides utilities for:
- Finding and managing CSB-created containers
- Finding and managing CSB-related Docker images
- Detecting orphaned .devcontainer directories
- Calculating disk usage
"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal


@dataclass
class ContainerInfo:
    """Information about a Docker container."""

    id: str
    name: str
    status: Literal["running", "exited", "paused", "created", "dead", "removing"]
    size_bytes: int
    project_path: Path
    image: str
    created: str

    @property
    def size_human(self) -> str:
        """Return human-readable size."""
        return _format_bytes(self.size_bytes)

    @property
    def is_running(self) -> bool:
        return self.status == "running"

    @property
    def is_removable(self) -> bool:
        return self.status in ("exited", "created", "dead")


@dataclass
class ImageInfo:
    """Information about a Docker image."""

    id: str
    repository: str
    tag: str
    size_bytes: int
    created: str
    in_use: bool = False
    is_dangling: bool = False

    @property
    def size_human(self) -> str:
        """Return human-readable size."""
        return _format_bytes(self.size_bytes)

    @property
    def full_name(self) -> str:
        if self.is_dangling:
            return "<dangling>"
        return f"{self.repository}:{self.tag}"


@dataclass
class OrphanedDevcontainer:
    """Information about an orphaned .devcontainer directory."""

    path: Path
    project_path: Path
    size_bytes: int
    has_csb_json: bool
    reason: str  # "no_container", "project_deleted", etc.

    @property
    def size_human(self) -> str:
        """Return human-readable size."""
        return _format_bytes(self.size_bytes)


@dataclass
class CleanupReport:
    """Complete cleanup report with all removable items."""

    containers: list[ContainerInfo] = field(default_factory=list)
    images: list[ImageInfo] = field(default_factory=list)
    orphaned_dirs: list[OrphanedDevcontainer] = field(default_factory=list)
    dangling_images: list[ImageInfo] = field(default_factory=list)

    @property
    def total_reclaimable_bytes(self) -> int:
        """Total bytes that can be reclaimed."""
        container_bytes = sum(
            c.size_bytes for c in self.containers if c.is_removable
        )
        image_bytes = sum(i.size_bytes for i in self.images if not i.in_use)
        orphan_bytes = sum(o.size_bytes for o in self.orphaned_dirs)
        dangling_bytes = sum(d.size_bytes for d in self.dangling_images)
        return container_bytes + image_bytes + orphan_bytes + dangling_bytes

    @property
    def total_reclaimable_human(self) -> str:
        return _format_bytes(self.total_reclaimable_bytes)

    @property
    def has_reclaimable(self) -> bool:
        """Check if there's anything that can be reclaimed."""
        has_removable_containers = any(c.is_removable for c in self.containers)
        has_unused_images = any(not i.in_use for i in self.images)
        return (
            has_removable_containers
            or has_unused_images
            or bool(self.orphaned_dirs)
            or bool(self.dangling_images)
        )


def _format_bytes(size_bytes: int) -> str:
    """Format bytes as human-readable string."""
    if size_bytes < 0:
        return "0 B"
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if abs(size_bytes) < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} PB"


def _parse_docker_size(size_str: str) -> int:
    """Parse Docker size string (e.g., '1.2GB', '500MB') to bytes."""
    if not size_str or size_str == "0B":
        return 0

    size_str = size_str.strip().upper()

    # Handle "N/A" or empty
    if size_str in ("N/A", "", "0"):
        return 0

    # Extract number and unit
    units = {
        "B": 1,
        "KB": 1024,
        "MB": 1024**2,
        "GB": 1024**3,
        "TB": 1024**4,
        "KIB": 1024,
        "MIB": 1024**2,
        "GIB": 1024**3,
        "TIB": 1024**4,
    }

    for unit, multiplier in sorted(units.items(), key=lambda x: -len(x[0])):
        if size_str.endswith(unit):
            try:
                number = float(size_str[: -len(unit)].strip())
                return int(number * multiplier)
            except ValueError:
                return 0

    # If no unit found, try parsing as bytes
    try:
        return int(float(size_str))
    except ValueError:
        return 0


def _run_docker_command(
    args: list[str], timeout: int = 30
) -> tuple[bool, str, str]:
    """Run a docker command and return (success, stdout, stderr)."""
    try:
        result = subprocess.run(
            ["docker"] + args,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result.returncode == 0, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return False, "", "Command timed out"
    except FileNotFoundError:
        return False, "", "Docker not found"
    except Exception as e:
        return False, "", str(e)


def _get_directory_size(path: Path) -> int:
    """Calculate total size of a directory in bytes."""
    total = 0
    try:
        for entry in path.rglob("*"):
            if entry.is_file() and not entry.is_symlink():
                try:
                    total += entry.stat().st_size
                except (OSError, PermissionError):
                    pass
    except (OSError, PermissionError):
        pass
    return total


def _is_csb_project(project_path: Path) -> bool:
    """Check if a project path is a CSB-managed project.

    A project is CSB-managed if it has a .devcontainer/csb.json file.
    """
    csb_json = project_path / ".devcontainer" / "csb.json"
    return csb_json.exists()


def get_all_csb_containers(
    include_running: bool = False,
) -> list[ContainerInfo]:
    """Find all containers created by CSB.

    Only returns containers for projects that have a .devcontainer/csb.json file,
    which is CSB's marker file. Other devcontainer-created containers are ignored.

    Args:
        include_running: If True, include running containers in results.

    Returns:
        List of ContainerInfo objects for CSB-managed containers.
    """
    containers = []

    # Get all containers with devcontainer label
    # Format: ID|Name|Status|Image|CreatedAt|LocalFolder
    format_str = "{{.ID}}|{{.Names}}|{{.Status}}|{{.Image}}|{{.CreatedAt}}|{{.Label \"devcontainer.local_folder\"}}"

    success, stdout, _ = _run_docker_command(
        ["ps", "-a", "--format", format_str, "--no-trunc"]
    )

    if not success or not stdout.strip():
        return containers

    for line in stdout.strip().split("\n"):
        if not line:
            continue

        parts = line.split("|")
        if len(parts) < 6:
            continue

        container_id, name, status_str, image, created, local_folder = parts[:6]

        # Skip containers without devcontainer label
        if not local_folder:
            continue

        project_path = Path(local_folder)

        # Skip containers that aren't CSB-managed (no csb.json)
        if not _is_csb_project(project_path):
            continue

        # Parse status (e.g., "Up 2 hours" -> "running", "Exited (0) 3 days ago" -> "exited")
        status_lower = status_str.lower()
        if "up" in status_lower:
            status = "running"
        elif "exited" in status_lower:
            status = "exited"
        elif "paused" in status_lower:
            status = "paused"
        elif "created" in status_lower:
            status = "created"
        elif "dead" in status_lower:
            status = "dead"
        elif "removing" in status_lower:
            status = "removing"
        else:
            status = "exited"

        # Skip running containers unless requested
        if status == "running" and not include_running:
            continue

        # Get container size
        size_bytes = _get_container_size(container_id)

        containers.append(
            ContainerInfo(
                id=container_id,
                name=name,
                status=status,
                size_bytes=size_bytes,
                project_path=project_path,
                image=image,
                created=created,
            )
        )

    return containers


def _get_container_size(container_id: str) -> int:
    """Get the disk size of a container."""
    # Use docker inspect to get size
    success, stdout, _ = _run_docker_command(
        ["inspect", container_id, "--format", "{{.SizeRw}}"]
    )

    if success and stdout.strip():
        try:
            return int(stdout.strip())
        except ValueError:
            pass

    # Fallback: use docker ps --size (slower but more reliable)
    success, stdout, _ = _run_docker_command(
        [
            "ps",
            "-a",
            "--filter",
            f"id={container_id}",
            "--format",
            "{{.Size}}",
            "--size",
        ]
    )

    if success and stdout.strip():
        # Format is like "0B (virtual 1.2GB)" - we want the first part
        size_str = stdout.strip().split()[0] if stdout.strip() else "0B"
        return _parse_docker_size(size_str)

    return 0


def _get_csb_project_folder_names() -> set[str]:
    """Get folder names of all CSB-managed projects with containers.

    Returns folder names (not full paths) for projects that have csb.json.
    Used to match against image names (vsc-{folder_name}-{hash}).
    """
    folder_names = set()

    # Get all containers with devcontainer label
    format_str = "{{.Label \"devcontainer.local_folder\"}}"
    success, stdout, _ = _run_docker_command(
        ["ps", "-a", "--format", format_str]
    )

    if success and stdout.strip():
        for line in stdout.strip().split("\n"):
            if not line:
                continue
            project_path = Path(line)
            if _is_csb_project(project_path):
                folder_names.add(project_path.name)

    return folder_names


def get_all_csb_images() -> list[ImageInfo]:
    """Find all Docker images created by CSB.

    Only returns images for CSB-managed projects (those with csb.json).
    Images are matched by folder name pattern: vsc-{folder_name}-{hash}.

    Returns:
        List of ImageInfo objects for CSB-related images.
    """
    images = []

    # Devcontainer images follow pattern: vsc-{project_name}-{hash}
    # Format: ID|Repository|Tag|Size|CreatedAt
    success, stdout, _ = _run_docker_command(
        [
            "images",
            "--format",
            "{{.ID}}|{{.Repository}}|{{.Tag}}|{{.Size}}|{{.CreatedAt}}",
            "--no-trunc",
        ]
    )

    if not success or not stdout.strip():
        return images

    # Get list of images currently in use by containers
    in_use_images = _get_images_in_use()

    # Get folder names of CSB projects to filter images
    csb_folder_names = _get_csb_project_folder_names()

    for line in stdout.strip().split("\n"):
        if not line:
            continue

        parts = line.split("|")
        if len(parts) < 5:
            continue

        image_id, repository, tag, size_str, created = parts[:5]

        # Filter to only vsc-* images (devcontainer pattern)
        if not repository.startswith("vsc-"):
            continue

        # Extract folder name from image name (vsc-{folder_name}-{hash})
        # The folder name is everything between "vsc-" and the last "-{hash}"
        name_part = repository[4:]  # Remove "vsc-" prefix
        # The hash is typically 64 hex chars at the end after a dash
        # Find the folder name by removing the hash suffix
        folder_name = None
        for csb_folder in csb_folder_names:
            if name_part.startswith(csb_folder + "-"):
                folder_name = csb_folder
                break

        # Skip images that don't belong to CSB projects
        if folder_name is None:
            continue

        size_bytes = _parse_docker_size(size_str)
        in_use = image_id in in_use_images or f"{repository}:{tag}" in in_use_images

        images.append(
            ImageInfo(
                id=image_id,
                repository=repository,
                tag=tag,
                size_bytes=size_bytes,
                created=created,
                in_use=in_use,
                is_dangling=False,
            )
        )

    return images


def get_dangling_images() -> list[ImageInfo]:
    """Find dangling images (untagged images from builds).

    Returns:
        List of ImageInfo objects for dangling images.
    """
    images = []

    success, stdout, _ = _run_docker_command(
        [
            "images",
            "--filter",
            "dangling=true",
            "--format",
            "{{.ID}}|{{.Size}}|{{.CreatedAt}}",
            "--no-trunc",
        ]
    )

    if not success or not stdout.strip():
        return images

    for line in stdout.strip().split("\n"):
        if not line:
            continue

        parts = line.split("|")
        if len(parts) < 3:
            continue

        image_id, size_str, created = parts[:3]
        size_bytes = _parse_docker_size(size_str)

        images.append(
            ImageInfo(
                id=image_id,
                repository="<none>",
                tag="<none>",
                size_bytes=size_bytes,
                created=created,
                in_use=False,
                is_dangling=True,
            )
        )

    return images


def _get_images_in_use() -> set[str]:
    """Get set of image IDs and names currently used by containers."""
    in_use = set()

    success, stdout, _ = _run_docker_command(
        ["ps", "-a", "--format", "{{.Image}}"]
    )

    if success and stdout.strip():
        for line in stdout.strip().split("\n"):
            if line:
                in_use.add(line.strip())

    return in_use


def find_orphaned_devcontainers(
    search_paths: list[Path] | None = None,
    max_depth: int = 3,
) -> list[OrphanedDevcontainer]:
    """Find .devcontainer directories without corresponding containers.

    Args:
        search_paths: Directories to search. Defaults to home directory common locations.
        max_depth: Maximum directory depth to search.

    Returns:
        List of OrphanedDevcontainer objects.
    """
    orphans = []

    if search_paths is None:
        # Default search paths: common code directories
        home = Path.home()
        search_paths = [
            home / "code",
            home / "projects",
            home / "src",
            home / "dev",
            home / "workspace",
            home / "repos",
            home / "git",
            home / "Documents" / "code",
            home / "Documents" / "projects",
        ]
        # Filter to only existing directories
        search_paths = [p for p in search_paths if p.exists() and p.is_dir()]

    # Get all containers with their project paths
    all_containers = get_all_csb_containers(include_running=True)
    container_paths = {c.project_path.resolve() for c in all_containers}

    # Search for .devcontainer directories
    found_devcontainers: list[Path] = []

    for search_path in search_paths:
        _find_devcontainers_recursive(
            search_path, found_devcontainers, max_depth, current_depth=0
        )

    for devcontainer_path in found_devcontainers:
        project_path = devcontainer_path.parent
        csb_json_path = devcontainer_path / "csb.json"

        # Only consider directories with csb.json (created by this tool)
        if not csb_json_path.exists():
            continue

        # Check if there's a corresponding container
        resolved_project = project_path.resolve()
        has_container = resolved_project in container_paths

        if not has_container:
            size_bytes = _get_directory_size(devcontainer_path)
            orphans.append(
                OrphanedDevcontainer(
                    path=devcontainer_path,
                    project_path=project_path,
                    size_bytes=size_bytes,
                    has_csb_json=True,
                    reason="no_container",
                )
            )

    return orphans


def _find_devcontainers_recursive(
    path: Path,
    results: list[Path],
    max_depth: int,
    current_depth: int,
) -> None:
    """Recursively find .devcontainer directories."""
    if current_depth > max_depth:
        return

    try:
        for entry in path.iterdir():
            if not entry.is_dir():
                continue

            # Skip hidden directories (except .devcontainer)
            if entry.name.startswith(".") and entry.name != ".devcontainer":
                continue

            # Skip common non-project directories
            skip_dirs = {
                "node_modules",
                ".git",
                "__pycache__",
                ".venv",
                "venv",
                ".cache",
                "dist",
                "build",
                "target",
            }
            if entry.name in skip_dirs:
                continue

            if entry.name == ".devcontainer":
                results.append(entry)
            else:
                _find_devcontainers_recursive(
                    entry, results, max_depth, current_depth + 1
                )
    except (PermissionError, OSError):
        pass


def generate_cleanup_report(
    include_running: bool = False,
    search_paths: list[Path] | None = None,
    include_dangling: bool = True,
) -> CleanupReport:
    """Generate a complete cleanup report.

    Args:
        include_running: Include running containers in report.
        search_paths: Paths to search for orphaned devcontainers.
        include_dangling: Include dangling images in report.

    Returns:
        CleanupReport with all findings.
    """
    containers = get_all_csb_containers(include_running=include_running)
    images = get_all_csb_images()
    orphans = find_orphaned_devcontainers(search_paths=search_paths)
    dangling = get_dangling_images() if include_dangling else []

    return CleanupReport(
        containers=containers,
        images=images,
        orphaned_dirs=orphans,
        dangling_images=dangling,
    )


def remove_container(container_id: str, force: bool = False) -> tuple[bool, str]:
    """Remove a container by ID.

    Args:
        container_id: The container ID to remove.
        force: If True, force remove even if running.

    Returns:
        Tuple of (success, message).
    """
    args = ["rm"]
    if force:
        args.append("-f")
    args.append(container_id)

    success, stdout, stderr = _run_docker_command(args)

    if success:
        return True, f"Removed container {container_id[:12]}"
    return False, stderr or "Failed to remove container"


def remove_image(image_id: str, force: bool = False) -> tuple[bool, str]:
    """Remove an image by ID.

    Args:
        image_id: The image ID to remove.
        force: If True, force remove.

    Returns:
        Tuple of (success, message).
    """
    args = ["rmi"]
    if force:
        args.append("-f")
    args.append(image_id)

    success, stdout, stderr = _run_docker_command(args, timeout=60)

    if success:
        return True, f"Removed image {image_id[:12]}"
    return False, stderr or "Failed to remove image"


def remove_orphaned_directory(path: Path) -> tuple[bool, str]:
    """Remove an orphaned .devcontainer directory.

    Args:
        path: Path to the .devcontainer directory.

    Returns:
        Tuple of (success, message).
    """
    if not path.exists():
        return True, "Directory already removed"

    if path.name != ".devcontainer":
        return False, "Safety check failed: not a .devcontainer directory"

    try:
        shutil.rmtree(path)
        return True, f"Removed {path}"
    except (OSError, PermissionError) as e:
        return False, f"Failed to remove: {e}"


def prune_dangling_images() -> tuple[bool, str, int]:
    """Remove all dangling images.

    Returns:
        Tuple of (success, message, space_reclaimed_bytes).
    """
    # Get size before pruning
    dangling = get_dangling_images()
    total_size = sum(img.size_bytes for img in dangling)

    if not dangling:
        return True, "No dangling images to remove", 0

    success, stdout, stderr = _run_docker_command(
        ["image", "prune", "-f"], timeout=120
    )

    if success:
        return True, f"Removed {len(dangling)} dangling image(s)", total_size
    return False, stderr or "Failed to prune images", 0


def get_docker_disk_usage() -> dict:
    """Get overall Docker disk usage.

    Returns:
        Dict with 'containers', 'images', 'volumes', 'build_cache' sizes.
    """
    success, stdout, _ = _run_docker_command(
        ["system", "df", "--format", "{{json .}}"]
    )

    result = {
        "containers": 0,
        "images": 0,
        "volumes": 0,
        "build_cache": 0,
    }

    if not success or not stdout.strip():
        return result

    for line in stdout.strip().split("\n"):
        if not line:
            continue
        try:
            data = json.loads(line)
            type_name = data.get("Type", "").lower()
            size_str = data.get("Size", "0B")
            size_bytes = _parse_docker_size(size_str)

            if "container" in type_name:
                result["containers"] = size_bytes
            elif "image" in type_name:
                result["images"] = size_bytes
            elif "volume" in type_name:
                result["volumes"] = size_bytes
            elif "build" in type_name or "cache" in type_name:
                result["build_cache"] = size_bytes
        except json.JSONDecodeError:
            continue

    return result
