"""Entry point for python -m autonomous_coder."""
import sys
from pathlib import Path

from .app import AutonomousCoderApp


def main() -> None:
    """Launch the TUI. Optionally pass a task as the first CLI argument."""
    task = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else ""
    project_path = Path.cwd()

    app = AutonomousCoderApp(task=task, project_path=project_path)

    # If a task was supplied, schedule it to run after the TUI mounts
    if task:
        async def _on_mount() -> None:
            await app.run_task(task)

        app.call_after_refresh(lambda: app.run_worker(_on_mount(), name="startup"))

    app.run()


if __name__ == "__main__":
    main()
