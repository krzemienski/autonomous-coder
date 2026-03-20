"""
Autonomous Coder - AI-powered autonomous coding skill with TUI dashboard.

Two execution modes:
  1. TUI Mode: python -m autonomous_coder ["task description"]
  2. Legacy CLI: python -c "from autonomous_coder import main; main()"

Architecture:
  - Four-phase pipeline: Research → Explore → Plan → Code
  - PhaseRunner protocol for extensible phase implementations
  - Textual TUI with live agent streaming, cost tracking, progress display
  - SQLite + FTS5 persistence for sessions and conversations
  - can_use_tool security callback (defense-in-depth)
"""

# Legacy API (preserved for backward compatibility)
from .agent import AutonomousCoderAgent, main, run_autonomous_coder
from .client import AutonomousCoderClient, create_client
from .progress import ProgressTracker, create_feature_list, update_feature_status
from .prompts import (
    ensure_prompt_templates_exist,
    get_coder_prompt,
    get_explorer_prompt,
    get_planner_prompt,
    get_researcher_prompt,
    get_system_prompt,
)
from .researcher import ResearchPhase, run_research_phase
from .security import (
    ALLOWED_COMMANDS,
    DANGEROUS_PATTERNS,
    bash_security_hook,
    get_sandbox_settings,
    get_security_permissions,
    is_command_allowed,
)

# TUI components
from .app import AutonomousCoderApp
from .config import OrchestratorConfig, RoleConfig, MCP_SERVERS
from .orchestrator import AgentOrchestrator, PhaseContext, PhaseResult, PhaseRunner, security_callback
from .agent_factory import AgentFactory
from .agent_instance import AgentInstance, AgentStatus
from .memory import MemoryStore
from .messages import (
    AgentStarted, AgentOutput, AgentCompleted, AgentError,
    CostUpdate, SecurityBlock, PhaseStarted, PhaseCompleted,
)

# Phase runners
from .agents import ResearchPhaseRunner, ExplorerPhaseRunner, PlannerPhaseRunner, CoderPhaseRunner

__version__ = "2.0.0"
__author__ = "Claude Code Skills Factory"

__all__ = [
    # TUI entry point
    "AutonomousCoderApp",
    # Orchestration
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
    # Phase runners
    "ResearchPhaseRunner",
    "ExplorerPhaseRunner",
    "PlannerPhaseRunner",
    "CoderPhaseRunner",
    # Persistence
    "MemoryStore",
    # Messages
    "AgentStarted",
    "AgentOutput",
    "AgentCompleted",
    "AgentError",
    "CostUpdate",
    "SecurityBlock",
    "PhaseStarted",
    "PhaseCompleted",
    # Legacy API
    "run_autonomous_coder",
    "main",
    "AutonomousCoderAgent",
    "AutonomousCoderClient",
    "create_client",
    "ProgressTracker",
    "create_feature_list",
    "update_feature_status",
    "get_researcher_prompt",
    "get_explorer_prompt",
    "get_planner_prompt",
    "get_coder_prompt",
    "get_system_prompt",
    "ensure_prompt_templates_exist",
    "ResearchPhase",
    "run_research_phase",
    "ALLOWED_COMMANDS",
    "DANGEROUS_PATTERNS",
    "bash_security_hook",
    "is_command_allowed",
    "get_security_permissions",
    "get_sandbox_settings",
]
