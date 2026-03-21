"""Real-time cost tracking widget."""
from textual.app import ComposeResult
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Static

BUDGET_WARNING_THRESHOLD = 0.80  # flash warning at 80% of budget


class CostDisplay(Widget):
    """Shows total cost and per-agent breakdown; warns when nearing budget."""

    total_cost: reactive[float] = reactive(0.0)
    budget_limit: reactive[float] = reactive(5.0)
    agent_costs: reactive[dict] = reactive(dict)

    DEFAULT_CSS = """
    CostDisplay {
        padding: 1;
        border: solid $accent;
    }
    CostDisplay.warning {
        border: solid $warning;
    }
    CostDisplay #total-cost {
        text-style: bold;
        text-align: center;
    }
    CostDisplay #agent-breakdown {
        margin-top: 1;
    }
    """

    def compose(self) -> ComposeResult:
        """Lay out the total cost, budget label, and per-agent breakdown."""
        yield Static("$0.0000", id="total-cost")
        yield Static("Budget: $5.00", id="budget-label")
        yield Static("", id="agent-breakdown")

    def watch_total_cost(self, cost: float) -> None:
        """Update the displayed total cost and check budget threshold."""
        self.query_one("#total-cost", Static).update(f"[bold]${cost:.4f}[/bold]")
        self._check_budget_warning(cost)

    def watch_budget_limit(self, limit: float) -> None:
        """Update the budget label when the limit changes."""
        self.query_one("#budget-label", Static).update(f"Budget: ${limit:.2f}")

    def watch_agent_costs(self, costs: dict) -> None:
        """Re-render the per-agent cost breakdown."""
        lines = []
        for agent, cost in costs.items():
            lines.append(f"  {agent}: ${cost:.4f}")
        breakdown = self.query_one("#agent-breakdown", Static)
        breakdown.update("\n".join(lines) if lines else "No agents yet")

    def _check_budget_warning(self, cost: float) -> None:
        """Toggle the 'warning' CSS class when cost nears the budget limit."""
        at_risk = self.budget_limit > 0 and (cost / self.budget_limit) >= BUDGET_WARNING_THRESHOLD
        if at_risk:
            self.add_class("warning")
        else:
            self.remove_class("warning")

    def record_cost(self, agent_name: str, cost: float, total_cost: float) -> None:
        """Update per-agent cost and total."""
        costs = dict(self.agent_costs)
        costs[agent_name] = cost
        self.agent_costs = costs
        self.total_cost = total_cost
