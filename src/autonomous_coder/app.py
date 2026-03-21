"""Main Textual application for the Autonomous Coder TUI."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.reactive import reactive
from textual.widgets import Header, Footer
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
    """Top-level TUI application."""

    CSS_PATH = "styles.tcss"

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
        super().__init__(**kwargs)
        self.task = task
        self.project_path = Path(project_path) if project_path else Path.cwd()
        self._orchestrator: AgentOrchestrator | None = None

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal():
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
    # Message handlers
    # ------------------------------------------------------------------

    def on_agent_started(self, message: AgentStarted) -> None:
        tree = self.query_one("#agent-tree", AgentTree)
        tree.add_agent(message.agent_name, message.phase)
        tree.set_agent_running(message.agent_name)

        tabs = self.query_one("#agent-tabs", AgentTabs)
        tabs.add_agent_tab(message.agent_name)
        tabs.focus_agent(message.agent_name)

    def on_agent_output(self, message: AgentOutput) -> None:
        tabs = self.query_one("#agent-tabs", AgentTabs)
        tabs.append_output(message.agent_name, message.text, message.block_type)

    def on_agent_completed(self, message: AgentCompleted) -> None:
        tree = self.query_one("#agent-tree", AgentTree)
        tree.set_agent_complete(message.agent_name, message.success)

    def on_agent_error(self, message: AgentError) -> None:
        tree = self.query_one("#agent-tree", AgentTree)
        tree.set_agent_complete(message.agent_name, success=False)

        tabs = self.query_one("#agent-tabs", AgentTabs)
        tabs.append_output(message.agent_name, message.error, block_type="error")

    def on_cost_update(self, message: CostUpdate) -> None:
        self.total_cost = message.total_cost
        cost_display = self.query_one("#cost-display", CostDisplay)
        cost_display.record_cost(message.agent_name, message.cost, message.total_cost)

    def on_security_block(self, message: SecurityBlock) -> None:
        tabs = self.query_one("#agent-tabs", AgentTabs)
        text = f"BLOCKED tool '{message.tool_name}': {message.reason}"
        tabs.append_output(message.agent_name, text, block_type="error")

    def on_phase_started(self, message: PhaseStarted) -> None:
        self.current_phase = message.phase
        progress = self.query_one("#progress", ProgressPanel)
        progress.set_phase(message.phase, message.phase_index, message.total_phases)

    def on_phase_completed(self, message: PhaseCompleted) -> None:
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
        if self._orchestrator:
            self._orchestrator.pause()
            self.notify("Pipeline paused. Press 'r' to resume.")
        else:
            self.notify("No pipeline running.", severity="warning")

    def action_resume(self) -> None:
        if self._orchestrator:
            self._orchestrator.resume()
            self.notify("Pipeline resumed.")
        else:
            self.notify("No pipeline running.", severity="warning")

    def action_cancel_agent(self) -> None:
        if self._orchestrator:
            self._orchestrator.cancel()
            self.notify("Pipeline cancelled.", severity="warning")
        else:
            self.notify("No pipeline running.", severity="warning")

    def action_cycle_agents(self) -> None:
        tabs = self.query_one("#agent-tabs", AgentTabs)
        tabs.action_next_tab()

    # ------------------------------------------------------------------
    # Pipeline execution
    # ------------------------------------------------------------------

    async def run_task(self, task: str) -> None:
        """Launch the full orchestration pipeline as a background worker."""
        self.task = task
        config = OrchestratorConfig(project_path=self.project_path)
        self._orchestrator = AgentOrchestrator(config=config, app=self)

        runners = {
            "research": ResearchPhaseRunner(self._orchestrator.factory),
            "explore": ExplorerPhaseRunner(self._orchestrator.factory),
            "plan": PlannerPhaseRunner(self._orchestrator.factory),
            "code": CoderPhaseRunner(self._orchestrator.factory),
        }

        self.run_worker(
            self._orchestrator.run_pipeline(task, runners),
            name="pipeline",
            exclusive=True,
        )

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
