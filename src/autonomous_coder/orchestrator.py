"""Agent orchestration engine with PhaseRunner protocol."""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from claude_agent_sdk import PermissionResultAllow, PermissionResultDeny, query
from claude_agent_sdk.types import AssistantMessage, ResultMessage, TextBlock, ToolUseBlock

from .agent_factory import AgentFactory
from .agent_instance import AgentInstance, AgentStatus
from .config import OrchestratorConfig
from .messages import (
    AgentCompleted,
    AgentError,
    AgentOutput,
    AgentStarted,
    CostUpdate,
    PhaseCompleted,
    PhaseStarted,
)
from .security import is_command_allowed


# ---------------------------------------------------------------------------
# Phase data contracts
# ---------------------------------------------------------------------------


@dataclass
class PhaseContext:
    """Input context handed to a PhaseRunner."""

    phase_name: str
    input_data: dict[str, Any]
    config: OrchestratorConfig
    budget_remaining: float
    task_description: str = ""


@dataclass
class PhaseResult:
    """Output produced by a PhaseRunner."""

    phase_name: str
    output_data: dict[str, Any]
    cost_incurred: float = 0.0
    duration_seconds: float = 0.0
    success: bool = True
    error: str | None = None


# ---------------------------------------------------------------------------
# PhaseRunner protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class PhaseRunner(Protocol):
    """Structural protocol — any object with an async run() satisfies it."""

    async def run(self, context: PhaseContext) -> PhaseResult:
        """Execute the phase logic and return results.

        Args:
            context: Input context for this phase.

        Returns:
            PhaseResult with output data and cost metrics.
        """
        ...


# ---------------------------------------------------------------------------
# Security callback (can_use_tool)
# ---------------------------------------------------------------------------


async def security_callback(
    tool_name: str,
    tool_input: dict,
    ctx: Any,  # ToolPermissionContext — opaque from SDK perspective
) -> Any:  # PermissionResultAllow | PermissionResultDeny
    """Called by the SDK BEFORE every tool execution.

    Blocks Bash commands that fail is_command_allowed(), passes everything else.
    Non-Bash tools (Read, Write, Edit, etc.) are always allowed here because
    permission_mode="acceptEdits" governs file-system access at the session level.
    """
    if tool_name == "Bash":
        command = tool_input.get("command", "")
        is_allowed, reason = is_command_allowed(command)
        if not is_allowed:
            return PermissionResultDeny(
                behavior="deny",
                message=f"Blocked by security policy: {reason}",
                interrupt=False,
            )

    return PermissionResultAllow(
        behavior="allow",
        updated_input=None,
        updated_permissions=None,
    )


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


