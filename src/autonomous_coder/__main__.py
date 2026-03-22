"""Entry point: CLI parsing + process supervision with retry.

Usage:
  autonomous-coder "Add JWT authentication"                 # CLI mode (default)
  autonomous-coder "Add JWT auth" --project ./myapp         # Specify project
  autonomous-coder --resume                                 # Resume last session
  autonomous-coder --plan-only "Add caching"                # Stop after planning
  autonomous-coder --budget 10.0 --verbose "Add auth"       # Custom budget
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path


class AutonomousCoderError(Exception):
    """User-friendly error with remediation hint."""

    def __init__(self, message: str, hint: str = "") -> None:
        super().__init__(message)
        self.hint = hint


MAX_RETRIES = 3


def main() -> None:
    """Parse arguments and run the session with supervision."""
    parser = argparse.ArgumentParser(
        prog="autonomous-coder",
        description="Autonomous multi-phase coding agent (Claude Agent SDK)",
    )
    parser.add_argument(
        "task", nargs="*", help="Task description (joins multiple words)"
    )
    parser.add_argument(
        "--project", "-p", type=Path, default=None, help="Target project directory"
    )
    parser.add_argument("--model", "-m", default=None, help="Override model")
    parser.add_argument(
        "--budget", type=float, default=None, help="Max cost in USD (default: 5.0)"
    )
    parser.add_argument(
        "--max-turns", type=int, default=None, help="Max agent loop turns"
    )
    parser.add_argument(
        "--timeout", type=int, default=None, help="Wall-clock timeout in seconds"
    )
    parser.add_argument(
        "--effort",
        choices=["low", "medium", "high"],
        default=None,
        help="Reasoning effort level",
    )
    parser.add_argument(
        "--thinking-budget", type=int, default=None,
        help="Extended thinking token budget (default: 32000)",
    )
    parser.add_argument(
        "--research-model", default=None,
        help="Model for research subagents (default: claude-sonnet-4-6)",
    )
    parser.add_argument(
        "--implement-model", default=None,
        help="Model for implementation subagents (default: claude-opus-4-6)",
    )
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    parser.add_argument(
        "--resume", action="store_true", help="Resume the last session"
    )
    parser.add_argument(
        "--plan-only", action="store_true", help="Stop after Phase 3 (Plan)"
    )

    args = parser.parse_args()
    task = " ".join(args.task) if args.task else ""
    project_path = (args.project or Path.cwd()).resolve()

    if not task and not args.resume:
        parser.print_help()
        print("\nError: task description is required (or use --resume)", file=sys.stderr)
        sys.exit(1)

    # Build config overrides from CLI args
    cli_overrides: dict = {}
    if args.model:
        cli_overrides["model"] = args.model
    if args.budget is not None:
        cli_overrides["budget_limit"] = args.budget
    if args.max_turns is not None:
        cli_overrides["max_turns"] = args.max_turns
    if args.timeout is not None:
        cli_overrides["max_duration_seconds"] = args.timeout
    if args.effort:
        cli_overrides["effort"] = args.effort
    if args.thinking_budget is not None:
        cli_overrides["thinking_budget"] = args.thinking_budget
    if args.research_model:
        cli_overrides["research_model"] = args.research_model
    if args.implement_model:
        cli_overrides["implement_model"] = args.implement_model
    if args.verbose:
        cli_overrides["verbose"] = True
    if args.plan_only:
        cli_overrides["plan_only"] = True

    from .display import CliEventHandler
    from .config import load_config
    from .session import SessionState, load_last_session_id

    config = load_config(project_path, cli_overrides)

    if args.resume:
        config.resume_session_id = load_last_session_id(project_path)
        if not config.resume_session_id:
            print("No previous session found to resume.", file=sys.stderr)
            sys.exit(1)
        # Show previous progress
        prev = SessionState.load(
            project_path / ".autonomous-coder" / "session.json"
        )
        if prev:
            print(f"Resuming session {prev.session_id[:8]}...")
            print(f"  Task: {prev.task}")
            print(f"  Budget used: ${prev.budget_used:.4f}")
        if not task:
            task = prev.task if prev else "Continue from where you left off."

    handler = CliEventHandler(verbose=config.verbose)

    print(f"Autonomous Coder v3")
    print(f"Task: {task}")
    print(f"Project: {project_path}")
    print(f"Model: {config.model} | Budget: ${config.budget_limit:.2f} | Effort: {config.effort} | Thinking: {config.thinking_budget}t")
    print("=" * 60)

    try:
        state = asyncio.run(
            _run_with_supervision(config, task, handler)
        )
    except AutonomousCoderError as e:
        print(f"\nError: {e}", file=sys.stderr)
        if e.hint:
            print(f"Hint: {e.hint}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nInterrupted by user.", file=sys.stderr)
        sys.exit(130)

    sys.exit(0 if state and state.success else 1)


async def _run_with_supervision(
    config, task: str, handler
):
    """Run session with retry on transient failures."""
    from .session import SessionManager, load_last_session_id

    manager: SessionManager | None = None

    for attempt in range(MAX_RETRIES):
        try:
            async with asyncio.timeout(config.max_duration_seconds):
                manager = SessionManager(config, handler)
                return await manager.run(task)
        except TimeoutError:
            print(
                f"\nSession timed out after {config.max_duration_seconds}s",
                file=sys.stderr,
            )
            if manager:
                await manager.interrupt()
            raise AutonomousCoderError(
                "Session timed out",
                hint=f"Increase timeout with --timeout {config.max_duration_seconds * 2}",
            )
        except (ConnectionError, OSError) as e:
            if attempt < MAX_RETRIES - 1:
                config.resume_session_id = load_last_session_id(
                    config.project_path
                )
                print(
                    f"Connection error, resuming (attempt {attempt + 2}/{MAX_RETRIES}): {e}",
                    file=sys.stderr,
                )
            else:
                raise AutonomousCoderError(
                    f"Session failed after {MAX_RETRIES} attempts: {e}",
                    hint="Check network connectivity and API key validity.",
                ) from e

    return None


if __name__ == "__main__":
    main()
