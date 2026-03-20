"""Orchestrator configuration dataclasses and MCP server registry."""
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class RoleConfig:
    """Configuration for a single agent role."""

    model: str
    tools: list[str]
    mcp_keys: list[str]  # keys into MCP_SERVERS dict
    budget_limit: float
    max_turns: int


@dataclass
class OrchestratorConfig:
    """Top-level orchestrator configuration."""

    project_path: Path
    total_budget: float = 5.0
    roles: dict[str, RoleConfig] = field(
        default_factory=lambda: {
            "research": RoleConfig(
                model="claude-sonnet-4-5-20250514",
                tools=["Read", "Grep", "Glob", "WebSearch", "WebFetch"],
                mcp_keys=["firecrawl-mcp", "Context7"],
                budget_limit=0.50,
                max_turns=25,
            ),
            "explore": RoleConfig(
                model="claude-sonnet-4-5-20250514",
                tools=["Read", "Grep", "Glob"],
                mcp_keys=["serena"],
                budget_limit=0.50,
                max_turns=20,
            ),
            "plan": RoleConfig(
                model="claude-sonnet-4-5-20250514",
                tools=["Read", "Grep", "Glob"],
                mcp_keys=["sequential-thinking", "serena"],
                budget_limit=1.00,
                max_turns=10,
            ),
            "code": RoleConfig(
                model="claude-sonnet-4-5-20250514",
                tools=["Read", "Write", "Edit", "Bash", "Grep", "Glob"],
                mcp_keys=["serena", "Context7"],
                budget_limit=2.00,
                max_turns=30,
            ),
            "reviewer": RoleConfig(
                model="claude-sonnet-4-5-20250514",
                tools=["Read", "Grep", "Glob"],
                mcp_keys=["serena"],
                budget_limit=0.25,
                max_turns=10,
            ),
        }
    )


MCP_SERVERS: dict[str, dict] = {
    "serena": {"command": "uvx", "args": ["serena"], "env": {}},
    "sequential-thinking": {
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-sequential-thinking"],
    },
    "Context7": {
        "command": "npx",
        "args": ["-y", "@upstash/context7-mcp"],
    },
    "firecrawl-mcp": {
        "command": "npx",
        "args": ["-y", "firecrawl-mcp"],
        "env": {"FIRECRAWL_API_KEY": "${FIRECRAWL_API_KEY}"},
    },
}
