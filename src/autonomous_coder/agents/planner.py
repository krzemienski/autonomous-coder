"""Planner phase runner implementation."""
import time

from claude_agent_sdk import query
from claude_agent_sdk.types import AssistantMessage, ResultMessage, TextBlock, ToolUseBlock

from ..agent_factory import AgentFactory
from ..orchestrator import PhaseContext, PhaseResult, security_callback
from ..prompts import get_planner_prompt


class PlannerPhaseRunner:
    """Runs the plan phase: produces a structured implementation plan.

    Combines research and exploration outputs to generate a JSON plan
    with ordered tasks, dependencies, and test criteria.
    """

    def __init__(self, factory: AgentFactory) -> None:
        """Initialize with an agent factory.

        Args:
            factory: Factory used to build ``ClaudeAgentOptions`` for the
                plan role.
        """
        self.factory = factory

    async def run(self, context: PhaseContext) -> PhaseResult:
        """Execute the planning phase query.

        Args:
            context: Phase input including task description and prior outputs.

        Returns:
            PhaseResult with ``plan_output`` in ``output_data``.
        """
        start_time = time.time()
        total_cost = 0.0
        collected_text: list[str] = []

        system_prompt = self._build_system_prompt(context)
        prompt = self._build_prompt(context)

        options = self.factory.create_options(
            role="plan",
            system_prompt=system_prompt,
            security_callback=security_callback,
        )

        try:
            async for msg in query(prompt=prompt, options=options):
                if isinstance(msg, AssistantMessage):
                    for block in msg.content:
                        if isinstance(block, TextBlock):
                            collected_text.append(block.text)
                elif isinstance(msg, ResultMessage):
                    total_cost += msg.total_cost_usd or 0.0
                    if total_cost > context.budget_remaining:
                        break

            return PhaseResult(
                phase_name=context.phase_name,
                output_data={"plan_output": "\n".join(collected_text)},
                cost_incurred=total_cost,
                duration_seconds=time.time() - start_time,
                success=True,
            )
        except Exception as e:
            return PhaseResult(
                phase_name=context.phase_name,
                output_data={},
                cost_incurred=total_cost,
                duration_seconds=time.time() - start_time,
                success=False,
                error=str(e),
            )

    def _build_system_prompt(self, context: PhaseContext) -> str:
        """Build the system prompt from the planner template with exploration data."""
        exploration_results = context.input_data.get("explore_output", "")
        return get_planner_prompt(
            task=context.task_description,
            exploration_results=exploration_results,
            project_path=str(context.config.project_path),
        )

    def _build_prompt(self, context: PhaseContext) -> str:
        """Build the user-turn prompt combining research and exploration summaries."""
        task = context.input_data.get("task", context.task_description)
        explore = context.input_data.get("explore_output", "")
        research = context.input_data.get("research_output", "")

        parts = [f"Task: {task}", ""]
        if research:
            parts.append(f"Research summary:\n{research[:400]}\n")
        if explore:
            parts.append(f"Exploration findings:\n{explore[:600]}\n")
        parts.append(
            "Produce a detailed JSON implementation plan with ordered tasks, "
            "dependencies, and test criteria."
        )
        return "\n".join(parts)
