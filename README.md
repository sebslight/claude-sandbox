# csb - Claude Sandbox CLI

Run Claude Code in isolated devcontainers. Requires Docker or a Docker-compatible `docker` CLI (e.g., OrbStack, Podman with `podman-docker`).

## Installation

```bash
# Install globally with uv
uv tool install .

# Or run directly without installing
uv run csb --help
```

### Prerequisites

- [devcontainer CLI](https://github.com/devcontainers/cli): `npm install -g @devcontainers/cli`
- Docker or a Docker-compatible `docker` CLI (OrbStack, Podman with `podman-docker`)
- `ANTHROPIC_API_KEY` environment variable

## Quick Start

```bash
# Initialize a project (interactive mode)
cd ~/your-project
csb init

# Or use non-interactive mode
csb init --mcp filesystem,github,firecrawl

# Set required environment variables
export ANTHROPIC_API_KEY="sk-ant-..."
export GITHUB_TOKEN="ghp_..."      # if using GitHub MCP server
export FIRECRAWL_API_KEY="fc-..."  # if using Firecrawl MCP server
export NOTION_TOKEN="ntn_..."      # if using Notion MCP server

# Start the sandbox
csb start
```

## Commands

| Command | Description |
|---------|-------------|
| `csb init [--force] [--mcp servers] [--dockerfile path] [--with-claude-context\|--no-claude-context]` | Initialize .devcontainer/ with MCP server selection |
| `csb start [--rebuild] [--no-cache]` | Build container and launch Claude Code |
| `csb stop` | Stop the running container |
| `csb remove [--image] [--all] [--force]` | Remove container (and optionally image/configs) |
| `csb shell` | Open a shell in the running container |
| `csb logs [-f] [-n NUM]` | Show container logs |
| `csb status` | Show container status |
| `csb update` | Regenerate config files (not Dockerfile) from csb.json |
| `csb config` | View global configuration |
| `csb mcp list` | List available and configured MCP servers |
| `csb mcp add <server>` | Add a built-in MCP server |
| `csb mcp add-custom <name> -c <cmd>` | Add a custom MCP server |
| `csb mcp remove <server>` | Remove an MCP server |
| `csb claude list` | List Claude context (CLAUDE.md, skills, agents, etc.) |
| `csb claude sync` | Sync Claude context from parent directories |
| `csb claude refresh` | Refresh context in running container |
| `csb claude add <path>` | Add extra Claude context source |
| `csb claude remove <path>` | Remove extra Claude context source |

## MCP Servers

### Built-in Servers

| Server | Description | Required Env Var |
|--------|-------------|------------------|
| `filesystem` | File system access | - |
| `firecrawl` | Web scraping | `FIRECRAWL_API_KEY` |
| `notion` | Notion integration (Notion-Version: 2025-09-03) | `NOTION_TOKEN` |
| `github` | GitHub access | `GITHUB_TOKEN` |

### Managing Servers

```bash
# List available and configured servers
csb mcp list

# Add a built-in server
csb mcp add github

# Remove a server
csb mcp remove github

# Add a custom MCP server
csb mcp add-custom myserver -c npx -a "-y,my-mcp-server"

# Add custom server with env vars
csb mcp add-custom dbserver -c node -a "server.js" -e "DB_URL,DB_PASSWORD"
```

### Container Management

```bash
# Remove container only (keeps image and configs)
csb remove

# Remove container and Docker image
csb remove --image

# Full cleanup (container + image + .devcontainer/)
csb remove --all

# Force rebuild with no Docker cache (for Dockerfile changes)
csb start --rebuild --no-cache
```

## Claude Context

csb automatically handles your Claude Code configuration files (CLAUDE.md, skills, agents, commands) so they work inside the container.

### What's Included

| Source | Location | How It's Handled |
|--------|----------|------------------|
| Global config | `~/.claude/` | Mounted directly (CLAUDE.md, skills, agents, commands, settings) |
| Project config | `./.claude/` | Available at `/workspace/.claude/` |
| Parent configs | `../CLAUDE.md`, `../../.claude/` | Copied to container on init/sync |

### Including Parent Context

When you run `csb init`, it automatically discovers CLAUDE.md files and `.claude/` directories in parent folders and offers to include them:

```bash
# Interactive mode - will prompt if parent context is found
csb init

# Non-interactive mode - explicitly include parent context
csb init --with-claude-context

# Skip parent context
csb init --no-claude-context
```

### Managing Context

```bash
# See what Claude context is included
csb claude list

# Re-sync from parent directories (copies fresh content)
csb claude sync

# Refresh context in a running container
csb claude refresh

# Add extra context from anywhere
csb claude add ~/my-org/CLAUDE.md
csb claude add ~/shared-skills/.claude/skills/

# Remove extra context
csb claude remove ~/my-org/CLAUDE.md
```

### When Do Changes Take Effect?

After running `csb claude refresh`:

| Content | Applied When |
|---------|--------------|
| CLAUDE.md | On your next prompt |
| Skills, agents, commands, rules | Immediately (symlinked) |

### How It Works

1. **Global `~/.claude/`** is bind-mounted into the container, so your personal skills, agents, and settings work automatically

2. **Parent directories** are scanned during `csb init` for:
   - `CLAUDE.md` files
   - `.claude/rules/`, `.claude/skills/`, `.claude/agents/`, `.claude/commands/`

3. **Discovered content** is copied to `.devcontainer/claude-context/` and symlinked into place when the container starts

4. **MCP configs are generated for runtime** - CSB writes `.devcontainer/.mcp.runtime.json` and mounts it to `/workspace/.mcp.json` in the container. If Claude context setup is enabled, the runtime config merges global `~/.claude/.mcp.json` with project servers (project servers win).

## How It Works

1. `csb init` creates a `.devcontainer/` folder with:
   - `devcontainer.json` - Container configuration
   - `Dockerfile` - Ubuntu 24.04 with Node.js, Python (via uv), Claude Code
   - `.mcp.json` - MCP server selections
   - `.mcp.runtime.json` - Runtime MCP config mounted into the container
   - `.settings.runtime.json` - Runtime settings overlay for the container
   - `csb.json` - Tracks your MCP server selections for updates

2. `csb start` runs `devcontainer up` and launches Claude Code with `--dangerously-skip-permissions`

3. Your project directory is mounted at `/workspace` in the container

4. `csb update` regenerates config files when you modify csb.json (Dockerfile is not touched)

## Configuration

### Global Config

Stored at `~/.config/csb/config.json`:

```json
{
  "default_mcp_servers": ["filesystem"],
  "container_runtime": "docker"
}
```

`default_mcp_servers` controls which MCP servers are pre-selected in the interactive `csb init` prompts.
`container_runtime` is reserved for future use; csb currently shells out to a Docker-compatible `docker` CLI.

### Custom Dockerfile

Use a custom Dockerfile instead of the built-in default:

```bash
csb init --dockerfile ./my-dockerfile
```

This copies your Dockerfile into `.devcontainer/`. The Dockerfile is only written on `init` - subsequent `update`/`mcp add`/`mcp remove` commands don't touch it.

To update the Dockerfile later:

```bash
# Option 1: Edit .devcontainer/Dockerfile directly, then rebuild
csb start --rebuild --no-cache

# Option 2: Reinitialize with a new custom Dockerfile
csb init --force --dockerfile ./my-dockerfile
```

## Using with OrbStack

OrbStack is fully compatible with csb as long as its Docker-compatible `docker` CLI is available.

```bash
# OrbStack provides docker command compatibility
# Just ensure OrbStack is running, then:
csb init
csb start
```

Note: Docker Desktop's `docker sandbox` command is NOT available on OrbStack - that's why this CLI exists!

## Development

```bash
# Clone and install
git clone <repo>
cd code
uv sync

# Run locally
uv run csb --help

# Lint
uv run ruff check src/
```

## Project Structure

```
.devcontainer/
├── devcontainer.json  # Container config (auto-generated)
├── Dockerfile         # Container image (auto-generated)
├── .mcp.json          # MCP server selections (auto-generated)
├── .mcp.runtime.json  # Runtime MCP config mounted into the container
├── .settings.runtime.json # Runtime settings overlay for the container
├── csb.json           # Your selections (preserved on update)
└── claude-context/    # Parent Claude context (if enabled)
    ├── parents/
    │   ├── level-1/   # Immediate parent's context
    │   │   ├── CLAUDE.md
    │   │   ├── skills/
    │   │   ├── agents/
    │   │   ├── commands/
    │   │   └── rules/
    │   └── level-2/   # Grandparent's context
    │       └── CLAUDE.md
    └── setup-claude-context.sh  # Runs on container start
```

Parent content is symlinked into `/home/claude/.claude/` with level suffixes to avoid conflicts (e.g., `my-skill-level-1/`).

See the [User Guide](USER_GUIDE.md#inside-the-container) for full details on the container directory structure.
