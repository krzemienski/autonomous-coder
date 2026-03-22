"""Hook closures for observability, safety, and coordination.

All mutable state lives in HookContext — no module-level globals.
Hook closures are created via factory functions bound to the context.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from claude_agent_sdk import HookMatcher

from .security import is_command_allowed


@dataclass
class HookContext:
    """Encapsulates all mutable state used by hooks."""

    project_path: Path
    extra_allowed_commands: set[str] = field(default_factory=set)
    audit_log: list[dict] = field(default_factory=list)
    subagent_tracker: dict[str, float] = field(default_factory=dict)
    on_progress: Callable[[str, str, str], None] | None = None

    def persist_audit_log(self, path: Path | None = None) -> None:
        """Write audit log to disk as JSONL."""
        import json

        target = path or (self.project_path / ".autonomous-coder" / "audit.jsonl")
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, "w") as f:
            for entry in self.audit_log:
                f.write(json.dumps(entry) + "\n")


# === PreToolUse Hooks ===


def _make_bash_security_gate(ctx: HookContext):
    async def bash_security_gate(
        input_data: Any, tool_use_id: str | None, context: Any
    ) -> dict:
        command = input_data["tool_input"].get("command", "")
        allowed, reason = is_command_allowed(command, ctx.extra_allowed_commands)
        if not allowed:
            return {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": f"Blocked: {reason}",
                }
            }
        return {}

    return bash_security_gate


def _make_file_scope_guard(ctx: HookContext):
    async def file_scope_guard(
        input_data: Any, tool_use_id: str | None, context: Any
    ) -> dict:
        file_path = input_data["tool_input"].get("file_path", "")
        if not file_path:
            return {}
        try:
            resolved = Path(file_path).resolve()
            project_resolved = ctx.project_path.resolve()
            if not str(resolved).startswith(str(project_resolved)):
                return {
                    "hookSpecificOutput": {
                        "hookEventName": "PreToolUse",
                        "permissionDecision": "deny",
                        "permissionDecisionReason": f"Write outside project: {file_path}",
                    }
                }
        except (ValueError, OSError):
            return {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": f"Invalid path: {file_path}",
                }
            }
        return {}

    return file_scope_guard


# === PostToolUse Hooks ===


def _make_audit_logger(ctx: HookContext):
    async def audit_logger(
        input_data: Any, tool_use_id: str | None, context: Any
    ) -> dict:
        entry: dict[str, Any] = {
            "tool": input_data.get("tool_name", "unknown"),
            "timestamp": time.time(),
            "tool_use_id": tool_use_id,
        }
        tool_input = input_data.get("tool_input", {})
        if "command" in tool_input:
            entry["detail"] = tool_input["command"][:120]
        elif "file_path" in tool_input:
            entry["detail"] = tool_input["file_path"]
        ctx.audit_log.append(entry)
        return {}

    return audit_logger


def _make_progress_extractor(ctx: HookContext):
    async def progress_extractor(
        input_data: Any, tool_use_id: str | None, context: Any
    ) -> dict:
        tool_name = input_data.get("tool_name", "")
        if tool_name == "mcp__autonomous-coder__report_progress":
            tool_input = input_data.get("tool_input", {})
            phase = tool_input.get("phase", "")
            status = tool_input.get("status", "")
            detail = tool_input.get("detail", "")
            if ctx.on_progress:
                ctx.on_progress(phase, status, detail)
        return {}

    return progress_extractor


# === SubagentStart/Stop Hooks ===


def _make_subagent_start_tracker(ctx: HookContext):
    async def subagent_start_tracker(
        input_data: Any, tool_use_id: str | None, context: Any
    ) -> dict:
        agent_id = input_data.get("agent_id", "unknown")
        ctx.subagent_tracker[agent_id] = time.time()
        return {}

    return subagent_start_tracker


def _make_subagent_stop_handler(ctx: HookContext):
    async def subagent_stop_handler(
        input_data: Any, tool_use_id: str | None, context: Any
    ) -> dict:
        agent_id = input_data.get("agent_id", "unknown")
        start_time = ctx.subagent_tracker.pop(agent_id, time.time())
        duration = time.time() - start_time
        ctx.audit_log.append({
            "tool": f"subagent:{agent_id}",
            "timestamp": time.time(),
            "duration": duration,
            "transcript_path": input_data.get("agent_transcript_path", ""),
        })
        return {}

    return subagent_stop_handler


# === PreCompact Hook ===


async def _auto_save_context(
    input_data: Any, tool_use_id: str | None, context: Any
) -> dict:
    """Remind Claude to save findings before context compaction."""
    return {
        "systemMessage": (
            "CONTEXT COMPACTION IMMINENT. If you have unsaved findings from the "
            "current phase, call save_findings NOW before your context is compressed. "
            "After compaction, use get_findings to retrieve previously saved results."
        ),
    }


# === Builder ===


def build_hooks(ctx: HookContext) -> dict[str, list[HookMatcher]]:
    """Assemble the complete hook configuration from a HookContext."""
    return {
        "PreToolUse": [
            HookMatcher(matcher="Bash", hooks=[_make_bash_security_gate(ctx)]),
            HookMatcher(matcher="Write|Edit", hooks=[_make_file_scope_guard(ctx)]),
        ],
        "PostToolUse": [
            HookMatcher(hooks=[_make_audit_logger(ctx)]),
            HookMatcher(
                matcher="mcp__autonomous-coder__report_progress",
                hooks=[_make_progress_extractor(ctx)],
            ),
        ],
        "SubagentStart": [
            HookMatcher(hooks=[_make_subagent_start_tracker(ctx)]),
        ],
        "SubagentStop": [
            HookMatcher(hooks=[_make_subagent_stop_handler(ctx)]),
        ],
        "PreCompact": [
            HookMatcher(hooks=[_auto_save_context]),
        ],
    }
