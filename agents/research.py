"""Research phase runner implementation."""
import time
from typing import Any

from claude_code_sdk import query
from claude_code_sdk.types import AssistantMessage, ResultMessage, TextBlock, ToolUseBlock

from ..agent_factory import AgentFactory
from ..orchestrator import PhaseContext, PhaseResult, security_callback
from ..prompts import get_researcher_prompt


class ResearchPhaseRunner:
    """Runs the research phase: web research and MCP discovery."""

    def __init__(self, factory: AgentFactory) -> None:
        self.factory = factory

    async def run(self, context: PhaseContext) -> PhaseResult:
        start_time = time.time()
        total_cost = 0.0
        collected_text: list[str] = []

        system_prompt = self._build_system_prompt(context)
        prompt = self._build_prompt(context)

        options = self.factory.create_options(
            role="research",
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
                output_data={"research_output": "\n".join(collected_text)},
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
        return get_researcher_prompt(
            task=context.task_description,
            project_path=str(context.config.project_path),
        )

    def _build_prompt(self, context: PhaseContext) -> str:
        task = context.input_data.get("task", context.task_description)
        return (
            f"Research task: {task}\n\n"
            "Identify relevant MCP servers, skills, libraries, and resources. "
            "Return a structured JSON report with your findings."
        )
