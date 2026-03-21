# API Reference — autonomous-coder v2.0

Two execution modes:

1. **TUI Mode**: `python -m autonomous_coder ["task description"]`
2. **Legacy CLI**: `python -c "from autonomous_coder import main; main()"`

Architecture: Four-phase pipeline (Research, Explore, Plan, Code) with Textual TUI, SQLite+FTS5 persistence, and `can_use_tool` security callback.

---

## Table of Contents

- [Core](#core)
  - [autonomous_coder.app](#autonomous_coderapp)
  - [autonomous_coder.orchestrator](#autonomous_coderorchestrator)
  - [autonomous_coder.agent_factory](#autonomous_coderagent_factory)
  - [autonomous_coder.agent_instance](#autonomous_coderagent_instance)
  - [autonomous_coder.messages](#autonomous_codermessages)
  - [autonomous_coder.config](#autonomous_coderconfig)
  - [autonomous_coder.memory](#autonomous_codermemory)
- [Security](#security)
  - [autonomous_coder.security](#autonomous_codersecurity)
- [Legacy API](#legacy-api)
  - [autonomous_coder.client](#autonomous_coderclient)
  - [autonomous_coder.agent](#autonomous_coderagent)
  - [autonomous_coder.progress](#autonomous_coderprogress)
  - [autonomous_coder.researcher](#autonomous_coderresearcher)
  - [autonomous_coder.prompts](#autonomous_coderprompts)
- [Widgets](#widgets)
  - [autonomous_coder.widgets.agent_tree](#autonomous_coderwidgetsagent_tree)
  - [autonomous_coder.widgets.agent_tabs](#autonomous_coderwidgetsagent_tabs)
  - [autonomous_coder.widgets.streaming_log](#autonomous_coderwidgetsstreaming_log)
  - [autonomous_coder.widgets.progress_panel](#autonomous_coderwidgetsprogress_panel)
  - [autonomous_coder.widgets.task_detail](#autonomous_coderwidgetstask_detail)
  - [autonomous_coder.widgets.cost_display](#autonomous_coderwidgetscost_display)
- [Phase Runners](#phase-runners)
  - [autonomous_coder.agents.research](#autonomous_coderagentsresearch)
  - [autonomous_coder.agents.explorer](#autonomous_coderagentsexplorer)
  - [autonomous_coder.agents.planner](#autonomous_coderagentsplanner)
  - [autonomous_coder.agents.coder](#autonomous_coderagentscoder)

---

## Core

### `autonomous_coder.app`

> Source: `src/autonomous_coder/app.py`

#### `AutonomousCoderApp`

Top-level Textual TUI application. Extends `textual.app.App`.

**Constructor**

```python
AutonomousCoderApp(
    task: str = "",
    project_path: str | Path | None = None,
    **kwargs: Any,
) -> None
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `task` | `str` | `""` | Task description; if non-empty, pipeline auto-starts on ready |
| `project_path` | `str \| Path \| None` | `None` | Project root directory; defaults to `Path.cwd()` |

**Reactive Attributes**

| Attribute | Type | Default | Description |
|-----------|------|---------|-------------|
| `current_phase` | `reactive[str]` | `"idle"` | Name of the currently executing phase |
| `total_cost` | `reactive[float]` | `0.0` | Cumulative USD cost across all agents |

**Key Bindings**

| Key | Action | Description |
|-----|--------|-------------|
| `q` | `quit` | Quit the application |
| `p` | `pause` | Pause pipeline between phases |
| `r` | `resume` | Resume a paused pipeline |
| `c` | `cancel_agent` | Cancel the running pipeline |
| `tab` | `cycle_agents` | Switch to next agent tab |
| `/` | `command_palette` | Open command palette |

**Methods**

```python
async def run_task(self, task: str) -> None
```
Execute the full orchestration pipeline. Creates an `AgentOrchestrator`, registers all four `PhaseRunner` implementations, and calls `run_pipeline()`.

**Message Handlers**

| Handler | Message Type | Behavior |
|---------|-------------|----------|
| `on_agent_started` | `AgentStarted` | Adds agent to tree and tabs |
| `on_agent_output` | `AgentOutput` | Appends text to agent's tab |
| `on_agent_completed` | `AgentCompleted` | Marks agent complete in tree |
| `on_agent_error` | `AgentError` | Marks agent failed, shows error |
| `on_cost_update` | `CostUpdate` | Updates cost display |
| `on_security_block` | `SecurityBlock` | Shows blocked tool in agent tab |
| `on_phase_started` | `PhaseStarted` | Updates progress panel |
| `on_phase_completed` | `PhaseCompleted` | Updates progress panel |

---

### `autonomous_coder.orchestrator`

> Source: `src/autonomous_coder/orchestrator.py`

#### `PhaseContext`

Dataclass. Input context handed to a `PhaseRunner`.

```python
@dataclass
class PhaseContext:
    phase_name: str
    input_data: dict[str, Any]
    config: OrchestratorConfig
    budget_remaining: float
    task_description: str = ""
```

| Field | Type | Description |
|-------|------|-------------|
| `phase_name` | `str` | Name of the phase (e.g. `"research"`) |
| `input_data` | `dict[str, Any]` | Accumulated data from prior phases |
| `config` | `OrchestratorConfig` | Full orchestrator configuration |
| `budget_remaining` | `float` | USD budget remaining for this phase |
| `task_description` | `str` | Natural-language task description |

#### `PhaseResult`

Dataclass. Output produced by a `PhaseRunner`.

```python
@dataclass
class PhaseResult:
    phase_name: str
    output_data: dict[str, Any]
    cost_incurred: float = 0.0
    duration_seconds: float = 0.0
    success: bool = True
    error: str | None = None
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `phase_name` | `str` | | Phase that produced this result |
| `output_data` | `dict[str, Any]` | | Arbitrary output data merged into next phase's input |
| `cost_incurred` | `float` | `0.0` | USD cost of this phase |
| `duration_seconds` | `float` | `0.0` | Wall-clock duration |
| `success` | `bool` | `True` | Whether the phase succeeded |
| `error` | `str \| None` | `None` | Error message on failure |

#### `PhaseRunner`

Runtime-checkable structural `Protocol`. Any object with an `async run()` method satisfies it.

```python
@runtime_checkable
class PhaseRunner(Protocol):
    async def run(self, context: PhaseContext) -> PhaseResult: ...
```

#### `security_callback`

Async function called by the SDK before every tool execution. Blocks Bash commands that fail `is_command_allowed()`; allows all non-Bash tools.

```python
async def security_callback(
    tool_name: str,
    tool_input: dict,
    ctx: Any,
) -> PermissionResultAllow | PermissionResultDeny
```

#### `AgentOrchestrator`

Runs a sequential Research, Explore, Plan, Code pipeline. Each phase is driven by a caller-supplied `PhaseRunner`. Posts Textual `Message` objects for live UI updates.

**Constructor**

```python
AgentOrchestrator(
    config: OrchestratorConfig,
    app: Any = None,
) -> None
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `config` | `OrchestratorConfig` | | Configuration including roles and budget |
| `app` | `Any` | `None` | Textual `App` instance for UI updates; `None` for headless |

**Class Attributes**

| Attribute | Type | Value |
|-----------|------|-------|
| `PHASE_ORDER` | `list[str]` | `["research", "explore", "plan", "code"]` |

**Instance Attributes**

| Attribute | Type | Description |
|-----------|------|-------------|
| `config` | `OrchestratorConfig` | Orchestrator configuration |
| `factory` | `AgentFactory` | Factory for creating `ClaudeAgentOptions` |
| `app` | `Any` | Textual app (or `None`) |
| `agents` | `dict[str, AgentInstance]` | Registry of all agents that have run |
| `total_cost` | `float` | Cumulative USD cost |
| `phase_results` | `dict[str, PhaseResult]` | Results keyed by phase name |

**Methods**

```python
async def run_pipeline(
    self,
    task: str,
    runners: dict[str, PhaseRunner],
) -> dict[str, PhaseResult]
```
Execute the full phase pipeline sequentially. Missing phases are skipped. Returns mapping of phase name to `PhaseResult`. Aborts on phase failure. Budget is decremented after each phase.

```python
async def run_agent(
    self,
    role: str,
    phase: str,
    prompt: str,
    system_prompt: str,
) -> tuple[str, float]
```
Run one agent query with budget tracking and UI message dispatch. Returns `(collected_text, cost_incurred)`.

```python
def pause(self) -> None
```
Pause pipeline between phases (does not interrupt a running agent).

```python
def resume(self) -> None
```
Resume a paused pipeline.

```python
def cancel(self) -> None
```
Cancel pipeline; current agent query runs to its next yield point.

---

### `autonomous_coder.agent_factory`

> Source: `src/autonomous_coder/agent_factory.py`

#### `AgentFactory`

Creates configured `ClaudeAgentOptions` for each agent role. Maps role config to SDK options, assembles MCP servers as a dict, and injects `SERENA_PROJECT` env.

**Constructor**

```python
AgentFactory(config: OrchestratorConfig) -> None
```

**Methods**

```python
def create_options(
    self,
    role: str,
    system_prompt: str,
    security_callback: Callable | None = None,
    hooks: dict | None = None,
) -> ClaudeAgentOptions
```
Build `ClaudeAgentOptions` for a specific agent role.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `role` | `str` | | Key into `OrchestratorConfig.roles` |
| `system_prompt` | `str` | | Full system prompt text |
| `security_callback` | `Callable \| None` | `None` | `can_use_tool` callback |
| `hooks` | `dict \| None` | `None` | Hooks dict passed through to SDK |

Returns a `ClaudeAgentOptions` with `permission_mode="acceptEdits"` and `include_partial_messages=True`.

```python
def get_budget_limit(self, role: str) -> float
```
Return the manual budget cap for a role.

---

### `autonomous_coder.agent_instance`

> Source: `src/autonomous_coder/agent_instance.py`

#### `AgentStatus`

Enum representing agent lifecycle states.

| Member | Value |
|--------|-------|
| `PENDING` | `"pending"` |
| `RUNNING` | `"running"` |
| `COMPLETED` | `"completed"` |
| `FAILED` | `"failed"` |
| `CANCELLED` | `"cancelled"` |

#### `AgentInstance`

Dataclass tracking a single agent's lifecycle and cost.

```python
@dataclass
class AgentInstance:
    name: str
    role: str
    phase: str
    status: AgentStatus = AgentStatus.PENDING
    cost: float = 0.0
    budget_limit: float = 1.0
    start_time: float = 0.0
    end_time: float = 0.0
    turns_used: int = 0
    max_turns: int = 30
    session_id: str | None = None
    error: str | None = None
```

**Properties**

| Property | Type | Description |
|----------|------|-------------|
| `duration` | `float` | Elapsed seconds (live if still running) |
| `budget_remaining` | `float` | `max(0.0, budget_limit - cost)` |
| `budget_exceeded` | `bool` | `True` if `cost >= budget_limit` |

**Methods**

```python
def add_cost(self, amount: float) -> None
```
Add cost to the agent's running total.

```python
def start(self) -> None
```
Transition to `RUNNING` and record start time.

```python
def complete(self, error: str | None = None) -> None
```
Transition to `COMPLETED` or `FAILED` and record end time.

```python
def cancel(self) -> None
```
Transition to `CANCELLED` and record end time.

---

### `autonomous_coder.messages`

> Source: `src/autonomous_coder/messages.py`

All classes extend `textual.message.Message` and are used for inter-widget communication.

#### `AgentStarted`

Fired when an agent begins execution.

```python
AgentStarted(agent_name: str, phase: str)
```

#### `AgentOutput`

Fired when an agent produces output text.

```python
AgentOutput(agent_name: str, text: str, block_type: str = "text")
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `agent_name` | `str` | | Agent identifier |
| `text` | `str` | | Output text content |
| `block_type` | `str` | `"text"` | One of `"text"`, `"tool"`, `"error"` |

#### `AgentCompleted`

Fired when an agent finishes execution.

```python
AgentCompleted(
    agent_name: str,
    phase: str,
    cost: float,
    duration: float,
    success: bool,
    error: str | None = None,
)
```

#### `AgentError`

Fired when an agent encounters a fatal error.

```python
AgentError(agent_name: str, error: str, phase: str)
```

#### `CostUpdate`

Fired when agent cost changes.

```python
CostUpdate(agent_name: str, cost: float, total_cost: float)
```

#### `SecurityBlock`

Fired when a tool call is blocked by security policy.

```python
SecurityBlock(agent_name: str, tool_name: str, reason: str)
```

#### `PhaseStarted`

Fired when a pipeline phase begins.

```python
PhaseStarted(phase: str, phase_index: int, total_phases: int)
```

#### `PhaseCompleted`

Fired when a pipeline phase finishes.

```python
PhaseCompleted(
    phase: str,
    phase_index: int,
    cost: float,
    duration: float,
    success: bool,
)
```

---

### `autonomous_coder.config`

> Source: `src/autonomous_coder/config.py`

#### `RoleConfig`

Dataclass. Configuration for a single agent role.

```python
@dataclass
class RoleConfig:
    model: str
    tools: list[str]
    mcp_keys: list[str]
    budget_limit: float
    max_turns: int
```

| Field | Type | Description |
|-------|------|-------------|
| `model` | `str` | Claude model identifier |
| `tools` | `list[str]` | Allowed SDK tools (e.g. `["Read", "Write", "Bash"]`) |
| `mcp_keys` | `list[str]` | Keys into `MCP_SERVERS` dict |
| `budget_limit` | `float` | Per-role USD budget cap |
| `max_turns` | `int` | Maximum conversation turns |

#### `OrchestratorConfig`

Dataclass. Top-level orchestrator configuration.

```python
@dataclass
class OrchestratorConfig:
    project_path: Path
    total_budget: float = 5.0
    roles: dict[str, RoleConfig] = field(default_factory=...)
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `project_path` | `Path` | | Project root directory |
| `total_budget` | `float` | `5.0` | Total USD budget for the pipeline |
| `roles` | `dict[str, RoleConfig]` | *(see below)* | Role configurations |

**Default Roles**

| Role | Model | Budget | Max Turns | MCP Keys |
|------|-------|--------|-----------|----------|
| `research` | `claude-sonnet-4-5-20250514` | $0.50 | 25 | `firecrawl-mcp`, `Context7` |
| `explore` | `claude-sonnet-4-5-20250514` | $0.50 | 20 | `serena` |
| `plan` | `claude-sonnet-4-5-20250514` | $1.00 | 10 | `sequential-thinking`, `serena` |
| `code` | `claude-sonnet-4-5-20250514` | $2.00 | 30 | `serena`, `Context7` |
| `reviewer` | `claude-sonnet-4-5-20250514` | $0.25 | 10 | `serena` |

#### `MCP_SERVERS`

Module-level `dict[str, dict]`. Registry of MCP server configurations.

| Key | Command | Description |
|-----|---------|-------------|
| `"serena"` | `uvx serena` | Semantic code analysis |
| `"sequential-thinking"` | `npx -y @modelcontextprotocol/server-sequential-thinking` | Step-by-step reasoning |
| `"Context7"` | `npx -y @upstash/context7-mcp` | Library documentation |
| `"firecrawl-mcp"` | `npx -y firecrawl-mcp` | Web research (requires `FIRECRAWL_API_KEY`) |

---

### `autonomous_coder.memory`

> Source: `src/autonomous_coder/memory.py`

#### `ConversationEntry`

Dataclass representing a single conversation record.

```python
@dataclass
class ConversationEntry:
    session_id: str
    agent_name: str
    phase: str
    role: str           # "user", "assistant", "tool"
    content: str
    block_type: str = "text"   # "text", "tool_use", "tool_result"
    cost: float = 0.0
    timestamp: float = 0.0
```

#### `MemoryStore`

SQLite-backed persistence for agent sessions. Uses WAL mode, foreign keys, and FTS5 full-text search on conversation content.

**Constructor**

```python
MemoryStore(db_path: Path | str) -> None
```
Creates the database file and parent directories if they do not exist. Initializes `sessions`, `conversations`, `conversations_fts`, and `cost_tracking` tables.

**Session Methods**

```python
def create_session(self, session_id: str, task: str) -> None
```
Insert a new session record.

```python
def update_session(self, session_id: str, **kwargs: Any) -> None
```
Update arbitrary session fields. Automatically sets `updated_at`.

```python
def get_session(self, session_id: str) -> dict | None
```
Retrieve a session by ID. Returns `None` if not found. Parses `metadata` from JSON.

```python
def list_sessions(self, limit: int = 20) -> list[dict]
```
List sessions ordered by `updated_at` descending.

**Conversation Methods**

```python
def add_conversation(self, entry: ConversationEntry) -> int
```
Insert a conversation entry. Auto-sets `timestamp` if zero. Returns the row ID.

```python
def get_conversations(
    self,
    session_id: str,
    agent_name: str | None = None,
    limit: int = 100,
) -> list[dict]
```
Retrieve conversations for a session, optionally filtered by agent name.

```python
def search_conversations(
    self,
    query: str,
    session_id: str | None = None,
) -> list[dict]
```
Full-text search across conversation content using FTS5. Optionally scoped to a session.

**Cost Tracking Methods**

```python
def record_cost(
    self,
    session_id: str,
    agent_name: str,
    phase: str,
    cost: float,
    cumulative: float,
) -> None
```
Record a cost event and update the session's `total_cost`.

```python
def get_session_cost(self, session_id: str) -> float
```
Get total cost for a session.

```python
def get_cost_breakdown(self, session_id: str) -> dict[str, float]
```
Get per-agent cost breakdown for a session. Returns `{agent_name: total_cost}`.

---

## Security

### `autonomous_coder.security`

> Source: `src/autonomous_coder/security.py`

Defense-in-depth security through Bash command allowlisting, PreToolUse hook validation, and permission scoping.

#### `ALLOWED_COMMANDS`

`set[str]` of allowed base command names. Includes package managers, version control, build tools, runtimes, compilers, linters, formatters, safe shell utilities, dev tools, container tools, database clients, and cloud CLIs.

#### `DANGEROUS_PATTERNS`

`list[str]` of patterns that are always blocked regardless of allowlist (e.g. `rm -rf /`, fork bombs, `curl | sh`).

#### `is_command_allowed`

```python
def is_command_allowed(command: str) -> tuple[bool, str]
```
Check if a bash command is allowed to execute. Checks dangerous patterns first, then extracts the base command and validates against the allowlist.

| Parameter | Type | Description |
|-----------|------|-------------|
| `command` | `str` | The bash command to validate |

Returns `(is_allowed, reason)`.

#### `bash_security_hook`

```python
async def bash_security_hook(
    tool_input: dict[str, Any],
) -> dict[str, Any] | None
```
PreToolUse hook for validating bash commands. Returns `None` to allow, or a dict with `"error"` key to block.

#### `get_security_permissions`

```python
def get_security_permissions(project_path: str) -> dict[str, Any]
```
Get the security permissions configuration for Claude SDK. Scopes file operations to the project directory. Returns a permissions dict with `defaultMode: "acceptEdits"` and an `allow` list of tool patterns.

#### `get_sandbox_settings`

```python
def get_sandbox_settings() -> dict[str, Any]
```
Get the sandbox configuration. Returns `{"enabled": True, "autoAllowBashIfSandboxed": True}`.

---

## Legacy API

### `autonomous_coder.client`

> Source: `src/autonomous_coder/client.py`

#### `AutonomousCoderClient`

Client for running autonomous coding sessions with Claude. Configures the Claude Agent SDK with security permissions, MCP servers, and sandbox settings.

**Constructor**

```python
AutonomousCoderClient(
    project_path: str | Path,
    model: str = "claude-sonnet-4-20250514",
    max_tokens: int = 16384,
    sandbox_enabled: bool = True,
)
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `project_path` | `str \| Path` | | Project directory (must exist) |
| `model` | `str` | `"claude-sonnet-4-20250514"` | Claude model |
| `max_tokens` | `int` | `16384` | Maximum tokens for responses |
| `sandbox_enabled` | `bool` | `True` | Enable OS sandbox |

**Methods**

```python
def get_mcp_servers(self) -> dict[str, Any]
```
Get MCP server configuration for the four-phase workflow. Returns configs for `serena`, `sequential-thinking`, `Context7`, and `firecrawl-mcp`.

```python
def get_options(self, system_prompt: str | None = None) -> ClaudeAgentOptions
```
Get Claude Agent SDK options with security configuration.

```python
async def run_session(
    self,
    prompt: str,
    system_prompt: str | None = None,
) -> AsyncIterator[ContentBlock]
```
Run a Claude session, yielding content blocks as they stream. Validates bash commands inline via `bash_security_hook`.

```python
async def run_session_to_completion(
    self,
    prompt: str,
    system_prompt: str | None = None,
) -> dict[str, Any]
```
Run a session and collect all results into `{"text": str, "tool_uses": list, "tool_results": list, "success": bool}`.

```python
async def explore_codebase(
    self,
    task: str,
    explorer_prompt: str,
) -> dict[str, Any]
```
Run the exploration phase using Serena MCP.

```python
async def create_plan(
    self,
    task: str,
    exploration_results: dict[str, Any],
    planner_prompt: str,
) -> dict[str, Any]
```
Run the planning phase based on exploration results.

```python
async def implement_task(
    self,
    task: dict[str, Any],
    coder_prompt: str,
) -> dict[str, Any]
```
Implement a single task from the plan.

#### `create_client`

```python
def create_client(
    project_path: str | Path,
    model: str = "claude-sonnet-4-20250514",
    sandbox_enabled: bool = True,
) -> AutonomousCoderClient
```
Factory function to create a configured client.

---

### `autonomous_coder.agent`

> Source: `src/autonomous_coder/agent.py`

#### `AutonomousCoderAgent`

Main orchestrator for the legacy (non-TUI) autonomous coding sessions. Manages the four-phase workflow with session resumption, progress tracking, and git auto-commits.

**Constructor**

```python
AutonomousCoderAgent(
    project_path: str | Path,
    model: str = "claude-sonnet-4-20250514",
    max_iterations: int = 10,
    sandbox_enabled: bool = True,
    auto_commit: bool = True,
)
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `project_path` | `str \| Path` | | Project directory |
| `model` | `str` | `"claude-sonnet-4-20250514"` | Claude model |
| `max_iterations` | `int` | `10` | Maximum iterations per task |
| `sandbox_enabled` | `bool` | `True` | Enable OS sandbox |
| `auto_commit` | `bool` | `True` | Auto-commit after each task |

**Methods**

```python
async def run(self, task: str, resume: bool = True) -> dict[str, Any]
```
Run the complete autonomous coding workflow. Returns `{"task": str, "phases": dict, "success": bool, "error": str | None}`.

```python
def get_status(self) -> dict[str, Any]
```
Get current workflow status including summary, progress, project path, and model.

```python
def reset(self) -> None
```
Reset all progress and start fresh.

#### `run_autonomous_coder`

```python
async def run_autonomous_coder(
    task: str,
    project_path: str | Path,
    model: str = "claude-sonnet-4-20250514",
    max_iterations: int = 10,
    sandbox_enabled: bool = True,
    auto_commit: bool = True,
    resume: bool = True,
) -> dict[str, Any]
```
Main entry point for running the autonomous coder programmatically. Creates an `AutonomousCoderAgent` and calls `run()`.

#### `main`

```python
def main() -> None
```
CLI entry point for standalone execution. Parses command-line arguments (`task`, `project_path`, `--model`, `--max-iterations`, `--no-sandbox`, `--no-commit`, `--fresh`).

---

### `autonomous_coder.progress`

> Source: `src/autonomous_coder/progress.py`

#### `ProgressTracker`

Tracks progress of the autonomous coding workflow. Persists state to `.autonomous-coder/progress.json`.

**Constructor**

```python
ProgressTracker(project_path: str | Path)
```

**Methods**

```python
def save(self) -> None
```
Save current progress to the JSON file.

```python
def start_task(self, task: str) -> None
```
Start tracking a new task. Resets all progress state.

```python
def set_exploration_complete(self, exploration_results: dict[str, Any]) -> None
```
Mark exploration phase as complete.

```python
def set_plan(self, plan: dict[str, Any]) -> None
```
Set the implementation plan. Transitions status to `"implementing"`.

```python
def start_task_implementation(self, task_id: int) -> None
```
Mark a task as being implemented. Increments session counter.

```python
def complete_task(self, task_id: int, commit_hash: str | None = None) -> None
```
Mark a task as completed. Records commit hash if provided. Auto-detects pipeline completion.

```python
def record_error(self, task_id: int | None, error: str) -> None
```
Record an error that occurred during implementation.

```python
def get_next_task(self) -> dict[str, Any] | None
```
Get the next task to implement, respecting dependency ordering. Returns `None` when all tasks are complete.

```python
def get_status_summary(self) -> str
```
Get a human-readable status summary string.

```python
def is_resumable(self) -> bool
```
Check if there is existing progress that can be resumed.

```python
def reset(self) -> None
```
Reset all progress and delete the progress file.

```python
def to_dict(self) -> dict[str, Any]
```
Get the full progress state as a dictionary.

#### `create_feature_list`

```python
def create_feature_list(
    project_path: str | Path,
    tasks: list[dict[str, Any]],
) -> Path
```
Create a `feature_list.json` file at `.autonomous-coder/feature_list.json` for tracking tasks. Returns the path to the created file.

#### `update_feature_status`

```python
def update_feature_status(
    project_path: str | Path,
    task_id: int,
    status: str,
) -> None
```
Update the status of a feature in `feature_list.json`. Valid statuses: `"pending"`, `"in_progress"`, `"completed"`, `"failed"`.

---

### `autonomous_coder.researcher`

> Source: `src/autonomous_coder/researcher.py`

#### `MCP_DISCOVERY_SOURCES`

`list[str]` of URLs for common MCP server registries (GitHub, npm, PyPI).

#### `TASK_TYPE_MCP_HINTS`

`dict[str, list[str]]` mapping task types (e.g. `"ios"`, `"web"`, `"aws"`) to relevant MCP server keywords.

#### `ResearchPhase`

Executes the Research/Onboarding phase. Runs before the Explorer phase to identify task types, search for MCP servers, find skills/examples, and gather library documentation.

**Constructor**

```python
ResearchPhase(client: AutonomousCoderClient)
```

**Methods**

```python
async def run(
    self,
    task: str,
    researcher_prompt: str,
) -> dict[str, Any]
```
Execute the research phase. Returns a dict with keys: `task_types`, `mcp_servers`, `skills`, `libraries`, `recommendations`, `search_queries_used`, `success`.

#### `run_research_phase`

```python
async def run_research_phase(
    client: AutonomousCoderClient,
    task: str,
    researcher_prompt: str,
) -> dict[str, Any]
```
Convenience function wrapping `ResearchPhase.run()`.

---

### `autonomous_coder.prompts`

> Source: `src/autonomous_coder/prompts.py`

#### `PROMPTS_DIR`

`Path` to the `prompts/` subdirectory within the package.

#### `load_prompt_template`

```python
def load_prompt_template(template_name: str) -> str
```
Load a prompt template from the prompts directory. Appends `.md` if not present.

#### `format_prompt`

```python
def format_prompt(template: str, **kwargs: Any) -> str
```
Format a prompt template using `str.format()`. Raises `ValueError` on missing variables.

#### `get_researcher_prompt`

```python
def get_researcher_prompt(
    task: str,
    project_path: str,
    additional_context: str = "",
) -> str
```
Get the formatted researcher prompt for web research and MCP discovery.

#### `get_explorer_prompt`

```python
def get_explorer_prompt(
    task: str,
    project_path: str,
    additional_context: str = "",
) -> str
```
Get the formatted explorer prompt for codebase analysis.

#### `get_planner_prompt`

```python
def get_planner_prompt(
    task: str,
    exploration_results: str,
    project_path: str,
) -> str
```
Get the formatted planner prompt for implementation planning.

#### `get_coder_prompt`

```python
def get_coder_prompt(
    task: dict[str, Any],
    plan: dict[str, Any],
    completed_tasks: list[int],
    project_path: str,
) -> str
```
Get the formatted coder prompt for a specific implementation task. Formats task details (id, title, description, files, dependencies, test criteria, complexity) and plan context (goal, summary, total tasks, completed count, risks).

#### `get_system_prompt`

```python
def get_system_prompt() -> str
```
Get the base system prompt for all agents. Describes available Serena MCP tools and guidelines.

#### `ensure_prompt_templates_exist`

```python
def ensure_prompt_templates_exist() -> None
```
Ensure prompt template files exist in `PROMPTS_DIR`, creating them from built-in fallbacks if needed. Templates: `researcher_prompt.md`, `explorer_prompt.md`, `planner_prompt.md`, `coder_prompt.md`.

---

## Widgets

### `autonomous_coder.widgets.agent_tree`

> Source: `src/autonomous_coder/widgets/agent_tree.py`

#### `AgentTree`

Extends `textual.widgets.Tree`. Sidebar tree showing agents grouped by pipeline phase (`research`, `explore`, `plan`, `code`).

**Constructor**

```python
AgentTree(**kwargs) -> None
```

**Methods**

```python
def add_agent(self, agent_name: str, phase: str) -> None
```
Add a new agent node under the given phase.

```python
def set_agent_running(self, agent_name: str) -> None
```
Mark agent as currently running (icon: `▶`).

```python
def set_agent_complete(self, agent_name: str, success: bool) -> None
```
Mark agent as finished. Uses `✓` for success, `✗` for error.

---

### `autonomous_coder.widgets.agent_tabs`

> Source: `src/autonomous_coder/widgets/agent_tabs.py`

#### `AgentTabs`

Extends `textual.widgets.TabbedContent`. Dynamic tabbed view with one tab per agent, added on `AgentStarted`.

**Constructor**

```python
AgentTabs(**kwargs) -> None
```

**Methods**

```python
def add_agent_tab(self, agent_name: str) -> None
```
Create a new tab with a `RichLog` for the given agent. No-op if tab already exists.

```python
def append_output(self, agent_name: str, text: str, block_type: str = "text") -> None
```
Write formatted output to the agent's `RichLog`. Formats `"tool"` blocks in cyan, `"error"` blocks in red.

```python
def focus_agent(self, agent_name: str) -> None
```
Switch active tab to the named agent.

---

### `autonomous_coder.widgets.streaming_log`

> Source: `src/autonomous_coder/widgets/streaming_log.py`

#### `StreamingLog`

Extends `textual.widgets.RichLog`. Handles `AgentOutput` messages and renders with markup. Supports block types: `"tool"` (cyan), `"error"` (red), `"thinking"` (dim italic), `"result"` (green), and plain text.

---

### `autonomous_coder.widgets.progress_panel`

> Source: `src/autonomous_coder/widgets/progress_panel.py`

#### `ProgressPanel`

Extends `textual.widget.Widget`. Shows current phase name, progress bar, and task list with status icons.

**Reactive Attributes**

| Attribute | Type | Default |
|-----------|------|---------|
| `current_phase` | `reactive[str]` | `"idle"` |
| `phase_index` | `reactive[int]` | `0` |
| `total_phases` | `reactive[int]` | `4` |
| `tasks` | `reactive[list]` | `[]` |

**Methods**

```python
def set_phase(self, phase: str, index: int, total: int) -> None
```
Update the current phase, index, and total in one call.

```python
def update_tasks(self, tasks: list[dict]) -> None
```
Update the task list. Each dict: `{"name": str, "status": "pending" | "running" | "complete"}`.

---

### `autonomous_coder.widgets.task_detail`

> Source: `src/autonomous_coder/widgets/task_detail.py`

#### `TaskDetail`

Extends `textual.widget.Widget`. Shows details for the currently active task.

**Reactive Attributes**

| Attribute | Type | Default |
|-----------|------|---------|
| `task_name` | `reactive[str]` | `""` |
| `task_status` | `reactive[str]` | `"idle"` |
| `task_files` | `reactive[list]` | `[]` |
| `task_dependencies` | `reactive[list]` | `[]` |
| `estimated_cost` | `reactive[float]` | `0.0` |

**Methods**

```python
def update_task(
    self,
    name: str,
    status: str,
    files: list[str] | None = None,
    dependencies: list[str] | None = None,
    estimated_cost: float = 0.0,
) -> None
```
Update all task detail fields in one call.

---

### `autonomous_coder.widgets.cost_display`

> Source: `src/autonomous_coder/widgets/cost_display.py`

#### `BUDGET_WARNING_THRESHOLD`

`float` = `0.80`. Warning fires at 80% of budget.

#### `CostDisplay`

Extends `textual.widget.Widget`. Shows total cost and per-agent breakdown; adds a `"warning"` CSS class when nearing the budget.

**Reactive Attributes**

| Attribute | Type | Default |
|-----------|------|---------|
| `total_cost` | `reactive[float]` | `0.0` |
| `budget_limit` | `reactive[float]` | `5.0` |
| `agent_costs` | `reactive[dict]` | `{}` |

**Methods**

```python
def record_cost(self, agent_name: str, cost: float, total_cost: float) -> None
```
Update per-agent cost and total. Called by `AutonomousCoderApp.on_cost_update`.

---

## Phase Runners

All phase runners satisfy the `PhaseRunner` protocol and accept an `AgentFactory` in their constructor.

### `autonomous_coder.agents.research`

> Source: `src/autonomous_coder/agents/research.py`

#### `ResearchPhaseRunner`

Runs the research phase: web research and MCP discovery. Uses the `"research"` role.

```python
ResearchPhaseRunner(factory: AgentFactory)
```

```python
async def run(self, context: PhaseContext) -> PhaseResult
```
Executes a single agent query. Output key: `"research_output"`.

---

### `autonomous_coder.agents.explorer`

> Source: `src/autonomous_coder/agents/explorer.py`

#### `ExplorerPhaseRunner`

Runs the explore phase: codebase structure analysis via Serena. Uses the `"explore"` role. Injects research output as additional context.

```python
ExplorerPhaseRunner(factory: AgentFactory)
```

```python
async def run(self, context: PhaseContext) -> PhaseResult
```
Executes a single agent query. Output key: `"explore_output"`.

---

### `autonomous_coder.agents.planner`

> Source: `src/autonomous_coder/agents/planner.py`

#### `PlannerPhaseRunner`

Runs the plan phase: produces a structured implementation plan. Uses the `"plan"` role. Receives both research and exploration outputs.

```python
PlannerPhaseRunner(factory: AgentFactory)
```

```python
async def run(self, context: PhaseContext) -> PhaseResult
```
Executes a single agent query. Output key: `"plan_output"`.

---

### `autonomous_coder.agents.coder`

> Source: `src/autonomous_coder/agents/coder.py`

#### `CoderPhaseRunner`

Runs the code phase followed by a separate reviewer query (not a subagent). Uses the `"code"` role for implementation and the `"reviewer"` role for review.

```python
CoderPhaseRunner(factory: AgentFactory)
```

```python
async def run(self, context: PhaseContext) -> PhaseResult
```
Executes two sequential agent queries: coding pass then review pass. Output keys: `"code_output"`, `"review_output"`.
