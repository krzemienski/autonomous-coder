# Autonomous Coder — Complete Architecture Analysis

**Date:** 2026-03-21  
**Version:** 2.0.0  
**Package:** `autonomous-coder`  
**Python:** >=3.10  
**Dependencies:** `claude-agent-sdk>=0.1.40`, `textual>=1.0.0`  
**Build System:** Hatchling  
**Entry Point:** `autonomous-coder` → `autonomous_coder.__main__:main`

---

## 1. File Inventory (28 Python files)

| # | File | Lines | Purpose |
|---|------|-------|---------|
| 1 | `__init__.py` | 113 | Public API surface; re-exports everything |
| 2 | `__main__.py` | 101 | CLI entry point; dispatches to TUI or headless mode |
| 3 | `app.py` | 262 | Textual TUI application; widget layout + message handlers |
| 4 | `orchestrator.py` | 544 | Pipeline engine; PhaseRunner protocol; `run_pipeline()` + `run_query()` |
| 5 | `agent_factory.py` | 87 | Creates `ClaudeAgentOptions` per role from config |
| 6 | `agent_instance.py` | 93 | Tracks single agent lifecycle (status, cost, duration) |
| 7 | `config.py` | 93 | `OrchestratorConfig`, `RoleConfig` dataclasses, `MCP_SERVERS` registry |
| 8 | `messages.py` | 188 | 9 Textual `Message` subclasses for inter-widget communication |
| 9 | `security.py` | 269 | Bash allowlist, dangerous pattern blocklist, `can_use_tool` hook |
| 10 | `memory.py` | 380 | SQLite + FTS5 persistence (sessions, conversations, cost tracking) |
| 11 | `cli_adapter.py` | 168 | Duck-type `post_message()` adapter for headless CLI mode |
| 12 | `prompts.py` | 525 | Template loading, formatting, fallback prompts for all 4 phases |
| 13 | `client.py` | 367 | Legacy `AutonomousCoderClient` — direct SDK wrapper (v1 API) |
| 14 | `agent.py` | 594 | Legacy `AutonomousCoderAgent` — v1 orchestrator with progress tracking |
| 15 | `progress.py` | 330 | JSON-file progress tracker for legacy agent (`.autonomous-coder/progress.json`) |
| 16 | `researcher.py` | 255 | Legacy `ResearchPhase` class with task-type detection |
| 17 | `agents/__init__.py` | 7 | Re-exports 4 phase runners |
| 18 | `agents/research.py` | 142 | `ResearchPhaseRunner` — v2 research phase |
| 19 | `agents/explorer.py` | 143 | `ExplorerPhaseRunner` — v2 explore phase |
| 20 | `agents/planner.py` | 150 | `PlannerPhaseRunner` — v2 plan phase |
| 21 | `agents/coder.py` | 193 | `CoderPhaseRunner` — v2 code + review phase |
| 22 | `widgets/__init__.py` | 17 | Re-exports 6 widgets |
| 23 | `widgets/agent_tree.py` | 62 | Sidebar tree showing agents grouped by phase |
| 24 | `widgets/agent_tabs.py` | 77 | Tabbed output pane per agent (RichLog) |
| 25 | `widgets/streaming_log.py` | 26 | RichLog with markup for tool/error/thinking blocks |
| 26 | `widgets/progress_panel.py` | 87 | Phase progress bar + task list |
| 27 | `widgets/task_detail.py` | 93 | Current task detail panel (name, status, files, deps, cost) |
| 28 | `widgets/cost_display.py` | 71 | Real-time cost tracker with budget warning at 80% |

**Prompt Templates (5 Markdown files):**
- `prompts/researcher_prompt.md`
- `prompts/explorer_prompt.md`
- `prompts/planner_prompt.md`
- `prompts/coder_prompt.md`
- `prompts/orchestrator_prompt.md`

---

## 2. Entry Points

### 2.1 CLI Entry (`__main__.py`)

```
main()
├─ argparse: task (positional), --cli, --verbose, --project
├─ if --cli → _run_cli(task, project_path, verbose)
│   ├─ CliAdapter(verbose=verbose)
│   ├─ OrchestratorConfig(project_path=...)
│   ├─ AgentOrchestrator(config, app=adapter)
│   ├─ Create 4 PhaseRunners (research, explore, plan, code)
│   └─ asyncio.run(orchestrator.run_pipeline(task, runners))
└─ else → _run_tui(task, project_path)
    └─ AutonomousCoderApp(task, project_path).run()
```

### 2.2 TUI Entry (`app.py`)

```
AutonomousCoderApp(App)
├─ compose(): Header, Input, Horizontal(sidebar, main), Footer
│   ├─ sidebar: AgentTree + ProgressPanel
│   └─ main: AgentTabs + Horizontal(TaskDetail, CostDisplay)
├─ on_ready(): if task passed via CLI → run_worker(run_task)
├─ on_input_submitted(): same as above from TUI input
└─ run_task(task):
    ├─ OrchestratorConfig(project_path)
    ├─ AgentOrchestrator(config, app=self)
    ├─ Create 4 PhaseRunners
    └─ await orchestrator.run_pipeline(task, runners)
```

### 2.3 Legacy Entry (`agent.py`)

