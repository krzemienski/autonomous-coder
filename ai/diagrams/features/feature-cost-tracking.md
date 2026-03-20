# Cost Tracking — Manual Budget Management

**Type:** Feature Diagram
**Last Updated:** 2026-03-19
**Related Files:**
- `orchestrator.py` — Budget accumulation in `run_agent()`
- `agent_instance.py` — `AgentInstance.budget_exceeded` property
- `config.py` — Per-role `budget_limit` in `RoleConfig`
- `memory.py` — `record_cost()`, `get_cost_breakdown()`
- `widgets/cost_display.py` — Real-time cost UI

## Purpose

Shows how cost tracking works WITHOUT the phantom `max_budget_usd` SDK field — budget is enforced manually by accumulating `ResultMessage.total_cost_usd` and comparing against configurable per-role limits.

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

- **No SDK budget field**: `max_budget_usd` does NOT exist in claude-code-sdk v0.0.25 — budget is application-level logic
- **Per-role limits**: Code phase gets $2.00 (40% of total), research gets $0.50 (10%)
- **Graceful stopping**: Exceeding budget breaks the `async for` loop — the agent's last response is still captured
- **Persistent tracking**: Every cost event is recorded in SQLite for post-session analysis
- **80% warning**: CostDisplay widget highlights yellow when approaching the limit

## Change History

- **2026-03-19:** Initial cost tracking diagram
