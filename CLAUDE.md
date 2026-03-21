# CLAUDE.md — Autonomous Coder Project Context

## Project Purpose
Autonomous multi-phase coding agent that researches, plans, implements, and validates
code changes. Built on the Claude Agent SDK for Python.

## Architecture (v2.0 — SDK-Native)
- **Single SDK query** drives the entire multi-phase workflow via `sdk_orchestrator.py`
- **AgentDefinition subagents** for parallel research, implementation, validation, planning
- **HookMatcher hooks** for observability (tool logging, subagent tracking) and safety
- **Custom MCP tools** for phase tracking (`track_phase`) and findings persistence (`save_findings`)
- **External MCP servers**: Context7 (library docs), Firecrawl (web crawling)

## Key Files (SDK-Native)
- `src/autonomous_coder/sdk_orchestrator.py` — Core: single query() drives everything
- `src/autonomous_coder/sdk_agents.py` — AgentDefinition configs for subagents
- `src/autonomous_coder/sdk_hooks.py` — Hook callbacks (observability + safety)
- `src/autonomous_coder/sdk_tools.py` — Custom MCP tools (phase tracking, findings)
- `src/autonomous_coder/sdk_mcp_servers.py` — External MCP server configs
- `src/autonomous_coder/sdk_prompts.py` — System prompts for orchestrator + subagents
- `src/autonomous_coder/sdk_cli.py` — CLI entry point
- `src/autonomous_coder/display.py` — Terminal output formatting
- `src/autonomous_coder/types.py` — Shared type definitions

## Key Files (Legacy — preserved for backward compat)
- `src/autonomous_coder/orchestrator.py` — Manual phase loop orchestrator
- `src/autonomous_coder/agents/*.py` — Per-phase PhaseRunner implementations
- `src/autonomous_coder/app.py` — Textual TUI application
- `src/autonomous_coder/cli_adapter.py` — Legacy CLI output adapter

## Conventions
- Always read files completely before modifying
- Never create mock implementations or placeholder code
- Research phase must evaluate existing libraries before custom code
- Use Edit tool (not Write) for modifying existing files
- All testing uses real data in production configurations

## SDK Patterns
- `query()` for stateless single-shot sessions
- `ClaudeSDKClient` for stateful multi-turn conversations
- `AgentDefinition` with model="sonnet"|"opus"|"haiku" (not full model IDs)
- `HookMatcher(matcher="Bash", hooks=[callback])` for tool-specific hooks
- `create_sdk_mcp_server()` for in-process MCP tools
- Import from `claude_agent_sdk` (not `claude_code_sdk`)

## Running
```bash
# SDK-native mode (default)
autonomous-coder task_spec.txt --project /path/to/project -v

# TUI mode
autonomous-coder --tui "Add authentication"

# Legacy CLI mode
autonomous-coder --legacy-cli "Add authentication"
```