class AgentOrchestrator:
    """Runs a sequential Research → Explore → Plan → Code pipeline.

    Each phase is driven by a PhaseRunner supplied by the caller.
    Budget is tracked manually via ResultMessage.total_cost_usd (no SDK field).
    UI updates are dispatched as Textual Message objects via self.app.
    """

    PHASE_ORDER = ["research", "explore", "plan", "code"]

    def __init__(self, config: OrchestratorConfig, app: Any = None) -> None:
        """
        Args:
            config: Orchestrator configuration including roles and total budget.
            app: Optional Textual App instance. When provided, messages are
                 posted for live UI updates. Pass None for headless use.
        """
        self.config = config
        self.factory = AgentFactory(config)
        self.app = app
        self.agents: dict[str, AgentInstance] = {}
        self.total_cost: float = 0.0
        self.phase_results: dict[str, PhaseResult] = {}
        self._cancelled = False
        self._paused = False

    # ------------------------------------------------------------------
    # Textual message dispatch
    # ------------------------------------------------------------------

    def _post_message(self, message: Any) -> None:
        """Post a Textual message to the app if one is attached."""
        if self.app is not None:
            self.app.post_message(message)

    # ------------------------------------------------------------------
    # Pipeline entry point
    # ------------------------------------------------------------------

    async def run_pipeline(
        self,
        task: str,
        runners: dict[str, PhaseRunner],
    ) -> dict[str, PhaseResult]:
        """Execute the full phase pipeline sequentially.

        Args:
            task: Natural-language task description passed to every phase.
            runners: Mapping of phase_name → PhaseRunner. Missing phases are
                     skipped gracefully.

        Returns:
            Mapping of phase_name → PhaseResult for all phases that ran.
        """
        input_data: dict[str, Any] = {"task": task}
        budget_remaining = self.config.total_budget

        for i, phase_name in enumerate(self.PHASE_ORDER):
            if self._cancelled:
                break

            # Honour pause requests between phases
            while self._paused:
                await asyncio.sleep(0.5)

            runner = runners.get(phase_name)
            if runner is None:
                continue

            self._post_message(PhaseStarted(
                phase=phase_name,
                phase_index=i,
                total_phases=len(self.PHASE_ORDER),
            ))

            context = PhaseContext(
                phase_name=phase_name,
                input_data=input_data,
                config=self.config,
                budget_remaining=budget_remaining,
                task_description=task,
            )

            start_time = time.time()
            try:
                result = await runner.run(context)
            except Exception as exc:  # noqa: BLE001
                result = PhaseResult(
                    phase_name=phase_name,
                    output_data={},
                    cost_incurred=0.0,
                    duration_seconds=time.time() - start_time,
                    success=False,
                    error=str(exc),
                )

            self.phase_results[phase_name] = result
            self.total_cost += result.cost_incurred
            budget_remaining -= result.cost_incurred

            self._post_message(PhaseCompleted(
                phase=phase_name,
                phase_index=i,
                cost=result.cost_incurred,
                duration=result.duration_seconds,
                success=result.success,
            ))

            if not result.success:
                break  # Abort pipeline on phase failure

            # Merge phase outputs into next phase's input
            input_data = {**input_data, **result.output_data}

        return self.phase_results

    # ------------------------------------------------------------------
    # Single-agent runner (used by PhaseRunner implementations)
    # ------------------------------------------------------------------

    async def run_agent(
        self,
        role: str,
        phase: str,
        prompt: str,
        system_prompt: str,
    ) -> tuple[str, float]:
        """Run one agent query with budget tracking and UI message dispatch.

        Args:
            role: Role key (must exist in config.roles).
            phase: Phase label used for naming and messages.
            prompt: The user-turn prompt sent to the agent.
            system_prompt: The system prompt for this agent session.

        Returns:
            Tuple of (collected_text, cost_incurred).
        """
        agent = AgentInstance(
            name=f"{phase}-{role}",
            role=role,
            phase=phase,
            budget_limit=self.factory.get_budget_limit(role),
        )
        self.agents[agent.name] = agent
        agent.start()

        self._post_message(AgentStarted(agent_name=agent.name, phase=phase))

        options = self.factory.create_options(
            role=role,
            system_prompt=system_prompt,
            security_callback=security_callback,
        )

        collected_text: list[str] = []

        try:
            async for msg in query(prompt=prompt, options=options):
                if self._cancelled:
                    break

                if isinstance(msg, AssistantMessage):
                    for block in msg.content:
                        if isinstance(block, TextBlock):
                            collected_text.append(block.text)
                            self._post_message(AgentOutput(
                                agent_name=agent.name,
                                text=block.text,
                                block_type="text",
                            ))
                        elif isinstance(block, ToolUseBlock):
                            summary = _summarize_tool_input(block.input)
                            self._post_message(AgentOutput(
                                agent_name=agent.name,
                                text=f"[Tool: {block.name}] {summary}",
                                block_type="tool",
                            ))

                elif isinstance(msg, ResultMessage):
                    # Budget tracked at application level for per-role granularity
                    # SDK also supports max_budget_usd for hard caps
                    cost = msg.total_cost_usd or 0.0
                    agent.add_cost(cost)
                    self.total_cost += cost
                    self._post_message(CostUpdate(
                        agent_name=agent.name,
                        cost=cost,
                        total_cost=self.total_cost,
                    ))

                    if agent.budget_exceeded:
                        break

            agent.complete()

        except Exception as exc:  # noqa: BLE001
            agent.complete(error=str(exc))
            self._post_message(AgentError(
                agent_name=agent.name,
                error=str(exc),
                phase=phase,
            ))

        self._post_message(AgentCompleted(
            agent_name=agent.name,
            phase=phase,
            cost=agent.cost,
            duration=agent.duration,
            success=agent.status == AgentStatus.COMPLETED,
            error=agent.error,
        ))

        return "\n".join(collected_text), agent.cost

    # ------------------------------------------------------------------
    # Control interface
    # ------------------------------------------------------------------

    def pause(self) -> None:
        """Pause pipeline between phases (does not interrupt running agent)."""
        self._paused = True

    def resume(self) -> None:
        """Resume a paused pipeline."""
        self._paused = False

    def cancel(self) -> None:
        """Cancel pipeline; current agent query runs to its next yield point."""
        self._cancelled = True


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _summarize_tool_input(tool_input: dict) -> str:
    """Return a short human-readable summary of a tool's input dict."""
    if "command" in tool_input:
        return tool_input["command"][:80]
    if "file_path" in tool_input:
        return tool_input["file_path"]
    if "pattern" in tool_input:
        return f"pattern: {tool_input['pattern']}"
    return str(tool_input)[:60]
