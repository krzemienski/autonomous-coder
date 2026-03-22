"""Session configuration with CLI > TOML > defaults priority."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class SessionConfig:
    """Complete session configuration. Assembled from CLI args + TOML files."""

    # Required
    project_path: Path = field(default_factory=Path.cwd)

    # Model
    model: str = "claude-opus-4-6"
    research_model: str | None = None   # Default: claude-sonnet-4-6
    implement_model: str | None = None  # Default: claude-opus-4-6
    validate_model: str | None = None   # Default: claude-sonnet-4-6
    effort: str = "high"

    # Thinking
    thinking_budget: int = 32000  # Extended thinking token budget

    # Budget & Safety
    budget_limit: float = 5.0
    max_turns: int = 200
    max_duration_seconds: int = 3600  # 1 hour wall-clock

    # Session management
    resume_session_id: str | None = None

    # MCP servers (additional, beyond built-ins)
    extra_mcp_servers: dict[str, dict] = field(default_factory=dict)

    # Security
    extra_allowed_commands: set[str] = field(default_factory=set)
    permission_mode: str = "acceptEdits"

    # Output
    verbose: bool = False
    ui_mode: str = "cli"  # "cli" or "tui"

    # Workflow control
    plan_only: bool = False
    dry_run: bool = False



def load_config(
    project_path: Path,
    cli_overrides: dict | None = None,
) -> SessionConfig:
    """Load config from TOML files with CLI overrides applied last.

    Priority: CLI args > project .autonomous-coder.toml > user config > defaults.
    """
    config = SessionConfig(project_path=project_path)

    # User-level config
    user_config = Path.home() / ".config" / "autonomous-coder" / "config.toml"
    if user_config.exists():
        _apply_toml(config, user_config)

    # Project-level config
    project_config = project_path / ".autonomous-coder.toml"
    if project_config.exists():
        _apply_toml(config, project_config)

    # CLI overrides (highest priority)
    if cli_overrides:
        for key, value in cli_overrides.items():
            if value is not None and hasattr(config, key):
                setattr(config, key, value)

    return config


def _apply_toml(config: SessionConfig, path: Path) -> None:
    """Apply settings from a TOML file to the config."""
    with open(path, "rb") as f:
        data = tomllib.load(f)

    session = data.get("session", {})
    for key in (
        "model", "research_model", "implement_model", "validate_model",
        "effort", "thinking_budget", "budget_limit", "max_turns", "max_duration_seconds",
    ):
        if key in session:
            setattr(config, key, session[key])

    security = data.get("security", {})
    if "extra_allowed_commands" in security:
        config.extra_allowed_commands.update(security["extra_allowed_commands"])

    mcp = data.get("mcp", {})
    for name, server_config in mcp.items():
        if isinstance(server_config, dict) and "command" in server_config:
            config.extra_mcp_servers[name] = server_config
