"""Entry point for python -m autonomous_coder.

Supports three execution modes:
  SDK CLI (default):  autonomous-coder task_spec.txt --project /path/to/project
  TUI:               autonomous-coder --tui "Add auth"
  Legacy CLI:        autonomous-coder --legacy-cli "Add auth"
"""
import argparse
import asyncio
import sys
from pathlib import Path


def main() -> None:
    """Parse arguments and dispatch to SDK, TUI, or legacy CLI mode."""
    parser = argparse.ArgumentParser(
        prog="autonomous-coder",
        description="Autonomous multi-phase coding agent built on Claude Agent SDK",
    )
    parser.add_argument(
        "task",
        nargs="?",
        default=None,
        help="Path to task specification file, or inline task description",
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
    parser.add_argument(
        "--tui",
        action="store_true",
        help="Launch the Textual TUI dashboard",
    )
    parser.add_argument(
        "--legacy-cli",
        action="store_true",
        help="Use the legacy per-phase CLI mode",
    )
    # Backward compat: --cli maps to SDK mode (now the default)
    parser.add_argument(
        "--cli",
        action="store_true",
        help=argparse.SUPPRESS,
    )

    args = parser.parse_args()
    project_path = (args.project or Path.cwd()).resolve()

    # TUI mode
    if args.tui:
        task = args.task or ""
        _run_tui(task, project_path)
        return

    # Legacy CLI mode (per-phase orchestration)
    if args.legacy_cli:
        task = args.task or ""
        _run_legacy_cli(task, project_path, verbose=args.verbose)
        return

    # SDK-native mode (default)
    _run_sdk(args, project_path)


def _run_sdk(args: argparse.Namespace, project_path: Path) -> None:
    """Run the SDK-native orchestrator."""
    from .types import AutonomousCoderConfig
    from .sdk_orchestrator import run

    # Determine task path: if it looks like a file path, use it; otherwise treat as inline
    task_path = None
    if args.task:
        candidate = Path(args.task)
        if candidate.exists() and candidate.is_file():
            task_path = candidate.resolve()
        else:
            # Treat as inline task — write to temp file
            import tempfile
            tmp = tempfile.NamedTemporaryFile(
                mode="w", suffix=".txt", prefix="task_", delete=False
            )
            tmp.write(args.task)
            tmp.close()
            task_path = Path(tmp.name)

    config = AutonomousCoderConfig(
        task_path=task_path,
        project_dir=project_path,
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

    result = asyncio.run(run(config))

    if result.status in ("success", "end_turn"):
        sys.exit(0)
    else:
        sys.exit(1)


def _run_tui(task: str, project_path: Path) -> None:
    """Launch the Textual TUI."""
    from .app import AutonomousCoderApp

    app = AutonomousCoderApp(task=task, project_path=project_path)
    app.run()


def _run_legacy_cli(task: str, project_path: Path, *, verbose: bool = False) -> None:
    """Run the legacy per-phase pipeline headlessly."""
    if not task:
        print("Error: task is required in --legacy-cli mode", file=sys.stderr)
        sys.exit(1)

    from .agents import (
        CoderPhaseRunner,
        ExplorerPhaseRunner,
        PlannerPhaseRunner,
        ResearchPhaseRunner,
    )
    from .cli_adapter import CliAdapter
    from .config import OrchestratorConfig
    from .orchestrator import AgentOrchestrator

    adapter = CliAdapter(verbose=verbose)
    config = OrchestratorConfig(project_path=project_path)
    orchestrator = AgentOrchestrator(config=config, app=adapter)

    runners = {
        "research": ResearchPhaseRunner(orchestrator.factory, orchestrator),
        "explore": ExplorerPhaseRunner(orchestrator.factory, orchestrator),
        "plan": PlannerPhaseRunner(orchestrator.factory, orchestrator),
        "code": CoderPhaseRunner(orchestrator.factory, orchestrator),
    }

    print("Autonomous Coder — Legacy CLI Mode")
    print(f"Task: {task}")
    print(f"Project: {project_path}")

    results = asyncio.run(orchestrator.run_pipeline(task, runners))
    adapter.print_summary(results)

    all_ok = all(r.success for r in results.values())
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
