"""Terminal display adapters for the EventHandler protocol.

CliEventHandler renders streaming output to stdout.
Additional adapters (TUI, JSON, etc.) can implement the same EventHandler protocol.
"""

from __future__ import annotations


class CliEventHandler:
    """Prints streaming text and tool summaries to stdout."""

    def __init__(self, *, verbose: bool = False) -> None:
        self.verbose = verbose
        self._current_tool: str | None = None

    def on_text(self, text: str) -> None:
        print(text, end="", flush=True)

    def on_tool_start(self, tool_name: str) -> None:
        self._current_tool = tool_name
        print(f"\n  [{tool_name}] ", end="", flush=True)

    def on_tool_input_chunk(self, json_chunk: str) -> None:
        if self.verbose:
            print(json_chunk, end="", flush=True)

    def on_tool_end(self) -> None:
        if not self.verbose:
            print("done", flush=True)
        else:
            print(flush=True)
        self._current_tool = None

    def on_progress(self, phase: str, status: str, detail: str) -> None:
        symbol = {
            "starting": "->",
            "in_progress": "..",
            "complete": "OK",
            "skipped": "--",
            "error": "!!",
        }
        print(f"\n[{symbol.get(status, '??')}] {phase}: {detail}")

    def on_cost_update(self, total_cost: float, session_id: str) -> None:
        sid = session_id[:8] if session_id else "unknown"
        print(f"\n--- Cost: ${total_cost:.4f} | Session: {sid} ---")

    def on_complete(self, result: str | None, success: bool) -> None:
        status = "SUCCESS" if success else "FAILED"
        print(f"\n{'=' * 60}\n  Session {status}\n{'=' * 60}")
        if result:
            print(f"\n{result}")
