# Autonomous Coder

A multi-agent orchestration system for autonomous coding, built on the Claude Agent SDK (Python). Supports both a real-time TUI dashboard and headless CLI mode.

## What It Does

Orchestrates multiple Claude agents through a four-phase pipeline:

1. **Research** — Discovers relevant tools, libraries, and patterns via web research
2. **Explore** — Analyzes your codebase semantically using Serena MCP
3. **Plan** — Creates a detailed, dependency-aware implementation plan
4. **Code** — Implements tasks iteratively with live streaming output and code review

Each agent runs as a separate `query()` call with its own model, tools, budget limit, and security constraints.

### Two Execution Modes

**TUI Mode** (default) — Full Textual dashboard with live agent streaming, progress bars, and cost tracking:

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

**CLI Mode** (`--cli`) — Headless pipeline output printed to stdout. Same orchestrator, no TUI dependency at runtime.

## Quick Start

```bash
# Install (editable for development)
pip install -e .

# TUI mode (default) — full dashboard with live streaming
autonomous-coder "Add user authentication with JWT tokens"

# TUI mode — launch without a task, enter it in the input bar
autonomous-coder

# CLI mode (headless) — pipeline output printed to stdout
autonomous-coder --cli "Add user authentication with JWT tokens"

# CLI mode with verbose agent output
autonomous-coder --cli -v "Add auth" --project /path/to/project
```

### CLI Options

```
autonomous-coder [-h] [--cli] [--verbose] [--project PROJECT] [task ...]

positional arguments:
  task               Task description (joins multiple words)

options:
  --cli              Run in headless CLI mode (no TUI)
  --verbose, -v      Show full agent text output (CLI mode only)
  --project PROJECT  Project directory (defaults to cwd)
```

### Keyboard Shortcuts (TUI mode)

