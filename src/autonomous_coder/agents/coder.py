"""Coder phase runner implementation (coding + separate review pass)."""
from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from ..orchestrator import PhaseContext, PhaseResult
from ..prompts import get_coder_prompt

if TYPE_CHECKING:
    from ..agent_factory import AgentFactory
    from ..orchestrator import AgentOrchestrator


class CoderPhaseRunner:
    """Runs the code phase followed by a separate reviewer query.

    The coding pass implements the task using the full tool set, then a
    lightweight reviewer query provides feedback on correctness, style,
    and security.
    """

    def __init__(self, factory: AgentFactory, orchestrator: AgentOrchestrator | None = None) -> None:
        """Initialize with an agent factory.

        Args:
            factory: Factory used to build ``ClaudeAgentOptions`` for the
                code and reviewer roles.
            orchestrator: Optional orchestrator for emitting lifecycle messages.
        """
        self.factory = factory
        self.orchestrator = orchestrator

    async def run(self, context: PhaseContext) -> PhaseResult:
        """Execute coding and review passes sequentially.

        Args:
            context: Phase input including task description and plan output.

        Returns:
            PhaseResult with ``code_output`` and ``review_output`` in
            ``output_data``.
        """
        start_time = time.time()
        total_cost = 0.0

        # --- Coding pass ---
        coding_text, coding_cost = await self._run_coding(context)
        total_cost += coding_cost

        budget_after_coding = context.budget_remaining - coding_cost

        # --- Review pass (separate query, not a subagent) ---
        review_text, review_cost = await self._run_review(
            context, coding_text, budget_after_coding
        )
        total_cost += review_cost

        return PhaseResult(
            phase_name=context.phase_name,
            output_data={
                "code_output": coding_text,
                "review_output": review_text,
            },
            cost_incurred=total_cost,
            duration_seconds=time.time() - start_time,
            success=True,
        )

    async def _run_coding(self, context: PhaseContext) -> tuple[str, float]:
        """Run the implementation coding pass."""
        plan_output = context.input_data.get("plan_output", "")
        task_description = context.task_description

        task_dict = {
            "id": 1,
            "title": task_description,
            "description": task_description,
            "files": [],
            "dependencies": [],
            "test_criteria": "Verify the implementation works end-to-end.",
            "estimated_complexity": "medium",
        }
        plan_dict = {
            "goal": task_description,
            "context_summary": plan_output[:600] if plan_output else "",
            "tasks": [],
            "total_tasks": 1,
            "risks": [],
        }

        system_prompt = get_coder_prompt(
            task=task_dict,
            plan=plan_dict,
            completed_tasks=[],
            project_path=str(context.config.project_path),
        )

        prompt_parts = [
            f"Implement the following task: {task_description}",
            "",
        ]
        if plan_output:
            prompt_parts.append(f"Implementation plan:\n{plan_output}")

        prompt = "\n".join(prompt_parts)

        if self.orchestrator is not None:
            return await self.orchestrator.run_query(
                role="code",
                phase=f"{context.phase_name}-coding",
                prompt=prompt,
                system_prompt=system_prompt,
                budget_remaining=context.budget_remaining,
            )

        # Fallback: direct query
        return await self._run_direct(
            "code", prompt, system_prompt, context.budget_remaining
        )

    async def _run_review(
        self,
        context: PhaseContext,
        coding_output: str,
        budget_remaining: float,
    ) -> tuple[str, float]:
        """Run a completely separate reviewer query."""
        review_system = (
            "You are a senior code reviewer. Examine the implementation output below "
            "and provide concise, actionable feedback covering correctness, style, "
            "security concerns, and any missing edge cases."
        )

        review_prompt = (
            f"Task: {context.task_description}\n\n"
            f"Implementation output:\n{coding_output[:3000]}\n\n"
            "Review the above implementation and provide structured feedback."
        )

        if self.orchestrator is not None:
            return await self.orchestrator.run_query(
                role="reviewer",
                phase=f"{context.phase_name}-review",
                prompt=review_prompt,
                system_prompt=review_system,
                budget_remaining=budget_remaining,
            )

        # Fallback: direct query
        return await self._run_direct(
            "reviewer", review_prompt, review_system, budget_remaining
        )

    async def _run_direct(
        self,
        role: str,
        prompt: str,
        system_prompt: str,
        budget_remaining: float,
    ) -> tuple[str, float]:
        """Direct query fallback when no orchestrator is attached."""
        from claude_agent_sdk import query
        from claude_agent_sdk.types import AssistantMessage, ResultMessage, TextBlock

        from ..orchestrator import _string_to_stream, security_callback

        options = self.factory.create_options(
            role=role,
            system_prompt=system_prompt,
            security_callback=security_callback,
        )

        collected: list[str] = []
        total_cost = 0.0

        prompt_arg = _string_to_stream(prompt) if options.can_use_tool else prompt

        try:
            async for msg in query(prompt=prompt_arg, options=options):
                if isinstance(msg, AssistantMessage):
                    for block in msg.content:
                        if isinstance(block, TextBlock):
                            collected.append(block.text)
                elif isinstance(msg, ResultMessage):
                    total_cost += msg.total_cost_usd or 0.0
                    if total_cost > budget_remaining:
                        break
        except Exception as e:
            collected.append(f"[Error: {e}]")

        return "\n".join(collected), total_cost
