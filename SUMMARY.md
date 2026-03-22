# autonomous-coder v3 — Executive Summary

## Overview

autonomous-coder v3 is a Python CLI tool that wraps the Claude Agent SDK to execute complex software development tasks autonomously through a disciplined multi-phase pipeline. It replaces v2's Textual TUI and custom PhaseRunner protocol with SDK-native primitives: `ClaudeSDKClient` multi-turn sessions, `AgentDefinition` subagents, hook-driven observability, and custom MCP tools for findings persistence. The core design shift is that Claude itself becomes the orchestrator — Python code handles lifecycle management while all task routing and decision-making happens inside the agent loop.

The architecture enforces a functional validation philosophy at three independent layers: system prompts that instruct agents to never create test files, PreToolUse hooks that block writes to test file paths, and a can_use_tool callback that validates Bash commands against a 142-command allowlist. Custom MCP tools (`save_findings`, `get_findings`) persist phase data to disk so it survives context compaction — solving the fundamental problem that causes long-running agent sessions to lose important context mid-execution.

The system auto-detects whether it's operating on a greenfield project or an existing codebase and routes accordingly: greenfield projects go through spec-builder → researcher → planner → implementer → validator, while existing projects go through onboarder → researcher → planner → implementer → validator. All streaming output is timestamped, phase-aware, and subagent-tracking, giving the developer real-time visibility from the moment they press Enter.

## Key Architectural Decisions

| Decision | Rationale | Risk |
|---|---|---|
| ClaudeSDKClient over query() | Full hook, MCP, subagent, streaming, interrupt support | More complex lifecycle management |
| Claude as orchestrator (not Python for-loop) | Intelligent phase routing, adaptive error handling | Model may deviate from prescribed sequence |
| 6 specialized subagents | Clean separation of concerns, per-agent tool restrictions | Possible over-engineering; 4 agents may suffice |
| Custom MCP tools for findings | Data survives context compaction; recoverable after resume | Tool calls consume context window tokens |
| PreToolUse hook for test file blocking | Hard enforcement independent of prompt compliance | Pattern matching may have false positives |
| Opus for orchestrator/planner/implementer, Sonnet for rest | Balance cost vs quality at each phase | Opus cost adds up over long sessions |
| acceptEdits permission mode + can_use_tool for Bash | Auto-approve file ops, validate Bash commands | No Write/Edit path restriction (fixable via hook) |

## Top 5 Risks (Ranked by Severity)

1. **Bash allowlist too permissive** (Critical — Security): docker, kubectl, aws commands allowed without argument validation. Mitigate: add argument-level validation for high-risk commands.

2. **No Write/Edit path restriction** (Critical — Security): Subagents can write to any path on the filesystem, not just the project directory. Mitigate: add PreToolUse hook validating file_path prefix.

3. **Context compaction degrades long sessions** (Critical — Operations): After compaction, agents operate on summarized context and may lose nuanced implementation decisions. Mitigate: save findings aggressively and test compaction recovery explicitly.

4. **MCP server supply chain** (Warning — Security): npx -y auto-installs unversioned packages that could be compromised. Mitigate: pin versions, validate signatures.

5. **Streaming output signal-to-noise** (Warning — DX): Default mode shows too little, verbose shows too much. Mitigate: add --progress intermediate mode with task-level tracking.

## Recommended Next Steps

1. **Implement Write/Edit path validation hook** — one-line security fix, highest impact per effort
2. **Add Bash argument validation** for docker, kubectl, aws, curl — blocks the critical security concern
3. **Pin MCP server versions** in the config — prevents supply chain attacks
4. **Build the core: runner.py, agents.py, mcp_tools.py, hooks.py, security.py, display.py** — the 6 files that constitute the v3 implementation (~2,000 lines total)
5. **Test compaction recovery** — run a 200+ turn session, trigger compaction, verify findings recovery works
6. **Add --progress mode** — intermediate verbosity with task-level progress tracking
7. **Consider agent consolidation** — merge onboarder into researcher, remove spec-builder as standalone agent, reducing from 6 to 4 agents
8. **Add --interactive flag** — pause between phases for human review, leveraging ClaudeSDKClient.interrupt()
9. **Add git auto-commit** — PostToolUse hook on Write/Edit that creates commits after each task completion
10. **Functional validation** — run autonomous-coder on itself: use it to implement its own v3 architecture
