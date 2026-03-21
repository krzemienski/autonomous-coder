"""Explorer phase runner implementation."""
from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from ..orchestrator import PhaseContext, PhaseResult
from ..prompts import get_explorer_prompt

if TYPE_CHECKING:
    from ..agent_factory import AgentFactory
    from ..orchestrator import AgentOrchestrator


class ExplorerPhaseRunner:
    """Runs the explore phase: codebase structure analysis.

    Uses Serena MCP to analyze project layout, detect technology stack,
    and map relevant symbols.
    """

    def __init__(self, factory: AgentFactory, orchestrator: AgentOrchestrator | None = None) -> None:
        """Initialize with an agent factory.

        Args:
            factory: Factory used to build ``ClaudeAgentOptions`` for the
                explore role.
            orchestrator: Optional orchestrator for emitting lifecycle messages.
        """
        self.factory = factory
        self.orchestrator = orchestrator

    async def run(self, context: PhaseContext) -> PhaseResult:
        """Execute the exploration phase query.

        Args:
            context: Phase input including task description and prior research.

        Returns:
            PhaseResult with ``explore_output`` in ``output_data``.
        """
        start_time = time.time()

        system_prompt = self._build_system_prompt(context)
        prompt = self._build_prompt(context)

        if self.orchestrator is not None:
            try:
                text, cost = await self.orchestrator.run_query(
                    role="explore",
                    phase=context.phase_name,
                    prompt=prompt,
                    system_prompt=system_prompt,
                    budget_remaining=context.budget_remaining,
                )
                return PhaseResult(
                    phase_name=context.phase_name,
                    output_data={"explore_output": text},
                    cost_incurred=cost,
                    duration_seconds=time.time() - start_time,
                    success=True,
                )
            except Exception as e:
                return PhaseResult(
                    phase_name=context.phase_name,
                    output_data={},
                    cost_incurred=0.0,
                    duration_seconds=time.time() - start_time,
                    success=False,
                    error=str(e),
                )

        # Fallback: direct query (no observability)
        return await self._run_direct(context, prompt, system_prompt, start_time)

    async def _run_direct(
        self,
        context: PhaseContext,
        prompt: str,
        system_prompt: str,
        start_time: float,
    ) -> PhaseResult:
        """Direct query fallback when no orchestrator is attached."""
        from claude_agent_sdk import query
        from claude_agent_sdk.types import AssistantMessage, ResultMessage, TextBlock

        from ..orchestrator import security_callback

        total_cost = 0.0
        collected_text: list[str] = []

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
        """Build the system prompt, injecting prior research as additional context."""
        research_output = context.input_data.get("research_output", "")
        return get_explorer_prompt(
            task=context.task_description,
            project_path=str(context.config.project_path),
            additional_context=research_output,
        )

    def _build_prompt(self, context: PhaseContext) -> str:
        """Build the user-turn prompt for the exploration query."""
        task = context.input_data.get("task", context.task_description)
        research = context.input_data.get("research_output", "")
        parts = [f"Task: {task}", "", "Explore the codebase and produce a structured JSON report."]
        if research:
            parts.insert(1, f"Research findings:\n{research[:500]}")
        return "\n".join(parts)
