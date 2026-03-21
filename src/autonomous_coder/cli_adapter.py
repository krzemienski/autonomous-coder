"""CLI adapter that prints orchestrator messages to stdout.

Provides the same ``post_message()`` interface that the Textual App uses,
so the AgentOrchestrator can run headlessly with real-time console output.
"""
from __future__ import annotations

import sys
import time
from typing import Any

from .messages import (
    AgentCompleted,
    AgentError,
    AgentLifecycle,
    AgentOutput,
    AgentStarted,
    CostUpdate,
    PhaseCompleted,
    PhaseStarted,
    SecurityBlock,
)


class CliAdapter:
    """Headless message sink that prints orchestrator events to stdout.

    Drop-in replacement for ``AutonomousCoderApp`` when running in CLI mode.
    The ``AgentOrchestrator`` calls ``self.app.post_message(msg)`` — this class
    fulfils that contract by printing human-readable lines to the terminal.
    """

    def __init__(self, *, verbose: bool = False) -> None:
        """Initialize the CLI adapter.

        Args:
            verbose: When True, stream all agent text output to stdout.
        """
        self.verbose = verbose
        self._start_time = time.time()
        self._current_phase: str = ""
        self._total_cost: float = 0.0

    # ------------------------------------------------------------------
    # Duck-type interface expected by AgentOrchestrator
    # ------------------------------------------------------------------

    def post_message(self, message: Any) -> None:
        """Dispatch a Textual-style message to the appropriate printer."""
        if isinstance(message, PhaseStarted):
            self._on_phase_started(message)
        elif isinstance(message, PhaseCompleted):
            self._on_phase_completed(message)
        elif isinstance(message, AgentStarted):
            self._on_agent_started(message)
        elif isinstance(message, AgentOutput):
            self._on_agent_output(message)
        elif isinstance(message, AgentCompleted):
            self._on_agent_completed(message)
        elif isinstance(message, AgentError):
            self._on_agent_error(message)
        elif isinstance(message, CostUpdate):
            self._on_cost_update(message)
        elif isinstance(message, AgentLifecycle):
            self._on_agent_lifecycle(message)
        elif isinstance(message, SecurityBlock):
            self._on_security_block(message)

    # ------------------------------------------------------------------
    # Printers
    # ------------------------------------------------------------------

    def _elapsed(self) -> str:
        secs = int(time.time() - self._start_time)
        m, s = divmod(secs, 60)
        return f"{m:02d}:{s:02d}"

    def _ts(self) -> str:
        """Return a compact timestamp for verbose output."""
        return time.strftime("%H:%M:%S")

    # -- Lifecycle states mapped to human-readable labels --
    _LIFECYCLE_LABELS = {
        "init": "Initializing agent",
        "connecting": "Connecting to Claude API",
        "prompt_sent": "Prompt sent, waiting for first token",
        "waiting": "Waiting for API response",
        "streaming": "Receiving response stream",
        "tool_calling": "Agent calling tool",
        "tool_result": "Tool result received",
        "budget_check": "Checking budget",
        "complete": "Agent query complete",
        "error": "Error occurred",
    }

    def _on_phase_started(self, msg: PhaseStarted) -> None:
        """Print a banner when a new pipeline phase begins."""
        self._current_phase = msg.phase
        idx = msg.phase_index + 1
        total = msg.total_phases
        print(f"\n{'='*60}")
        print(f"  Phase {idx}/{total}: {msg.phase.upper()}")
        print(f"{'='*60}")
        if self.verbose:
            print(f"  [{self._ts()}] Phase started")

    def _on_phase_completed(self, msg: PhaseCompleted) -> None:
        status = "DONE" if msg.success else "FAILED"
        err = f"\n  Error: {msg.error}" if msg.error else ""
        print(f"  [{status}] {msg.phase} — ${msg.cost:.4f} in {msg.duration:.1f}s{err}")

    def _on_agent_started(self, msg: AgentStarted) -> None:
        print(f"\n  >> Agent: {msg.agent_name} ({msg.phase})")
        if self.verbose:
            print(f"     [{self._ts()}] Agent spawned")

    def _on_agent_lifecycle(self, msg: AgentLifecycle) -> None:
        """Print lifecycle state transitions — always shown in verbose mode."""
        if not self.verbose:
            return
        label = self._LIFECYCLE_LABELS.get(msg.state, msg.state)
        detail = f" — {msg.detail}" if msg.detail else ""
        print(f"     [{self._ts()}] {label}{detail}")

    def _on_agent_output(self, msg: AgentOutput) -> None:
        """Print agent output; tool calls always shown, text only in verbose mode."""
        if msg.block_type == "tool":
            if self.verbose:
                print(f"     [{self._ts()}] Tool: {msg.text}")
            else:
                print(f"     {msg.text}")
        elif self.verbose:
            for line in msg.text.splitlines():
                print(f"     {line}")

    def _on_agent_completed(self, msg: AgentCompleted) -> None:
        icon = "+" if msg.success else "x"
        err = f" — {msg.error}" if msg.error else ""
        print(f"  [{icon}] {msg.agent_name} ${msg.cost:.4f} ({msg.duration:.1f}s){err}")

    def _on_agent_error(self, msg: AgentError) -> None:
        print(f"  [ERROR] {msg.agent_name}: {msg.error}", file=sys.stderr)
        if self.verbose:
            print(f"     [{self._ts()}] Fatal error in {msg.phase}", file=sys.stderr)

    def _on_cost_update(self, msg: CostUpdate) -> None:
        self._total_cost = msg.total_cost
        if self.verbose:
            print(f"     [{self._ts()}] Cost: ${msg.cost:.4f} (total: ${msg.total_cost:.4f})")

    def _on_security_block(self, msg: SecurityBlock) -> None:
        print(f"  [BLOCKED] {msg.agent_name}: tool '{msg.tool_name}' — {msg.reason}")

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------

    def print_summary(self, results: dict[str, Any]) -> None:
        """Print a final summary of the pipeline run."""
        print(f"\n{'='*60}")
        print(f"  PIPELINE COMPLETE — {self._elapsed()} elapsed")
        print(f"  Total cost: ${self._total_cost:.4f}")
        phases = len(results)
        succeeded = sum(1 for r in results.values() if r.success)
        failed = phases - succeeded
        print(f"  Phases: {succeeded} succeeded, {failed} failed")
        print(f"{'='*60}")
