"""
Claude Code SDK client with security configuration and MCP setup.

Provides a configured client for running autonomous coding sessions
with defense-in-depth security.
"""

import asyncio
from pathlib import Path
from typing import Any, AsyncIterator

from claude_code_sdk import ClaudeCodeOptions, query
from claude_code_sdk.types import (
    AssistantMessage,
    ContentBlock,
    ResultMessage,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
)

from .security import (
    bash_security_hook,
    get_sandbox_settings,
    get_security_permissions,
)


class AutonomousCoderClient:
    """
    Client for running autonomous coding sessions with Claude.

    Configures Claude Code SDK with:
    - Security permissions scoped to project directory
    - Bash command validation via PreToolUse hooks
    - MCP server configuration for four-phase workflow:
      * Research: Firecrawl (web research), Context7 (library docs)
      * Explorer: Serena (semantic code analysis)
      * Planner: Sequential-thinking (reasoning)
      * Coder: All tools for implementation
    - Sandbox settings for additional isolation
    """

    def __init__(
        self,
        project_path: str | Path,
        model: str = "claude-sonnet-4-20250514",
        max_tokens: int = 16384,
        sandbox_enabled: bool = True,
    ):
        """
        Initialize the autonomous coder client.

        Args:
            project_path: Path to the project directory
            model: Claude model to use
            max_tokens: Maximum tokens for responses
            sandbox_enabled: Whether to enable OS sandbox
        """
        self.project_path = Path(project_path).resolve()
        self.model = model
        self.max_tokens = max_tokens
        self.sandbox_enabled = sandbox_enabled

        # Validate project path exists
        if not self.project_path.exists():
            raise ValueError(f"Project path does not exist: {self.project_path}")

        if not self.project_path.is_dir():
            raise ValueError(f"Project path is not a directory: {self.project_path}")

    def get_mcp_servers(self) -> dict[str, Any]:
        """
        Get MCP server configuration for four-phase workflow.

        Returns:
            Dictionary of MCP server configurations

        MCP Servers by Phase:
            Research Phase:
            - firecrawl-mcp: Web research, scraping, MCP discovery
            - Context7: Library documentation and API references

            Explorer Phase:
            - serena: Semantic code analysis (symbols, references, patterns)

            Planner Phase:
            - sequential-thinking: Step-by-step reasoning for complex planning

            Coder Phase:
            - All servers: Full access for implementation
        """
        return {
            "serena": {
                "command": "uvx",
                "args": ["serena"],
                "env": {
                    "SERENA_PROJECT": str(self.project_path),
                },
            },
            "sequential-thinking": {
                "command": "npx",
                "args": ["-y", "@modelcontextprotocol/server-sequential-thinking"],
            },
            "Context7": {
                "command": "npx",
                "args": ["-y", "@upstash/context7-mcp"],
            },
            "firecrawl-mcp": {
                "command": "npx",
                "args": ["-y", "firecrawl-mcp"],
                "env": {
                    "FIRECRAWL_API_KEY": "${FIRECRAWL_API_KEY}",
                },
            },
        }

    def get_options(self, system_prompt: str | None = None) -> ClaudeCodeOptions:
        """
        Get Claude Code SDK options with security configuration.

        Args:
            system_prompt: Optional system prompt override

        Returns:
            Configured ClaudeCodeOptions
        """
        permissions = get_security_permissions(str(self.project_path))
        sandbox = get_sandbox_settings() if self.sandbox_enabled else {}

        options = ClaudeCodeOptions(
            model=self.model,
            max_tokens=self.max_tokens,
            cwd=str(self.project_path),
            permissions=permissions,
            mcp_servers=self.get_mcp_servers(),
        )

        # Add sandbox settings if enabled
        if self.sandbox_enabled and sandbox:
            options.sandbox = sandbox

        # Add system prompt if provided
        if system_prompt:
            options.system_prompt = system_prompt

        return options

    async def run_session(
        self,
        prompt: str,
        system_prompt: str | None = None,
    ) -> AsyncIterator[ContentBlock]:
        """
        Run a Claude session with the given prompt.

        This is the core method for interacting with Claude. It yields
        content blocks as they are streamed from the API.

        Args:
            prompt: The user prompt to send
            system_prompt: Optional system prompt

        Yields:
            Content blocks from the response
        """
        options = self.get_options(system_prompt)

        async for message in query(prompt=prompt, options=options):
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    # Validate bash commands before execution
                    if isinstance(block, ToolUseBlock):
                        if block.name == "Bash":
                            validation = await bash_security_hook(block.input)
                            if validation is not None:
                                # Command blocked - yield error block
                                yield TextBlock(
                                    type="text",
                                    text=f"Security: {validation.get('error', 'Command blocked')}",
                                )
                                continue

                    yield block

            elif isinstance(message, ResultMessage):
                # Final result - yield any remaining content
                for block in message.content:
                    yield block

    async def run_session_to_completion(
        self,
        prompt: str,
        system_prompt: str | None = None,
    ) -> dict[str, Any]:
        """
        Run a session and collect all results.

        Args:
            prompt: The user prompt
            system_prompt: Optional system prompt

        Returns:
            Dictionary with collected results
        """
        text_content: list[str] = []
        tool_uses: list[dict[str, Any]] = []
        tool_results: list[dict[str, Any]] = []

        async for block in self.run_session(prompt, system_prompt):
            if isinstance(block, TextBlock):
                text_content.append(block.text)
            elif isinstance(block, ToolUseBlock):
                tool_uses.append({
                    "name": block.name,
                    "input": block.input,
                    "id": block.id,
                })
            elif isinstance(block, ToolResultBlock):
                tool_results.append({
                    "tool_use_id": block.tool_use_id,
                    "content": block.content,
                })

        return {
            "text": "\n".join(text_content),
            "tool_uses": tool_uses,
            "tool_results": tool_results,
            "success": True,
        }

    async def explore_codebase(
        self,
        task: str,
        explorer_prompt: str,
    ) -> dict[str, Any]:
        """
        Run the exploration phase.

        Uses Serena MCP to analyze the codebase structure and
        gather context for the given task.

        Args:
            task: The user's task description
            explorer_prompt: The formatted explorer prompt

        Returns:
            Exploration results dictionary
        """
        result = await self.run_session_to_completion(explorer_prompt)

        # Try to parse JSON from the response
        text = result.get("text", "")
        exploration = self._extract_json_from_text(text)

        if exploration:
            result["exploration"] = exploration

        return result

    async def create_plan(
        self,
        task: str,
        exploration_results: dict[str, Any],
        planner_prompt: str,
    ) -> dict[str, Any]:
        """
        Run the planning phase.

        Creates a comprehensive implementation plan based on
        the exploration results.

        Args:
            task: The user's task description
            exploration_results: Results from exploration phase
            planner_prompt: The formatted planner prompt

        Returns:
            Planning results with implementation plan
        """
        result = await self.run_session_to_completion(planner_prompt)

        # Try to parse JSON plan from the response
        text = result.get("text", "")
        plan = self._extract_json_from_text(text)

        if plan:
            result["plan"] = plan

        return result

    async def implement_task(
        self,
        task: dict[str, Any],
        coder_prompt: str,
    ) -> dict[str, Any]:
        """
        Implement a single task from the plan.

        Args:
            task: The task to implement
            coder_prompt: The formatted coder prompt

        Returns:
            Implementation results
        """
        result = await self.run_session_to_completion(coder_prompt)
        result["task_id"] = task.get("id")
        return result

    def _extract_json_from_text(self, text: str) -> dict[str, Any] | None:
        """
        Extract JSON object from text.

        Handles JSON embedded in markdown code blocks.

        Args:
            text: Text potentially containing JSON

        Returns:
            Parsed JSON dictionary or None
        """
        import json
        import re

        # Try to find JSON in code blocks
        json_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass

        # Try to find standalone JSON object
        json_match = re.search(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", text, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(0))
            except json.JSONDecodeError:
                pass

        return None


def create_client(
    project_path: str | Path,
    model: str = "claude-sonnet-4-20250514",
    sandbox_enabled: bool = True,
) -> AutonomousCoderClient:
    """
    Create a configured autonomous coder client.

    Args:
        project_path: Path to the project directory
        model: Claude model to use
        sandbox_enabled: Whether to enable OS sandbox

    Returns:
        Configured AutonomousCoderClient
    """
    return AutonomousCoderClient(
        project_path=project_path,
        model=model,
        sandbox_enabled=sandbox_enabled,
    )


# Export
__all__ = [
    "AutonomousCoderClient",
    "create_client",
]
