# Claude Agent SDK Cookbook Analysis: Reusable Architectural Patterns

**Date:** 2026-03-21
**Source Cookbooks:**
- `00_The_one_liner_research_agent.ipynb` — Stateless & stateful research agents
- `01_The_chief_of_staff_agent.ipynb` — Multi-agent orchestration with subagents, hooks, commands
- `02_The_observability_agent.ipynb` — MCP server integration (Git, GitHub)
- `03_The_site_reliability_agent.ipynb` — Custom MCP server, guardrails, human-in-the-loop

**Local Files Analyzed:**
- `/Users/nick/Desktop/claude-cookbooks/claude_agent_sdk/` (all .ipynb, agent.py, MCP servers, hooks, agents, settings)
- `/Users/nick/Desktop/autonomous-coder/src/autonomous_coder/` (orchestrator, agent_factory, client, agent, config)

---

## Table of Contents

1. [Pattern 1: One-Liner Research Agent](#pattern-1-one-liner-research-agent)
2. [Pattern 2: Stateful Multi-Turn Investigator](#pattern-2-stateful-multi-turn-investigator)
3. [Pattern 3: Chief-of-Staff Orchestrator](#pattern-3-chief-of-staff-orchestrator)
4. [Pattern 4: Plan-Then-Execute Gate](#pattern-4-plan-then-execute-gate)
5. [Pattern 5: MCP-Confined Specialist](#pattern-5-mcp-confined-specialist)
6. [Pattern 6: Custom MCP Server with Guardrail Hooks](#pattern-6-custom-mcp-server-with-guardrail-hooks)
7. [Pattern 7: Human-in-the-Loop Incident Response](#pattern-7-human-in-the-loop-incident-response)
8. [Composite Mapping: Autonomous-Coder Integration](#composite-mapping-autonomous-coder-integration)
9. [Summary Decision Matrix](#summary-decision-matrix)

---

## Pattern 1: One-Liner Research Agent

**Reusable Pattern Name:** Stateless Query Agent

### How It Works

```python
from claude_agent_sdk import ClaudeAgentOptions, query

async for msg in query(
    prompt="Research question here",
    options=ClaudeAgentOptions(
        model="claude-opus-4-6",
        allowed_tools=["WebSearch"],
    ),
):
    process(msg)
```

### Extraction Summary

| Dimension | Detail |
|-----------|--------|
| **Agent Spawning** | `query()` — single-turn, stateless, no conversation memory. Each call is independent. |
| **Tool Registration** | `allowed_tools=["WebSearch"]` — agent can use freely without approval. `disallowed_tools` removes tools from context entirely. Default tools (Read) are always available. |
| **Handoff/Delegation** | None — single agent, no subagents. |
| **Streaming/Observability** | Async iteration over messages. `print_activity(msg)` for real-time display. Message types: `AssistantMessage` (thinking/tool use), `ResultMessage` (final). |
| **Error Handling** | `max_buffer_size` (default 1MB, increase to 10MB+ for multimodal). Buffer overflow on base64-encoded images is the primary failure mode. |
| **Guardrails** | System prompt enforces citation format. Tool permission levels (allowed/default/disallowed). |

### Mapping to Autonomous-Coder

| Aspect | Current Code | SDK Pattern Replacement |
|--------|-------------|------------------------|
| **Phase** | Research phase (`agents/research.py`) | Direct `query()` call for single-shot web research |
| **Current Implementation** | `AutonomousCoderClient` wraps `query()` with full MCP config | Simplify to bare `query()` with `allowed_tools=["WebSearch"]` for research-only tasks |
| **Advantage** | Eliminates unnecessary MCP server startup for simple research. Zero-config, instant spinup. Ideal for parallel independent research queries. |

---

## Pattern 2: Stateful Multi-Turn Investigator

**Reusable Pattern Name:** Conversational Research Agent

### How It Works

```python
from claude_agent_sdk import ClaudeSDKClient, ClaudeAgentOptions

async with ClaudeSDKClient(
    options=ClaudeAgentOptions(
        model="claude-opus-4-6",
        system_prompt=SYSTEM_PROMPT,
        allowed_tools=["WebSearch", "Read"],
        cwd="research_agent",
        max_buffer_size=10 * 1024 * 1024,
    )
) as agent:
    await agent.query("First question")
    async for msg in agent.receive_response():
        process(msg)

    # Context maintained for follow-up
    await agent.query("Follow-up based on first answer")
    async for msg in agent.receive_response():
        process(msg)
```

### Extraction Summary

| Dimension | Detail |
|-----------|--------|
| **Agent Spawning** | `ClaudeSDKClient` as async context manager. Maintains conversation state across multiple `.query()` calls. |
| **Tool Registration** | Same as Pattern 1 but with `cwd` for filesystem scope and `max_buffer_size` for multimodal content. |
| **Handoff/Delegation** | None inherent — but the multi-turn pattern enables iterative refinement (analyze image, then validate via web search). |
| **Streaming/Observability** | Same async iteration. `reset_activity_context()` between logical conversation boundaries. `visualize_conversation(messages)` for full timeline. |
| **Error Handling** | `try/except` around the `ClaudeSDKClient` context. Buffer overflow management. Graceful degradation. |
| **Guardrails** | System prompt with domain-specific citation requirements. `cwd` scopes file access. |

### Mapping to Autonomous-Coder

| Aspect | Current Code | SDK Pattern Replacement |
|--------|-------------|------------------------|
| **Phase** | Explorer phase (`agents/explorer.py`) | `ClaudeSDKClient` with multi-turn: first query explores structure, follow-ups drill into specific areas |
| **Current Implementation** | Single `query()` call per phase with all context packed into one prompt | Multi-turn allows progressive discovery — explore broadly, then narrow. Reduces prompt size. |
| **Advantage** | Context persistence eliminates re-sending full codebase context. Each follow-up builds on prior findings naturally. More efficient token usage. |

---

## Pattern 3: Chief-of-Staff Orchestrator

**Reusable Pattern Name:** Multi-Agent Delegator with Subagent Task Tool

### How It Works

```python
# Main orchestrator
async with ClaudeSDKClient(
    options=ClaudeAgentOptions(
        model="claude-opus-4-6",
        allowed_tools=["Task", "Read", "Write", "Edit", "Bash", "WebSearch"],
        system_prompt="Delegate financial questions to financial-analyst subagent.",
        cwd="chief_of_staff_agent",
        setting_sources=["project", "local"],
    )
) as agent:
    await agent.query("Should we hire 5 engineers?")
    async for msg in agent.receive_response():
        process(msg)  # Subagent calls appear as Task tool usage
```

**Subagent definition** (`.claude/agents/financial-analyst.md`):
```markdown
---
name: financial-analyst
description: Financial analysis expert
tools: Read, Bash, WebSearch
---
You are a senior financial analyst...
```

### Extraction Summary

| Dimension | Detail |
|-----------|--------|
| **Agent Spawning** | Parent agent with `allowed_tools=["Task"]`. Subagents defined as markdown files in `.claude/agents/`. Parent delegates via natural language — SDK handles subagent lifecycle. |
| **Tool Registration** | Parent: `Task` + operational tools. Subagents: own tool set defined in frontmatter (`tools: Read, Bash, WebSearch`). `setting_sources=["project", "local"]` loads slash commands, hooks, output styles, agent definitions. |
| **Handoff/Delegation** | Parent decides when to delegate based on system prompt + tool descriptions. Subagents have separate conversation history, own tools, specialized instructions. Results flow back to parent. Can run in parallel. |
| **Streaming/Observability** | Subagent activity visible in message stream: `"Delegating to subagent: financial-analyst"`. Tool calls indented under subagent in visualization. |
| **Error Handling** | Subagent failures captured in parent context. Parent can retry or handle differently. |
| **Guardrails** | Subagent isolation (separate context, can't escape to parent). Tool restrictions per subagent. `setting_sources` controls what filesystem config loads. |

### Critical Configuration Requirements

| Feature | Required Config | Without It |
|---------|----------------|------------|
| CLAUDE.md context | `cwd="dir"` + `setting_sources=["project"]` | Agent has no project memory |
| Slash commands | `setting_sources=["project"]` | Commands silently unavailable |
| Hooks | `setting_sources=["project", "local"]` | Hooks never fire |
| Subagents | `allowed_tools=["Task"]` + `setting_sources=["project"]` | Cannot delegate |
| Output styles | `settings='{"outputStyle":"executive"}'` + `setting_sources=["project"]` | Style not applied |

### Mapping to Autonomous-Coder

| Aspect | Current Code | SDK Pattern Replacement |
|--------|-------------|------------------------|
| **Phase** | Entire orchestration (`orchestrator.py`, `agent_factory.py`) | Single parent agent with `Task` tool delegates to Research/Explorer/Planner/Coder subagents defined in `.claude/agents/` |
| **Current Implementation** | `AgentFactory.create_options()` builds separate `ClaudeAgentOptions` per role. `Orchestrator` runs phases sequentially via `PhaseRunner` protocol. | Parent agent decides phase transitions dynamically. Subagent definitions in markdown files replace `config.py` role definitions. |
| **Advantage** | **Dynamic delegation** — parent agent can decide at runtime whether to research more, re-plan, or skip phases. Current sequential pipeline is rigid. **Simpler code** — replace ~300 lines of orchestrator/factory with agent markdown files + parent system prompt. **Parallel subagents** — SDK handles concurrent Task calls natively. |

---

## Pattern 4: Plan-Then-Execute Gate

**Reusable Pattern Name:** Plan Mode with Gated Execution

### How It Works

```python
# Phase 1: Plan only (no execution)
async with ClaudeSDKClient(
    options=ClaudeAgentOptions(
        model="claude-opus-4-6",
        permission_mode="plan",
        cwd="chief_of_staff_agent",
    )
) as agent:
    await agent.query("""Create plan. Wrap in <plan></plan> tags.
        DO NOT use Write tool. Output directly.""")
    async for msg in agent.receive_response():
        capture_plan(msg)

# Phase 2: Execute (after review)
    await agent.query("Execute the plan")
    async for msg in agent.receive_response():
        process(msg)
```

### Plan Extraction Fallback Chain

1. **Message stream** — parse `<plan>` XML tags from assistant text blocks
2. **Write tool captures** — intercept Write tool calls for plan content
3. **Claude plan directory** — check `~/.claude/plans/` for recent `.md` files (within 5 min)
4. **Full content fallback** — use entire response if >500 chars

### Extraction Summary

| Dimension | Detail |
|-----------|--------|
| **Agent Spawning** | Same `ClaudeSDKClient`, but with `permission_mode="plan"`. Agent calls `ExitPlanMode()` when done planning. |
| **Tool Registration** | Planning mode restricts write operations. Agent can read/analyze but not modify. |
| **Handoff/Delegation** | Plan output feeds into execution phase via `continue_conversation=True`. |
| **Streaming/Observability** | Plan content extracted via XML tags or fallback chain. `save_plan_to_file()` persists with metadata (timestamp, model, source). |
| **Error Handling** | Multi-source plan extraction with 4-level fallback. Diagnostic output when all sources fail. |
| **Guardrails** | `permission_mode="plan"` prevents unintended execution during planning. Explicit gate between plan and execute. |

### Mapping to Autonomous-Coder

| Aspect | Current Code | SDK Pattern Replacement |
|--------|-------------|------------------------|
| **Phase** | Planner phase (`agents/planner.py`) | Use `permission_mode="plan"` for the planning agent. Agent plans without executing. |
| **Current Implementation** | Planner runs as regular agent with system prompt asking it to "only plan". No enforcement — planner could execute if it decided to. | SDK enforces plan-only at the permission level. No possibility of accidental execution. |
| **Advantage** | **Enforced safety** — `permission_mode="plan"` is a hard gate, not a soft prompt instruction. **Plan persistence** — built-in extraction and save utilities. **Seamless transition** — `continue_conversation=True` carries plan context into execution without re-sending. |

---

## Pattern 5: MCP-Confined Specialist

**Reusable Pattern Name:** MCP-Only Agent with Tool Confinement

### How It Works

```python
git_mcp = {
    "git": {
        "command": "uv",
        "args": ["run", "python", "-m", "mcp_server_git", "--repository", repo_root],
    }
}

async with ClaudeSDKClient(
    options=ClaudeAgentOptions(
        model="claude-opus-4-6",
        mcp_servers=git_mcp,
        allowed_tools=["mcp__git"],
        disallowed_tools=["Bash", "Task", "WebSearch", "WebFetch"],
        permission_mode="acceptEdits",
    )
) as agent:
    await agent.query("Explore git history")
```

### Extraction Summary

| Dimension | Detail |
|-----------|--------|
| **Agent Spawning** | Standard `ClaudeSDKClient` with MCP server config. MCP servers defined as `{name: {command, args, env}}`. |
| **Tool Registration** | `allowed_tools=["mcp__git"]` — prefix-based wildcard allows all tools from that MCP server. `disallowed_tools` blocks Bash to prevent `git` CLI bypass. This is critical: without `disallowed_tools`, agent can use Bash to bypass MCP confinement. |
| **Handoff/Delegation** | None — focused specialist. Multiple MCP servers can be composed: `{**git_mcp, **github_mcp}`. |
| **Streaming/Observability** | Same message iteration. Tool names prefixed: `mcp__git__git_log()`, `mcp__github__search_repositories()`. |
| **Error Handling** | MCP server process management handled by SDK. Docker-based MCP servers (`ghcr.io/github/github-mcp-server`) for isolation. |
| **Guardrails** | `disallowed_tools` is the key guardrail — prevents tool bypass. `allowed_tools` alone only controls permission prompting, NOT availability. Environment variables passed via `env` dict. |

### Critical Insight: `allowed_tools` vs `disallowed_tools`

> `allowed_tools` controls **permission prompting** (can use freely vs needs approval).
> `disallowed_tools` controls **availability** (removed from agent's context entirely).
> To truly confine an agent to MCP tools, you MUST use `disallowed_tools` to block Bash.

### Mapping to Autonomous-Coder

| Aspect | Current Code | SDK Pattern Replacement |
|--------|-------------|------------------------|
| **Phase** | Explorer phase with Serena MCP | Confine explorer to `mcp__serena` only, with `disallowed_tools=["Bash"]` to prevent shell-based code exploration |
| **Current Implementation** | `AgentFactory` injects MCP servers but does not block Bash. Explorer could theoretically use `grep`/`find` instead of Serena. | `disallowed_tools` enforces that explorer MUST use semantic analysis, not text search. |
| **Advantage** | **Enforced tool confinement** — agent cannot bypass MCP with shell commands. **Composable** — mix multiple MCP servers per agent role. **Docker isolation** — run MCP servers in containers for untrusted environments. |

---

## Pattern 6: Custom MCP Server with Guardrail Hooks

**Reusable Pattern Name:** SRE Multi-Tool Agent with Pre/Post Hooks

### How It Works

**Custom MCP server** (subprocess via stdio/JSON-RPC):
```python
options = ClaudeAgentOptions(
    system_prompt=SYSTEM_PROMPT,
    mcp_servers={
        "sre": {
            "command": sys.executable,
            "args": [str(MCP_SERVER_PATH)],
        }
    },
    allowed_tools=["mcp__sre__query_metrics", "mcp__sre__edit_config_file", ...],
    hooks={
        "PreToolUse": [
            {
                "matcher": "mcp__sre__edit_config_file",
                "hooks": [{"type": "command", "command": f"bash {HOOKS_DIR}/validate_pool_size.sh"}],
            },
            {
                "matcher": "mcp__sre__run_shell_command",
                "hooks": [{"type": "command", "command": f"bash {HOOKS_DIR}/validate_config_before_deploy.sh"}],
            },
        ],
    },
    permission_mode="acceptEdits",
)
```

### MCP Server Protocol

The MCP server communicates via JSON-RPC over stdin/stdout:
- `initialize` — handshake with SDK
- `tools/list` — returns available tool schemas with rich descriptions
- `tools/call` — executes specific tool, returns `{content: [{type, text}], isError: bool}`

### Tool-Level Safety Patterns in MCP Handlers

```python
# 1. Directory restriction
if not full_path.is_relative_to(allowed_root):
    return {"content": [{"type": "text", "text": "Error: restricted"}], "isError": True}

# 2. Command allowlist
if args[0] not in ("docker-compose", "docker"):
    return {"content": [{"type": "text", "text": "Error: only docker allowed"}], "isError": True}

# 3. Container name whitelist
if container not in {"api-server", "postgres", "prometheus"}:
    return {"content": [{"type": "text", "text": "Error: invalid container"}], "isError": True}
```

### Extraction Summary

| Dimension | Detail |
|-----------|--------|
| **Agent Spawning** | `query()` with full MCP + hooks config. MCP server as subprocess (`sys.executable` + script path). |
| **Tool Registration** | Explicit tool allowlist (12 specific MCP tools). Rich descriptions with example queries embedded in tool schemas. Tool descriptions drive agent behavior more than system prompt. |
| **Handoff/Delegation** | Two-phase: investigation (read-only), then remediation (read-write) after human approval. |
| **Streaming/Observability** | `AssistantMessage` → `TextBlock` (reasoning) + `ToolUseBlock` (tool calls). `ResultMessage` with `is_error` flag. Tool names stripped of `mcp__sre__` prefix for display. |
| **Error Handling** | Every tool handler returns `{content, isError}` structured response. Prometheus query errors caught and reported. Subprocess timeout (60s) on shell commands. |
| **Guardrails** | **Three layers:** (1) `PreToolUse` hooks for validation scripts before dangerous tools; (2) Tool handler safety checks (directory restriction, command allowlist, container whitelist); (3) `permission_mode` for human approval gates. |

### Mapping to Autonomous-Coder

| Aspect | Current Code | SDK Pattern Replacement |
|--------|-------------|------------------------|
| **Phase** | Coder phase (`agents/coder.py`) with Bash access | Custom MCP server wrapping dangerous operations (file writes, shell commands) with safety checks built into handlers |
| **Current Implementation** | `security.py` with `is_command_allowed()` callback. Bash commands validated at the `can_use_tool` level. | Move safety into MCP tool handlers + PreToolUse hooks. Defense-in-depth: SDK hooks validate BEFORE tool call, handler validates WITHIN tool call. |
| **Advantage** | **Defense-in-depth** — three independent safety layers vs current single `can_use_tool` callback. **Rich tool descriptions** — embed example usage directly in tool schemas, reducing system prompt size. **Audit trail** — PostToolUse hooks log all operations (see `report-tracker.py` pattern). |

---

## Pattern 7: Human-in-the-Loop Incident Response

**Reusable Pattern Name:** Two-Phase Read-Then-Write Agent

### How It Works

```python
# Phase 1: Investigation (read-only tools)
result = await query(prompt="Check health of all services", options=read_only_options)

# Human reviews findings, approves remediation

# Phase 2: Remediation (write tools enabled)
result = await query(prompt="Fix DB_POOL_SIZE and redeploy", options=read_write_options)
```

### Integration Points

- **Slack bot** (`sre_bot_slack.py`): Real-time incident response via Slack Socket Mode
- **PagerDuty**: Conditional tool registration when `PAGERDUTY_API_KEY` is set
- **Confluence**: Post-mortem documentation via MCP tools
- **Skills** (`.claude/skills/`): Runbook and post-mortem templates

### Extraction Summary

| Dimension | Detail |
|-----------|--------|
| **Agent Spawning** | Same `query()` but with different tool sets per phase. Read-only phase has no write tools. |
| **Tool Registration** | Conditional: `pagerduty_*` tools only registered if API key exists. Dynamic tool sets based on incident phase. |
| **Handoff/Delegation** | Human approval gate between investigation and remediation. Post-mortem generation as final step. |
| **Streaming/Observability** | Slack integration for real-time updates. PagerDuty for incident tracking. Confluence for documentation. |
| **Error Handling** | Validation hooks prevent invalid config changes. Backup files for known-good state. |
| **Guardrails** | Phase-based tool restriction. `PreToolUse` validation hooks on write operations. Human gate between phases. |

### Mapping to Autonomous-Coder

| Aspect | Current Code | SDK Pattern Replacement |
|--------|-------------|------------------------|
| **Phase** | Validation phase (not yet implemented) | Two-phase pattern: coder implements (write), then validator reviews (read-only) before committing |
| **Current Implementation** | No formal validation gate. Coder phase has full write access throughout. | Validation agent runs with `permission_mode="plan"` or read-only tools. Must approve before git commit. |
| **Advantage** | **Safety gate** before irreversible operations (git commit, deployment). **Conditional tools** — enable dangerous operations only when warranted. |

---

## Composite Mapping: Autonomous-Coder Integration

### Current Architecture

```
AutonomousCoderAgent (agent.py)
  ├── AutonomousCoderClient (client.py)
  │     └── query() with full MCP config
  ├── AgentFactory (agent_factory.py)
  │     └── create_options() per role
  ├── Orchestrator (orchestrator.py)
  │     └── PhaseRunner protocol, sequential phases
  └── Phases:
        ├── Research  → query() + WebSearch/Firecrawl/Context7
        ├── Explorer  → query() + Serena MCP
        ├── Planner   → query() + Sequential-thinking MCP
        └── Coder     → query() + all tools + Bash security
```

### Proposed SDK-Native Architecture

```
Chief-of-Staff Agent (parent)
  ├── allowed_tools: ["Task"]
  ├── system_prompt: phase orchestration logic
  ├── setting_sources: ["project", "local"]
  │
  ├── .claude/agents/researcher.md
  │     tools: WebSearch, Read
  │     (Pattern 1: stateless query for independent research)
  │
  ├── .claude/agents/explorer.md
  │     tools: mcp__serena
  │     disallowed: Bash
  │     (Pattern 5: MCP-confined specialist)
  │
  ├── .claude/agents/planner.md
  │     tools: Read
  │     permission_mode: plan
  │     (Pattern 4: plan-then-execute gate)
  │
  └── .claude/agents/coder.md
        tools: Bash, Write, Edit, Read
        hooks: PreToolUse validation
        (Pattern 6: custom hooks + safety)
```

### What Gets Replaced

| Current File | Lines | Replacement | Pattern Used |
|-------------|-------|-------------|--------------|
| `orchestrator.py` | ~200 | Parent agent system prompt + Task tool | Pattern 3 (Chief-of-Staff) |
| `agent_factory.py` | ~90 | `.claude/agents/*.md` files | Pattern 3 (subagent definitions) |
| `config.py` (role defs) | ~100 | Subagent markdown frontmatter | Pattern 3 |
| `client.py` | ~80 | Single `ClaudeSDKClient` with `setting_sources` | Pattern 3 |
| `security.py` (can_use_tool) | ~60 | MCP handler safety + PreToolUse hooks | Pattern 6 (defense-in-depth) |
| `agent.py` (sequential phases) | ~150 | Dynamic delegation by parent agent | Pattern 3 |
| N/A (new) | — | `permission_mode="plan"` for planner | Pattern 4 |
| N/A (new) | — | `disallowed_tools` for explorer | Pattern 5 |
| N/A (new) | — | PostToolUse audit hooks | Pattern 6 |

**Estimated reduction:** ~680 lines of Python replaced by ~5 markdown files + 1 parent agent config.

### Phase-to-Pattern Mapping

| Autonomous-Coder Phase | Primary Pattern | Secondary Pattern | Key SDK Feature |
|------------------------|-----------------|-------------------|-----------------|
| **Research** | Pattern 1 (Stateless Query) | Pattern 2 (Multi-Turn) for deep research | `query()` with `allowed_tools=["WebSearch"]` |
| **Explore** | Pattern 5 (MCP-Confined) | Pattern 2 (Multi-Turn) for iterative discovery | `disallowed_tools=["Bash"]` + `mcp__serena` |
| **Plan** | Pattern 4 (Plan-Then-Execute) | Pattern 3 (delegated from parent) | `permission_mode="plan"` |
| **Implement** | Pattern 6 (Hooks + Safety) | Pattern 7 (Two-Phase for validation) | `PreToolUse` hooks + handler safety |
| **Validate** (new) | Pattern 7 (Human-in-the-Loop) | Pattern 5 (read-only confinement) | Read-only tool set + approval gate |
| **Orchestration** | Pattern 3 (Chief-of-Staff) | — | `allowed_tools=["Task"]` + `.claude/agents/` |

---

## Summary Decision Matrix

| Pattern | Complexity | Safety | Flexibility | Best For |
|---------|-----------|--------|-------------|----------|
| 1. Stateless Query | Lowest | Low (no confinement) | Low (single turn) | Quick research, parallel independent queries |
| 2. Multi-Turn | Low | Low | Medium (context persists) | Iterative investigation, progressive discovery |
| 3. Chief-of-Staff | Medium | Medium (subagent isolation) | **Highest** (dynamic delegation) | **Orchestration layer** — replaces rigid pipelines |
| 4. Plan-Then-Execute | Low | **High** (enforced gate) | Medium | Planning phases where execution must be prevented |
| 5. MCP-Confined | Low | **High** (tool confinement) | Low (restricted tools) | Specialist agents that must use specific tools |
| 6. Hooks + Custom MCP | **Highest** | **Highest** (3 layers) | High | Write operations, dangerous commands |
| 7. Two-Phase | Medium | **High** (approval gate) | Medium | Any workflow needing human review before commit |

---

## Key SDK Gotchas Discovered

1. **`allowed_tools` does NOT restrict availability** — it only controls whether the agent needs to ask permission. Use `disallowed_tools` to actually remove tools from the agent's context.

2. **`setting_sources` is critical and easy to forget:**
   - Missing `"project"` = no CLAUDE.md, no slash commands, no subagents, no output styles
   - Missing `"local"` = no hooks fire
   - Missing `"user"` = no global user settings

3. **`max_buffer_size` defaults to 1MB** — any multimodal content (images, large documents) will cause `JSON message exceeded maximum buffer size` errors. Set to 10MB+ for multimodal agents.

4. **CLAUDE.md is context, not constraint** — agents may prefer detailed data sources (CSVs) over CLAUDE.md high-level context. Use explicit prompts to guide CLAUDE.md usage.

5. **MCP tool descriptions drive behavior more than system prompts** — the SRE cookbook embeds example PromQL queries, investigation workflows, and usage hints directly in tool description strings. This is more reliable than system prompt instructions for tool usage guidance.

6. **Plan extraction requires multiple fallback sources** — plans may appear in message text, Write tool calls, or `~/.claude/plans/`. Production code needs a fallback chain.

---

## Unresolved Questions

1. **Subagent concurrency limits** — the cookbooks show parallel Task calls but don't document max concurrent subagents or memory implications. Need to test with 4+ simultaneous subagents.

2. **`continue_conversation` with subagents** — unclear if parent agent conversation state includes subagent outputs for follow-up queries, or if subagent context is discarded after each Task call.

3. **Hook execution environment** — hooks receive `tool_input` and `tool_response` via stdin JSON, but the exact schema varies by tool type. Need to validate schema for each tool the autonomous-coder uses.

4. **Cost tracking** — none of the cookbooks demonstrate per-agent or per-phase cost tracking. The autonomous-coder's `CostUpdate` message type may need custom implementation outside SDK patterns.

5. **Error recovery across phases** — the Chief-of-Staff pattern delegates dynamically, but if a subagent fails mid-task, the parent agent's retry behavior is undocumented. Current `PhaseRunner` has explicit retry logic that would need to be replicated in parent agent instructions.

---

*Report generated from analysis of Anthropic Claude Agent SDK cookbooks (00-03) and autonomous-coder source code.*
*Sources: https://platform.claude.com/cookbook/claude-agent-sdk-00-the-one-liner-research-agent through 03, local files at `/Users/nick/Desktop/claude-cookbooks/claude_agent_sdk/`*
