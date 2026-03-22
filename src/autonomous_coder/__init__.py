"""Autonomous Coder v4 — SDK-native multi-agent architecture.

Built on Claude Agent SDK Python (v0.1.49+). Single ClaudeSDKClient session
with 6 specialized subagents (researcher, planner, implementer, validator,
code-reviewer, security-auditor). Claude drives the full lifecycle
(Research → Explore → Plan → Implement → Review) via system prompt guidance.
Python controls session lifecycle, security gates, and UI rendering.
"""

from .config import SessionConfig, load_config
from .session import SessionManager, SessionState

__version__ = "4.0.0"

__all__ = [
    "SessionConfig",
    "SessionManager",
    "SessionState",
    "load_config",
]
