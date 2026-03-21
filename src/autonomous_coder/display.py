"""Terminal output formatting for the autonomous coder CLI mode.

Provides structured, timestamped output that mirrors the quickstart's
visual style. Used by hooks and the orchestrator for observability
output that fires outside the context window.
"""
from __future__ import annotations

import sys
import time
from datetime import datetime
from typing import Any

from .types import AutonomousCoderConfig, SessionResult


class Display:
    """Formats and prints structured output to the terminal.

    This class is NOT consumed by Claude — it provides human-readable
    observability output via hooks, which fire outside the context window.
    """

    def __init__(self, *, verbose: bool = False) -> None:
        self.verbose = verbose
        self._start_time = time.monotonic()
        self._subagent_count = 0

    def _ts(self) -> str:
        """Return a compact HH:MM:SS timestamp."""
        return datetime.now().strftime("%H:%M:%S")

    def _elapsed(self) -> str:
        """Return elapsed time as MM:SS."""
        secs = int(time.monotonic() - self._start_time)
        m, s = divmod(secs, 60)
        return f"{m:02d}:{s:02d}"

    # ------------------------------------------------------------------
    # Session-level output
    # ------------------------------------------------------------------

    def header(self, config: AutonomousCoderConfig) -> None:
        """Print the session header banner."""
        print()
        print("=" * 60)
        print("  AUTONOMOUS CODER v2.0 — SDK-Native Mode")
        print("=" * 60)
        if config.task_path:
            print(f"  Task: {config.task_path}")
        print(f"  Project: {config.project_dir}")
        print(f"  Model: {config.model or 'claude-opus-4-6'}")
        print(f"  Budget: ${config.max_budget:.2f}")
        print(f"  Max turns: {config.max_turns}")
        print("=" * 60)
        print()

    def result(self, result: SessionResult) -> None:
        """Print the final session result summary."""
        print()
        print("=" * 60)
        print(f"  SESSION COMPLETE — {self._elapsed()} elapsed")
        print(f"  Status: {result.status}")
        print(f"  Total cost: ${result.total_cost_usd:.4f}")
        print(f"  Turns: {result.num_turns}")
        if result.stop_reason:
            print(f"  Stop reason: {result.stop_reason}")
        if result.phases:
            print()
            print("  Phase Summary:")
            for phase in result.phases:
                icon = "+" if phase.status == "completed" else "x"
                print(f"    [{icon}] {phase.phase}: {phase.status}"
                      + (f" — {phase.details}" if phase.details else ""))
        print("=" * 60)

    # ------------------------------------------------------------------
    # Tool-level output (called from hooks)
    # ------------------------------------------------------------------

    def tool_use(self, tool_name: str, tool_input: dict[str, Any]) -> None:
        """Print a tool call event."""
        ts = self._ts()
        if tool_name == "Bash":
            cmd = tool_input.get("command", "")[:80]
            print(f"  [{ts}] Tool: Bash — {cmd}")
        elif tool_name == "Read":
            path = tool_input.get("file_path", "")
            print(f"  [{ts}] Tool: Read — {path}")
        elif tool_name == "Write":
            path = tool_input.get("file_path", "")
            print(f"  [{ts}] Tool: Write — {path}")
        elif tool_name == "Edit":
            path = tool_input.get("file_path", "")
            print(f"  [{ts}] Tool: Edit — {path}")
        elif tool_name == "Glob":
            pattern = tool_input.get("pattern", "")
            print(f"  [{ts}] Tool: Glob — {pattern}")
        elif tool_name == "Grep":
            pattern = tool_input.get("pattern", "")
            print(f"  [{ts}] Tool: Grep — {pattern}")
        elif tool_name == "Agent":
            subagent = tool_input.get("subagent_type", tool_input.get("description", ""))
            print(f"  [{ts}] Tool: Agent — {subagent}")
        elif tool_name in ("WebSearch", "WebFetch"):
            query = tool_input.get("query", tool_input.get("url", ""))
            print(f"  [{ts}] Tool: {tool_name} — {str(query)[:60]}")
        else:
            # MCP tools and others
            if self.verbose:
                summary = str(tool_input)[:60]
                print(f"  [{ts}] Tool: {tool_name} — {summary}")
            else:
                print(f"  [{ts}] Tool: {tool_name}")

    def tool_result(self, tool_name: str, tool_use_id: str | None) -> None:
        """Print a tool completion event (verbose only)."""
        if self.verbose:
            print(f"  [{self._ts()}] Done: {tool_name}")

    def blocked_command(self, command: str, pattern: str) -> None:
        """Print a blocked command warning."""
        print(f"  [{self._ts()}] BLOCKED: '{command[:60]}' — pattern '{pattern}'",
              file=sys.stderr)

    # ------------------------------------------------------------------
    # Subagent-level output (called from hooks)
    # ------------------------------------------------------------------

    def subagent_started(self, agent_id: str) -> None:
        """Print a subagent spawn event."""
        self._subagent_count += 1
        print(f"\n  >> Subagent: {agent_id}")
        print(f"     [{self._ts()}] Spawned")

    def subagent_completed(self, agent_id: str, transcript_path: str = "") -> None:
        """Print a subagent completion event."""
        print(f"  << Subagent completed: {agent_id}")

    # ------------------------------------------------------------------
    # Agent text output
    # ------------------------------------------------------------------

    def agent_text(self, text: str) -> None:
        """Print agent text output (verbose only)."""
        if self.verbose:
            for line in text.splitlines():
                print(f"     {line}")

    def thinking(self, text: str) -> None:
        """Print thinking output (verbose only)."""
        if self.verbose:
            # Show just first few lines of thinking
            lines = text.splitlines()[:3]
            for line in lines:
                print(f"     [think] {line}")
            if len(text.splitlines()) > 3:
                print(f"     [think] ... ({len(text.splitlines())} lines)")

    # ------------------------------------------------------------------
    # Session events
    # ------------------------------------------------------------------

    def session_stopped(self) -> None:
        """Print session stop event."""
        print(f"\n  [{self._ts()}] Session stopped")
