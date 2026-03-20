"""Current task detail panel."""
from textual.app import ComposeResult
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Static


class TaskDetail(Widget):
    """Shows details for the currently active task."""

    task_name: reactive[str] = reactive("")
    task_status: reactive[str] = reactive("idle")
    task_files: reactive[list] = reactive(list)
    task_dependencies: reactive[list] = reactive(list)
    estimated_cost: reactive[float] = reactive(0.0)

    DEFAULT_CSS = """
    TaskDetail {
        padding: 1;
        border: solid $accent;
    }
    TaskDetail .detail-label {
        text-style: bold;
        color: $text-muted;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("Task Detail", id="task-title")
        yield Static("", id="task-body")

    def watch_task_name(self, _: str) -> None:
        self._refresh_body()

    def watch_task_status(self, _: str) -> None:
        self._refresh_body()

    def watch_task_files(self, _: list) -> None:
        self._refresh_body()

    def watch_task_dependencies(self, _: list) -> None:
        self._refresh_body()

    def watch_estimated_cost(self, _: float) -> None:
        self._refresh_body()

    def _refresh_body(self) -> None:
        name = self.task_name or "—"
        status = self.task_status or "idle"
        files = ", ".join(self.task_files) if self.task_files else "—"
        deps = ", ".join(self.task_dependencies) if self.task_dependencies else "—"
        cost = f"${self.estimated_cost:.4f}"

        body = (
            f"[bold]Name:[/bold]         {name}\n"
            f"[bold]Status:[/bold]       {status}\n"
            f"[bold]Files:[/bold]        {files}\n"
            f"[bold]Dependencies:[/bold] {deps}\n"
            f"[bold]Est. Cost:[/bold]    {cost}"
        )
        self.query_one("#task-title", Static).update(f"[bold underline]Task Detail[/bold underline]")
        self.query_one("#task-body", Static).update(body)

    def update_task(
        self,
        name: str,
        status: str,
        files: list[str] | None = None,
        dependencies: list[str] | None = None,
        estimated_cost: float = 0.0,
    ) -> None:
        self.task_name = name
        self.task_status = status
        self.task_files = files or []
        self.task_dependencies = dependencies or []
        self.estimated_cost = estimated_cost