```
main() [legacy CLI]
├─ argparse: task, project_path, --model, --max-iterations, --no-sandbox, --no-commit, --fresh
└─ asyncio.run(run_autonomous_coder(...))
    └─ AutonomousCoderAgent(project_path, model, ...).run(task, resume)

AutonomousCoderAgent.run():
├─ Phase 1: _run_research(task) → ResearchPhase(client).run()
├─ Phase 2: _run_exploration(task) → client.explore_codebase()
├─ Phase 3: _run_planning(task, exploration) → client.create_plan()
└─ Phase 4: _run_implementation() → iterates tasks, client.implement_task()
    └─ _git_commit() after each task
```

---

## 3. Orchestrator (`orchestrator.py`)

### 3.1 Class: `AgentOrchestrator`

**Constructor:** `__init__(self, config: OrchestratorConfig, app: Any = None)`
- `config` — roles, budget, project path
- `app` — Textual App or CliAdapter (duck-typed via `post_message()`)
- `factory` — `AgentFactory(config)` created immediately
- Internal state: `agents: dict`, `total_cost: float`, `phase_results: dict`, `_cancelled`, `_paused`

**Pipeline:** `PHASE_ORDER = ["research", "explore", "plan", "code"]`

```python
async def run_pipeline(task, runners) -> dict[str, PhaseResult]:
    input_data = {"task": task}
    for phase_name in PHASE_ORDER:
        # honour pause/cancel
        runner = runners.get(phase_name)
        context = PhaseContext(phase_name, input_data, config, budget_remaining, task)
        result = await runner.run(context)
        # merge outputs: input_data = {**input_data, **result.output_data}
        # abort on failure
```

**Data Flow Between Phases:**
```
Phase 1 (research) → output_data: {"research_output": str}
Phase 2 (explore)  → reads research_output, adds {"explore_output": str}
Phase 3 (plan)     → reads research_output + explore_output, adds {"plan_output": str}
Phase 4 (code)     → reads plan_output, adds {"code_output": str, "review_output": str}
```

**CRITICAL: All inter-phase data is freeform text strings, NOT structured JSON.**

### 3.2 Two Agent Execution Methods

1. **`run_agent(role, phase, prompt, system_prompt)`** — Original method. Creates `AgentInstance`, tracks lifecycle manually. Used by nobody currently (orphaned).

2. **`run_query(role, phase, prompt, system_prompt, budget_remaining)`** — Preferred method. Full lifecycle observability via `AgentLifecycle` messages. Does NOT create `AgentInstance`. Used by all 4 PhaseRunners.

**PAIN POINT:** `run_agent()` creates `AgentInstance` objects but `run_query()` does not, so the `self.agents` dict is always empty in the current architecture.

### 3.3 PhaseRunner Protocol

```python
@runtime_checkable
class PhaseRunner(Protocol):
    async def run(self, context: PhaseContext) -> PhaseResult: ...
```

### 3.4 Data Contracts

```python
@dataclass
class PhaseContext:
    phase_name: str
    input_data: dict[str, Any]     # accumulated from prior phases
    config: OrchestratorConfig
    budget_remaining: float
    task_description: str = ""

@dataclass
class PhaseResult:
    phase_name: str
    output_data: dict[str, Any]    # merged into next phase's input_data
    cost_incurred: float = 0.0
    duration_seconds: float = 0.0
    success: bool = True
    error: str | None = None
```

### 3.5 Security Callback

```python
async def security_callback(tool_name, tool_input, ctx):
    # Only checks Bash commands
    # Non-Bash tools always allowed (permission_mode="acceptEdits" governs file access)
    if tool_name == "Bash":
        is_allowed, reason = is_command_allowed(command)
        if not is_allowed: return PermissionResultDeny(...)
    return PermissionResultAllow(...)
```

### 3.6 Helpers

- `_string_to_stream(prompt)` — Wraps string as `AsyncIterator` (SDK requires this when `can_use_tool` is set)
- `_summarize_tool_input(tool_input)` — Extracts command/file_path/pattern for display

---

## 4. Agent Factory (`agent_factory.py`)

### Class: `AgentFactory`

**Constructor:** `__init__(self, config: OrchestratorConfig)`

**Key Method:** `create_options(role, system_prompt, security_callback=None, hooks=None) -> ClaudeAgentOptions`

Assembly logic:
1. Look up `RoleConfig` from `config.roles[role]`
2. Build MCP servers dict from `role_config.mcp_keys` → `MCP_SERVERS` registry
3. Inject `SERENA_PROJECT` env into serena server config
4. Only attach `can_use_tool` if role has "Bash" in tools list
5. Return `ClaudeAgentOptions` with: model, system_prompt, allowed_tools, mcp_servers, max_turns, cwd, permission_mode="acceptEdits", can_use_tool, include_partial_messages=True

**`get_budget_limit(role)`** — Returns the manual budget cap from config.

---

## 5. Agent Instance (`agent_instance.py`)

### Enum: `AgentStatus`
`PENDING → RUNNING → COMPLETED | FAILED | CANCELLED`

### Dataclass: `AgentInstance`
Fields: name, role, phase, status, cost, budget_limit, start_time, end_time, turns_used, max_turns, session_id, error

Properties:
- `duration` — wall-clock seconds
- `budget_remaining` — max(0, limit - cost)
- `budget_exceeded` — cost >= limit

Methods: `add_cost()`, `start()`, `complete(error=None)`, `cancel()`

**PAIN POINT:** `AgentInstance` is fully implemented but `run_query()` (the active code path) never creates one. Only the orphaned `run_agent()` method uses it.

---

## 6. Phase Runners (`agents/`)