| Key | Action |
| --- | ------ |
| `q` | Quit |
| `p` | Pause pipeline |
| `r` | Resume pipeline |
| `c` | Cancel current agent |
| `Tab` | Cycle agent tabs |
| `/` | Command palette |

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                    TUI LAYER (Textual)                            │
│  AgentTree │ AgentTabs │ ProgressPanel │ CostDisplay │ TaskDetail │
├──────────────────────────────────────────────────────────────────┤
│              CLI LAYER (CliAdapter — headless alternative)        │
│  post_message() → stdout printing │ Same orchestrator interface   │
├──────────────────────────────────────────────────────────────────┤
│                    ORCHESTRATION LAYER                            │
│  AgentOrchestrator │ PhaseRunners (R→E→P→C) │ AgentFactory       │
├──────────────────────────────────────────────────────────────────┤
│                SDK LAYER (claude-agent-sdk)                       │
│  query() │ ClaudeAgentOptions │ can_use_tool │ ResultMessage      │
├──────────────────────────────────────────────────────────────────┤
│                    PERSISTENCE LAYER                              │
│  SQLite + FTS5 + WAL │ Session Management │ Cost Aggregation      │
└──────────────────────────────────────────────────────────────────┘
```

The `AgentOrchestrator` accepts any object with a `post_message()` method as its `app` parameter. The TUI passes `AutonomousCoderApp` (Textual); the CLI passes `CliAdapter` (prints to stdout); passing `None` silently drops messages (headless/programmatic use).

### Key Design Decisions

- **`ClaudeAgentOptions`** — Uses verified fields from `claude-agent-sdk`. All field names and types confirmed via `inspect.signature()`.
- **`can_use_tool` for security** — Pre-execution Bash command validation via `PermissionResultAllow`/`PermissionResultDeny`. Blocks dangerous commands *before* they run.
- **Application-level budget tracking** — `ResultMessage.total_cost_usd` accumulated per-agent with configurable limits. The SDK also offers `max_budget_usd` for SDK-enforced caps.
- **Textual Messages for UI** — Built-in `post_message()` system. 8 message types: `AgentStarted`, `AgentOutput`, `AgentCompleted`, `AgentError`, `CostUpdate`, `SecurityBlock`, `PhaseStarted`, `PhaseCompleted`.
- **PhaseRunner protocol** — Each phase implements `async def run(context: PhaseContext) -> PhaseResult`. Composable and extensible.
- **Duck-typed app interface** — `AgentOrchestrator(app=...)` accepts TUI, CLI adapter, or `None`. No coupling to Textual.
- **Sequential pipeline v1** — Phases run sequentially to avoid file conflicts. Parallel execution deferred to v2.

## Requirements

- Python 3.10+
- [claude-agent-sdk](https://pypi.org/project/claude-agent-sdk/) v0.1.40+
- [Textual](https://pypi.org/project/textual/) v1.0.0+ (TUI mode only)
- Claude Code CLI installed and authenticated

### MCP Servers (auto-configured)

| Server | Phase | Purpose |
| ------ | ----- | ------- |
| Serena | Explore, Plan, Code | Semantic code analysis |
| Context7 | Research, Code | Library documentation |
| Firecrawl | Research | Web research and scraping |
| Sequential Thinking | Plan | Step-by-step reasoning |

## Budget Configuration

Default budget allocation ($5.00 total):

| Role | Budget | Model | Max Turns |
| ---- | ------ | ----- | --------- |
| Research | $0.50 | claude-opus-4-6 | 25 |
| Explore | $0.50 | claude-opus-4-6 | 20 |
| Plan | $1.00 | claude-opus-4-6 | 10 |
| Code | $2.00 | claude-opus-4-6 | 30 |
| Reviewer | $0.25 | claude-opus-4-6 | 10 |

Budget is enforced per-role via `ResultMessage.total_cost_usd` accumulation. Exceeding a role's budget stops that agent gracefully. The SDK also supports `max_budget_usd` on `ClaudeAgentOptions` for SDK-level enforcement.

## Security Model

Defense-in-depth with three layers:

1. **`can_use_tool` callback** — Called by the SDK *before* every tool execution. Blocks Bash commands not in the allowlist. Returns `PermissionResultDeny(interrupt=False)` so the agent can try alternatives.
2. **Command allowlist** — 142 curated safe commands (package managers, build tools, runtimes, linters, shell utilities).
3. **Dangerous pattern blocklist** — 20 patterns always blocked regardless of allowlist (`rm -rf /`, fork bombs, `curl | sh`, etc.).

## File Structure

```
src/autonomous_coder/
├── __init__.py               # Package exports (v2.0)
├── __main__.py               # Entry point: TUI + CLI dispatch (argparse)
├── app.py                    # Textual App (TUI mode)
├── cli_adapter.py            # CliAdapter (headless CLI mode)
├── orchestrator.py           # Phase pipeline engine + PhaseRunner protocol
├── agent_factory.py          # ClaudeAgentOptions builder per role
├── agent_instance.py         # Agent lifecycle + budget tracking
├── messages.py               # Textual Message subclasses (8 types)
├── config.py                 # Role configs, MCP servers, budget limits
├── memory.py                 # SQLite + FTS5 + WAL persistence
├── security.py               # Command allowlist + can_use_tool callback
├── prompts.py                # Prompt template loading utilities
├── styles.tcss               # TUI CSS styling (supplementary)
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
├── agent.py                  # Legacy CLI orchestrator
├── client.py                 # Legacy SDK client
├── progress.py               # Legacy progress tracker
└── researcher.py             # Legacy research phase
```

## Programmatic API

```python
from autonomous_coder import (
    AutonomousCoderApp,
    CliAdapter,
    AgentOrchestrator,
    OrchestratorConfig,
    AgentFactory,
    MemoryStore,
)
from autonomous_coder.agents import (
    ResearchPhaseRunner, ExplorerPhaseRunner,
    PlannerPhaseRunner, CoderPhaseRunner,
)

# TUI mode
app = AutonomousCoderApp(task="Add auth", project_path="/my/project")
app.run()

# CLI mode (headless with stdout output)
adapter = CliAdapter(verbose=True)
config = OrchestratorConfig(project_path=Path("/my/project"))
orchestrator = AgentOrchestrator(config=config, app=adapter)
runners = {
    "research": ResearchPhaseRunner(orchestrator.factory),
    "explore": ExplorerPhaseRunner(orchestrator.factory),
    "plan": PlannerPhaseRunner(orchestrator.factory),
    "code": CoderPhaseRunner(orchestrator.factory),
}
results = await orchestrator.run_pipeline("Add auth", runners)
adapter.print_summary(results)

# Silent mode (no output, just results)
orchestrator = AgentOrchestrator(config=config, app=None)
results = await orchestrator.run_pipeline("Add auth", runners)
```

## Documentation

- [`docs/architecture.md`](docs/architecture.md) — System architecture, component relationships, Mermaid diagrams, extension guide
- [`docs/api-reference.md`](docs/api-reference.md) — Full API reference for all public classes and methods
- [`docs/doc-coverage-audit.md`](docs/doc-coverage-audit.md) — Documentation coverage analysis
- [`ai/diagrams/`](ai/diagrams/README.md) — DDD architecture diagrams

## License

MIT
