"""External MCP server configurations for the autonomous coder.

Declarative MCP server definitions that the SDK manages automatically.
Replaces the ad-hoc MCP connection management from the quickstart.
"""
from __future__ import annotations

import os
from typing import Any

from .types import AutonomousCoderConfig


def build_mcp_server_configs(config: AutonomousCoderConfig) -> dict[str, dict[str, Any]]:
    """Build MCP server configurations based on available API keys and config.

    Only includes servers whose dependencies are available. For example,
    firecrawl is only included if FIRECRAWL_API_KEY is set.

    Returns:
        Dict of server_name -> MCP server config suitable for ClaudeAgentOptions.
    """
    servers: dict[str, dict[str, Any]] = {}

    # Context7 — library documentation lookup (always available)
    servers["context7"] = {
        "command": "npx",
        "args": ["-y", "@upstash/context7-mcp"],
    }

    # Firecrawl — web crawling and research (requires API key)
    firecrawl_key = os.environ.get("FIRECRAWL_API_KEY", "")
    if firecrawl_key:
        servers["firecrawl"] = {
            "command": "npx",
            "args": ["-y", "firecrawl-mcp"],
            "env": {"FIRECRAWL_API_KEY": firecrawl_key},
        }

    # Sequential thinking — structured reasoning (always available)
    servers["sequential-thinking"] = {
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-sequential-thinking"],
    }

    return servers
