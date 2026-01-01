"""MCP server registry and configuration generator."""

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
            "OPENAPI_MCP_HEADERS": '{"Authorization": "Bearer ${NOTION_TOKEN}", "Notion-Version": "2022-06-28"}',
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