All 4 runners follow the same pattern:

```python
class XxxPhaseRunner:
    def __init__(self, factory: AgentFactory, orchestrator: AgentOrchestrator | None = None)

    async def run(self, context: PhaseContext) -> PhaseResult:
        # Build system_prompt and user prompt
        # If orchestrator: use orchestrator.run_query() (full observability)
        # Else: fallback to _run_direct() (no UI messages)

    async def _run_direct(self, ...):
        # Direct claude_agent_sdk.query() call — no lifecycle messages

    def _build_system_prompt(self, context) -> str:
        # Loads from prompts module, injects prior phase outputs

    def _build_prompt(self, context) -> str:
        # Builds user-turn text from context.input_data
```

### 6.1 ResearchPhaseRunner (`agents/research.py`)
- Role: `"research"`
- System prompt: `get_researcher_prompt(task, project_path)`
- User prompt: "Research task: {task}\n\nIdentify relevant MCP servers..."
- Output key: `"research_output"`
- MCP servers: firecrawl-mcp, Context7

### 6.2 ExplorerPhaseRunner (`agents/explorer.py`)
- Role: `"explore"`
- System prompt: `get_explorer_prompt(task, project_path, additional_context=research_output)`
- User prompt: "Task: {task}\n\nExplore the codebase..." + research[:500]
- Output key: `"explore_output"`
- MCP servers: serena

### 6.3 PlannerPhaseRunner (`agents/planner.py`)
- Role: `"plan"`
- System prompt: `get_planner_prompt(task, exploration_results=explore_output, project_path)`
- User prompt: "Task: {task}" + research[:400] + explore[:600] + "Produce a detailed JSON plan..."
- Output key: `"plan_output"`
- MCP servers: sequential-thinking, serena

### 6.4 CoderPhaseRunner (`agents/coder.py`)
- Role: `"code"` (coding pass) + `"reviewer"` (review pass)
- **TWO sequential queries:**
  1. `_run_coding()` — role="code", phase="{phase}-coding"
     - System prompt: `get_coder_prompt(task_dict, plan_dict, [], project_path)`
     - Wraps task_description into a synthetic task_dict + plan_dict
  2. `_run_review()` — role="reviewer", phase="{phase}-review"
     - System prompt: hardcoded reviewer instructions
     - User prompt: coding_output[:3000]
- Output keys: `"code_output"`, `"review_output"`
- Coding MCP: serena, Context7
- Review MCP: serena (read-only)

**PAIN POINT:** Coder truncates plan_output to 600 chars via `plan_output[:600]` and coding_output to 3000 chars for review. Large plans/implementations are silently truncated.

---

## 7. Message System (`messages.py`)

9 Textual `Message` subclasses:

| # | Message | Fields | Emitted By | Consumed By |
|---|---------|--------|------------|-------------|
| 1 | `AgentStarted` | agent_name, phase | orchestrator.run_query / run_agent | app.on_agent_started, cli._on_agent_started |
| 2 | `AgentOutput` | agent_name, text, block_type | orchestrator (TextBlock/ToolUseBlock) | app.on_agent_output, cli._on_agent_output |
| 3 | `AgentCompleted` | agent_name, phase, cost, duration, success, error | orchestrator | app.on_agent_completed, cli._on_agent_completed |
| 4 | `AgentError` | agent_name, error, phase | orchestrator (exception handler) | app.on_agent_error, cli._on_agent_error |
| 5 | `CostUpdate` | agent_name, cost, total_cost | orchestrator (ResultMessage) | app.on_cost_update, cli._on_cost_update |
| 6 | `SecurityBlock` | agent_name, tool_name, reason | **NEVER EMITTED** | app.on_security_block, cli._on_security_block |
| 7 | `AgentLifecycle` | agent_name, state, detail | orchestrator.run_query | app.on_agent_lifecycle, cli._on_agent_lifecycle |
| 8 | `PhaseStarted` | phase, phase_index, total_phases | orchestrator.run_pipeline | app.on_phase_started, cli._on_phase_started |
| 9 | `PhaseCompleted` | phase, phase_index, cost, duration, success, error | orchestrator.run_pipeline | app.on_phase_completed, cli._on_phase_completed |

**AgentLifecycle states:** init, connecting, prompt_sent, waiting, streaming, tool_calling, tool_result, budget_check, complete, error

**PAIN POINT:** `SecurityBlock` message is defined and handled in both TUI and CLI but the `security_callback` function returns `PermissionResultDeny` directly — it never posts a `SecurityBlock` message. The message type is dead code.

---

## 8. Security (`security.py`)

### ALLOWED_COMMANDS (97 entries)
Package managers, version control, build tools, runtimes/compilers, testing frameworks, linters/formatters, shell utilities, dev utilities, container tools, database clients, cloud CLIs, process management.

### DANGEROUS_PATTERNS (18 entries)
`rm -rf /`, fork bomb, `chmod 777`, `sudo rm`, `curl | sh`, `eval $(`, etc.

### Functions

| Function | Signature | Purpose |
|----------|-----------|---------|
| `is_command_allowed` | `(command: str) -> tuple[bool, str]` | Validates Bash commands against allowlist + dangerous patterns |
| `bash_security_hook` | `async (tool_input: dict) -> dict | None` | PreToolUse hook (legacy, not used in v2) |
| `get_security_permissions` | `(project_path: str) -> dict` | Returns permissions dict for ClaudeAgentOptions (legacy) |
| `get_sandbox_settings` | `() -> dict` | Returns sandbox config dict (legacy) |

