"""TabbedContent widget giving each agent its own output pane."""
from __future__ import annotations

import time
from typing import Any

from textual.widgets import TabbedContent, TabPane, RichLog


# Lifecycle state → (Rich markup color, human label)
_LIFECYCLE_STYLES: dict[str, tuple[str, str]] = {
    "init": ("dim", "Initializing"),
    "connecting": ("yellow", "Connecting to API"),
    "prompt_sent": ("yellow", "Prompt sent, waiting for first token"),
    "waiting": ("yellow", "Waiting for response"),
    "streaming": ("green", "Streaming response"),
    "tool_calling": ("cyan", "Calling tool"),
    "tool_result": ("cyan", "Tool result received"),
    "budget_check": ("yellow", "Budget check"),
    "complete": ("green bold", "Complete"),
    "error": ("red bold", "Error"),
}


class AgentTabs(TabbedContent):
    """Dynamic tabbed view — one tab per agent, added on AgentStarted."""

    def __init__(self, **kwargs: Any) -> None:
        """Initialize with an empty agent-to-log mapping."""
        super().__init__(**kwargs)
        self._agent_logs: dict[str, RichLog] = {}

    def add_agent_tab(self, agent_name: str) -> None:
        """Create a new tab with a RichLog for the given agent."""
        if agent_name in self._agent_logs:
            return
        log = RichLog(highlight=True, markup=True, id=f"log-{agent_name}")
        self._agent_logs[agent_name] = log
        pane = TabPane(agent_name, log, id=f"tab-{agent_name}")
        self.add_pane(pane)

    def append_output(self, agent_name: str, text: Any, block_type: str = "text") -> None:
        """Write formatted output to the agent's RichLog.

        Args:
            agent_name: Target agent tab.
            text: Either a plain string or an ``AgentLifecycle`` message.
            block_type: One of "text", "tool", "error", "lifecycle".
        """
        log = self._agent_logs.get(agent_name)
        if log is None:
            return

        if block_type == "lifecycle":
            self._write_lifecycle(log, text)
        elif block_type == "tool":
            log.write(f"[bold cyan]\\[tool][/bold cyan] {text}")
        elif block_type == "error":
            log.write(f"[bold red]{text}[/bold red]")
        else:
            log.write(str(text))

    def _write_lifecycle(self, log: RichLog, msg: Any) -> None:
        """Render a lifecycle message with color-coded state and timestamp."""
        ts = time.strftime("%H:%M:%S")
        state = getattr(msg, "state", "unknown")
        detail = getattr(msg, "detail", "")

        style, label = _LIFECYCLE_STYLES.get(state, ("dim", state))
        detail_str = f" — {detail}" if detail else ""
        log.write(f"[{style}]\\[{ts}] {label}{detail_str}[/{style}]")

    def focus_agent(self, agent_name: str) -> None:
        """Switch active tab to the named agent."""
        tab_id = f"tab-{agent_name}"
        self.active = tab_id
