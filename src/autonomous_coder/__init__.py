"""
Autonomous Coder - AI-powered autonomous coding agent with Claude Agent SDK.

v2.0: SDK-native mode with subagents, hooks, and single-query orchestration.

Execution modes:
  1. SDK CLI (default): autonomous-coder task_spec.txt --project /path
  2. TUI Mode: autonomous-coder --tui "task description"
  3. Legacy CLI: autonomous-coder --legacy-cli "task description"
  4. Python API: from autonomous_coder import sdk_run; asyncio.run(sdk_run(config))

Architecture:
  - Single SDK query() drives the entire multi-phase workflow
  - AgentDefinition subagents for researcher, implementer, validator, planner
  - HookMatcher hooks for observability and safety (outside context window)
  - Custom MCP tools for phase tracking and findings persistence
  - Built-in cost ceiling, session resume, and automatic context compaction
"""

# SDK-native API (v2.0)
from .types import AutonomousCoderConfig, PhaseEvent, SessionResult
from .sdk_orchestrator import run as sdk_run
from .sdk_agents import build_agent_definitions
from .sdk_hooks import build_hooks
from .sdk_tools import build_custom_tools_server
from .sdk_mcp_servers import build_mcp_server_configs
from .sdk_prompts import build_orchestrator_prompt
from .display import Display

# Legacy API (v1.x — preserved for backward compatibility)
from .config import OrchestratorConfig, RoleConfig, MCP_SERVERS
from .orchestrator import AgentOrchestrator, PhaseContext, PhaseResult, PhaseRunner, security_callback
from .agent_factory import AgentFactory
from .agent_instance import AgentInstance, AgentStatus
from .memory import MemoryStore
from .messages import (
    AgentStarted, AgentOutput, AgentCompleted, AgentError,
    CostUpdate, SecurityBlock, PhaseStarted, PhaseCompleted,
)
from .agents import ResearchPhaseRunner, ExplorerPhaseRunner, PlannerPhaseRunner, CoderPhaseRunner
from .cli_adapter import CliAdapter
from .security import (
    ALLOWED_COMMANDS,
    DANGEROUS_PATTERNS,
    bash_security_hook,
    is_command_allowed,
    get_security_permissions,
    get_sandbox_settings,
)
from .prompts import (
    ensure_prompt_templates_exist,
    get_coder_prompt,
    get_explorer_prompt,
    get_planner_prompt,
    get_researcher_prompt,
    get_system_prompt,
)

# Legacy imports (may fail if legacy modules removed — that's OK)
try:
    from .agent import AutonomousCoderAgent, main as legacy_main, run_autonomous_coder
    from .client import AutonomousCoderClient, create_client
    from .progress import ProgressTracker, create_feature_list, update_feature_status
    from .researcher import ResearchPhase, run_research_phase
except ImportError:
    pass

__version__ = "2.0.0"
__author__ = "Claude Code Skills Factory"

__all__ = [
    # SDK-native API (v2.0)
    "AutonomousCoderConfig",
    "PhaseEvent",
    "SessionResult",
    "sdk_run",
    "build_agent_definitions",
    "build_hooks",
    "build_custom_tools_server",
    "build_mcp_server_configs",
    "build_orchestrator_prompt",
    "Display",
    # Legacy API
    "AutonomousCoderApp",
    "CliAdapter",
    "AgentOrchestrator",
    "AgentFactory",
    "AgentInstance",
    "AgentStatus",
    "PhaseContext",
    "PhaseResult",
    "PhaseRunner",
    "OrchestratorConfig",
    "RoleConfig",
    "MCP_SERVERS",
    "security_callback",
    "ResearchPhaseRunner",
    "ExplorerPhaseRunner",
    "PlannerPhaseRunner",
    "CoderPhaseRunner",
    "MemoryStore",
    "AgentStarted",
    "AgentOutput",
    "AgentCompleted",
    "AgentError",
    "CostUpdate",
    "SecurityBlock",
    "PhaseStarted",
    "PhaseCompleted",
    "ALLOWED_COMMANDS",
    "DANGEROUS_PATTERNS",
    "bash_security_hook",
    "is_command_allowed",
    "get_security_permissions",
    "get_sandbox_settings",
]
