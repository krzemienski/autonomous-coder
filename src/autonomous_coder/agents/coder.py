"""Coder phase runner implementation (coding + separate review pass)."""
import time

from claude_agent_sdk import query
from claude_agent_sdk.types import AssistantMessage, ResultMessage, TextBlock, ToolUseBlock

from ..agent_factory import AgentFactory
from ..orchestrator import PhaseContext, PhaseResult, security_callback
from ..prompts import get_coder_prompt


class CoderPhaseRunner:
    """Runs the code phase followed by a separate reviewer query."""

    def __init__(self, factory: AgentFactory) -> None:
        self.factory = factory

    async def run(self, context: PhaseContext) -> PhaseResult:
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
        plan_output = context.input_data.get("plan_output", "")
        task_description = context.task_description

        # Build a minimal task/plan dict for get_coder_prompt
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

        options = self.factory.create_options(
            role="code",
            system_prompt=system_prompt,
            security_callback=security_callback,
        )

        collected: list[str] = []
        total_cost = 0.0

        try:
            async for msg in query(prompt="\n".join(prompt_parts), options=options):
                if isinstance(msg, AssistantMessage):
                    for block in msg.content:
                        if isinstance(block, TextBlock):
                            collected.append(block.text)
                elif isinstance(msg, ResultMessage):
                    total_cost += msg.total_cost_usd or 0.0
                    if total_cost > context.budget_remaining:
                        break
        except Exception as e:
            collected.append(f"[Coding error: {e}]")

        return "\n".join(collected), total_cost

    async def _run_review(
        self,
        context: PhaseContext,
        coding_output: str,
        budget_remaining: float,
    ) -> tuple[str, float]:
        """Run a completely separate reviewer query (not a subagent)."""
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

        options = self.factory.create_options(
            role="reviewer",
            system_prompt=review_system,
            security_callback=security_callback,
        )

        collected: list[str] = []
        total_cost = 0.0

        try:
            async for msg in query(prompt=review_prompt, options=options):
                if isinstance(msg, AssistantMessage):
                    for block in msg.content:
                        if isinstance(block, TextBlock):
                            collected.append(block.text)
                elif isinstance(msg, ResultMessage):
                    total_cost += msg.total_cost_usd or 0.0
                    if total_cost > budget_remaining:
                        break
        except Exception as e:
            collected.append(f"[Review error: {e}]")

        return "\n".join(collected), total_cost
