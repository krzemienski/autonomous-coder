"""Entry point for python -m autonomous_coder.

Supports two execution modes:
  TUI (default):  autonomous-coder "Add auth"
  CLI (headless):  autonomous-coder --cli "Add auth"
"""
import argparse
import asyncio
import sys
from pathlib import Path


def main() -> None:
    """Parse arguments and dispatch to TUI or CLI mode."""
    parser = argparse.ArgumentParser(
        prog="autonomous-coder",
        description="AI-powered autonomous coding assistant",
    )
    parser.add_argument(
        "task",
        nargs="*",
        help="Task description (joins multiple words)",
    )
    parser.add_argument(
        "--cli",
        action="store_true",
        help="Run in headless CLI mode (no TUI)",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show full agent text output (CLI mode only)",
    )
    parser.add_argument(
        "--project",
        type=Path,
        default=None,
        help="Project directory (defaults to cwd)",
    )

    args = parser.parse_args()
    task = " ".join(args.task) if args.task else ""
    project_path = args.project or Path.cwd()

    if args.cli:
        _run_cli(task, project_path, verbose=args.verbose)
    else:
        _run_tui(task, project_path)


def _run_tui(task: str, project_path: Path) -> None:
    """Launch the Textual TUI."""
    from .app import AutonomousCoderApp

    app = AutonomousCoderApp(task=task, project_path=project_path)
    app.run()


def _run_cli(task: str, project_path: Path, *, verbose: bool = False) -> None:
    """Run the pipeline headlessly with stdout output."""
    if not task:
        print("Error: task is required in --cli mode", file=sys.stderr)
        print("Usage: autonomous-coder --cli \"Add user authentication\"", file=sys.stderr)
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
        "research": ResearchPhaseRunner(orchestrator.factory),
        "explore": ExplorerPhaseRunner(orchestrator.factory),
        "plan": PlannerPhaseRunner(orchestrator.factory),
        "code": CoderPhaseRunner(orchestrator.factory),
    }

    print(f"Autonomous Coder — CLI Mode")
    print(f"Task: {task}")
    print(f"Project: {project_path}")

    results = asyncio.run(orchestrator.run_pipeline(task, runners))
    adapter.print_summary(results)

    # Exit with appropriate code
    all_ok = all(r.success for r in results.values())
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
