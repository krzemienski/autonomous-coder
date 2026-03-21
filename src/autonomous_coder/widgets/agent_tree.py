"""Tree widget showing agents grouped by phase in the sidebar."""
from textual.widgets import Tree
from textual.widgets.tree import TreeNode

# Status icons
ICON_RUNNING = "▶"
ICON_COMPLETE = "✓"
ICON_ERROR = "✗"
ICON_PENDING = "○"

PHASES = ["research", "explore", "plan", "code"]


class AgentTree(Tree):
    """Sidebar tree showing agents grouped by pipeline phase."""

    def __init__(self, **kwargs) -> None:
        """Initialize the agent tree with empty phase and agent node mappings."""
        super().__init__("Agents", **kwargs)
        self._phase_nodes: dict[str, TreeNode] = {}
        self._agent_nodes: dict[str, TreeNode] = {}
        self._agent_status: dict[str, str] = {}

    def on_mount(self) -> None:
        """Create top-level phase nodes when the widget is mounted."""
        self.root.expand()
        for phase in PHASES:
            node = self.root.add(phase.capitalize(), expand=True)
            self._phase_nodes[phase] = node

    def add_agent(self, agent_name: str, phase: str) -> None:
        """Add a new agent node under the given phase."""
        self._agent_status[agent_name] = "pending"
        parent = self._phase_nodes.get(phase, self.root)
        label = f"{ICON_PENDING} {agent_name}"
        node = parent.add_leaf(label)
        self._agent_nodes[agent_name] = node

    def set_agent_running(self, agent_name: str) -> None:
        """Mark agent as currently running."""
        self._update_agent_icon(agent_name, "running")

    def set_agent_complete(self, agent_name: str, success: bool) -> None:
        """Mark agent as finished (success or error)."""
        status = "complete" if success else "error"
        self._update_agent_icon(agent_name, status)

    def _update_agent_icon(self, agent_name: str, status: str) -> None:
        """Replace the icon prefix on an agent's tree node label."""
        node = self._agent_nodes.get(agent_name)
        if node is None:
            return
        icon_map = {
            "running": ICON_RUNNING,
            "complete": ICON_COMPLETE,
            "error": ICON_ERROR,
            "pending": ICON_PENDING,
        }
        icon = icon_map.get(status, ICON_PENDING)
        self._agent_status[agent_name] = status
        node.set_label(f"{icon} {agent_name}")
