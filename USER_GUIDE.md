# CSB User Guide

**Claude Sandbox CLI** — Run Claude Code in isolated devcontainers

---

## Table of Contents

1. [Overview](#overview)
2. [Installation](#installation)
3. [Quick Start](#quick-start)
4. [Core Concepts](#core-concepts)
5. [Commands Reference](#commands-reference)
6. [MCP Servers](#mcp-servers)
7. [Claude Context](#claude-context)
8. [Configuration](#configuration)
9. [Workflow Examples](#workflow-examples)
10. [Troubleshooting](#troubleshooting)
11. [Advanced Usage](#advanced-usage)

---

## Overview

CSB (Claude Sandbox) is a command-line tool that runs Claude Code inside isolated containers. It provides:

- **Isolation**: All Claude Code operations run inside a container, protecting your host system
- **MCP Server Management**: Easy configuration of Model Context Protocol servers
- **Cross-Runtime Support**: Works with Docker or a Docker-compatible `docker` CLI (OrbStack, Podman with `podman-docker`)
- **Reproducibility**: Generated devcontainer configurations can be committed to version control

### Why Use CSB?

When running Claude Code with `--dangerously-skip-permissions`, Claude has unrestricted access to execute commands and modify files. CSB mitigates this risk by:

1. Containing all operations within a disposable container
2. Mounting only your project directory (at `/workspace`) plus `~/.claude` for Claude config
3. Keeping credentials in `~/.claude` on the host (mounted into the container)
4. Providing a consistent, reproducible environment

---

## Installation

### Prerequisites

Before installing CSB, ensure you have:

1. **Python 3.13+**
   ```bash
   python --version  # Should show 3.13 or higher
   ```

2. **Container Runtime** (Docker-compatible `docker` CLI required):
   - [Docker Desktop](https://www.docker.com/products/docker-desktop/)
   - [OrbStack](https://orbstack.dev/) (macOS, Docker-compatible CLI)
   - [Podman](https://podman.io/) (with `podman-docker`)

3. **devcontainer CLI**
   ```bash
   npm install -g @devcontainers/cli
   ```

4. **Anthropic API Key**
   ```bash
   export ANTHROPIC_API_KEY="sk-ant-..."
   ```

### Install CSB

```bash
# Option 1: Install globally with uv (recommended)
uv tool install /path/to/csb

# Option 2: Run directly without installing
cd /path/to/csb
uv run csb --help

# Option 3: Install in development mode
cd /path/to/csb
uv sync
uv run csb --help
```

### Verify Installation

```bash
csb --help
```

You should see the help output listing all available commands.

---

## Quick Start

### 1. Initialize a Project

Navigate to your project directory and run:

```bash
cd ~/my-project
csb init
```

This starts an interactive prompt where you select which MCP servers to enable:

```

Defaults for these prompts come from `default_mcp_servers` in `~/.config/csb/config.json`.
? Enable 'filesystem' (File system access)? [Y/n]: y
? Enable 'github' (GitHub repository access)? [Y/n]: n
? Enable 'firecrawl' (Web scraping and crawling)? [Y/n]: n
? Enable 'notion' (Notion workspace integration)? [Y/n]: n
```

Alternatively, use non-interactive mode:

```bash
csb init --mcp filesystem,github
```

### 2. Set Environment Variables

Based on your MCP server selections, set the required environment variables:

```bash
export ANTHROPIC_API_KEY="sk-ant-..."    # Always required
export GITHUB_TOKEN="ghp_..."            # If using GitHub server
export FIRECRAWL_API_KEY="fc-..."        # If using Firecrawl server
export NOTION_TOKEN="ntn_..."            # If using Notion server
```

### 3. Start the Sandbox

```bash
csb start
```

This:
1. Builds the container image (first run takes 2-5 minutes)
2. Starts the container
3. Launches Claude Code with `--dangerously-skip-permissions`

You're now running Claude Code inside an isolated container!

### 4. When You're Done

```bash
csb stop
```

---

## Core Concepts

### Project Structure

After running `csb init`, your project contains:

```
your-project/
├── .devcontainer/
│   ├── devcontainer.json   # Container configuration
│   ├── Dockerfile          # Container image definition
│   ├── .mcp.json           # MCP server configuration for Claude
│   └── csb.json            # Your selections (preserved on updates)
└── ... your project files
```

### File Purposes

| File | Purpose | Auto-generated? |
|------|---------|-----------------|
| `devcontainer.json` | Defines container settings, mounts, environment | Yes |
| `Dockerfile` | Defines the container image (Ubuntu 24.04 base) | Yes |
| `.mcp.json` | Configures MCP servers that Claude Code will use | Yes |
| `csb.json` | Stores your MCP server selections | Preserved on update |

### Container Environment

Inside the container:

| Aspect | Value |
|--------|-------|
| Base OS | Ubuntu 24.04 |
| User | `claude` (non-root with sudo) |
| Shell | zsh |
| Working Directory | `/workspace` (your project) |
| Node.js | v22 LTS |
| Python | 3.13 (via uv) |
| Claude Code | Latest (npm global) |

### Mount Points

| Host | Container | Purpose |
|------|-----------|---------|
| Your project directory | `/workspace` | Project files |
| `~/.claude` | `/home/claude/.claude` | Claude credentials and config |

---

## Commands Reference

### `csb init`

Initialize a new Claude sandbox in a project directory.

```bash
csb init [PATH] [OPTIONS]
```

**Arguments:**
- `PATH`: Directory to initialize (default: current directory)

**Options:**
- `--force, -f`: Overwrite existing `.devcontainer/` directory
- `--mcp, -m`: Comma-separated list of MCP servers (skips interactive prompts)
- `--dockerfile, -d`: Path to custom Dockerfile (copied into `.devcontainer/`)
- `--with-claude-context`: Include Claude context from parent directories
- `--no-claude-context`: Skip parent Claude context

**Examples:**

```bash
# Interactive mode in current directory
csb init

# Non-interactive with specific servers
csb init --mcp filesystem,github,firecrawl

# Initialize a different directory
csb init ~/projects/my-app

# Reinitialize, overwriting existing config
csb init --force

# Initialize another directory with servers
csb init ~/projects/api --mcp filesystem,github

# Use a custom Dockerfile
csb init --dockerfile ./my-dockerfile

# Reinitialize with custom Dockerfile
csb init --force --dockerfile ./my-dockerfile
```

**Output:**
- Creates `.devcontainer/` with all required files
- Displays list of required environment variables

---

### `csb start`

Build the container and launch Claude Code.

```bash
csb start [PATH] [OPTIONS]
```

**Arguments:**
- `PATH`: Project directory (default: current directory)

**Options:**
- `--rebuild, -r`: Remove existing container and rebuild
- `--no-cache`: Force full image rebuild without Docker cache (implies `--rebuild`)

**Examples:**

```bash
# Start sandbox for current project
csb start

# Rebuild container (removes existing, uses cached image layers)
csb start --rebuild

# Force full image rebuild (no Docker cache - use after Dockerfile changes)
csb start --rebuild --no-cache

# Start sandbox for specific project
csb start ~/projects/my-app
```

**Behavior:**
1. Runs `devcontainer up` to build/start the container
2. Executes `claude --dangerously-skip-permissions` inside the container
3. Replaces the current shell process with Claude Code

**Timeouts:**
- Container build: 10 minutes (600 seconds) to accommodate `--no-cache` builds

---

### `csb stop`

Stop the running container.

```bash
csb stop [PATH]
```

**Arguments:**
- `PATH`: Project directory (default: current directory)

**Examples:**

```bash
# Stop current project's container
csb stop

# Stop specific project's container
csb stop ~/projects/my-app
```

**Behavior:**
- Gracefully stops the container with a 30-second timeout
- Container can be restarted with `csb start`

---

### `csb remove`

Remove the sandbox container (and optionally more).

```bash
csb remove [PATH] [OPTIONS]
```

**Arguments:**
- `PATH`: Project directory (default: current directory)

**Options:**
- `--image, -i`: Also remove the Docker image
- `--all, -a`: Remove container, image, AND `.devcontainer/` directory
- `--force, -f`: Skip confirmation prompts

**Examples:**

```bash
# Remove container only (default)
csb remove

# Remove container and Docker image
csb remove --image

# Full cleanup (container + image + .devcontainer/)
csb remove --all

# Full cleanup without confirmation
csb remove --all --force

# Remove for specific project
csb remove ~/projects/my-app --image
```

**Behavior:**
- Stops container if running, then removes it
- With `--image`: Also removes the Docker image (frees disk space)
- With `--all`: Removes everything including `.devcontainer/` (requires confirmation or `--force`)

**Use Cases:**
- Reset container state without losing config: `csb remove`
- Free disk space: `csb remove --image`
- Start completely fresh: `csb remove --all` then `csb init`

---

### `csb shell`

Open an interactive shell inside the running container.

```bash
csb shell [PATH]
```

**Arguments:**
- `PATH`: Project directory (default: current directory)

**Examples:**

```bash
# Open shell in current project's container
csb shell

# Open shell in specific project's container
csb shell ~/projects/my-app
```

**Behavior:**
- Opens a `zsh` shell as the `claude` user
- Requires the container to be running
- Useful for debugging or manual operations

---

### `csb logs`

Show container logs.

```bash
csb logs [PATH] [OPTIONS]
```

**Arguments:**
- `PATH`: Project directory (default: current directory)

**Options:**
- `--follow, -f`: Follow log output in real-time (like `tail -f`)
- `--tail, -n`: Show only the last N lines

**Examples:**

```bash
# Show all logs
csb logs

# Follow logs in real-time
csb logs --follow

# Show last 50 lines
csb logs --tail 50

# Follow logs for specific project
csb logs ~/projects/my-app -f
```

---

### `csb status`

Show the current sandbox status.

```bash
csb status [PATH]
```

**Arguments:**
- `PATH`: Project directory (default: current directory)

**Examples:**

```bash
csb status
```

**Output:**

```
Project: /Users/you/projects/my-app
Devcontainer: initialized
Container: running
```

---

### `csb mcp list`

List available and configured MCP servers.

```bash
csb mcp list [OPTIONS]
```

**Options:**
- `--path, -p`: Project directory (default: current directory)

**Examples:**

```bash
# List servers for current project
csb mcp list

# List servers for specific project
csb mcp list --path ~/projects/my-app
```

**Output:**

```
Built-in MCP servers:

┌────────────┬──────────────┬─────────────────────────────┬───────────────────┐
│ Name       │ Status       │ Description                 │ Required Env      │
├────────────┼──────────────┼─────────────────────────────┼───────────────────┤
│ filesystem │ ✓ configured │ File system access          │ -                 │
│ firecrawl  │ available    │ Web scraping and crawling   │ FIRECRAWL_API_KEY │
│ notion     │ available    │ Notion workspace integration│ NOTION_TOKEN      │
│ github     │ ✓ configured │ GitHub repository access    │ GITHUB_TOKEN      │
└────────────┴──────────────┴─────────────────────────────┴───────────────────┘
```

---

### `csb mcp add`

Add a built-in MCP server to the sandbox.

```bash
csb mcp add <SERVER> [OPTIONS]
```

**Arguments:**
- `SERVER`: Name of the built-in MCP server (required)

**Options:**
- `--path, -p`: Project directory (default: current directory)

**Available Servers:**
- `filesystem` - File system access
- `github` - GitHub repository access
- `firecrawl` - Web scraping and crawling
- `notion` - Notion workspace integration

**Examples:**

```bash
# Add GitHub server
csb mcp add github

# Add to specific project
csb mcp add firecrawl --path ~/projects/my-app
```

**Behavior:**
- Updates `csb.json` with the new server
- Regenerates `devcontainer.json` and `.mcp.json`
- Displays any required environment variables

---

### `csb mcp add-custom`

Add a custom MCP server with an arbitrary command.

```bash
csb mcp add-custom <NAME> --command <CMD> [OPTIONS]
```

**Arguments:**
- `NAME`: Unique name for the custom server (required)

**Options:**
- `--command, -c`: Command to run (required). Examples: `npx`, `node`, `python`
- `--args, -a`: Comma-separated arguments to pass to the command
- `--env, -e`: Comma-separated environment variable names required by the server
- `--path, -p`: Project directory (default: current directory)

**Examples:**

```bash
# Add a custom npx-based server
csb mcp add-custom myserver -c npx -a "-y,@my-org/mcp-server"

# Add a Node.js server with args
csb mcp add-custom dbserver -c node -a "server.js,--port,3000"

# Add a server with required environment variables
csb mcp add-custom apiserver -c npx -a "-y,api-mcp" -e "API_KEY,API_SECRET"

# Add to specific project
csb mcp add-custom myserver -c node -a "index.js" --path ~/projects/app
```

**How Environment Variables Work:**

When you specify `-e "VAR1,VAR2"`, CSB:
1. Adds these to `csb.json` as required environment variables
2. Configures the server to receive `${VAR1}` and `${VAR2}` at runtime
3. You must set these variables on your host before running `csb start`

---

### `csb mcp remove`

Remove an MCP server (built-in or custom).

```bash
csb mcp remove <SERVER> [OPTIONS]
```

**Arguments:**
- `SERVER`: Name of the server to remove (required)

**Options:**
- `--path, -p`: Project directory (default: current directory)

**Examples:**

```bash
# Remove a built-in server
csb mcp remove github

# Remove a custom server
csb mcp remove myserver

# Remove from specific project
csb mcp remove firecrawl --path ~/projects/my-app
```

---

### `csb update`

Regenerate config files from `csb.json`.

```bash
csb update [PATH]
```

**Arguments:**
- `PATH`: Project directory (default: current directory)

**Examples:**

```bash
csb update
```

**When to Use:**
- After manually editing `csb.json`
- After updating CSB to get the latest config file formats

**Behavior:**
- Reads `csb.json` for your MCP server selections
- Regenerates `devcontainer.json` and `.mcp.json`
- Does NOT regenerate Dockerfile (use `csb init --force` for that)
- Preserves your selections in `csb.json`

---

### `csb config`

Show global CSB configuration.

```bash
csb config
```

**Output:**

```
Config location: ~/.config/csb/config.json

Current settings:
  default_mcp_servers: ['filesystem']
  container_runtime: docker
```

---

## MCP Servers

### Built-in Servers

CSB includes four pre-configured MCP servers:

| Server | Description | Required Env Var | Command |
|--------|-------------|------------------|---------|
| `filesystem` | Read/write files in `/workspace` | None | `npx -y @modelcontextprotocol/server-filesystem /workspace` |
| `github` | Access GitHub repositories | `GITHUB_TOKEN` | `npx -y @modelcontextprotocol/server-github` |
| `firecrawl` | Web scraping and crawling | `FIRECRAWL_API_KEY` | `npx -y firecrawl-mcp` |
| `notion` | Notion workspace integration | `NOTION_TOKEN` | `npx -y @notionhq/notion-mcp-server` |

### Adding Built-in Servers

```bash
# During init
csb init --mcp filesystem,github

# After init
csb mcp add github
csb mcp add firecrawl

# List what's available and configured
csb mcp list
```

### Custom MCP Servers

For servers not included in CSB, use `mcp add-custom`:

```bash
# Basic custom server
csb mcp add-custom sqlite -c npx -a "-y,@anthropic/mcp-server-sqlite"

# With environment variables
csb mcp add-custom slack -c npx -a "-y,@anthropic/mcp-server-slack" -e "SLACK_TOKEN"

# Python-based server
csb mcp add-custom mypy -c python -a "-m,my_mcp_server"
```

### Custom Server Configuration

Custom servers are stored in `csb.json`:

```json
{
  "version": "1.0",
  "mcp_servers": ["filesystem"],
  "custom_mcp_servers": {
    "myserver": {
      "command": "npx",
      "args": ["-y", "my-mcp-server"],
      "env": {
        "API_KEY": "${API_KEY}"
      },
      "required_env": ["API_KEY"]
    }
  }
}
```

### MCP Server Behavior

All MCP servers in CSB are configured with:

```json
{
  "trusted": true,
  "autoStart": true
}
```

This means:
- Servers start automatically when Claude Code launches
- No additional permission prompts for MCP operations

---

## Claude Context

CSB automatically manages your Claude Code configuration files (CLAUDE.md, skills, agents, commands) so they work inside the container.

### What's Included Automatically

| Source | Location | How It's Handled |
|--------|----------|------------------|
| **Global config** | `~/.claude/` | Bind-mounted directly into container |
| **Project config** | `./.claude/` | Available at `/workspace/.claude/` |
| **Parent configs** | `../CLAUDE.md`, `../../.claude/` | Discovered and copied on init/sync |

### Global Context (~/.claude/)

Your global Claude configuration is automatically mounted into the container:

- `~/.claude/CLAUDE.md` - Global instructions
- `~/.claude/skills/` - Personal skills
- `~/.claude/agents/` - Personal agents
- `~/.claude/commands/` - Custom slash commands
- `~/.claude/settings.json` - Your settings
- `~/.claude/.mcp.json` - Global MCP servers (merged with project servers)

No additional setup needed - this works automatically.

### Parent Directory Context

Claude Code normally discovers CLAUDE.md files in parent directories. Since the container only mounts your project at `/workspace`, parent directories aren't visible.

CSB solves this by:

1. **Discovering** parent CLAUDE.md files and `.claude/` directories during `csb init`
2. **Copying** them into `.devcontainer/claude-context/`
3. **Symlinking** them into place when the container starts

#### Enabling Parent Context

```bash
# Interactive mode - prompts if parent context is found
csb init

# Non-interactive - explicitly enable
csb init --with-claude-context

# Non-interactive - explicitly disable
csb init --no-claude-context
```

### Managing Claude Context

#### `csb claude list`

Show all Claude context that will be included:

```bash
csb claude list
```

**Output:**

```
Global Context (~/.claude/)
  ✓ Mounted: CLAUDE.md, skills/, agents/, commands/

Parent Contexts
  ✓ Level 1: /Users/you/code
      Found: CLAUDE.md, rules/
  ✓ Level 2: /Users/you
      Found: CLAUDE.md

Sync Status
  ✓ Context copied to .devcontainer/claude-context/
      3 items synced
```

#### `csb claude sync`

Re-copy context from source directories:

```bash
csb claude sync
```

Use this after modifying CLAUDE.md, skills, or agents in parent directories.

#### `csb claude refresh`

Sync and apply changes in a running container:

```bash
csb claude refresh
```

This:
1. Re-syncs from source directories (copies latest content)
2. If container is running, re-runs the setup script to update symlinks

**When do changes take effect?**

| Content Type | When It's Applied |
|--------------|-------------------|
| CLAUDE.md files | On your next prompt to Claude |
| Skills | Immediately (symlinked) |
| Agents | Immediately (symlinked) |
| Commands | Immediately (symlinked) |
| Rules | Immediately (symlinked) |

If the container isn't running, changes will be applied on the next `csb start`.

#### `csb claude add`

Add extra Claude context from anywhere:

```bash
# Add a CLAUDE.md from another location
csb claude add ~/my-org/CLAUDE.md

# Add a skills directory
csb claude add ~/shared-skills/.claude/skills/

# Add agents from a team directory
csb claude add /team/shared/.claude/agents/
```

**Options:**
- `--project, -p`: Target project directory (default: current directory)

#### `csb claude remove`

Remove an extra source:

```bash
csb claude remove ~/my-org/CLAUDE.md
```

**Options:**
- `--project, -p`: Target project directory (default: current directory)

### How MCP Configs Are Merged

CSB merges your global `~/.claude/.mcp.json` with the project's MCP servers **only when Claude context setup is enabled** (via `csb init --with-claude-context` or `csb claude sync`):

1. Global MCP servers from `~/.claude/.mcp.json` are loaded
2. Project MCP servers from `.devcontainer/.mcp.json` are merged in
3. **Project servers take precedence** if there are name conflicts

If Claude context setup is not enabled, the project `.mcp.json` is copied into the container and replaces the global config.

### Inside the Container

When the container starts, CSB sets up your Claude context as follows:

**Directory Structure:**

```
/home/claude/.claude/           # Claude's home config directory
├── CLAUDE.md                   # Your global instructions (mounted from ~/.claude/)
├── settings.json               # Your settings (mounted)
├── .mcp.json                   # Merged MCP config (global + project)
├── skills/                     # Skills directory
│   ├── my-skill/               # Your global skills (mounted)
│   └── org-skill-level-1/      # Parent skills (symlinked, suffixed with level)
├── agents/                     # Agents directory
│   ├── my-agent.md             # Your global agents (mounted)
│   └── org-agent-level-1.md    # Parent agents (symlinked with level suffix)
├── commands/                   # Commands directory
│   └── ...                     # Same pattern
├── rules/                      # Rules directory
│   └── ...                     # Same pattern
└── parents/                    # Parent CLAUDE.md files
    ├── level-1-CLAUDE.md       # Symlink to immediate parent's CLAUDE.md
    └── level-2-CLAUDE.md       # Symlink to grandparent's CLAUDE.md

/workspace/.devcontainer/claude-context/  # Copied parent content
├── parents/
│   ├── level-1/
│   │   ├── CLAUDE.md
│   │   ├── skills/
│   │   └── agents/
│   └── level-2/
│       └── CLAUDE.md
└── setup-claude-context.sh     # Setup script run on container start
```

**How Parent Discovery Works:**

1. CSB scans up to 3 parent directories (configurable via `parent_max_depth`)
2. Your home directory (`~`) is **skipped** since `~/.claude/` is already mounted as global context
3. For each parent with Claude content, files are copied to `.devcontainer/claude-context/parents/level-N/`
4. When the container starts, the setup script symlinks these into `/home/claude/.claude/`

**Naming Convention for Parent Content:**

To avoid conflicts with your global content, parent skills/agents/commands are suffixed with their level:

| Original | In Container |
|----------|--------------|
| `skills/my-skill/` (level 1) | `skills/my-skill-level-1/` |
| `agents/deploy.md` (level 2) | `agents/deploy-level-2.md` |
| `rules/style.md` (level 1) | `rules/style-level-1.md` |

### Configuration Storage

Parent context settings are stored in `csb.json`:

```json
{
  "version": "1.0",
  "mcp_servers": ["filesystem"],
  "claude_context": {
    "global": {
      "include": true,
      "components": ["CLAUDE.md", "agents", "commands", "skills", "rules", "settings.json"]
    },
    "parents": {
      "auto_discover": true,
      "max_depth": 3
    },
    "extra": [
      "/Users/you/my-org/CLAUDE.md"
    ]
  }
}
```

---

## Configuration

### Global Configuration

CSB stores global settings at `~/.config/csb/config.json`:

```json
{
  "default_mcp_servers": ["filesystem"],
  "container_runtime": "docker"
}
```

**Settings:**

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `default_mcp_servers` | array | `["filesystem"]` | Servers pre-selected in interactive `csb init` |
| `container_runtime` | string | `"docker"` | Reserved; CSB currently uses a Docker-compatible `docker` CLI |

### Custom Dockerfile

Use a custom Dockerfile instead of the built-in default by passing the `--dockerfile` flag:

```bash
csb init --dockerfile ./my-dockerfile
```

This copies your Dockerfile into `.devcontainer/`. The Dockerfile is only written during `init` - subsequent `update`/`mcp add`/`mcp remove` commands don't touch it, so you can also edit `.devcontainer/Dockerfile` directly.

**To update the Dockerfile later:**

```bash
# Option 1: Edit .devcontainer/Dockerfile directly, then rebuild
csb start --rebuild --no-cache

# Option 2: Reinitialize with a new custom Dockerfile
csb init --force --dockerfile ./my-dockerfile
```

**Use Cases:**
- Adding additional programming languages
- Pre-installing specific tools or packages
- Using a different base image
- Adding custom configuration

**Example Custom Dockerfile:**

```dockerfile
FROM ubuntu:24.04

# Install additional tools
RUN apt-get update && apt-get install -y \
    curl wget git ripgrep jq fzf zsh sudo ca-certificates \
    build-essential cmake \
    && rm -rf /var/lib/apt/lists/*

# Install Node.js 22
RUN curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y nodejs

# Install Rust
RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y

# Create claude user
RUN useradd -m -s /bin/zsh claude \
    && echo "claude ALL=(ALL) NOPASSWD:ALL" >> /etc/sudoers

USER claude
WORKDIR /workspace

# Install uv and Python
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/home/claude/.local/bin:$PATH"
RUN uv python install 3.13

# Install Claude Code
RUN npm install -g @anthropic-ai/claude-code
```

### Project Configuration

Each project's configuration is stored in `.devcontainer/csb.json`:

```json
{
  "version": "1.0",
  "mcp_servers": ["filesystem", "github"],
  "custom_mcp_servers": {}
}
```

This file is preserved when running `csb update`, allowing you to:
1. Manually edit MCP server selections
2. Run `csb update` to regenerate other files

---

## Workflow Examples

### Example 1: Basic Project Setup

```bash
# Navigate to project
cd ~/projects/my-web-app

# Initialize with filesystem access only
csb init --mcp filesystem

# Set API key
export ANTHROPIC_API_KEY="sk-ant-..."

# Start working
csb start

# ... use Claude Code ...

# When done
csb stop
```

### Example 2: Full-Featured Development Environment

```bash
# Initialize with multiple servers
cd ~/projects/research-tool
csb init --mcp filesystem,github,firecrawl

# Set all required environment variables
export ANTHROPIC_API_KEY="sk-ant-..."
export GITHUB_TOKEN="ghp_..."
export FIRECRAWL_API_KEY="fc-..."

# Start sandbox
csb start
```

### Example 3: Adding Servers to Existing Project

```bash
cd ~/projects/existing-app

# Project already has .devcontainer from csb init
csb mcp add github
csb mcp add notion

# Set new environment variables
export GITHUB_TOKEN="ghp_..."
export NOTION_TOKEN="ntn_..."

# Rebuild to pick up changes
csb start --rebuild
```

### Example 4: Custom MCP Server Integration

```bash
cd ~/projects/database-app

# Initialize with basic servers
csb init --mcp filesystem

# Add custom database server
csb mcp add-custom postgres -c npx -a "-y,@my-org/postgres-mcp" -e "DATABASE_URL"

# Set environment variables
export ANTHROPIC_API_KEY="sk-ant-..."
export DATABASE_URL="postgresql://user:pass@localhost:5432/mydb"

# Start
csb start
```

### Example 5: Updating the Dockerfile

```bash
cd ~/projects/my-app

# Edit the Dockerfile to add new tools
nano .devcontainer/Dockerfile

# Rebuild with no cache to apply changes
csb start --rebuild --no-cache

# Or for a complete reset:
csb remove --all --force
csb init --mcp filesystem,github
csb start
```

### Example 6: Using Parent Claude Context

```bash
# Scenario: You have a monorepo with shared CLAUDE.md at the root
# /code/CLAUDE.md          <- Shared team instructions
# /code/projects/my-app/   <- Your project

cd /code/projects/my-app

# Initialize - csb finds parent CLAUDE.md and asks to include
csb init --mcp filesystem

# Output:
# Claude Context Discovery:
#   ~/.claude/: CLAUDE.md, skills/, agents/ (always mounted)
#   Parent 1: /code/projects
#       Found: (none)
#   Parent 2: /code
#       Found: CLAUDE.md
#
# Include parent Claude context in sandbox? [Y/n]: y
#
# Synced 1 Claude context items

# Start sandbox - parent context is automatically set up
csb start

# Later, if team updates the parent CLAUDE.md
csb claude refresh
```

### Example 7: Adding Organization-Wide Skills

```bash
cd ~/projects/my-app

# Add shared skills from your org's repository
csb claude add ~/org-tools/.claude/skills/

# Sync to copy into container context
csb claude sync

# If container is already running
csb claude refresh

# See what's included
csb claude list
```

### Example 8: Debugging Container Issues

```bash
# Check status
csb status

# View logs
csb logs --tail 100

# Open shell to investigate
csb shell

# Inside container:
claude --version
node --version
python --version

# Exit shell
exit

# If needed, rebuild from scratch
csb start --rebuild
```

### Example 9: Team Collaboration

```bash
# Developer 1: Set up project
cd ~/projects/team-project
csb init --mcp filesystem,github
git add .devcontainer/
git commit -m "Add Claude sandbox configuration"
git push

# Developer 2: Clone and use
git clone <repo>
cd team-project
export ANTHROPIC_API_KEY="..."
export GITHUB_TOKEN="..."
csb start
```

---

## Troubleshooting

### "devcontainer CLI not found"

**Error:**
```
Error: devcontainer CLI is not installed.
```

**Solution:**
```bash
npm install -g @devcontainers/cli
```

### "Container not running"

**Error:**
```
Error: Container is not running for /path/to/project.
Run 'csb start' first.
```

**Solution:**
```bash
csb start
```

### "Devcontainer not initialized"

**Error:**
```
Error: No .devcontainer found in /path/to/project.
Run 'csb init' first.
```

**Solution:**
```bash
csb init
```

### Container Build Fails

**Symptoms:** Build hangs or fails during `csb start`

**Solutions:**

1. **Check Docker is running:**
   ```bash
   docker ps
   ```

2. **Rebuild from scratch:**
   ```bash
   csb start --rebuild
   ```

3. **Check logs:**
   ```bash
   csb logs --tail 100
   ```

4. **Verify network connectivity** (container needs to download packages)

### Environment Variable Errors

**Symptoms:** MCP servers fail to start, authentication errors

**Solutions:**

1. **Check required variables are set:**
   ```bash
   echo $ANTHROPIC_API_KEY
   echo $GITHUB_TOKEN  # if using GitHub server
   ```

2. **Set missing variables:**
   ```bash
   export ANTHROPIC_API_KEY="sk-ant-..."
   ```

3. **Restart container:**
   ```bash
   csb stop
   csb start
   ```

### MCP Server Not Working

**Symptoms:** Claude can't access MCP server functionality

**Solutions:**

1. **List configured servers:**
   ```bash
   csb mcp list
   ```

2. **Verify server is configured:**
   ```bash
   cat .devcontainer/csb.json
   cat .devcontainer/.mcp.json
   ```

3. **Check environment variables are passed:**
   ```bash
   csb shell
   env | grep -E "(API_KEY|TOKEN)"
   ```

4. **Regenerate configuration:**
   ```bash
   csb update
   csb start --rebuild
   ```

### Slow Container Startup

**Symptoms:** `csb start` takes a long time

**Causes:**
- First build downloads base image and packages
- Network issues slowing package downloads

**Solutions:**
- First build: Be patient (2-5 minutes is normal)
- Subsequent starts should be fast (container is cached)
- Use `--rebuild` only when necessary

### Permission Denied Errors

**Symptoms:** Can't write to files in container

**Solutions:**

1. **Check file ownership:**
   ```bash
   csb shell
   ls -la /workspace
   ```

2. **Fix permissions:**
   ```bash
   csb shell
   sudo chown -R claude:claude /workspace
   ```

### Claude Context Not Working

**Symptoms:** Claude doesn't see parent CLAUDE.md, skills, or agents

**Solutions:**

1. **Check what context is included:**
   ```bash
   csb claude list
   ```

2. **Verify context was synced:**
   ```bash
   ls -la .devcontainer/claude-context/
   ```

3. **Re-sync context:**
   ```bash
   csb claude sync
   ```

4. **If container is running, refresh:**
   ```bash
   csb claude refresh
   ```

5. **Check context inside container:**
   ```bash
   csb shell
   ls -la ~/.claude/
   ls -la ~/.claude/skills/
   ls -la ~/.claude/parents/
   ```

6. **Verify symlinks are correct:**
   ```bash
   csb shell
   readlink ~/.claude/skills/*
   ```

### Parent Context Not Discovered

**Symptoms:** `csb claude list` shows no parent contexts when you expect some

**Causes:**
- CLAUDE.md or `.claude/` not present in parent directories
- Parent is beyond the 3-level depth limit
- Home directory is intentionally skipped (to avoid duplicate with global)

**Solutions:**

1. **Increase search depth:**
   Edit `.devcontainer/csb.json`:
   ```json
   {
     "claude_context": {
       "parents": {
         "max_depth": 5
       }
     }
   }
   ```
   Then run `csb claude sync`.

2. **Manually add the source:**
   ```bash
   csb claude add /path/to/CLAUDE.md
   csb claude sync
   ```

---

## Advanced Usage

### Using with OrbStack (macOS)

OrbStack provides a Docker-compatible runtime. CSB works with OrbStack as long as the `docker` CLI is available:

```bash
# Ensure OrbStack is running
# Then use csb normally
csb init
csb start
```

Note: Docker Desktop's `docker sandbox` command is not available on OrbStack. CSB provides equivalent functionality.

### Using with Podman

CSB currently shells out to `docker`, so you need a Docker-compatible shim:

```bash
# Install podman-docker so `docker` is available
# Then use normally
csb init
csb start
```

### Committing Devcontainer to Version Control

The `.devcontainer/` directory can be committed to share sandbox configuration:

```bash
git add .devcontainer/
git commit -m "Add Claude sandbox configuration"
```

**What to commit:**
- `devcontainer.json` - Container settings
- `Dockerfile` - Container image
- `.mcp.json` - MCP server configuration
- `csb.json` - MCP server selections

**What NOT to commit:**
- Environment variables (set them in your shell or `.env` file)
- API keys or tokens

### Manually Editing csb.json

You can manually edit `.devcontainer/csb.json` and regenerate:

```json
{
  "version": "1.0",
  "mcp_servers": ["filesystem", "github", "firecrawl"],
  "custom_mcp_servers": {
    "myserver": {
      "command": "node",
      "args": ["server.js"],
      "env": {"PORT": "3000"},
      "required_env": []
    }
  }
}
```

Then regenerate:

```bash
csb update
csb start --rebuild
```

### Running Multiple Sandboxes

You can run sandboxes for different projects simultaneously:

```bash
# Terminal 1
cd ~/projects/app-a
csb start

# Terminal 2
cd ~/projects/app-b
csb start
```

Each project gets its own isolated container.

### Inspecting the Container

```bash
# View running containers
docker ps | grep devcontainer

# Get container ID
csb shell
# Then: docker inspect $(hostname)
```

### Security Considerations

CSB provides isolation through containerization, but be aware:

1. **`--dangerously-skip-permissions`**: Claude Code runs without permission prompts inside the container. This is safe because the container is isolated.

2. **Mounted directories**: Your project is accessible at `/workspace` and your `~/.claude` is mounted at `/home/claude/.claude`.

3. **Network access**: The container has full network access by default.

4. **API keys**: Are passed as environment variables. Don't commit them.

5. **Custom Dockerfiles**: When using custom templates, ensure you trust the image sources.

### Extending the Container

For project-specific customizations, use a custom Dockerfile:

```bash
# Create your custom Dockerfile
cat > my-dockerfile << 'EOF'
FROM ubuntu:24.04

# ... your customizations ...

EOF

# Initialize with custom Dockerfile
csb init --dockerfile ./my-dockerfile
```

The Dockerfile is copied into `.devcontainer/` and won't be overwritten by `update`/`mcp add`/`mcp remove` commands. You can also edit `.devcontainer/Dockerfile` directly after initialization.

To apply Dockerfile changes:
```bash
csb start --rebuild --no-cache
```

---

## Getting Help

- **CLI help:** `csb --help` or `csb <command> --help`
- **Check status:** `csb status`
- **View logs:** `csb logs -f`
- **Open shell:** `csb shell`

---

## Summary

| Task | Command |
|------|---------|
| Initialize project | `csb init` |
| Start Claude in sandbox | `csb start` |
| Rebuild container | `csb start --rebuild` |
| Full rebuild (no cache) | `csb start --rebuild --no-cache` |
| Stop sandbox | `csb stop` |
| Remove container | `csb remove` |
| Remove container + image | `csb remove --image` |
| Full cleanup | `csb remove --all` |
| Open shell in container | `csb shell` |
| View logs | `csb logs [-f]` |
| Check status | `csb status` |
| List MCP servers | `csb mcp list` |
| Add MCP server | `csb mcp add <server>` |
| Add custom server | `csb mcp add-custom <name> -c <cmd>` |
| Remove MCP server | `csb mcp remove <server>` |
| List Claude context | `csb claude list` |
| Sync parent context | `csb claude sync` |
| Refresh context in container | `csb claude refresh` |
| Add extra context source | `csb claude add <path>` |
| Remove context source | `csb claude remove <path>` |
| Update config files | `csb update` |
| View global config | `csb config` |