**Validation logic:**
1. Check for dangerous patterns (substring match, case-insensitive)
2. Extract base command (first word, strip path prefix)
3. Handle `./script` — allow `gradlew`, `mvnw`, `node_modules/.bin`
4. Check against ALLOWED_COMMANDS set

**PAIN POINT:** The allowlist is a flat set — `"go"` and `"test"` are separate entries, so `go test` is allowed because `go` matches, but the `"test"` entry is redundant noise. Same for `"cargo"` and `"test"`.

---

## 9. Config (`config.py`)

### RoleConfig Dataclass
```python
@dataclass
class RoleConfig:
    model: str           # e.g. "claude-opus-4-6"
    tools: list[str]     # e.g. ["Read", "Write", "Edit", "Bash", "Grep", "Glob"]
    mcp_keys: list[str]  # e.g. ["serena", "Context7"]
    budget_limit: float  # e.g. 2.00
    max_turns: int       # e.g. 30
```

### OrchestratorConfig Dataclass
```python
@dataclass
class OrchestratorConfig:
    project_path: Path
    total_budget: float = 5.0
    roles: dict[str, RoleConfig] = {default 5 roles}
```

### Default Role Configuration

| Role | Model | Tools | MCP Servers | Budget | Turns |
|------|-------|-------|-------------|--------|-------|
| research | claude-opus-4-6 | Read, Grep, Glob, WebSearch, WebFetch | firecrawl-mcp, Context7 | $0.50 | 25 |
| explore | claude-opus-4-6 | Read, Grep, Glob | serena | $0.50 | 20 |
| plan | claude-opus-4-6 | Read, Grep, Glob | sequential-thinking, serena | $1.00 | 10 |
| code | claude-opus-4-6 | Read, Write, Edit, Bash, Grep, Glob | serena, Context7 | $2.00 | 30 |
| reviewer | claude-opus-4-6 | Read, Grep, Glob | serena | $0.25 | 10 |

**Total default budget: $5.00** (sum of role limits: $4.25)

### MCP_SERVERS Registry
```python
MCP_SERVERS = {
    "serena":              {"command": "uvx", "args": ["serena"]},
    "sequential-thinking": {"command": "npx", "args": ["-y", "@modelcontextprotocol/server-sequential-thinking"]},
    "Context7":            {"command": "npx", "args": ["-y", "@upstash/context7-mcp"]},
    "firecrawl-mcp":       {"command": "npx", "args": ["-y", "firecrawl-mcp"], "env": {"FIRECRAWL_API_KEY": "${FIRECRAWL_API_KEY}"}},
}
```

**PAIN POINT:** `"WebSearch"` and `"WebFetch"` are listed in research role tools, but these are built-in Claude Code tools, not SDK tools. The SDK's `allowed_tools` may not recognize them — this depends on the SDK version's tool name resolution.

---

## 10. MemoryStore (`memory.py`)

SQLite + FTS5 persistence with 3 tables:

### Tables
1. **sessions** — id, task, status, total_cost, total_duration, current_phase, created_at, updated_at, metadata(JSON)
2. **conversations** — id, session_id(FK), agent_name, phase, role, content, block_type, cost, timestamp
3. **conversations_fts** — FTS5 virtual table on content, agent_name, phase (with insert/update/delete triggers)
4. **cost_tracking** — id, session_id(FK), agent_name, phase, cost, cumulative_cost, timestamp

### Class: `MemoryStore`
- `__init__(db_path)` — creates DB + tables + FTS triggers + WAL mode
- Session methods: `create_session()`, `update_session()`, `get_session()`, `list_sessions()`
- Conversation methods: `add_conversation()`, `get_conversations()`, `search_conversations()`
- Cost methods: `record_cost()`, `get_session_cost()`, `get_cost_breakdown()`

### Dataclass: `ConversationEntry`
Fields: session_id, agent_name, phase, role, content, block_type, cost, timestamp

**PAIN POINT:** `MemoryStore` is fully implemented and exported in `__init__.py` but is NEVER instantiated or used anywhere in the v2 pipeline. The orchestrator, phase runners, and app all operate without persistence. This is completely disconnected dead infrastructure.

---

## 11. CLI Adapter (`cli_adapter.py`)

### Class: `CliAdapter`

Duck-type replacement for `AutonomousCoderApp`. Provides `post_message(message)` method that dispatches to type-specific printers.

**Constructor:** `__init__(self, *, verbose: bool = False)`

**Message Handling:**

| Message Type | Verbose Off | Verbose On |
|-------------|-------------|------------|
| PhaseStarted | Banner with phase name | + timestamp |
| PhaseCompleted | Status + cost + duration | same |
| AgentStarted | Agent name + phase | + timestamp |
| AgentLifecycle | (hidden) | State label + detail |
| AgentOutput (tool) | Tool summary | + timestamp |
| AgentOutput (text) | (hidden) | Full text |
| AgentCompleted | Icon + cost + duration | same |
| AgentError | Error to stderr | + timestamp |
| CostUpdate | (hidden) | Cost details |
| SecurityBlock | Always shown | same |

**`print_summary(results)`** — Final banner with elapsed time, total cost, phase success/fail counts.

---

## 12. Prompts System (`prompts.py`)

