"""Custom in-process MCP tools for the autonomous coder.

These tools provide phase tracking and findings persistence that operate
outside the agent's context window via the SDK's MCP server mechanism.

The @tool decorator creates SdkMcpTool objects that are registered with
create_sdk_mcp_server(). The underlying logic functions (_track_phase_impl etc.)
are kept separate so they can be called directly from Python for testing
and from the Display class for phase tracking.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from claude_agent_sdk import create_sdk_mcp_server, tool


# Module-level state for phase tracking
_phase_log: list[dict[str, Any]] = []
_findings_dir: Path | None = None


def set_findings_dir(path: Path) -> None:
    """Set the directory where findings will be saved."""
    global _findings_dir
    _findings_dir = path


def get_phase_log() -> list[dict[str, Any]]:
    """Return the accumulated phase log entries."""
    return list(_phase_log)


def clear_phase_log() -> None:
    """Reset the phase log for a new session."""
    _phase_log.clear()


def record_phase(phase: str, status: str, details: str = "") -> dict[str, Any]:
    """Record a phase transition event (callable from Python).

    Args:
        phase: Phase name (research, plan, implement, validate).
        status: Phase status (started, completed, failed).
        details: Additional details about the transition.

    Returns:
        The phase log entry dict.
    """
    entry = {
        "phase": phase,
        "status": status,
        "details": details,
        "timestamp": datetime.now().isoformat(),
    }
    _phase_log.append(entry)
    return entry


# ---------------------------------------------------------------------------
# MCP Tool definitions (invoked by the SDK via the in-process MCP server)
# ---------------------------------------------------------------------------


@tool(
    "track_phase",
    "Record a phase transition with timing metadata. Use this at the start and end of each workflow phase.",
    {
        "phase": {"type": "string", "description": "Phase name (research, plan, implement, validate)"},
        "status": {"type": "string", "description": "Phase status (started, completed, failed)"},
        "details": {"type": "string", "description": "Additional details about the transition"},
    },
)
async def track_phase_tool(args: dict[str, Any]) -> dict[str, Any]:
    """Record a phase transition event."""
    entry = record_phase(args["phase"], args["status"], args.get("details", ""))
    return {
        "content": [
            {
                "type": "text",
                "text": f"Phase '{args['phase']}' marked as '{args['status']}' at {entry['timestamp']}",
            }
        ]
    }


@tool(
    "save_findings",
    "Persist research findings, plans, or analysis results to disk for later reference.",
    {
        "category": {"type": "string", "description": "Category of findings (research, plan, analysis)"},
        "content": {"type": "string", "description": "The content to save"},
        "filename": {"type": "string", "description": "Filename to save as (e.g. 'technology-stack.md')"},
    },
)
async def save_findings_tool(args: dict[str, Any]) -> dict[str, Any]:
    """Save findings to the project's .autonomous-coder directory."""
    base_dir = _findings_dir or Path(".autonomous-coder")
    findings_path = base_dir / "findings" / args.get("category", "general")
    findings_path.mkdir(parents=True, exist_ok=True)

    filename = args["filename"]
    file_path = findings_path / filename
    file_path.write_text(args["content"], encoding="utf-8")

    return {
        "content": [
            {
                "type": "text",
                "text": f"Saved findings to {file_path}",
            }
        ]
    }


@tool(
    "get_phase_status",
    "Get the current status of all tracked phases.",
    {},
)
async def get_phase_status_tool(args: dict[str, Any]) -> dict[str, Any]:
    """Return the current phase tracking status."""
    if not _phase_log:
        return {
            "content": [{"type": "text", "text": "No phases tracked yet."}]
        }

    summary_lines = []
    for entry in _phase_log:
        summary_lines.append(
            f"[{entry['timestamp']}] {entry['phase']}: {entry['status']}"
            + (f" — {entry['details']}" if entry.get("details") else "")
        )

    return {
        "content": [{"type": "text", "text": "\n".join(summary_lines)}]
    }


def build_custom_tools_server() -> dict[str, Any]:
    """Build the in-process MCP server config for custom tools.

    Returns a dict suitable for the mcp_servers field of ClaudeAgentOptions.
    """
    return create_sdk_mcp_server(
        name="autonomous-coder-tools",
        version="2.0.0",
        tools=[track_phase_tool, save_findings_tool, get_phase_status_tool],
    )
