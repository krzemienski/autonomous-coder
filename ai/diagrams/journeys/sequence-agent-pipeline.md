# Agent Pipeline — User Journey

**Type:** Sequence Diagram
**Last Updated:** 2026-03-19
**Related Files:**
- `orchestrator.py` — Pipeline execution
- `agents/research.py`, `agents/explorer.py`, `agents/planner.py`, `agents/coder.py`
- `messages.py` — Textual Message types
- `memory.py` — Conversation persistence

## Purpose

Shows the complete user journey from launching a task through the four-phase pipeline, highlighting what the user sees at each stage and how budget/cost tracking works.

## Diagram

```mermaid
sequenceDiagram
    actor User
    participant App as TUI App
    participant Orch as Orchestrator
    participant R as Research Agent
    participant E as Explorer Agent
    participant P as Planner Agent
    participant C as Coder Agent
    participant DB as SQLite

    User->>App: python -m autonomous_coder "Add auth"
    App->>Orch: run_pipeline(task, runners)
    Note over App: ⚡ TUI renders immediately<br/>User sees empty dashboard

    rect rgb(240, 248, 255)
        Note over Orch,R: Phase 1: Research (budget: $0.50)
        Orch->>App: PhaseStarted("research")
        Note over App: 📊 Progress: Research ▶
        Orch->>R: query(prompt, ClaudeAgentOptions)
        R-->>App: AgentOutput(text, tool calls)
        Note over App: 📝 Streaming output in Research tab
        R-->>Orch: ResultMessage(cost=$0.12)
        Orch->>App: CostUpdate($0.12)
        Note over App: 💰 Cost display: $0.12 / $5.00
        Orch->>DB: save conversation + cost
        Orch->>App: PhaseCompleted("research")
    end

    rect rgb(240, 255, 240)
        Note over Orch,E: Phase 2: Explore (budget: $0.50)
        Orch->>App: PhaseStarted("explore")
        Orch->>E: query(prompt + research_output)
        E-->>App: AgentOutput(codebase analysis)
        E-->>Orch: ResultMessage(cost=$0.08)
        Orch->>App: CostUpdate($0.20)
        Orch->>DB: save conversation + cost
    end

    rect rgb(255, 248, 240)
        Note over Orch,P: Phase 3: Plan (budget: $1.00)
        Orch->>App: PhaseStarted("plan")
        Orch->>P: query(prompt + research + exploration)
        P-->>App: AgentOutput(implementation plan)
        P-->>Orch: ResultMessage(cost=$0.15)
        Orch->>App: CostUpdate($0.35)
    end

    rect rgb(248, 240, 255)
        Note over Orch,C: Phase 4: Code (budget: $2.00)
        Orch->>App: PhaseStarted("code")
        Orch->>C: query(prompt + full context)
        C-->>App: AgentOutput(code + tool calls)
        Note over App: 📝 [Tool: Write] src/auth.ts<br/>[Tool: Bash] npm install jsonwebtoken
        C-->>Orch: ResultMessage(cost=$0.45)

        Note over C: Separate reviewer query()
        Orch->>C: query(review prompt, reviewer role)
        C-->>App: AgentOutput(review feedback)
        C-->>Orch: ResultMessage(cost=$0.08)
        Orch->>App: CostUpdate($0.88)
    end

    Orch->>App: Pipeline complete
    App->>User: ✅ "Pipeline complete. Total: $0.88"
    Note over User: 🎉 User sees full history<br/>in all tabs + cost breakdown
```

## Key Insights

- **User sees progress immediately** — TUI renders before any agent starts, showing the empty dashboard layout
- **Each phase chains data forward** — Research output feeds Explorer, Explorer feeds Planner, Planner feeds Coder
- **Budget is enforced per-role** — If research exceeds $0.50, that agent stops but the pipeline continues
- **Reviewer is a separate query()** — NOT a subagent parameter; appears as its own tab in the TUI
- **All conversations persisted** — SQLite stores every message for session resume

## Change History

- **2026-03-19:** Initial journey diagram created