### Template Loading
- Templates stored as `.md` files in `src/autonomous_coder/prompts/`
- `load_prompt_template(name)` — reads from disk
- `format_prompt(template, **kwargs)` — Python `str.format()` substitution
- `ensure_prompt_templates_exist()` — writes fallback content if templates missing

### Prompt Functions

| Function | Template | Variables |
|----------|----------|-----------|
| `get_researcher_prompt` | researcher_prompt.md | task, project_path, additional_context |
| `get_explorer_prompt` | explorer_prompt.md | task, project_path, additional_context |
| `get_planner_prompt` | planner_prompt.md | task, exploration_results, project_path |
| `get_coder_prompt` | coder_prompt.md | task_details (formatted dict), plan_context (formatted dict), project_path |
| `get_system_prompt` | (inline) | (none) — returns hardcoded base system prompt |

### Fallback Prompts
All 4 phase prompts have inline `FALLBACK_*_PROMPT` strings that get written to disk if template files are missing. These contain full instructions and JSON output format specifications.

**Expected JSON outputs from phases:**
- Research: `{task_analysis, mcp_servers[], skills[], libraries[], recommendations}`
- Explorer: `{stack, architecture, entry_points[], relevant_files[], patterns_detected[], impact_areas[], key_symbols[]}`
- Planner: `{goal, context_summary, tasks[{id, title, description, files, dependencies, test_criteria, estimated_complexity}], risks[], total_tasks}`
- Coder: Free-form text summary of changes made

---

## 13. Legacy System (v1 API)

Three files form the v1 system that predates the v2 TUI/orchestrator:

### 13.1 `client.py` — `AutonomousCoderClient`
- Direct wrapper around `claude_agent_sdk.query()`
- Configures MCP servers inline (duplicates `MCP_SERVERS` registry)
- Uses `SandboxSettings` for isolation
- Implements `bash_security_hook` at the application layer (not SDK callback)
- Methods: `run_session()`, `run_session_to_completion()`, `explore_codebase()`, `create_plan()`, `implement_task()`
- Has `_extract_json_from_text()` — regex JSON extraction from markdown

### 13.2 `agent.py` — `AutonomousCoderAgent`
- v1 orchestrator with `ProgressTracker`-based state management
- Same 4-phase pipeline but using `AutonomousCoderClient` directly
- Supports session resume from `.autonomous-coder/progress.json`
- Auto-commits via `subprocess.run(["git", ...])` after each task
- Default model: `claude-sonnet-4-20250514` (unlike v2 which defaults to `claude-opus-4-6`)

### 13.3 `researcher.py` — `ResearchPhase`
- Task-type detection via keyword matching
- Generates search queries based on detected types
- Uses `AutonomousCoderClient.run_session_to_completion()` directly
- Has `MCP_DISCOVERY_SOURCES` and `TASK_TYPE_MCP_HINTS` constants

### 13.4 `progress.py` — `ProgressTracker`
- JSON file persistence in `.autonomous-coder/progress.json`
- Tracks: status, task, exploration, plan, completed_tasks, current_task, commits, errors
- Methods: `start_task()`, `set_exploration_complete()`, `set_plan()`, `complete_task()`, `get_next_task()`, `is_resumable()`, `reset()`
- `create_feature_list()` and `update_feature_status()` — write `feature_list.json`

---

## 14. Widgets (`widgets/`)

### 14.1 AgentTree (sidebar)
- `Tree` subclass with 4 phase nodes: research, explore, plan, code
- Icon states: ○ pending, ▶ running, ✓ complete, ✗ error
- Methods: `add_agent()`, `set_agent_running()`, `set_agent_complete()`

### 14.2 AgentTabs (main area)
- `TabbedContent` subclass — one `TabPane` per agent
- Each tab contains a `RichLog` with Rich markup
- Lifecycle messages rendered with color-coded timestamps
- Methods: `add_agent_tab()`, `append_output()`, `focus_agent()`

### 14.3 StreamingLog
- `RichLog` subclass that handles `AgentOutput` messages directly
- Block types: tool (cyan), error (red), thinking (dim italic), result (green), text (plain)
- **Note:** Defined but not directly used by AgentTabs (which uses plain RichLog instead)

### 14.4 ProgressPanel (sidebar)
- Shows: phase label, ProgressBar, task list with status icons
- Reactive properties: current_phase, phase_index, total_phases, tasks
- Methods: `set_phase()`, `update_tasks()`

### 14.5 TaskDetail (bottom panel)
- Shows: task name, status, files, dependencies, estimated cost
- All fields are reactive with watchers that call `_refresh_body()`
- Method: `update_task(name, status, files, dependencies, estimated_cost)`
- **Note:** Never updated by the current pipeline — remains at default "idle" state

### 14.6 CostDisplay (bottom-right)
- Shows: total cost, budget label, per-agent breakdown
- Warning CSS class added at 80% of budget
- Method: `record_cost(agent_name, cost, total_cost)`

---

## 15. Complete Data Flow

