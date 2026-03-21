"""Entry point for python -m autonomous_coder."""
import sys
from pathlib import Path

from .app import AutonomousCoderApp


def main() -> None:
    """Launch the TUI. Optionally pass a task as the first CLI argument."""
    task = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else ""
    project_path = Path.cwd()

    app = AutonomousCoderApp(task=task, project_path=project_path)
    app.run()


if __name__ == "__main__":
    main()
