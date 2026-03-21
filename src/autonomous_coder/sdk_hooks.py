"""Hook callbacks for observability, safety, and coordination.

These replace inline print statements and manual logging with SDK-native
hooks that fire OUTSIDE the context window. The hooks provide:
- Tool call logging with timestamps
- Safety guards for dangerous commands
- Subagent lifecycle tracking
- Session completion events
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from claude_agent_sdk import HookMatcher

from .display import Display


def build_hooks(display: Display) -> dict[str, list[HookMatcher]]:
    """Build the complete hook configuration for observability and safety.

    Args:
        display: Display instance for formatting terminal output.

    Returns:
        Dict of hook_event -> list[HookMatcher] for ClaudeAgentOptions.hooks.
    """

    async def pre_tool_use_logger(input_data: dict, tool_use_id: str | None, context: Any) -> dict:
        """Log every tool call with timestamp."""
        tool_name = input_data.get("tool_name", "")
        tool_input = input_data.get("tool_input", {})
        display.tool_use(tool_name, tool_input)
        return {}

    async def safety_guard(input_data: dict, tool_use_id: str | None, context: Any) -> dict:
        """Block dangerous bash commands before execution."""
        if input_data.get("tool_name") != "Bash":
            return {}

        tool_input = input_data.get("tool_input", {})
        command = tool_input.get("command", "")

        blocked_patterns = [
            "rm -rf /", "rm -rf ~", "rm -rf /*",
            "rm -rf $HOME",
            "> /dev/sda", "mkfs.",
            ":(){:|:&};:",
            "dd if=/dev/zero of=/dev/",
            "chmod -R 777 /",
            "chmod 777 /",
            "sudo rm", "sudo chmod", "sudo chown",
            "curl | sh", "curl | bash",
            "wget | sh", "wget | bash",
            "eval $(", "base64 -d |",
        ]

        command_lower = command.lower()
        for pattern in blocked_patterns:
            if pattern.lower() in command_lower:
                display.blocked_command(command, pattern)
                return {
                    "hookSpecificOutput": {
                        "hookEventName": "PreToolUse",
                        "permissionDecision": "deny",
                        "permissionDecisionReason": (
                            f"Safety guard: blocked dangerous pattern '{pattern}'"
                        ),
                    }
                }
        return {}

    async def post_tool_use_logger(input_data: dict, tool_use_id: str | None, context: Any) -> dict:
        """Log tool completion."""
        tool_name = input_data.get("tool_name", "")
        display.tool_result(tool_name, tool_use_id)
        return {}

    async def subagent_start(input_data: dict, tool_use_id: str | None, context: Any) -> dict:
        """Track subagent spawn events."""
        agent_id = input_data.get("agent_id", "unknown")
        display.subagent_started(agent_id)
        return {}

    async def subagent_stop(input_data: dict, tool_use_id: str | None, context: Any) -> dict:
        """Track subagent completion events."""
        agent_id = input_data.get("agent_id", "unknown")
        transcript_path = input_data.get("agent_transcript_path", "")
        display.subagent_completed(agent_id, transcript_path)
        return {}

    async def on_stop(input_data: dict, tool_use_id: str | None, context: Any) -> dict:
        """Handle session stop event."""
        display.session_stopped()
        return {}

    return {
        "PreToolUse": [
            HookMatcher(matcher="Bash", hooks=[safety_guard]),
            HookMatcher(hooks=[pre_tool_use_logger]),
        ],
        "PostToolUse": [
            HookMatcher(hooks=[post_tool_use_logger]),
        ],
        "SubagentStart": [
            HookMatcher(hooks=[subagent_start]),
        ],
        "SubagentStop": [
            HookMatcher(hooks=[subagent_stop]),
        ],
        "Stop": [
            HookMatcher(hooks=[on_stop]),
        ],
    }
