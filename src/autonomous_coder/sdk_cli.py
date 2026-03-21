"""CLI entry point for the SDK-native autonomous coder.

Provides a clean CLI interface that feeds into the SDK orchestrator.
The TUI mode from the original app.py is preserved separately.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from .types import AutonomousCoderConfig


def sdk_main() -> None:
    """Parse CLI arguments and run the SDK-native orchestrator."""
    parser = argparse.ArgumentParser(
        prog="autonomous-coder",
        description="Autonomous multi-phase coding agent built on Claude Agent SDK",
    )
    parser.add_argument(
        "task",
        nargs="?",
        default=None,
        help="Path to task specification file",
    )
    parser.add_argument(
        "--project", "-p",
        type=Path,
        default=None,
        help="Target project directory (defaults to cwd)",
    )
    parser.add_argument(
        "--model", "-m",
        default=None,
        help="Override orchestrator model (e.g. claude-opus-4-6)",
    )
    parser.add_argument(
        "--research-model",
        default=None,
        help="Model for research subagents (sonnet/opus/haiku)",
    )
    parser.add_argument(
        "--implement-model",
        default=None,
        help="Model for implementation subagents (sonnet/opus/haiku)",
    )
    parser.add_argument(
        "--max-turns",
        type=int,
        default=200,
        help="Maximum agent loop turns (default: 200)",
    )
    parser.add_argument(
        "--max-budget",
        type=float,
        default=50.0,
        help="Maximum cost in USD (default: 50.0)",
    )
    parser.add_argument(
        "--effort",
        choices=["low", "medium", "high", "max"],
        default="high",
        help="Thinking effort level (default: high)",
    )
    parser.add_argument(
        "--thinking-budget",
        type=int,
        default=32000,
        help="Extended thinking token budget (default: 32000)",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show detailed output including tool calls and thinking",
    )
    parser.add_argument(
        "--resume",
        default=None,
        help="Resume a previous session by ID",
    )

    # Legacy compatibility
    parser.add_argument(
        "--cli",
        action="store_true",
        help="(Legacy) Run in CLI mode — this is now the default",
    )
    parser.add_argument(
        "--tui",
        action="store_true",
        help="Launch the Textual TUI dashboard instead of CLI mode",
    )

    args = parser.parse_args()

    # Handle TUI mode
    if args.tui:
        task = args.task or ""
        project_path = args.project or Path.cwd()
        _run_tui(task, project_path)
        return

    # SDK-native CLI mode (default)
    task_path = Path(args.task).resolve() if args.task else None

    config = AutonomousCoderConfig(
        task_path=task_path,
        project_dir=(args.project or Path.cwd()).resolve(),
        model=args.model,
        research_model=args.research_model,
        implement_model=args.implement_model,
        max_turns=args.max_turns,
        max_budget=args.max_budget,
        effort=args.effort,
        thinking_budget=args.thinking_budget,
        verbose=args.verbose,
        resume_session=args.resume,
        cli_mode=True,
    )

    from .sdk_orchestrator import run

    result = asyncio.run(run(config))

    if result.status in ("success", "end_turn"):
        sys.exit(0)
    else:
        sys.exit(1)


def _run_tui(task: str, project_path: Path) -> None:
    """Launch the legacy Textual TUI."""
    from .app import AutonomousCoderApp

    app = AutonomousCoderApp(task=task, project_path=project_path)
    app.run()


if __name__ == "__main__":
    sdk_main()
