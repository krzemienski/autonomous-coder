"""Core SDK-native orchestrator.

This replaces the manual phase loop and tool dispatch with a single SDK
query() call. The SDK handles the entire agent loop internally — tool
execution, retries, context compaction, and streaming. We just configure
the right tools, permissions, system prompts, subagents, and hooks, then
let Claude drive the multi-phase workflow autonomously.

Architecture comparison:
- OLD (quickstart/v1): Manual for-loop over phases, per-phase query() calls,
  custom tool_use block parsing and result dispatch
- NEW (SDK-native): Single query() with AgentDefinition subagents, HookMatcher
  observability, and declarative MCP server management
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from claude_agent_sdk import (
    ClaudeAgentOptions,
    query,
)
from claude_agent_sdk.types import (
    AssistantMessage,
    ResultMessage,
    TextBlock,
    ThinkingBlock,
    ToolUseBlock,
)

from .display import Display
from .sdk_agents import build_agent_definitions
from .sdk_hooks import build_hooks
from .sdk_mcp_servers import build_mcp_server_configs
from .sdk_prompts import build_orchestrator_prompt
from .sdk_tools import build_custom_tools_server, clear_phase_log, get_phase_log, set_findings_dir
from .types import AutonomousCoderConfig, PhaseEvent, SessionResult


async def run(config: AutonomousCoderConfig) -> SessionResult:
    """Execute the autonomous coding workflow via a single SDK query.

    This is the ENTIRE orchestration. No manual phase loop. No tool dispatch.
    The SDK agent loop handles all of that. We configure and observe.

    Args:
        config: Session configuration including task, project, model, budget.

    Returns:
        SessionResult with cost, timing, phase tracking, and completion status.
    """
    display = Display(verbose=config.verbose)
    start_time = time.monotonic()

    # Read the task specification
    if config.task_path:
        task_spec = config.task_path.read_text(encoding="utf-8")
    else:
        task_spec = "No task specification file provided. Ask the user what to do."

    # Set up findings directory in the target project
    findings_dir = config.project_dir / ".autonomous-coder"
    set_findings_dir(findings_dir)
    clear_phase_log()

    # Build SDK configuration components
    agents = build_agent_definitions(config)
    hooks = build_hooks(display)
    custom_tools_server = build_custom_tools_server()
    mcp_servers = build_mcp_server_configs(config)
    mcp_servers["autonomous-coder-tools"] = custom_tools_server

    system_prompt = build_orchestrator_prompt(
        task_spec=task_spec,
        project_dir=str(config.project_dir),
    )

    # Build allowed tools list including all MCP tool namespaces
    allowed_tools = [
        "Read", "Edit", "Write", "Bash", "Glob", "Grep",
        "WebSearch", "WebFetch", "Agent",
        "mcp__autonomous-coder-tools__*",
    ]
    for server_name in mcp_servers:
        if server_name != "autonomous-coder-tools":
            allowed_tools.append(f"mcp__{server_name}__*")

    # Configure the SDK options
    options = ClaudeAgentOptions(
        model=config.model or "claude-opus-4-6",
        system_prompt=system_prompt,
        max_turns=config.max_turns,
        max_budget_usd=config.max_budget,
        effort=config.effort,
        allowed_tools=allowed_tools,
        agents=agents,
        hooks=hooks,
        mcp_servers=mcp_servers,
        permission_mode="acceptEdits",
        cwd=str(config.project_dir),
        setting_sources=["project"],
        thinking={"type": "enabled", "budget_tokens": config.thinking_budget},
        include_partial_messages=True,
    )

    # Build the prompt
    prompt = (
        f"Execute the following task specification against the project at {config.project_dir}.\n\n"
        f"## Task Specification\n{task_spec}\n\n"
        "## Instructions\n"
        "Follow your multi-phase workflow (Research -> Plan -> Implement -> Validate).\n"
        "Use subagents for parallel work where possible.\n"
        "Track all phase transitions with the track_phase tool.\n"
        "Save all research findings and plans with the save_findings tool.\n"
        "Read every relevant file COMPLETELY before making any changes.\n"
    )

    display.header(config)

    # Run the single SDK query — this drives the entire workflow
    session_result = SessionResult()

    try:
        async for message in query(prompt=prompt, options=options):
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock) and block.text:
                        display.agent_text(block.text)
                    elif isinstance(block, ToolUseBlock):
                        display.tool_use(block.name, block.input)
                    elif isinstance(block, ThinkingBlock):
                        if config.verbose:
                            display.thinking(block.thinking)

            elif isinstance(message, ResultMessage):
                elapsed = time.monotonic() - start_time
                session_result = SessionResult(
                    session_id=message.session_id,
                    status=message.subtype or ("error" if message.is_error else "success"),
                    total_cost_usd=message.total_cost_usd or 0.0,
                    num_turns=message.num_turns,
                    elapsed_seconds=elapsed,
                    phases=[
                        PhaseEvent(
                            phase=entry["phase"],
                            status=entry["status"],
                            details=entry.get("details", ""),
                            timestamp=entry.get("timestamp", ""),
                        )
                        for entry in get_phase_log()
                    ],
                    result=message.result,
                    stop_reason=message.stop_reason,
                    usage=message.usage,
                )

    except Exception as exc:
        elapsed = time.monotonic() - start_time
        session_result = SessionResult(
            status="error",
            total_cost_usd=0.0,
            num_turns=0,
            elapsed_seconds=elapsed,
            result=str(exc),
        )

    display.result(session_result)
    return session_result
