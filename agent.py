"""
Autonomous Coder Agent - Main orchestrator module.

Implements the four-phase architecture:
1. Research - Discovers relevant MCP servers, skills, and resources via web research
2. Explorer - Analyzes codebase using Serena MCP
3. Planner - Creates detailed implementation plan
4. Coder - Implements tasks iteratively

Uses Claude Code SDK with defense-in-depth security.
"""

import asyncio
import json
from pathlib import Path
from typing import Any

from .client import AutonomousCoderClient, create_client
from .progress import ProgressTracker, create_feature_list, update_feature_status
from .prompts import (
    ensure_prompt_templates_exist,
    get_coder_prompt,
    get_explorer_prompt,
    get_planner_prompt,
    get_researcher_prompt,
    get_system_prompt,
)
from .researcher import ResearchPhase, run_research_phase


class AutonomousCoderAgent:
    """
    Main orchestrator for autonomous coding sessions.

    Manages the four-phase workflow:
    1. Research phase: Discovers MCP servers, skills, and resources via web research
    2. Explorer phase: Analyzes codebase structure and context
    3. Planner phase: Creates implementation plan with atomic tasks
    4. Coder phase: Implements each task iteratively

    Supports:
    - Web research for MCP discovery and skill recommendations
    - Session resumption from persisted state
    - Progress tracking with git commits
    - Error recovery and retry logic
    """

    def __init__(
        self,
        project_path: str | Path,
        model: str = "claude-sonnet-4-20250514",
        max_iterations: int = 10,
        sandbox_enabled: bool = True,
        auto_commit: bool = True,
    ):
        """
        Initialize the autonomous coder agent.

        Args:
            project_path: Path to the project directory
            model: Claude model to use
            max_iterations: Maximum iterations per task
            sandbox_enabled: Whether to enable OS sandbox
            auto_commit: Whether to auto-commit after each task
        """
        self.project_path = Path(project_path).resolve()
        self.model = model
        self.max_iterations = max_iterations
        self.sandbox_enabled = sandbox_enabled
        self.auto_commit = auto_commit

        # Initialize components
        self.client = create_client(
            project_path=self.project_path,
            model=model,
            sandbox_enabled=sandbox_enabled,
        )
        self.progress = ProgressTracker(self.project_path)

        # Ensure prompt templates exist
        ensure_prompt_templates_exist()

    async def run(self, task: str, resume: bool = True) -> dict[str, Any]:
        """
        Run the complete autonomous coding workflow.

        Args:
            task: The task description
            resume: Whether to resume from existing progress

        Returns:
            Dictionary with workflow results
        """
        results: dict[str, Any] = {
            "task": task,
            "phases": {},
            "success": False,
            "error": None,
        }

        try:
            # Check for existing progress
            if resume and self.progress.is_resumable():
                print(f"Resuming from: {self.progress.get_status_summary()}")
                results["resumed"] = True
            else:
                # Start fresh
                self.progress.start_task(task)
                results["resumed"] = False

            # Phase 1: Research (if not already done)
            if self.progress.progress.get("research") is None:
                print("\n=== Phase 1: Research & MCP Discovery ===")
                print("Discovering relevant MCP servers, skills, and resources...")
                research_results = await self._run_research(task)
                results["phases"]["research"] = research_results

                if not research_results.get("success", False):
                    print("⚠ Research phase encountered issues, continuing anyway...")

                # Store research results for later phases
                self.progress.progress["research"] = research_results.get("research", {})
                self.progress.save()

            # Phase 2: Exploration (if not already done)
            if self.progress.progress.get("exploration") is None:
                print("\n=== Phase 2: Exploring Codebase ===")
                exploration_results = await self._run_exploration(task)
                results["phases"]["exploration"] = exploration_results

                if not exploration_results.get("success", False):
                    raise RuntimeError("Exploration phase failed")

                self.progress.set_exploration_complete(
                    exploration_results.get("exploration", {})
                )

            # Phase 3: Planning (if not already done)
            if self.progress.progress.get("plan") is None:
                print("\n=== Phase 3: Creating Implementation Plan ===")
                exploration_data = self.progress.progress.get("exploration", {})
                plan_results = await self._run_planning(task, exploration_data)
                results["phases"]["planning"] = plan_results

                if not plan_results.get("success", False):
                    raise RuntimeError("Planning phase failed")

                plan = plan_results.get("plan", {})
                self.progress.set_plan(plan)

                # Create feature list for tracking
                tasks = plan.get("tasks", [])
                if tasks:
                    create_feature_list(self.project_path, tasks)

            # Phase 4: Implementation
            print("\n=== Phase 4: Implementing Tasks ===")
            implementation_results = await self._run_implementation()
            results["phases"]["implementation"] = implementation_results

            # Check final status
            if self.progress.progress.get("status") == "completed":
                results["success"] = True
                print("\n✓ All tasks completed successfully!")
            else:
                results["success"] = False
                print(f"\n⚠ Workflow incomplete: {self.progress.get_status_summary()}")

        except Exception as e:
            results["error"] = str(e)
            self.progress.record_error(None, str(e))
            print(f"\n✗ Error: {e}")

        return results

    async def _run_research(self, task: str) -> dict[str, Any]:
        """
        Run the research/onboarding phase.

        Uses web research to discover:
        - Relevant MCP servers for the task domain
        - Existing skills and examples
        - Library documentation
        - Best practices and resources

        Args:
            task: The task description

        Returns:
            Research results with MCP recommendations
        """
        researcher_prompt = get_researcher_prompt(
            task=task,
            project_path=str(self.project_path),
            additional_context="",
        )

        # Run research phase using the ResearchPhase class
        phase = ResearchPhase(self.client)
        result = await phase.run(task, researcher_prompt)

        # Display research findings
        research = result.get("research", {})

        # Show discovered MCP servers
        mcp_servers = research.get("mcp_servers", [])
        if mcp_servers:
            print("\n📦 Discovered MCP Servers:")
            for server in mcp_servers[:5]:  # Show top 5
                relevance = server.get("relevance", "unknown")
                name = server.get("name", "Unknown")
                desc = server.get("description", "")
                print(f"  [{relevance.upper()}] {name}")
                if desc:
                    print(f"      {desc[:80]}...")

        # Show discovered skills
        skills = research.get("skills", [])
        if skills:
            print("\n🔧 Found Relevant Skills:")
            for skill in skills[:3]:  # Show top 3
                name = skill.get("name", "Unknown")
                source = skill.get("source_url", "")
                print(f"  • {name}")
                if source:
                    print(f"    {source}")

        # Show recommendations
        recommendations = research.get("recommendations", {})
        if recommendations:
            must_install = recommendations.get("must_install", [])
            if must_install:
                print("\n⚡ Recommended MCPs to Install:")
                for item in must_install:
                    name = item.get("name", "Unknown")
                    reason = item.get("reason", "")
                    command = item.get("command", "")
                    print(f"  • {name}: {reason}")
                    if command:
                        print(f"    Install: {command}")

        return result

    async def _run_exploration(self, task: str) -> dict[str, Any]:
        """
        Run the exploration phase.

        Uses Serena MCP to analyze codebase structure and gather context.

        Args:
            task: The task description

        Returns:
            Exploration results
        """
        explorer_prompt = get_explorer_prompt(
            task=task,
            project_path=str(self.project_path),
            additional_context="",
        )

        result = await self.client.explore_codebase(task, explorer_prompt)

        # Validate exploration results
        exploration = result.get("exploration", {})
        if not exploration:
            # Try to extract from text
            text = result.get("text", "")
            if "relevant_files" in text or "architecture" in text:
                result["success"] = True
            else:
                result["success"] = False
        else:
            result["success"] = True

        return result

    async def _run_planning(
        self,
        task: str,
        exploration_results: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Run the planning phase.

        Creates a detailed implementation plan based on exploration.

        Args:
            task: The task description
            exploration_results: Results from exploration phase

        Returns:
            Planning results with implementation plan
        """
        # Format exploration results as string for prompt
        exploration_str = json.dumps(exploration_results, indent=2, default=str)

        planner_prompt = get_planner_prompt(
            task=task,
            exploration_results=exploration_str,
            project_path=str(self.project_path),
        )

        result = await self.client.create_plan(task, exploration_results, planner_prompt)

        # Validate plan
        plan = result.get("plan", {})
        if plan and plan.get("tasks"):
            result["success"] = True
        else:
            result["success"] = False

        return result

    async def _run_implementation(self) -> dict[str, Any]:
        """
        Run the implementation phase.

        Implements each task from the plan iteratively.

        Returns:
            Implementation results
        """
        results: dict[str, Any] = {
            "tasks_completed": [],
            "tasks_failed": [],
            "iterations": 0,
        }

        plan = self.progress.progress.get("plan", {})
        completed_tasks = self.progress.progress.get("completed_tasks", [])

        while results["iterations"] < self.max_iterations:
            results["iterations"] += 1

            # Get next task
            next_task = self.progress.get_next_task()
            if next_task is None:
                # All tasks complete
                break

            task_id = next_task.get("id")
            task_title = next_task.get("title", "Unknown")
            print(f"\n--- Task {task_id}: {task_title} ---")

            # Mark task as in progress
            self.progress.start_task_implementation(task_id)
            update_feature_status(self.project_path, task_id, "in_progress")

            try:
                # Get coder prompt
                coder_prompt = get_coder_prompt(
                    task=next_task,
                    plan=plan,
                    completed_tasks=completed_tasks,
                    project_path=str(self.project_path),
                )

                # Implement the task
                task_result = await self.client.implement_task(next_task, coder_prompt)

                # Check for success indicators
                task_text = task_result.get("text", "").lower()
                if "error" in task_text or "failed" in task_text:
                    raise RuntimeError(f"Task implementation reported errors")

                # Success - commit if enabled
                commit_hash = None
                if self.auto_commit:
                    commit_hash = await self._git_commit(task_id, task_title)

                # Mark complete
                self.progress.complete_task(task_id, commit_hash)
                update_feature_status(self.project_path, task_id, "completed")
                completed_tasks.append(task_id)
                results["tasks_completed"].append(task_id)

                print(f"  ✓ Task {task_id} completed")

            except Exception as e:
                # Record error and continue to next task
                error_msg = str(e)
                self.progress.record_error(task_id, error_msg)
                update_feature_status(self.project_path, task_id, "failed")
                results["tasks_failed"].append({"id": task_id, "error": error_msg})

                print(f"  ✗ Task {task_id} failed: {error_msg}")

                # Don't block on failed tasks - continue with independent tasks
                continue

        return results

    async def _git_commit(self, task_id: int, task_title: str) -> str | None:
        """
        Create a git commit for the completed task.

        Args:
            task_id: The task ID
            task_title: The task title

        Returns:
            Commit hash or None if commit failed
        """
        try:
            import subprocess

            # Check for changes
            result = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=self.project_path,
                capture_output=True,
                text=True,
            )

            if not result.stdout.strip():
                return None  # No changes to commit

            # Stage all changes
            subprocess.run(
                ["git", "add", "-A"],
                cwd=self.project_path,
                check=True,
            )

            # Create commit
            commit_msg = f"[autonomous-coder] Task {task_id}: {task_title}"
            subprocess.run(
                ["git", "commit", "-m", commit_msg],
                cwd=self.project_path,
                check=True,
            )

            # Get commit hash
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=self.project_path,
                capture_output=True,
                text=True,
                check=True,
            )

            return result.stdout.strip()[:8]

        except subprocess.CalledProcessError:
            return None
        except FileNotFoundError:
            # Git not available
            return None

    def get_status(self) -> dict[str, Any]:
        """
        Get current workflow status.

        Returns:
            Status dictionary
        """
        return {
            "summary": self.progress.get_status_summary(),
            "progress": self.progress.to_dict(),
            "project_path": str(self.project_path),
            "model": self.model,
        }

    def reset(self) -> None:
        """Reset all progress and start fresh."""
        self.progress.reset()
        print("Progress reset. Ready for new task.")


async def run_autonomous_coder(
    task: str,
    project_path: str | Path,
    model: str = "claude-sonnet-4-20250514",
    max_iterations: int = 10,
    sandbox_enabled: bool = True,
    auto_commit: bool = True,
    resume: bool = True,
) -> dict[str, Any]:
    """
    Main entry point for running the autonomous coder.

    This is the primary function to use when integrating the
    autonomous coder into other workflows.

    Args:
        task: The task description
        project_path: Path to the project directory
        model: Claude model to use
        max_iterations: Maximum iterations per task
        sandbox_enabled: Whether to enable OS sandbox
        auto_commit: Whether to auto-commit after each task
        resume: Whether to resume from existing progress

    Returns:
        Dictionary with workflow results

    Example:
        >>> result = await run_autonomous_coder(
        ...     task="Add user authentication with JWT",
        ...     project_path="/path/to/project",
        ... )
        >>> if result["success"]:
        ...     print("Task completed!")
    """
    agent = AutonomousCoderAgent(
        project_path=project_path,
        model=model,
        max_iterations=max_iterations,
        sandbox_enabled=sandbox_enabled,
        auto_commit=auto_commit,
    )

    return await agent.run(task, resume=resume)


def main() -> None:
    """
    CLI entry point for standalone execution.

    Usage:
        python -m autonomous_coder "Add feature X" /path/to/project
    """
    import argparse

    parser = argparse.ArgumentParser(
        description="Autonomous Coder - AI-powered coding assistant"
    )
    parser.add_argument("task", help="Task description")
    parser.add_argument("project_path", help="Path to the project directory")
    parser.add_argument(
        "--model",
        default="claude-sonnet-4-20250514",
        help="Claude model to use",
    )
    parser.add_argument(
        "--max-iterations",
        type=int,
        default=10,
        help="Maximum iterations per task",
    )
    parser.add_argument(
        "--no-sandbox",
        action="store_true",
        help="Disable OS sandbox",
    )
    parser.add_argument(
        "--no-commit",
        action="store_true",
        help="Disable auto-commit",
    )
    parser.add_argument(
        "--fresh",
        action="store_true",
        help="Start fresh (don't resume)",
    )

    args = parser.parse_args()

    result = asyncio.run(
        run_autonomous_coder(
            task=args.task,
            project_path=args.project_path,
            model=args.model,
            max_iterations=args.max_iterations,
            sandbox_enabled=not args.no_sandbox,
            auto_commit=not args.no_commit,
            resume=not args.fresh,
        )
    )

    # Print summary
    if result.get("success"):
        print("\n" + "=" * 50)
        print("✓ Autonomous coding completed successfully!")
        print("=" * 50)
    else:
        print("\n" + "=" * 50)
        print("✗ Autonomous coding did not complete")
        if result.get("error"):
            print(f"Error: {result['error']}")
        print("=" * 50)

    # Return exit code
    exit(0 if result.get("success") else 1)


# Export
__all__ = [
    "AutonomousCoderAgent",
    "run_autonomous_coder",
    "main",
]
