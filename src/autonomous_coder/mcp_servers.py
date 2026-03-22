"""MCP server configuration — built-in and user-defined servers.

Built-in servers:
  - serena: Code intelligence MCP (semantic analysis via LSP)
  - context7: Library documentation lookup

The findings server (autonomous-coder) is created separately in tools.py
and injected by session.py.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .config import SessionConfig
from .streaming import EventHandler
from .tools import FindingsStore, create_findings_server


BUILTIN_MCP_SERVERS: dict[str, dict[str, Any]] = {
    "serena": {
        "command": "uvx",
        "args": ["serena"],
        "env": {"SERENA_PROJECT": "{project_path}"},
    },
    "context7": {
        "command": "npx",
        "args": ["-y", "@upstash/context7-mcp"],
    },
}


def build_mcp_servers(
    config: SessionConfig,
    store: FindingsStore,
    handler: EventHandler,
) -> dict[str, Any]:
    """Build the complete MCP server configuration.

    Merges built-in servers, the in-process findings server,
    and any user-defined extra MCP servers from config.
    """
    servers: dict[str, Any] = {}

    for name, server_config in BUILTIN_MCP_SERVERS.items():
        servers[name] = dict(server_config)

    # Template serena's project path
    if "serena" in servers:
        serena = dict(servers["serena"])
        env = dict(serena.get("env", {}))
        env["SERENA_PROJECT"] = str(config.project_path)
        serena["env"] = env
        servers["serena"] = serena

    # In-process findings server
    servers["autonomous-coder"] = create_findings_server(
        store, on_progress=handler.on_progress
    )

    # User's extra MCP servers from TOML config
    servers.update(config.extra_mcp_servers)

    return servers
