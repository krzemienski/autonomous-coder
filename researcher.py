"""
Research/Onboarding phase for discovering relevant MCP servers, skills, and resources.

This module performs web research BEFORE codebase exploration to identify:
- Relevant MCP servers for the specific task type
- Existing skills and examples that could be adapted
- Library documentation and best practices
- GitHub repositories with relevant implementations
"""

import asyncio
import json
from pathlib import Path
from typing import Any

from .client import AutonomousCoderClient


# Common MCP server registries and sources
MCP_DISCOVERY_SOURCES = [
    "github.com/modelcontextprotocol",
    "github.com/anthropics",
    "npmjs.com/search?q=mcp-server",
    "pypi.org/search/?q=mcp",
    "github.com/topics/mcp-server",
    "github.com/topics/model-context-protocol",
]

# Task type to MCP server mapping for common scenarios
TASK_TYPE_MCP_HINTS = {
    "ios": ["xcode", "ios-simulator", "swift", "xc-mcp"],
    "android": ["android", "adb", "gradle", "kotlin"],
    "web": ["playwright", "puppeteer", "browser", "chrome-devtools"],
    "database": ["postgres", "mysql", "mongodb", "sqlite", "database"],
    "api": ["openapi", "swagger", "rest", "graphql"],
    "aws": ["aws", "cloudformation", "cdk", "s3", "lambda"],
    "docker": ["docker", "container", "kubernetes", "k8s"],
    "git": ["git", "github", "gitlab"],
    "testing": ["jest", "pytest", "vitest", "testing"],
    "documentation": ["docs", "markdown", "readme", "documentation"],
}


class ResearchPhase:
    """
    Executes the Research/Onboarding phase of the autonomous coder.

    This phase runs BEFORE the Explorer phase to:
    1. Identify the task type and domain
    2. Search for relevant MCP servers
    3. Find existing skills and examples
    4. Gather library documentation
    5. Recommend additional tools to install
    """

    def __init__(self, client: AutonomousCoderClient):
        """
        Initialize the research phase.

        Args:
            client: Configured AutonomousCoderClient with MCP servers
        """
        self.client = client
        self.project_path = client.project_path

    def _detect_task_types(self, task: str) -> list[str]:
        """
        Detect task types from the task description.

        Args:
            task: User's task description

        Returns:
            List of detected task type keywords
        """
        task_lower = task.lower()
        detected = []

        # Check for explicit task type mentions
        type_keywords = {
            "ios": ["ios", "iphone", "ipad", "swift", "xcode", "swiftui", "uikit"],
            "android": ["android", "kotlin", "java mobile", "gradle"],
            "web": ["web", "browser", "html", "css", "javascript", "react", "vue", "angular"],
            "database": ["database", "sql", "postgres", "mysql", "mongodb", "sqlite", "orm"],
            "api": ["api", "rest", "graphql", "endpoint", "openapi", "swagger"],
            "aws": ["aws", "amazon", "s3", "lambda", "cloudformation", "cdk", "ec2"],
            "docker": ["docker", "container", "kubernetes", "k8s", "helm"],
            "git": ["git", "github", "gitlab", "version control", "repository"],
            "testing": ["test", "testing", "unit test", "integration test", "e2e"],
            "documentation": ["documentation", "docs", "readme", "markdown"],
        }

        for task_type, keywords in type_keywords.items():
            if any(kw in task_lower for kw in keywords):
                detected.append(task_type)

        return detected if detected else ["general"]

    def _get_search_queries(self, task: str, task_types: list[str]) -> list[str]:
        """
        Generate search queries for finding relevant MCP servers and resources.

        Args:
            task: User's task description
            task_types: Detected task types

        Returns:
            List of search queries
        """
        queries = []

        # MCP server discovery queries
        for task_type in task_types:
            hints = TASK_TYPE_MCP_HINTS.get(task_type, [])
            for hint in hints[:2]:  # Limit to top 2 hints per type
                queries.append(f"MCP server {hint} model context protocol")
                queries.append(f"github mcp-server {hint}")

        # General MCP discovery
        queries.append("MCP server tools model context protocol github")

        # Skills and examples discovery
        for task_type in task_types:
            queries.append(f"Claude Code skill {task_type}")
            queries.append(f"anthropic claude {task_type} automation")

        # Deduplicate while preserving order
        seen = set()
        unique_queries = []
        for q in queries:
            if q not in seen:
                seen.add(q)
                unique_queries.append(q)

        return unique_queries[:8]  # Limit to 8 queries

    async def run(
        self,
        task: str,
        researcher_prompt: str,
    ) -> dict[str, Any]:
        """
        Execute the research phase.

        This method:
        1. Detects task types from the description
        2. Generates relevant search queries
        3. Uses Firecrawl MCP to search for resources
        4. Uses Context7 to find library documentation
        5. Returns structured research findings

        Args:
            task: User's task description
            researcher_prompt: Formatted researcher prompt template

        Returns:
            Research results dictionary with:
            - task_types: Detected task categories
            - mcp_servers: Discovered MCP servers with relevance scores
            - skills: Found skills and examples
            - libraries: Relevant library documentation
            - recommendations: Actionable recommendations
        """
        # Detect task types
        task_types = self._detect_task_types(task)

        # Generate search queries
        search_queries = self._get_search_queries(task, task_types)

        # Run the research session with Claude
        result = await self.client.run_session_to_completion(researcher_prompt)

        # Extract structured research from response
        research = self._extract_research_results(result.get("text", ""))

        # Add detected metadata
        research["task_types"] = task_types
        research["search_queries_used"] = search_queries

        # Determine success
        result["research"] = research
        result["success"] = bool(
            research.get("mcp_servers") or
            research.get("skills") or
            research.get("libraries")
        )

        return result

    def _extract_research_results(self, text: str) -> dict[str, Any]:
        """
        Extract structured research results from response text.

        Args:
            text: Raw response text potentially containing JSON

        Returns:
            Parsed research results or empty structure
        """
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

        # Return empty structure if no JSON found
        return {
            "mcp_servers": [],
            "skills": [],
            "libraries": [],
            "recommendations": [],
            "raw_findings": text[:2000] if text else "",
        }


async def run_research_phase(
    client: AutonomousCoderClient,
    task: str,
    researcher_prompt: str,
) -> dict[str, Any]:
    """
    Convenience function to run the research phase.

    Args:
        client: Configured client
        task: User's task description
        researcher_prompt: Formatted prompt template

    Returns:
        Research results
    """
    phase = ResearchPhase(client)
    return await phase.run(task, researcher_prompt)


# Export
__all__ = [
    "ResearchPhase",
    "run_research_phase",
    "MCP_DISCOVERY_SOURCES",
    "TASK_TYPE_MCP_HINTS",
]