```
User Input (task string)
    │
    ▼
__main__.main()
    ├─ TUI mode → AutonomousCoderApp.run_task(task)
    └─ CLI mode → asyncio.run(orchestrator.run_pipeline(task, runners))
    │
    ▼
AgentOrchestrator.run_pipeline(task, runners)
    │
    ├─ Phase 1: ResearchPhaseRunner.run(PhaseContext)
    │   ├─ get_researcher_prompt(task, project_path)
    │   ├─ orchestrator.run_query(role="research", prompt=..., system_prompt=...)
    │   │   ├─ factory.create_options("research", system_prompt, security_callback)
    │   │   │   └─ ClaudeAgentOptions(model, tools=[Read,Grep,Glob,WebSearch,WebFetch],
    │   │   │       mcp_servers={firecrawl-mcp, Context7}, max_turns=25, ...)
    │   │   ├─ _string_to_stream(prompt) if can_use_tool set
    │   │   ├─ async for msg in query(prompt, options):
    │   │   │   ├─ AssistantMessage → TextBlock → AgentOutput msg
    │   │   │   ├─ AssistantMessage → ToolUseBlock → AgentOutput msg (tool summary)
    │   │   │   └─ ResultMessage → CostUpdate msg + budget check
    │   │   └─ AgentCompleted msg
    │   └─ return PhaseResult(output_data={"research_output": text})
    │
    ├─ input_data = {task, research_output} (merged)
    │
    ├─ Phase 2: ExplorerPhaseRunner.run(PhaseContext)
    │   ├─ get_explorer_prompt(task, project_path, additional_context=research_output)
    │   ├─ orchestrator.run_query(role="explore", ...)
    │   │   └─ ClaudeAgentOptions(tools=[Read,Grep,Glob], mcp={serena}, turns=20)
    │   └─ return PhaseResult(output_data={"explore_output": text})
    │
    ├─ input_data = {task, research_output, explore_output} (merged)
    │
    ├─ Phase 3: PlannerPhaseRunner.run(PhaseContext)
    │   ├─ get_planner_prompt(task, exploration_results=explore_output, project_path)
    │   ├─ orchestrator.run_query(role="plan", ...)
    │   │   └─ ClaudeAgentOptions(tools=[Read,Grep,Glob], mcp={sequential-thinking,serena}, turns=10)
    │   └─ return PhaseResult(output_data={"plan_output": text})
    │
    ├─ input_data = {task, research_output, explore_output, plan_output} (merged)
    │
    └─ Phase 4: CoderPhaseRunner.run(PhaseContext)
        ├─ _run_coding():
        │   ├─ get_coder_prompt(task_dict, plan_dict, [], project_path)
        │   ├─ orchestrator.run_query(role="code", phase="code-coding", ...)
        │   │   └─ ClaudeAgentOptions(tools=[Read,Write,Edit,Bash,Grep,Glob],
        │   │       mcp={serena,Context7}, turns=30, can_use_tool=security_callback)
        │   └─ returns (coding_text, coding_cost)
        │
        └─ _run_review():
            ├─ Hardcoded reviewer system prompt
            ├─ orchestrator.run_query(role="reviewer", phase="code-review", ...)
            │   └─ ClaudeAgentOptions(tools=[Read,Grep,Glob], mcp={serena}, turns=10)
            └─ returns (review_text, review_cost)
```

---

## 16. Inter-File Dependency Map

```
__main__.py
  ├─ app.py (TUI)
  ├─ cli_adapter.py (CLI)
  ├─ config.py
  ├─ orchestrator.py
  └─ agents/ (phase runners)

app.py
  ├─ agents/ (ResearchPhaseRunner, ExplorerPhaseRunner, PlannerPhaseRunner, CoderPhaseRunner)
  ├─ config.py (OrchestratorConfig)
  ├─ messages.py (all 9 message types)
  ├─ orchestrator.py (AgentOrchestrator)
  └─ widgets/ (AgentTree, AgentTabs, ProgressPanel, TaskDetail, CostDisplay)

orchestrator.py
  ├─ claude_agent_sdk (query, PermissionResultAllow, PermissionResultDeny)
  ├─ claude_agent_sdk.types (AssistantMessage, ResultMessage, TextBlock, ToolUseBlock)
  ├─ agent_factory.py (AgentFactory)
  ├─ agent_instance.py (AgentInstance, AgentStatus)
  ├─ config.py (OrchestratorConfig)
  ├─ messages.py (8 of 9 message types — not SecurityBlock)
  └─ security.py (is_command_allowed)

agent_factory.py
  ├─ claude_agent_sdk (ClaudeAgentOptions)
  └─ config.py (MCP_SERVERS, OrchestratorConfig)

agents/research.py, explorer.py, planner.py, coder.py
  ├─ orchestrator.py (PhaseContext, PhaseResult, security_callback, _string_to_stream)
  ├─ agent_factory.py (AgentFactory — TYPE_CHECKING only)
  ├─ prompts.py (get_*_prompt functions)
  └─ claude_agent_sdk (query — fallback path only)

cli_adapter.py
  └─ messages.py (all 9 message types)

memory.py
  └─ (standalone — sqlite3, json, no internal deps)

client.py (legacy)
  ├─ claude_agent_sdk (ClaudeAgentOptions, query, types)
  └─ security.py (bash_security_hook, get_sandbox_settings, get_security_permissions)

agent.py (legacy)
  ├─ client.py (AutonomousCoderClient, create_client)
  ├─ progress.py (ProgressTracker, create_feature_list, update_feature_status)
  ├─ prompts.py (all prompt functions)
  └─ researcher.py (ResearchPhase, run_research_phase)

researcher.py (legacy)
  └─ client.py (AutonomousCoderClient)
```

---

## 17. Claude Agent SDK Usage

