"""Main Textual application for the Autonomous Coder TUI."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.reactive import reactive
from textual.widgets import Header, Footer, Input
from textual.worker import Worker

from .agents import ResearchPhaseRunner, ExplorerPhaseRunner, PlannerPhaseRunner, CoderPhaseRunner
from .config import OrchestratorConfig
from .messages import (
    AgentStarted,
    AgentOutput,
    AgentCompleted,
    AgentError,
    CostUpdate,
    SecurityBlock,
    PhaseStarted,
    PhaseCompleted,
)
from .orchestrator import AgentOrchestrator
from .widgets import (
    AgentTree,
    AgentTabs,
    ProgressPanel,
    TaskDetail,
    CostDisplay,
)


class AutonomousCoderApp(App):
    """Top-level TUI application.

    Composes a sidebar (agent tree + progress), a main area (tabbed agent
    output + task detail + cost display), and a task input bar. Orchestrates
    the Research -> Explore -> Plan -> Code pipeline via ``AgentOrchestrator``.
    """

    CSS = """
Screen { layout: vertical; }
Header { background: $primary-darken-2; }
#content { height: 1fr; }
#task-input { dock: bottom; height: 3; margin: 0 1; border: solid $primary-darken-1; }
#sidebar { width: 30; height: 100%; border-right: solid $primary-darken-1; }
#agent-tree { height: 60%; border-bottom: solid $primary-darken-1; }
#progress { height: 40%; padding: 1; }
#main { height: 100%; }
#agent-tabs { height: 70%; }
#details { height: 30%; border-top: solid $primary-darken-1; }
#task-detail { width: 1fr; padding: 1; border-right: solid $primary-darken-1; }
#cost-display { width: 30; padding: 1; text-align: center; }
CostDisplay .cost-total { text-style: bold; color: $success; }
CostDisplay .cost-warning { color: $warning; }
CostDisplay .cost-danger { color: $error; }
StreamingLog { scrollbar-size: 1 1; }
ProgressPanel ProgressBar { margin: 1 0; }
.status-running { color: $primary; }
.status-complete { color: $success; }
.status-error { color: $error; }
.status-pending { color: $text-muted; }
"""

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("p", "pause", "Pause"),
        ("r", "resume", "Resume"),
        ("c", "cancel_agent", "Cancel"),
        ("slash", "command_palette", "Command"),
        ("tab", "cycle_agents", "Next Agent"),
    ]

    current_phase: reactive[str] = reactive("idle")
    total_cost: reactive[float] = reactive(0.0)

    def __init__(
        self,
        task: str = "",
        project_path: str | Path | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize the TUI application.

        Args:
            task: Optional task description to auto-start on launch.
            project_path: Working directory for the orchestrator.
            **kwargs: Additional arguments forwarded to ``App.__init__``.
        """
        super().__init__(**kwargs)
        self._task = task
        self.project_path = Path(project_path) if project_path else Path.cwd()
        self._orchestrator: AgentOrchestrator | None = None

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------

    def compose(self) -> ComposeResult:
        """Build the widget layout: header, input bar, sidebar + main area, footer."""
        yield Header()
        yield Input(placeholder="Enter a task and press Enter...", id="task-input")
        with Horizontal(id="content"):
            with Vertical(id="sidebar"):
                yield AgentTree(id="agent-tree")
                yield ProgressPanel(id="progress")
            with Vertical(id="main"):
                yield AgentTabs(id="agent-tabs")
                with Horizontal(id="details"):
                    yield TaskDetail(id="task-detail")
                    yield CostDisplay(id="cost-display")
        yield Footer()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_ready(self) -> None:
        """Auto-start pipeline if a task was passed via CLI. Fires after all widgets mount."""
        if self._task:
            task_input = self.query_one("#task-input", Input)
            task_input.display = False
            self.run_worker(self.run_task(self._task), name="pipeline", exclusive=True)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle task submission from the TUI input widget."""
        task = event.value.strip()
        if not task:
            return
        event.input.display = False
        self.run_worker(self.run_task(task), name="pipeline", exclusive=True)

    # ------------------------------------------------------------------
    # Message handlers
    # ------------------------------------------------------------------

    def on_agent_started(self, message: AgentStarted) -> None:
        """Register a new agent in the tree and open a tab for its output."""
        tree = self.query_one("#agent-tree", AgentTree)
        tree.add_agent(message.agent_name, message.phase)
        tree.set_agent_running(message.agent_name)

        tabs = self.query_one("#agent-tabs", AgentTabs)
        tabs.add_agent_tab(message.agent_name)
        tabs.focus_agent(message.agent_name)

    def on_agent_output(self, message: AgentOutput) -> None:
        """Append streamed text to the agent's tab."""
        tabs = self.query_one("#agent-tabs", AgentTabs)
        tabs.append_output(message.agent_name, message.text, message.block_type)

    def on_agent_completed(self, message: AgentCompleted) -> None:
        """Update the agent tree icon to success or failure."""
        tree = self.query_one("#agent-tree", AgentTree)
        tree.set_agent_complete(message.agent_name, message.success)

    def on_agent_error(self, message: AgentError) -> None:
        """Mark the agent as failed and display the error in its tab."""
        tree = self.query_one("#agent-tree", AgentTree)
        tree.set_agent_complete(message.agent_name, success=False)

        tabs = self.query_one("#agent-tabs", AgentTabs)
        tabs.append_output(message.agent_name, message.error, block_type="error")

    def on_cost_update(self, message: CostUpdate) -> None:
        """Refresh the cost display widget with latest totals."""
        self.total_cost = message.total_cost
        cost_display = self.query_one("#cost-display", CostDisplay)
        cost_display.record_cost(message.agent_name, message.cost, message.total_cost)

    def on_security_block(self, message: SecurityBlock) -> None:
        """Display a security-blocked tool call as an error in the agent's tab."""
        tabs = self.query_one("#agent-tabs", AgentTabs)
        text = f"BLOCKED tool '{message.tool_name}': {message.reason}"
        tabs.append_output(message.agent_name, text, block_type="error")

    def on_phase_started(self, message: PhaseStarted) -> None:
        """Update the progress panel when a new phase begins."""
        self.current_phase = message.phase
        progress = self.query_one("#progress", ProgressPanel)
        progress.set_phase(message.phase, message.phase_index, message.total_phases)

    def on_phase_completed(self, message: PhaseCompleted) -> None:
        """Mark the completed phase in the progress panel."""
        progress = self.query_one("#progress", ProgressPanel)
        progress.set_phase(
            f"{message.phase} (done)",
            message.phase_index,
            self.query_one("#progress", ProgressPanel).total_phases,
        )

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def action_pause(self) -> None:
        """Pause the pipeline between phases."""
        if self._orchestrator:
            self._orchestrator.pause()
            self.notify("Pipeline paused. Press 'r' to resume.")
        else:
            self.notify("No pipeline running.", severity="warning")

    def action_resume(self) -> None:
        """Resume a paused pipeline."""
        if self._orchestrator:
            self._orchestrator.resume()
            self.notify("Pipeline resumed.")
        else:
            self.notify("No pipeline running.", severity="warning")

    def action_cancel_agent(self) -> None:
        """Cancel the running pipeline."""
        if self._orchestrator:
            self._orchestrator.cancel()
            self.notify("Pipeline cancelled.", severity="warning")
        else:
            self.notify("No pipeline running.", severity="warning")

    def action_cycle_agents(self) -> None:
        """Switch to the next agent output tab."""
        tabs = self.query_one("#agent-tabs", AgentTabs)
        tabs.action_next_tab()

    # ------------------------------------------------------------------
    # Pipeline execution
    # ------------------------------------------------------------------

    async def run_task(self, task: str) -> None:
        """Execute the full orchestration pipeline."""
        self._task = task
        config = OrchestratorConfig(project_path=self.project_path)
        self._orchestrator = AgentOrchestrator(config=config, app=self)

        runners = {
            "research": ResearchPhaseRunner(self._orchestrator.factory),
            "explore": ExplorerPhaseRunner(self._orchestrator.factory),
            "plan": PlannerPhaseRunner(self._orchestrator.factory),
            "code": CoderPhaseRunner(self._orchestrator.factory),
        }

        await self._orchestrator.run_pipeline(task, runners)

    def on_worker_state_changed(self, event: Worker.StateChanged) -> None:
        """Handle pipeline worker completion."""
        if event.worker.name == "pipeline" and event.worker.is_finished:
            if event.worker.error:
                self.notify(f"Pipeline failed: {event.worker.error}", severity="error")
            else:
                self.notify(
                    f"Pipeline complete. Total cost: ${self.total_cost:.4f}",
                    severity="information",
                )
