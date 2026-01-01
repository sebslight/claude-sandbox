"""Custom exceptions for csb."""


class CsbError(Exception):
    """Base exception for csb."""

    pass


class DevcontainerCliNotFoundError(CsbError):
    """Raised when devcontainer CLI is not installed."""

    def __init__(self):
        super().__init__(
            "devcontainer CLI not found.\n\n"
            "Install it with:\n"
            "  npm install -g @devcontainers/cli\n\n"
            "Or with npx (no install):\n"
            "  npx @devcontainers/cli --help"
        )


class ContainerNotRunningError(CsbError):
    """Raised when trying to interact with a container that isn't running."""

    def __init__(self, project_path: str):
        super().__init__(
            f"No running container for {project_path}.\nStart it with: csb start"
        )


class DevcontainerNotInitializedError(CsbError):
    """Raised when .devcontainer/ doesn't exist."""

    def __init__(self, project_path: str):
        super().__init__(
            f"No .devcontainer/ found in {project_path}.\nInitialize with: csb init"
        )