### Imports Used
```python
from claude_agent_sdk import ClaudeAgentOptions, query, PermissionResultAllow, PermissionResultDeny
from claude_agent_sdk.types import (
    AssistantMessage, ContentBlock, ResultMessage,
    SandboxSettings, TextBlock, ToolResultBlock, ToolUseBlock,
)
```

### SDK Call Pattern
```python
options = ClaudeAgentOptions(
    model="claude-opus-4-6",
    system_prompt=system_prompt,
    allowed_tools=["Read", "Write", ...],
    mcp_servers={"serena": {...}, ...},    # MUST be dict, not list
    max_turns=30,
    cwd=str(project_path),
    permission_mode="acceptEdits",
    can_use_tool=security_callback,        # only when Bash is allowed
    include_partial_messages=True,
    hooks={},
)

async for msg in query(prompt=prompt_arg, options=options):
    if isinstance(msg, AssistantMessage):
        for block in msg.content:
            if isinstance(block, TextBlock): ...
            elif isinstance(block, ToolUseBlock): ...
    elif isinstance(msg, ResultMessage):
        cost = msg.total_cost_usd or 0.0
```

### Streaming Requirement
When `can_use_tool` is set, the SDK requires an `AsyncIterable` prompt. The `_string_to_stream()` helper wraps a plain string into:
```python
yield {"type": "user", "message": {"role": "user", "content": prompt}, "parent_tool_use_id": None, "session_id": ""}
```

---

## 18. Documented Pain Points

### 18.1 Freeform Text Between Phases (NOT Structured)
- All inter-phase data flows as raw text strings
- Research output → explore prompt: first 500 chars truncated
- Explore output → plan prompt: first 600 chars truncated
- Plan output → coder prompt: first 600 chars truncated
- Coding output → review prompt: first 3000 chars truncated
- **Impact:** Phases cannot reliably extract structured data from prior phases. JSON that agents produce is embedded in freeform text.

### 18.2 MemoryStore Completely Disconnected
- Fully implemented SQLite + FTS5 persistence with sessions, conversations, cost tracking, full-text search
- Never instantiated anywhere in the v2 pipeline
- Zero calls to any MemoryStore method from orchestrator, runners, app, or CLI
- **Impact:** No persistence across runs; all data lost on exit

### 18.3 SecurityBlock Message Never Emitted
- `SecurityBlock` message class is defined in messages.py
- Handlers exist in both `app.py` and `cli_adapter.py`
- But `security_callback()` returns `PermissionResultDeny` to the SDK directly — it never posts a `SecurityBlock` message
- **Impact:** TUI/CLI users never see security blocks in the UI; they only see the SDK's internal handling

### 18.4 AgentInstance Never Created by Active Code Path
- `run_query()` (used by all phase runners) does NOT create `AgentInstance` objects
- Only `run_agent()` creates them, but `run_agent()` is never called
- `self.agents` dict on `AgentOrchestrator` is always empty
- **Impact:** Per-agent lifecycle tracking (turns_used, session_id, etc.) is non-functional

### 18.5 Rigid Phase Pipeline (No Dynamic Handoff)
- `PHASE_ORDER = ["research", "explore", "plan", "code"]` is hardcoded
- No way to skip phases, reorder, or add custom phases without modifying core code
- Failure in any phase aborts the entire pipeline
- Pause only works between phases, not during agent execution
- **Impact:** Cannot do iterative code-review-fix loops or conditional phase execution

### 18.6 Tool Name Resolution Uncertainty
- Research role declares `"WebSearch"` and `"WebFetch"` as allowed tools
- These are Claude Code built-in tools, not standard SDK tool names
- Whether the SDK recognizes them depends on the SDK version and execution context
- **Impact:** Research phase may silently fail to use web tools

### 18.7 Duplicate MCP Server Configuration
- `config.py` has `MCP_SERVERS` registry (v2 system)
- `client.py` has `get_mcp_servers()` method with same servers inline (v1 system)
- Two independent configurations that can drift
- **Impact:** Changes to MCP config must be made in two places

### 18.8 StreamingLog Widget Unused
- `StreamingLog` extends `RichLog` with `on_agent_output()` handler
- `AgentTabs` uses plain `RichLog` instead and manually handles formatting
- `StreamingLog` is exported but never instantiated
- **Impact:** Dead code; minor

### 18.9 TaskDetail Widget Never Updated
- `TaskDetail` has full reactive property system for showing current task info
- No code in the pipeline ever calls `TaskDetail.update_task()`
- Widget always shows default empty state
- **Impact:** Bottom-left panel is a permanently empty placeholder

### 18.10 Legacy v1 System Still Exported
- `agent.py`, `client.py`, `researcher.py`, `progress.py` form a complete parallel system
- All exported in `__init__.py.__all__`
- v1 uses `claude-sonnet-4-20250514`, v2 uses `claude-opus-4-6`
- v1 has its own progress tracking, git commits, JSON extraction
- **Impact:** Confusing dual API surface; maintenance burden

### 18.11 Cost Double-Counting in run_query
- `orchestrator.run_query()` does `self.total_cost += cost` inside the streaming loop
- `orchestrator.run_pipeline()` also does `self.total_cost += result.cost_incurred`
- But `run_query()` returns `total_cost` which becomes `PhaseResult.cost_incurred`
- This means `self.total_cost` is incremented TWICE for the same cost
- **Impact:** `self.total_cost` on the orchestrator is inflated (2x actual)

---

