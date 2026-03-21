"""TabbedContent widget giving each agent its own output pane."""
from textual.widgets import TabbedContent, TabPane, RichLog


class AgentTabs(TabbedContent):
    """Dynamic tabbed view — one tab per agent, added on AgentStarted."""

    def __init__(self, **kwargs) -> None:
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

    def append_output(self, agent_name: str, text: str, block_type: str = "text") -> None:
        """Write formatted output to the agent's RichLog."""
        log = self._agent_logs.get(agent_name)
        if log is None:
            return
        if block_type == "tool":
            log.write(f"[bold cyan]\\[tool][/bold cyan] {text}")
        elif block_type == "error":
            log.write(f"[bold red]{text}[/bold red]")
        else:
            log.write(text)

    def focus_agent(self, agent_name: str) -> None:
        """Switch active tab to the named agent."""
        tab_id = f"tab-{agent_name}"
        self.active = tab_id
