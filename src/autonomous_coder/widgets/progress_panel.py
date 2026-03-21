"""Phase and task progress panel."""
from textual.app import ComposeResult
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import ProgressBar, Static


class ProgressPanel(Widget):
    """Shows current phase name, progress bar, and task list with status icons."""

    current_phase: reactive[str] = reactive("idle")
    phase_index: reactive[int] = reactive(0)
    total_phases: reactive[int] = reactive(4)
    tasks: reactive[list] = reactive(list)

    DEFAULT_CSS = """
    ProgressPanel {
        padding: 1;
        border: solid $accent;
    }
    ProgressPanel #phase-label {
        text-style: bold;
        margin-bottom: 1;
    }
    ProgressPanel #task-list {
        margin-top: 1;
    }
    """

    def compose(self) -> ComposeResult:
        """Lay out the phase label, progress bar, and task list."""
        yield Static("Phase: idle", id="phase-label")
        yield ProgressBar(total=4, show_eta=False, id="phase-bar")
        yield Static("", id="task-list")

    def watch_current_phase(self, phase: str) -> None:
        """Update the phase label when the current phase changes."""
        label = self.query_one("#phase-label", Static)
        label.update(f"Phase: [bold]{phase}[/bold]")

    def watch_phase_index(self, index: int) -> None:
        """Advance the progress bar to match the current phase index."""
        bar = self.query_one("#phase-bar", ProgressBar)
        bar.advance(index - bar.progress if index > 0 else 0)

    def watch_total_phases(self, total: int) -> None:
        """Update the progress bar total when the phase count changes."""
        bar = self.query_one("#phase-bar", ProgressBar)
        bar.total = total

    def watch_tasks(self, tasks: list) -> None:
        """Re-render the task list with status icons."""
        lines = []
        for task in tasks:
            status = task.get("status", "pending")
            name = task.get("name", "")
            if status == "complete":
                icon = "[green]✓[/green]"
            elif status == "running":
                icon = "[yellow]▶[/yellow]"
            else:
                icon = "[dim]○[/dim]"
            lines.append(f"{icon} {name}")
        task_list = self.query_one("#task-list", Static)
        task_list.update("\n".join(lines) if lines else "No tasks")

    def set_phase(self, phase: str, index: int, total: int) -> None:
        """Update all phase-related reactive properties at once.

        Args:
            phase: Display name of the current phase.
            index: Zero-based phase position.
            total: Total number of phases.
        """
        self.total_phases = total
        self.current_phase = phase
        self.phase_index = index

    def update_tasks(self, tasks: list[dict]) -> None:
        """Replace the displayed task list.

        Args:
            tasks: List of dicts with "name" and "status" keys.
                Status values: "pending", "running", or "complete".
        """
        self.tasks = tasks
