# TUI Agent Orchestration System — Architecture Overview

**Type:** Architecture Diagram
**Last Updated:** 2026-03-20
**Related Files:**
- `app.py` — Textual App entry point
- `orchestrator.py` — Phase pipeline engine
- `agent_factory.py` — ClaudeAgentOptions builder
- `memory.py` — SQLite + FTS5 persistence
- `security.py` — Command allowlist + can_use_tool callback

## Purpose

Shows how the four-layer architecture (TUI → Orchestration → SDK → Persistence) delivers real-time visibility into autonomous coding sessions, replacing opaque CLI output with a live multi-pane dashboard.

## Diagram

```mermaid
graph TB
    subgraph "Front-Stage — User Experience"
        U[👤 User launches TUI]
        U --> |"python -m autonomous_coder 'task'"| APP

        subgraph "TUI Layer — What Users See"
            APP[AutonomousCoderApp<br/>⚡ Instant visual feedback]
            AT[AgentTree<br/>📊 Live agent status sidebar]
            TABS[AgentTabs<br/>📝 Streaming output per agent]
            PROG[ProgressPanel<br/>📈 Phase & task progress]
            COST[CostDisplay<br/>💰 Real-time spend tracking]
            TD[TaskDetail<br/>📋 Current task context]
        end

        APP --> AT & TABS & PROG & COST & TD
    end

    subgraph "Back-Stage — Technical Implementation"
        subgraph "Orchestration Layer"
            ORCH[AgentOrchestrator<br/>⏱️ Keeps phases sequential to avoid conflicts]
            PR[PhaseRunners<br/>🔄 R→E→P→C pipeline with budget gates]
            AF[AgentFactory<br/>⚙️ Per-role ClaudeAgentOptions]
        end

        subgraph "SDK Layer — claude-agent-sdk v0.1.49"
            Q["query() / ClaudeSDKClient<br/>⚡ Stateless or stateful sessions"]
            CUT["can_use_tool callback<br/>🛡️ Blocks dangerous commands BEFORE execution"]
            SE["StreamEvent<br/>📡 Real-time token streaming"]
            RM["ResultMessage<br/>💰 total_cost_usd + max_budget_usd"]
            AD["AgentDefinition<br/>🤖 Programmatic subagent definitions"]
        end

        subgraph "Persistence Layer"
            SQL["SQLite + FTS5 + WAL<br/>💾 Zero-dependency, crash-safe storage"]
            SESS["Session Management<br/>🔄 Resume interrupted work via session_id"]
            COSTDB["Cost Aggregation<br/>📊 Per-agent, per-phase breakdown"]
        end
    end

    APP -.->|"Textual Messages"| ORCH
    ORCH --> PR --> AF --> Q
    Q --> CUT & SE
    Q --> RM --> COSTDB
    AF -.-> AD
    ORCH --> SQL & SESS

    style U fill:#f9f,stroke:#333
    style APP fill:#e1f5fe
    style CUT fill:#c8e6c9
    style SQL fill:#fff3e0
```

## Key Insights

- **User impact**: Every agent action is visible in real-time through Textual Message dispatch — no more watching blank terminal output
- **Security**: `can_use_tool` callback blocks dangerous Bash commands BEFORE execution (not after, like the legacy client.py)
- **Cost control**: SDK supports `max_budget_usd` for hard caps; application also tracks `ResultMessage.total_cost_usd` per-role for granular control
- **Streaming**: `StreamEvent` (public in v0.1.49) enables real-time token-by-token output via `include_partial_messages=True`
- **Subagents**: `AgentDefinition` enables programmatic subagent definitions via the `agents` parameter on `ClaudeAgentOptions`
- **Resilience**: SQLite WAL mode + SDK `resume`/`fork_session` means interrupted work can be continued

## Change History

- **2026-03-20:** Updated SDK layer to reflect verified v0.1.49 capabilities (max_budget_usd, AgentDefinition, ClaudeSDKClient, StreamEvent)
- **2026-03-19:** Initial architecture diagram created during Phase A implementation
