"""Explorer phase runner implementation."""
import time

from claude_code_sdk import query
from claude_code_sdk.types import AssistantMessage, ResultMessage, TextBlock, ToolUseBlock

from ..agent_factory import AgentFactory
from ..orchestrator import PhaseContext, PhaseResult, security_callback
from ..prompts import get_explorer_prompt


class ExplorerPhaseRunner:
    """Runs the explore phase: codebase structure analysis."""

    def __init__(self, factory: AgentFactory) -> None:
        self.factory = factory

    async def run(self, context: PhaseContext) -> PhaseResult:
        start_time = time.time()
        total_cost = 0.0
        collected_text: list[str] = []

        system_prompt = self._build_system_prompt(context)
        prompt = self._build_prompt(context)

        options = self.factory.create_options(
            role="explore",
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
                output_data={"explore_output": "\n".join(collected_text)},
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
        research_output = context.input_data.get("research_output", "")
        return get_explorer_prompt(
            task=context.task_description,
            project_path=str(context.config.project_path),
            additional_context=research_output,
        )

    def _build_prompt(self, context: PhaseContext) -> str:
        task = context.input_data.get("task", context.task_description)
        research = context.input_data.get("research_output", "")
        parts = [f"Task: {task}", "", "Explore the codebase and produce a structured JSON report."]
        if research:
            parts.insert(1, f"Research findings:\n{research[:500]}")
        return "\n".join(parts)
