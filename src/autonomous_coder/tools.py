"""FindingsStore and custom in-process MCP tools.

Three tools registered as a single MCP server:
  - save_findings: persist phase results to disk (survives context compaction)
  - get_findings: retrieve previously saved findings
  - report_progress: notify the UI of phase transitions
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from claude_agent_sdk import create_sdk_mcp_server, tool

ALLOWED_CATEGORIES = {"research", "exploration", "plan", "implementation", "review"}
MAX_FINDINGS_SIZE = 50_000  # chars


@dataclass
class FindingsStore:
    """Encapsulates all mutable state for findings management.

    Passed to tool closures via factory — no module-level globals.
    """

    project_path: Path
    progress: dict[str, dict] = field(default_factory=dict)

    @property
    def dir(self) -> Path:
        return self.project_path / ".autonomous-coder" / "findings"

    def save(self, category: str, content: str) -> str:
        if category not in ALLOWED_CATEGORIES:
            return f"Invalid category: {category}. Must be one of: {ALLOWED_CATEGORIES}"

        if len(content) > MAX_FINDINGS_SIZE:
            content = content[:MAX_FINDINGS_SIZE] + "\n\n[TRUNCATED at 50,000 chars]"

        self.dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().isoformat(timespec="seconds")
        header = f"# {category.title()} Findings\n\nUpdated: {timestamp}\n\n"
        (self.dir / f"{category}.md").write_text(header + content, encoding="utf-8")
        return f"Saved {len(content)} chars to {category}.md"

    def load(self, category: str) -> str:
        path = self.dir / f"{category}.md"
        if not path.exists():
            return f"No findings saved for '{category}'"
        return path.read_text(encoding="utf-8")

    def report(self, phase: str, status: str, detail: str) -> None:
        self.progress[phase] = {
            "status": status,
            "detail": detail,
            "timestamp": datetime.now().isoformat(timespec="seconds"),
        }

    def persist_progress(self) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        (self.dir / "progress.json").write_text(
            json.dumps(self.progress, indent=2), encoding="utf-8"
        )


def create_findings_server(
    store: FindingsStore,
    on_progress: Callable[[str, str, str], None] | None = None,
) -> Any:
    """Create the in-process MCP server with tools bound to the store."""

    @tool(
        "save_findings",
        "Persist structured findings to disk. Call after each workflow phase "
        "to protect against context compaction. "
        "Categories: research, exploration, plan, implementation, review.",
        {"category": str, "content": str},
    )
    async def save_findings(args: dict[str, Any]) -> dict[str, Any]:
        result = store.save(args["category"], args["content"])
        return {"content": [{"type": "text", "text": result}]}

    @tool(
        "get_findings",
        "Retrieve previously saved findings by category. "
        "Use when you need to recall earlier phase results.",
        {"category": str},
    )
    async def get_findings(args: dict[str, Any]) -> dict[str, Any]:
        content = store.load(args["category"])
        return {"content": [{"type": "text", "text": content}]}

    @tool(
        "report_progress",
        "Report current progress to the user interface. "
        "Call at phase transitions and after completing significant steps.",
        {
            "type": "object",
            "properties": {
                "phase": {
                    "type": "string",
                    "enum": ["research", "explore", "plan", "implement", "review"],
                },
                "status": {
                    "type": "string",
                    "enum": ["starting", "in_progress", "complete", "skipped", "error"],
                },
                "detail": {"type": "string"},
            },
            "required": ["phase", "status", "detail"],
        },
    )
    async def report_progress(args: dict[str, Any]) -> dict[str, Any]:
        phase, status, detail = args["phase"], args["status"], args["detail"]
        store.report(phase, status, detail)
        store.persist_progress()
        if on_progress:
            on_progress(phase, status, detail)
        return {"content": [{"type": "text", "text": f"Progress: {phase} -> {status}"}]}

    return create_sdk_mcp_server(
        name="autonomous-coder",
        version="3.0.0",
        tools=[save_findings, get_findings, report_progress],
    )
