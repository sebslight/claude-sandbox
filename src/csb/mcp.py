"""MCP server registry and configuration generator."""

from __future__ import annotations

import json
from pathlib import Path

# Registry of available MCP servers
MCP_SERVERS = {
    "filesystem": {
        "description": "File system access (read/write files)",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-filesystem", "/workspace"],
        "required_env": [],
    },
    "firecrawl": {
        "description": "Web scraping and crawling",
        "command": "npx",
        "args": ["-y", "firecrawl-mcp"],
        "required_env": ["FIRECRAWL_API_KEY"],
        "env": {
            "FIRECRAWL_API_KEY": "${FIRECRAWL_API_KEY}",
        },
    },
    "notion": {
        "description": "Notion workspace integration",
        "command": "npx",
        "args": ["-y", "@notionhq/notion-mcp-server"],
        "required_env": ["NOTION_TOKEN"],
        "env": {
            "OPENAPI_MCP_HEADERS": '{"Authorization": "Bearer ${NOTION_TOKEN}", "Notion-Version": "2025-09-03"}',
        },
    },
    "github": {
        "description": "GitHub repository access",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-github"],
        "required_env": ["GITHUB_TOKEN"],
        "env": {
            "GITHUB_PERSONAL_ACCESS_TOKEN": "${GITHUB_TOKEN}",
        },
    },
}


def generate_mcp_config(
    server_names: list[str], custom_servers: dict | None = None
) -> dict:
    """Generate .mcp.json configuration for the given servers.

    Args:
        server_names: List of built-in MCP server names to include
        custom_servers: Dict of custom server configs {name: {command, args, env, ...}}
    """
    config = {"mcpServers": {}}

    # Add built-in servers
    for name in server_names:
        if name not in MCP_SERVERS:
            continue

        server = MCP_SERVERS[name]
        server_config = {
            "command": server["command"],
            "args": server["args"],
            "trusted": True,
            "autoStart": True,
        }

        if "env" in server:
            server_config["env"] = server["env"]

        config["mcpServers"][name] = server_config

    # Add custom servers
    if custom_servers:
        for name, server in custom_servers.items():
            server_config = {
                "command": server["command"],
                "args": server.get("args", []),
                "trusted": True,
                "autoStart": True,
            }
            if "env" in server:
                server_config["env"] = server["env"]
            config["mcpServers"][name] = server_config

    return config


def _load_mcp_config(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError:
        return None


def _merge_mcp_configs(base: dict, override: dict) -> dict:
    return {
        "mcpServers": {
            **base.get("mcpServers", {}),
            **override.get("mcpServers", {}),
        }
    }


def generate_runtime_mcp_config(
    server_names: list[str],
    custom_servers: dict | None = None,
    merge_global: bool = False,
    global_config_path: Path | None = None,
) -> dict:
    """Generate MCP config for container runtime."""
    project_config = generate_mcp_config(server_names, custom_servers)

    if not merge_global:
        return project_config

    if global_config_path is None:
        global_config_path = Path.home() / ".claude" / ".mcp.json"

    global_config = _load_mcp_config(global_config_path) or {"mcpServers": {}}
    return _merge_mcp_configs(global_config, project_config)
