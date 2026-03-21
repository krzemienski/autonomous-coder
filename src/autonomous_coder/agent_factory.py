"""Agent factory creating ClaudeAgentOptions per role."""
from typing import Any, Callable

from claude_agent_sdk import ClaudeAgentOptions

from .config import MCP_SERVERS, OrchestratorConfig


class AgentFactory:
    """Creates configured ClaudeAgentOptions for each agent role.

    Responsibilities:
    - Map role config → ClaudeAgentOptions fields
    - Assemble mcp_servers as a DICT (keyed by server name, NOT a list)
    - Inject SERENA_PROJECT env when serena is included
    - Expose budget_limit as a separate concern
    """

    def __init__(self, config: OrchestratorConfig) -> None:
        """Initialize the factory with orchestrator configuration.

        Args:
            config: Configuration containing role definitions and project path.
        """
        self.config = config

    def create_options(
        self,
        role: str,
        system_prompt: str,
        security_callback: Callable | None = None,
        hooks: dict | None = None,
    ) -> ClaudeAgentOptions:
        """Build ClaudeAgentOptions for a specific agent role.

        Args:
            role: Key into OrchestratorConfig.roles (e.g. "research", "code").
            system_prompt: Full system prompt text for this agent turn.
            security_callback: Optional can_use_tool callback for tool-level
                security enforcement. Signature: async (tool_name, tool_input, ctx).
            hooks: Optional hooks dict passed through to ClaudeAgentOptions.

        Returns:
            A fully configured ClaudeAgentOptions instance.
        """
        role_config = self.config.roles[role]

        # Build MCP servers dict — must be a dict, NOT a list
        mcp_servers: dict[str, Any] = {
            key: dict(MCP_SERVERS[key])  # shallow copy to avoid mutating registry
            for key in role_config.mcp_keys
            if key in MCP_SERVERS
        }

        # Inject project path into serena env so it knows which project to index
        if "serena" in mcp_servers:
            existing_env = mcp_servers["serena"].get("env", {}) or {}
            mcp_servers["serena"] = {
                **mcp_servers["serena"],
                "env": {**existing_env, "SERENA_PROJECT": str(self.config.project_path)},
            }

        return ClaudeAgentOptions(
            model=role_config.model,
            system_prompt=system_prompt,
            allowed_tools=role_config.tools,
            mcp_servers=mcp_servers,
            max_turns=role_config.max_turns,
            cwd=str(self.config.project_path),
            permission_mode="acceptEdits",
            can_use_tool=security_callback,
            include_partial_messages=True,
            hooks=hooks or {},
        )

    def get_budget_limit(self, role: str) -> float:
        """Return the manual budget cap for a role.

        Budget enforcement is application-level — callers compare
        ResultMessage.total_cost_usd against this value.
        """
        return self.config.roles[role].budget_limit
