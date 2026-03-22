# SUMMARY: Autonomous-Coder v3 Architecture Research

**Prompt**: 001-autonomous-coder-v3-architecture-research
**Purpose**: Research + Design
**Status**: Ready to execute

## What This Prompt Does
A fresh Claude Code session reads ALL 17 SDK doc pages, all 4 cookbook implementations, the original quickstart, the current codebase, and the user's Claude Code configuration. It then produces:

1. **Architecture Document** — Complete v3 design using ClaudeSDKClient with full streaming, AgentDefinition subagents, hooks, custom MCP tools, can_use_tool security, file checkpointing, structured outputs, plugins, and skills
2. **5 Architectural Critiques** — Security, Production Ops, Developer Experience, Architecture Purity, Competitive Analysis

## Key Decisions Baked In
- ClaudeSDKClient ONLY (never single message mode)
- include_partial_messages=True for full streaming visibility
- Opus 1M context via betas
- can_use_tool for security (PermissionResultDeny with graceful denial)
- Hooks for observability (PreToolUse/PostToolUse/SubagentStart/Stop)
- Custom MCP tools for phase tracking + findings persistence
- Two entry paths: greenfield (spec builder) vs existing (onboarding first)
- Functional validation philosophy enforced at multiple layers

## How to Run
```bash
cd /Users/nick/Desktop/autonomous-coder
claude -p "$(cat .prompts/001-autonomous-coder-v3-architecture-research/001-autonomous-coder-v3-architecture-research.md)"
```

Or in a new Claude Code session:
```
Read and execute the prompt at .prompts/001-autonomous-coder-v3-architecture-research/001-autonomous-coder-v3-architecture-research.md
```
