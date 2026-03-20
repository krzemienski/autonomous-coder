# Autonomous Coder

A TUI-based multi-agent orchestration system for autonomous coding, built on the Claude Code SDK (Python).

## What It Does

Launches a real-time terminal dashboard that orchestrates multiple Claude agents through a four-phase pipeline:

1. **Research** — Discovers relevant tools, libraries, and patterns via web research
2. **Explore** — Analyzes your codebase semantically using Serena MCP
3. **Plan** — Creates a detailed, dependency-aware implementation plan
4. **Code** — Implements tasks iteratively with live streaming output and code review

Each agent runs as a separate `query()` call with its own model, tools, budget limit, and security constraints — all visible in real-time through the TUI.

```
┌─────────────────────────────────────────────────────────────────────┐
│ [Header] Autonomous Coder v2.0  │ Model: sonnet-4.5 │ $0.1234 │ ⏱ │
├────────────────┬────────────────────────────────────────────────────┤
│ AGENTS         │ ACTIVE AGENT OUTPUT                    [Tabs]      │
│ ┌────────────┐ │ ┌─[Research]──[Explore]──[Plan]──[Code]─────────┐ │
│ │ ▶ Research │ │ │  Streaming output from the currently           │ │
│ │   Explore  │ │ │  selected agent appears here in real-time.     │ │
│ │   Planner  │ │ │                                                │ │
│ │   Coder    │ │ │  [Tool: Bash] Running: npm install...          │ │
│ │            │ │ │  [Tool: Write] Created: src/auth.ts            │ │
│ └────────────┘ │ └────────────────────────────────────────────────┘ │
├────────────────┼────────────────────────────────────────────────────┤
│ PROGRESS       │ TASK DETAILS                                      │
│ ████░░ 43%     │ Task 3/7: Add JWT middleware                      │
│ ✓ 1. Setup     │ Status: In Progress                               │
│ ▶ 3. Auth      │ Cost: $0.05                                       │
└────────────────┴────────────────────────────────────────────────────┘
```

## Quick Start

```bash
# Install dependencies
pip install claude-code-sdk textual

# Run with a task
python -m autonomous_coder "Add user authentication with JWT tokens"

# Or launch the TUI without a task
python -m autonomous_coder
```

### Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `q` | Quit |
| `p` | Pause pipeline |
| `r` | Resume pipeline |
| `c` | Cancel current agent |
| `Tab` | Cycle agent tabs |
| `/` | Command palette |

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                    TUI LAYER (Textual v7.0.0)                    │
│  AgentTree │ AgentTabs │ ProgressPanel │ CostDisplay │ TaskDetail│
├──────────────────────────────────────────────────────────────────┤
│                    ORCHESTRATION LAYER                            │
│  AgentOrchestrator │ PhaseRunners (R→E→P→C) │ AgentFactory       │
├──────────────────────────────────────────────────────────────────┤
│                    SDK LAYER (claude-code-sdk v0.0.25)            │
│  query() │ ClaudeCodeOptions │ can_use_tool │ ResultMessage       │
├──────────────────────────────────────────────────────────────────┤
│                    PERSISTENCE LAYER                             │
│  SQLite + FTS5 + WAL │ Session Management │ Cost Aggregation     │
└──────────────────────────────────────────────────────────────────┘
```

### Key Design Decisions

- **`ClaudeCodeOptions` only** — Uses only verified fields from `claude-code-sdk v0.0.25`. No fabricated API.
- **`can_use_tool` for security** — Pre-execution Bash command validation via `PermissionResultAllow`/`PermissionResultDeny`. Blocks dangerous commands *before* they run.
- **Manual budget tracking** — `ResultMessage.total_cost_usd` accumulated per-agent with configurable limits. No phantom `max_budget_usd` field.
- **Textual Messages for UI** — Built-in `post_message()` system, no custom EventBus. 8 message types: `AgentStarted`, `AgentOutput`, `AgentCompleted`, `AgentError`, `CostUpdate`, `SecurityBlock`, `PhaseStarted`, `PhaseCompleted`.
- **PhaseRunner protocol** — Each phase implements `async def run(context: PhaseContext) -> PhaseResult`. Composable and extensible.
- **Sequential pipeline v1** — Phases run sequentially to avoid file conflicts. Parallel execution deferred to v2.

## Requirements

- Python 3.12+
- [claude-code-sdk](https://pypi.org/project/claude-code-sdk/) v0.0.25+
- [Textual](https://pypi.org/project/textual/) v7.0.0+
- Claude Code CLI installed and authenticated

### MCP Servers (auto-configured)

| Server | Phase | Purpose |
|--------|-------|---------|
| Serena | Explore, Plan, Code | Semantic code analysis |
| Context7 | Research, Code | Library documentation |
| Firecrawl | Research | Web research and scraping |
| Sequential Thinking | Plan | Step-by-step reasoning |

## Budget Configuration

Default budget allocation ($5.00 total):

| Role | Budget | Model | Max Turns |
|------|--------|-------|-----------|
| Research | $0.50 | claude-sonnet-4-5 | 25 |
| Explore | $0.50 | claude-sonnet-4-5 | 20 |
| Plan | $1.00 | claude-sonnet-4-5 | 10 |
| Code | $2.00 | claude-sonnet-4-5 | 30 |
| Reviewer | $0.25 | claude-sonnet-4-5 | 10 |

Budget is enforced per-role via `ResultMessage.total_cost_usd` accumulation. Exceeding a role's budget stops that agent gracefully.

## Security Model

Defense-in-depth with three layers:

1. **`can_use_tool` callback** — Called by the SDK *before* every tool execution. Blocks Bash commands not in the allowlist. Returns `PermissionResultDeny(interrupt=False)` so the agent can try alternatives.
2. **Command allowlist** — 142 curated safe commands (package managers, build tools, runtimes, linters, shell utilities).
3. **Dangerous pattern blocklist** — 20 patterns always blocked regardless of allowlist (`rm -rf /`, fork bombs, `curl | sh`, etc.).

## File Structure

```
autonomous-coder/
├── app.py                    # Textual App entry point
├── orchestrator.py           # Phase pipeline engine + PhaseRunner protocol
├── agent_factory.py          # ClaudeCodeOptions builder per role
├── agent_instance.py         # Agent lifecycle + budget tracking
├── messages.py               # Textual Message subclasses (8 types)
├── config.py                 # Role configs, MCP servers, budget limits
├── memory.py                 # SQLite + FTS5 + WAL persistence
├── security.py               # Command allowlist + can_use_tool callback
├── styles.tcss               # TUI CSS styling
├── __main__.py               # python -m autonomous_coder entry point
├── __init__.py               # Package exports (v2.0)
├── widgets/                  # TUI widgets
│   ├── agent_tree.py         # Agent sidebar with status icons
│   ├── agent_tabs.py         # Tabbed streaming output per agent
│   ├── streaming_log.py      # Rich-formatted log display
│   ├── progress_panel.py     # Phase + task progress bars
│   ├── task_detail.py        # Current task metadata
│   └── cost_display.py       # Real-time cost tracking
├── agents/                   # PhaseRunner implementations
│   ├── research.py           # ResearchPhaseRunner
│   ├── explorer.py           # ExplorerPhaseRunner
│   ├── planner.py            # PlannerPhaseRunner
│   └── coder.py              # CoderPhaseRunner (+ reviewer)
├── prompts/                  # Phase-specific prompt templates
├── ai/diagrams/              # DDD architecture diagrams
│── agent.py                  # Legacy CLI orchestrator
├── client.py                 # Legacy SDK client
├── progress.py               # Legacy progress tracker
└── researcher.py             # Legacy research phase
```

## Programmatic API

```python
from autonomous_coder import (
    AutonomousCoderApp,
    AgentOrchestrator,
    OrchestratorConfig,
    AgentFactory,
    MemoryStore,
)

# Launch TUI
app = AutonomousCoderApp(task="Add auth", project_path="/my/project")
app.run()

# Or use the orchestrator headlessly (no TUI)
config = OrchestratorConfig(project_path=Path("/my/project"))
orchestrator = AgentOrchestrator(config=config)
results = await orchestrator.run_pipeline("Add auth", runners)
```

## Architecture Diagrams

See [`ai/diagrams/`](ai/diagrams/README.md) for DDD (Diagram Driven Development) diagrams:
- [System Architecture Overview](ai/diagrams/architecture/arch-system-overview.md)
- [Agent Pipeline Journey](ai/diagrams/journeys/sequence-agent-pipeline.md)
- [Security Pipeline](ai/diagrams/features/feature-security-pipeline.md)
- [Cost Tracking](ai/diagrams/features/feature-cost-tracking.md)

## License

MIT
