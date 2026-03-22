"""SessionManager — composition root for the autonomous coding session.

This is the core of v3. A single ClaudeSDKClient session where Claude drives
the entire workflow. Python controls lifecycle, security, and UI rendering.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient

from .agents import build_agent_definitions
from .config import SessionConfig
from .detect import detect_project_state
from .hooks import HookContext, build_hooks
from .mcp_servers import build_mcp_servers
from .prompts import build_system_prompt
from .security import security_gate
from .streaming import EventHandler, process_stream
from .tools import FindingsStore

logger = logging.getLogger(__name__)


@dataclass
class SessionState:
    """Persisted session state for resume capability."""

    session_id: str
    task: str
    project_path: str
    budget_used: float
    success: bool

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), indent=2))

    @classmethod
    def load(cls, path: Path) -> SessionState | None:
        if not path.exists():
            return None
        return cls(**json.loads(path.read_text()))


class SessionManager:
    """Manages the lifecycle of a single autonomous coding session."""

    def __init__(self, config: SessionConfig, handler: EventHandler) -> None:
        self.config = config
        self.handler = handler
        self._client: ClaudeSDKClient | None = None

    async def run(self, task: str) -> SessionState:
        """Run the autonomous coding session.

        Creates a single ClaudeSDKClient session. Claude drives phase ordering
        via its system prompt. Python handles lifecycle, security, and UI.
        """
        store = FindingsStore(self.config.project_path)
        hook_ctx = HookContext(
            project_path=self.config.project_path,
            extra_allowed_commands=self.config.extra_allowed_commands,
            on_progress=self.handler.on_progress,
        )

        project_state = detect_project_state(self.config.project_path)
        options = self._build_options(project_state, store, hook_ctx)
        initial_prompt = self._build_initial_prompt(task, project_state)

        async with ClaudeSDKClient(options=options) as client:
            self._client = client
            await client.query(initial_prompt)
            result_msg = await process_stream(client, self.handler)

        hook_ctx.persist_audit_log()

        state = SessionState(
            session_id=getattr(result_msg, "session_id", "") if result_msg else "",
            task=task,
            project_path=str(self.config.project_path),
            budget_used=(
                result_msg.total_cost_usd or 0.0
                if result_msg
                else 0.0
            ),
            success=not getattr(result_msg, "is_error", True) if result_msg else False,
        )
        state_path = self.config.project_path / ".autonomous-coder" / "session.json"
        state.save(state_path)
        return state

    async def interrupt(self) -> None:
        """Interrupt the running session gracefully."""
        if self._client:
            await self._client.interrupt()

    def _build_options(
        self,
        project_state: dict,
        store: FindingsStore,
        hook_ctx: HookContext,
    ) -> ClaudeAgentOptions:
        """Assemble ClaudeAgentOptions from config + project state."""
        mcp_servers = build_mcp_servers(self.config, store, self.handler)
        agents = build_agent_definitions(self.config)

        # Build allowed_tools with MCP wildcards
        allowed_tools = [
            "Read", "Edit", "Write", "Bash", "Glob", "Grep",
            "WebSearch", "WebFetch", "Agent",
        ]
        for server_name in mcp_servers:
            allowed_tools.append(f"mcp__{server_name}__*")

        return ClaudeAgentOptions(
            model=self.config.model,
            system_prompt=build_system_prompt(project_state, self.config),
            agents=agents,
            hooks=build_hooks(hook_ctx),
            allowed_tools=allowed_tools,
            can_use_tool=security_gate,
            mcp_servers=mcp_servers,
            include_partial_messages=True,
            permission_mode=self.config.permission_mode,
            max_budget_usd=self.config.budget_limit,
            max_turns=self.config.max_turns,
            effort=self.config.effort,
            cwd=str(self.config.project_path),
            thinking={"type": "enabled", "budget_tokens": self.config.thinking_budget},
            enable_file_checkpointing=True,
            resume=self.config.resume_session_id,
        )

    def _build_initial_prompt(self, task: str, project_state: dict) -> str:
        """Build the initial user prompt for the session."""
        state_desc = project_state.get("project_state", "unknown")
        stack = project_state.get("stack", {})

        parts = [f"## Task\n{task}"]
        if state_desc == "existing" and stack:
            parts.append(f"## Project Info\nStack: {stack}")
        parts.append(
            "## Instructions\n"
            "Follow your workflow phases. Save findings after each phase. "
            "Report progress at transitions. Read files completely before modifying."
        )
        return "\n\n".join(parts)



def load_last_session_id(project_path: Path) -> str | None:
    """Load the session ID from the last saved session state."""
    state = SessionState.load(
        project_path / ".autonomous-coder" / "session.json"
    )
    return state.session_id if state else None
