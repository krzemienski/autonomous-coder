"""Subagent definitions for the SDK-native orchestrator.

These AgentDefinition objects replace the manual per-phase agent creation
with declarative subagent configurations. The SDK handles spawning,
isolation, and lifecycle management.

Model selection is intentional:
- Researchers on sonnet: cheaper, excellent at search and synthesis
- Implementers on opus: best reasoning for complex code generation
- Validators on sonnet: cost-effective for verification tasks
- Planner on sonnet: good at structured decomposition
"""
from __future__ import annotations

from claude_agent_sdk import AgentDefinition

from .sdk_prompts import (
    IMPLEMENTER_PROMPT,
    PLANNER_PROMPT,
    RESEARCHER_PROMPT,
    VALIDATOR_PROMPT,
)
from .types import AutonomousCoderConfig


def build_agent_definitions(config: AutonomousCoderConfig) -> dict[str, AgentDefinition]:
    """Build the subagent registry from configuration.

    Args:
        config: Autonomous coder configuration with optional model overrides.

    Returns:
        Dict of agent_name -> AgentDefinition for ClaudeAgentOptions.agents.
    """
    research_model = config.research_model or "sonnet"
    implement_model = config.implement_model or "opus"
    validate_model = config.validate_model or "sonnet"

    return {
        "researcher": AgentDefinition(
            description=(
                "Deep research specialist for technology evaluation, library comparison, "
                "architecture analysis, and codebase comprehension. Use this agent when you "
                "need to: evaluate libraries or frameworks, analyze existing code patterns, "
                "search for best practices, or investigate technical approaches. "
                "Spawn MULTIPLE researcher instances in parallel for independent research domains."
            ),
            prompt=RESEARCHER_PROMPT,
            tools=[
                "Read", "Glob", "Grep", "WebSearch", "WebFetch",
                "mcp__context7__*",
                "mcp__firecrawl__*",
            ],
            model=research_model,
        ),
        "implementer": AgentDefinition(
            description=(
                "Code implementation specialist for writing, editing, and refactoring code. "
                "Use this agent when you need to: create new files, modify existing code, "
                "install dependencies, run build commands, or execute implementation plans. "
                "This agent has full write access to the filesystem and can run commands."
            ),
            prompt=IMPLEMENTER_PROMPT,
            tools=["Read", "Edit", "Write", "Bash", "Glob", "Grep"],
            model=implement_model,
        ),
        "validator": AgentDefinition(
            description=(
                "Validation and testing specialist for verifying implementations. "
                "Use this agent when you need to: run tests, verify builds, check "
                "that requirements are met, or validate integration points."
            ),
            prompt=VALIDATOR_PROMPT,
            tools=["Bash", "Read", "Glob", "Grep"],
            model=validate_model,
        ),
        "planner": AgentDefinition(
            description=(
                "Strategic planning specialist for creating detailed implementation plans. "
                "Use this agent when you need to: break down complex tasks into ordered steps, "
                "identify dependencies between changes, or create migration strategies."
            ),
            prompt=PLANNER_PROMPT,
            tools=["Read", "Glob", "Grep"],
            model=research_model,
        ),
    }
