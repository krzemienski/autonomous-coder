# Cost Tracking — Dual Budget Enforcement

**Type:** Feature Diagram
**Last Updated:** 2026-03-20
**Related Files:**
- `orchestrator.py` — Budget accumulation in `run_agent()`
- `agent_instance.py` — `AgentInstance.budget_exceeded` property
- `config.py` — Per-role `budget_limit` in `RoleConfig`
- `memory.py` — `record_cost()`, `get_cost_breakdown()`
- `widgets/cost_display.py` — Real-time cost UI

## Purpose

Shows how cost tracking works with dual enforcement: the SDK's `max_budget_usd` field provides hard caps, while the application layer accumulates `ResultMessage.total_cost_usd` for granular per-role limits.

## Diagram

```mermaid
flowchart TB
    subgraph "Front-Stage — User Sees Cost"
        DISPLAY[💰 CostDisplay widget<br/>Shows total + per-agent breakdown]
        WARN[⚠️ Warning at 80% budget<br/>Yellow highlight in TUI]
        STOP[🛑 Budget exceeded notification<br/>Agent stops, pipeline continues]
    end

    subgraph "Back-Stage — Budget Enforcement"
        RM[ResultMessage from SDK<br/>📊 total_cost_usd field]
        RM --> ACC[AgentInstance.add_cost<br/>💰 Accumulates per-agent]
        ACC --> CHECK{agent.budget_exceeded?<br/>cost >= budget_limit}

        CHECK -->|"No"| CONTINUE[Agent continues<br/>✅ Next turn]
        CHECK -->|"Yes"| BREAK[Break from query() loop<br/>🛑 Agent stops gracefully]

        ACC --> TOTAL[orchestrator.total_cost<br/>💰 Accumulates across all agents]
        TOTAL --> POST[CostUpdate message<br/>📢 Posted to TUI]
        ACC --> DB[memory.record_cost<br/>💾 Persisted to SQLite]
    end

    POST --> DISPLAY
    TOTAL -->|"> 80% of total_budget"| WARN
    BREAK --> STOP

    subgraph "Budget Configuration"
        CFG["OrchestratorConfig<br/>total_budget: $5.00"]
        R["research: $0.50"]
        E["explore: $0.50"]
        P["plan: $1.00"]
        C["code: $2.00"]
        RV["reviewer: $0.25"]
        CFG --> R & E & P & C & RV
    end

    style RM fill:#e1f5fe
    style CHECK fill:#fff3e0
    style BREAK fill:#ffcdd2
```

## Key Insights

- **SDK budget field exists**: `max_budget_usd` IS a real field on `ClaudeAgentOptions` in v0.1.49 — can be used for SDK-enforced hard caps
- **Dual enforcement**: Application tracks `ResultMessage.total_cost_usd` per-role for granular control; SDK `max_budget_usd` provides a safety net
- **Per-role limits**: Code phase gets $2.00 (40% of total), research gets $0.50 (10%)
- **Graceful stopping**: Exceeding budget breaks the `async for` loop — the agent's last response is still captured
- **Persistent tracking**: Every cost event is recorded in SQLite for post-session analysis
- **80% warning**: CostDisplay widget highlights yellow when approaching the limit

## Change History

- **2026-03-20:** Corrected SDK budget field documentation — `max_budget_usd` exists in v0.1.49 (verified via introspection)
- **2026-03-19:** Initial cost tracking diagram