## 19. Architecture Summary Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                    Entry Points                              │
│  __main__.py ──┬── AutonomousCoderApp (TUI)                │
│                └── CliAdapter (headless)                     │
│                                                              │
│  agent.py ──── AutonomousCoderAgent (legacy v1 CLI)         │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                  AgentOrchestrator                            │
│  PHASE_ORDER: research → explore → plan → code               │
│                                                              │
│  run_pipeline(task, runners)                                 │
│    └─ for phase in PHASE_ORDER:                              │
│         runner.run(PhaseContext) → PhaseResult                │
│         merge output_data into next input_data               │
│                                                              │
│  run_query(role, phase, prompt, system_prompt, budget)       │
│    └─ factory.create_options() → query() → stream msgs       │
│                                                              │
│  _post_message(msg) → app.post_message() (TUI or CLI)      │
└──────────────────────────┬──────────────────────────────────┘
                           │
              ┌────────────┼────────────┐
              ▼            ▼            ▼
┌──────────────┐ ┌──────────────┐ ┌──────────────┐
│ AgentFactory │ │  Security    │ │  Messages    │
│              │ │              │ │  (9 types)   │
│ create_opts()│ │ is_cmd_ok()  │ │              │
│ → ClaudeOpts │ │ callback()   │ │ → TUI widgets│
└──────┬───────┘ └──────────────┘ │ → CLI stdout │
       │                          └──────────────┘
       ▼
┌──────────────────────────────────────────────────┐
│              Phase Runners (agents/)              │
│                                                    │
│  ResearchPhaseRunner  → role=research              │
│  ExplorerPhaseRunner  → role=explore               │
│  PlannerPhaseRunner   → role=plan                  │
│  CoderPhaseRunner     → role=code + role=reviewer  │
│                                                    │
│  Each: build prompt → orchestrator.run_query()     │
│        OR _run_direct() as fallback                │
└──────────────────────────────────────────────────┘
              │
              ▼
┌──────────────────────────────────────────────────┐
│           claude_agent_sdk                         │
│  query(prompt, ClaudeAgentOptions)                 │
│  → AssistantMessage (TextBlock | ToolUseBlock)     │
│  → ResultMessage (total_cost_usd)                  │
└──────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────┐
│        Disconnected / Unused Components            │
│                                                    │
│  MemoryStore (memory.py) — SQLite+FTS5, no callers│
│  AgentInstance — only used by orphaned run_agent() │
│  StreamingLog — exported but AgentTabs uses RichLog│
│  TaskDetail — never receives update_task() calls   │
│  SecurityBlock msg — defined but never emitted     │
│  ProgressTracker (progress.py) — v1 only           │
│  AutonomousCoderClient (client.py) — v1 only       │
│  ResearchPhase (researcher.py) — v1 only           │
└──────────────────────────────────────────────────┘
```

---

## 20. File-by-File Quick Reference

### Core Pipeline (v2)
| File | Key Exports | Lines |
|------|-------------|-------|
| `config.py` | `OrchestratorConfig`, `RoleConfig`, `MCP_SERVERS` | 93 |
| `orchestrator.py` | `AgentOrchestrator`, `PhaseContext`, `PhaseResult`, `PhaseRunner`, `security_callback` | 544 |
| `agent_factory.py` | `AgentFactory` | 87 |
| `agent_instance.py` | `AgentInstance`, `AgentStatus` | 93 |
| `messages.py` | 9 Message classes | 188 |
| `security.py` | `ALLOWED_COMMANDS`, `DANGEROUS_PATTERNS`, `is_command_allowed`, `bash_security_hook` | 269 |
| `cli_adapter.py` | `CliAdapter` | 168 |
| `prompts.py` | `get_*_prompt()` × 5, `load_prompt_template`, `format_prompt` | 525 |

### Phase Runners (v2)
| File | Key Export | Role(s) |
|------|-----------|---------|
| `agents/research.py` | `ResearchPhaseRunner` | research |
| `agents/explorer.py` | `ExplorerPhaseRunner` | explore |
| `agents/planner.py` | `PlannerPhaseRunner` | plan |
| `agents/coder.py` | `CoderPhaseRunner` | code, reviewer |

### TUI Widgets
| File | Key Export | Widget Type |
|------|-----------|-------------|
| `widgets/agent_tree.py` | `AgentTree` | Tree (sidebar) |
| `widgets/agent_tabs.py` | `AgentTabs` | TabbedContent (main) |
| `widgets/streaming_log.py` | `StreamingLog` | RichLog (unused) |
| `widgets/progress_panel.py` | `ProgressPanel` | Widget (sidebar) |
| `widgets/task_detail.py` | `TaskDetail` | Widget (bottom) |
| `widgets/cost_display.py` | `CostDisplay` | Widget (bottom-right) |

### Legacy (v1)
| File | Key Export | Purpose |
|------|-----------|---------|
| `agent.py` | `AutonomousCoderAgent`, `run_autonomous_coder`, `main` | v1 orchestrator |
| `client.py` | `AutonomousCoderClient`, `create_client` | v1 SDK wrapper |
| `researcher.py` | `ResearchPhase`, `run_research_phase` | v1 research |
| `progress.py` | `ProgressTracker`, `create_feature_list`, `update_feature_status` | v1 persistence |

### Persistence (disconnected)
| File | Key Export | Purpose |
|------|-----------|---------|
| `memory.py` | `MemoryStore`, `ConversationEntry` | SQLite+FTS5 (unused) |

---

*Report generated by explore agent. All 28 Python files read in full.*
