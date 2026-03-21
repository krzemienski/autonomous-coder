"""Shared type definitions for the autonomous coder."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class AutonomousCoderConfig:
    """Configuration for an autonomous coder session.

    Attributes:
        task_path: Path to the task specification file.
        project_dir: Target project directory for the agent to work in.
        model: Override model for the orchestrator agent.
        research_model: Model for research subagents (sonnet/opus/haiku).
        implement_model: Model for implementation subagents.
        validate_model: Model for validation subagents.
        max_turns: Maximum agent loop turns.
        max_budget: Maximum cost ceiling in USD.
        effort: Thinking effort level.
        thinking_budget: Extended thinking token budget.
        verbose: Show detailed output including tool calls and thinking.
        resume_session: Session ID to resume from.
        cli_mode: Run in headless CLI mode (no TUI).
    """

    task_path: Path | None = None
    project_dir: Path = field(default_factory=Path.cwd)
    model: str | None = None
    research_model: str | None = None
    implement_model: str | None = None
    validate_model: str | None = None
    max_turns: int = 200
    max_budget: float = 50.0
    effort: str = "high"
    thinking_budget: int = 32000
    verbose: bool = False
    resume_session: str | None = None
    cli_mode: bool = False


@dataclass
class PhaseEvent:
    """Tracks a phase transition for observability."""

    phase: str
    status: str  # "started", "completed", "failed"
    details: str = ""
    timestamp: str = ""
    cost: float = 0.0
    duration_seconds: float = 0.0


@dataclass
class SessionResult:
    """Result from a completed autonomous coder session."""

    session_id: str = ""
    status: str = ""  # "success", "error", etc.
    total_cost_usd: float = 0.0
    num_turns: int = 0
    elapsed_seconds: float = 0.0
    phases: list[PhaseEvent] = field(default_factory=list)
    result: str | None = None
    stop_reason: str | None = None
    usage: dict[str, Any] | None = None
