"""
Progress tracking and persistence utilities.

Provides functions to track, save, and restore progress
for the autonomous coding workflow.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any


class ProgressTracker:
    """
    Tracks progress of the autonomous coding workflow.

    Maintains state across sessions and persists to a JSON file.
    """

    def __init__(self, project_path: str | Path):
        """
        Initialize the progress tracker.

        Args:
            project_path: Path to the project directory
        """
        self.project_path = Path(project_path)
        self.progress_file = self.project_path / ".autonomous-coder" / "progress.json"
        self.progress: dict[str, Any] = self._load_or_create()

    def _load_or_create(self) -> dict[str, Any]:
        """Load existing progress or create new state."""
        if self.progress_file.exists():
            try:
                return json.loads(self.progress_file.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pass

        return {
            "status": "not_started",
            "task": None,
            "exploration": None,
            "plan": None,
            "completed_tasks": [],
            "current_task": None,
            "commits": [],
            "started_at": None,
            "updated_at": None,
            "sessions": 0,
            "errors": [],
        }

    def save(self) -> None:
        """Save current progress to file."""
        self.progress["updated_at"] = datetime.now().isoformat()

        # Ensure directory exists
        self.progress_file.parent.mkdir(parents=True, exist_ok=True)

        self.progress_file.write_text(
            json.dumps(self.progress, indent=2, default=str),
            encoding="utf-8"
        )

    def start_task(self, task: str) -> None:
        """
        Start tracking a new task.

        Args:
            task: The task description
        """
        self.progress = {
            "status": "exploring",
            "task": task,
            "exploration": None,
            "plan": None,
            "completed_tasks": [],
            "current_task": None,
            "commits": [],
            "started_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "sessions": 0,
            "errors": [],
        }
        self.save()

    def set_exploration_complete(self, exploration_results: dict[str, Any]) -> None:
        """
        Mark exploration phase as complete.

        Args:
            exploration_results: Results from the exploration phase
        """
        self.progress["exploration"] = exploration_results
        self.progress["status"] = "planning"
        self.save()

    def set_plan(self, plan: dict[str, Any]) -> None:
        """
        Set the implementation plan.

        Args:
            plan: The implementation plan
        """
        self.progress["plan"] = plan
        self.progress["status"] = "implementing"
        self.save()

    def start_task_implementation(self, task_id: int) -> None:
        """
        Mark a task as being implemented.

        Args:
            task_id: The ID of the task being implemented
        """
        self.progress["current_task"] = task_id
        self.progress["sessions"] += 1
        self.save()

    def complete_task(self, task_id: int, commit_hash: str | None = None) -> None:
        """
        Mark a task as completed.

        Args:
            task_id: The ID of the completed task
            commit_hash: Optional git commit hash
        """
        if task_id not in self.progress["completed_tasks"]:
            self.progress["completed_tasks"].append(task_id)

        if commit_hash:
            self.progress["commits"].append({
                "task_id": task_id,
                "hash": commit_hash,
                "timestamp": datetime.now().isoformat(),
            })

        self.progress["current_task"] = None

        # Check if all tasks are complete
        plan = self.progress.get("plan", {})
        total_tasks = plan.get("total_tasks", 0)
        if len(self.progress["completed_tasks"]) >= total_tasks:
            self.progress["status"] = "completed"

        self.save()

    def record_error(self, task_id: int | None, error: str) -> None:
        """
        Record an error that occurred during implementation.

        Args:
            task_id: The task ID where the error occurred (or None)
            error: The error message
        """
        self.progress["errors"].append({
            "task_id": task_id,
            "error": error,
            "timestamp": datetime.now().isoformat(),
        })
        self.save()

    def get_next_task(self) -> dict[str, Any] | None:
        """
        Get the next task to implement.

        Returns:
            The next task dict, or None if all tasks are complete
        """
        plan = self.progress.get("plan", {})
        tasks = plan.get("tasks", [])
        completed = set(self.progress["completed_tasks"])

        for task in tasks:
            task_id = task.get("id")
            if task_id is None:
                continue

            if task_id in completed:
                continue

            # Check if dependencies are satisfied
            dependencies = set(task.get("dependencies", []))
            if dependencies.issubset(completed):
                return task

        return None

    def get_status_summary(self) -> str:
        """
        Get a human-readable status summary.

        Returns:
            Status summary string
        """
        status = self.progress.get("status", "unknown")

        if status == "not_started":
            return "Not started"

        if status == "exploring":
            return "Exploring codebase..."

        if status == "planning":
            return "Creating implementation plan..."

        if status == "implementing":
            plan = self.progress.get("plan", {})
            total = plan.get("total_tasks", 0)
            completed = len(self.progress["completed_tasks"])
            current = self.progress.get("current_task")

            if current is not None:
                return f"Implementing task {current} ({completed}/{total} complete)"
            return f"Ready for next task ({completed}/{total} complete)"

        if status == "completed":
            return "All tasks completed!"

        return f"Status: {status}"

    def is_resumable(self) -> bool:
        """
        Check if there's existing progress that can be resumed.

        Returns:
            True if progress can be resumed
        """
        status = self.progress.get("status", "not_started")
        return status in ("exploring", "planning", "implementing")

    def reset(self) -> None:
        """Reset all progress."""
        self.progress = {
            "status": "not_started",
            "task": None,
            "exploration": None,
            "plan": None,
            "completed_tasks": [],
            "current_task": None,
            "commits": [],
            "started_at": None,
            "updated_at": None,
            "sessions": 0,
            "errors": [],
        }
        if self.progress_file.exists():
            self.progress_file.unlink()

    def to_dict(self) -> dict[str, Any]:
        """Get the full progress state as a dictionary."""
        return self.progress.copy()


def create_feature_list(project_path: str | Path, tasks: list[dict[str, Any]]) -> Path:
    """
    Create a feature_list.json file for tracking tasks.

    Args:
        project_path: Path to the project directory
        tasks: List of tasks from the plan

    Returns:
        Path to the created file
    """
    project_path = Path(project_path)
    feature_list_path = project_path / ".autonomous-coder" / "feature_list.json"

    features = [
        {
            "id": task.get("id"),
            "title": task.get("title"),
            "status": "pending",
            "files": task.get("files", []),
        }
        for task in tasks
    ]

    feature_list_path.parent.mkdir(parents=True, exist_ok=True)
    feature_list_path.write_text(
        json.dumps({"features": features}, indent=2),
        encoding="utf-8"
    )

    return feature_list_path


def update_feature_status(
    project_path: str | Path,
    task_id: int,
    status: str,
) -> None:
    """
    Update the status of a feature in feature_list.json.

    Args:
        project_path: Path to the project directory
        task_id: ID of the task to update
        status: New status (pending, in_progress, completed, failed)
    """
    project_path = Path(project_path)
    feature_list_path = project_path / ".autonomous-coder" / "feature_list.json"

    if not feature_list_path.exists():
        return

    try:
        data = json.loads(feature_list_path.read_text(encoding="utf-8"))

        for feature in data.get("features", []):
            if feature.get("id") == task_id:
                feature["status"] = status
                break

        feature_list_path.write_text(
            json.dumps(data, indent=2),
            encoding="utf-8"
        )
    except (json.JSONDecodeError, OSError):
        pass


# Export
__all__ = [
    "ProgressTracker",
    "create_feature_list",
    "update_feature_status",
]
