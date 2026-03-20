# TUI Agent Orchestration System — Architecture Design

**Date**: 2026-03-19
**Status**: Phase A — Revision 2 (Post-Critic)
**Scope**: Transform `autonomous-coder` into a full-fledged TUI-based multi-agent orchestration system

---

## 1. Executive Summary

Transform the existing sequential 4-phase autonomous coder (Research → Explore → Plan → Code) into a **real-time TUI dashboard** that orchestrates multiple concurrent Claude agents with live streaming output, progress tracking, cost monitoring, and persistent memory.

**Core transformation**:
- FROM: CLI script with `print()` statements, single-agent sequential execution
- TO: Multi-pane Textual TUI with parallel agent workers, reactive state, live streaming

**Key technology decisions**:
| Decision | Choice | Rationale |
|----------|--------|-----------|
| TUI Framework | Textual v7.0.0 | Async-native, CSS styling, rich widgets, already installed |
| SDK API | `query()` with `ClaudeCodeOptions` | Streaming, hooks, `can_use_tool` security callback, MCP servers |
| Multi-Agent | Separate `query()` calls per agent + Textual `run_worker` | Each agent = independent `ClaudeCodeOptions`; no built-in subagent parameter |
| Memory | SQLite + FTS5 | Zero deps, embedded, fast full-text search |
| Codebase Index | Serena MCP (already configured) | Tree-sitter AST, symbol navigation, already in project |

---

## 2. Research Findings Summary

### Claude Code SDK (Python) v0.0.25

**Package**: `claude-code-sdk` (renamed from `claude-agent-sdk`)
**Auth**: Inherits from CLI session — NO API key needed for SDK usage
**Installed**: v0.0.25 at `/Users/nick/Library/Python/3.12/lib/python/site-packages`

**Two execution patterns**:

| Feature | `query()` (one-off) | `query()` with `resume` (multi-turn) |
|---------|---------------------|--------------------------------------|
| Session | New each time | Resumes existing session via `resume=session_id` |
| Conversation | Single exchange | Multi-turn with context via `continue_conversation=True` |
| Hooks | Yes (via `hooks` in options) | Yes (via `hooks` in options) |
| Security | Yes (via `can_use_tool` callback) | Yes (via `can_use_tool` callback) |
| MCP Tools | Yes (via `mcp_servers`) | Yes (via `mcp_servers`) |
| Streaming | Yes (`include_partial_messages=True`) | Yes (`include_partial_messages=True`) |

**Key `ClaudeCodeOptions` fields** (v0.0.25 — complete verified list):

```python
ClaudeCodeOptions(
    # === Fields the TUI orchestrator WILL use ===

    # Core agent identity
    model="claude-sonnet-4-5-20250514",       # Per-agent model selection
    system_prompt="You are a research agent...",  # Role-specific system prompt
    append_system_prompt="Additional context...", # Additive prompt (preserves defaults)
    cwd=Path("/project"),                     # Working directory for the agent

    # Tool control (primary sandboxing mechanism)
    allowed_tools=["Read", "Write", "Bash"],  # Whitelist per agent role
    disallowed_tools=["WebSearch"],            # Blacklist (takes precedence)

    # Security (CRITICAL — replaces our client-side bash validation)
    can_use_tool=security_callback,           # Async callback: (tool_name, tool_input, ctx) → Allow|Deny
    permission_mode="acceptEdits",            # "default"|"acceptEdits"|"plan"|"bypassPermissions"

    # MCP servers (Serena, Context7, Firecrawl, etc.)
    mcp_servers=[MCPServerConfig(...)],       # List of MCP server configs

    # Session management
    continue_conversation=True,               # Multi-turn within same session
    resume="session-id-uuid",                 # Resume a previous session by ID
    max_turns=25,                             # Per-agent turn limit

    # Streaming (for TUI real-time display)
    include_partial_messages=True,            # Stream partial content blocks to TUI

    # Observability hooks (logging/metrics — NOT security)
    hooks={
        "PreToolUse": [HookMatcher(matcher="Bash", hooks=[log_tool_use])],
        "PostToolUse": [HookMatcher(matcher="*", hooks=[track_metrics])],
    },

    # === Fields available but NOT used in v1 ===

    # settings={"key": "val"},               # Override settings dict
    # add_dirs=["/extra/dir"],                # Additional directories
    # env={"VAR": "val"},                     # Extra env vars for the agent process
    # extra_args=["--flag"],                  # CLI passthrough args
    # user="user-id",                         # User identifier
    # permission_prompt_tool_name="...",      # Custom permission prompt tool
    # debug_stderr=False,                     # Debug stderr output
)
```

**IMPORTANT — Fields that DO NOT exist** (removed from previous draft):
- ~~`fallback_model`~~ — No auto-fallback; handle model errors in orchestrator
- ~~`max_budget_usd`~~ — Budget tracking is manual via `ResultMessage.total_cost_usd`
- ~~`max_thinking_tokens`~~ — Not exposed in SDK
- ~~`agents`~~ — No subagent parameter; each agent is a separate `query()` call
- ~~`fork_session`~~ — Not a real field
- ~~`setting_sources`~~ — Not a real field; settings loaded from environment
- ~~`output_format` / `json_schema`~~ — Enforce structured output via system prompt + Pydantic
- ~~`enable_file_checkpointing`~~ — Not a real field
- ~~`betas`~~ — Not a real field
- ~~`sandbox`~~ — Not a real field

**Message type system**:
```
Message = UserMessage | AssistantMessage | SystemMessage | ResultMessage | StreamEvent

AssistantMessage.content: list[ContentBlock]
ContentBlock = TextBlock | ThinkingBlock | ToolUseBlock | ToolResultBlock

ResultMessage: session_id, total_cost_usd, duration_ms, num_turns, usage, is_error, result

StreamEvent: uuid, session_id, event (untyped dict — inspect at runtime), parent_tool_use_id
```

**Manual budget tracking** (since `max_budget_usd` does not exist):
```python
total_cost = 0.0
budget_limit = 2.00  # configurable per agent role

async for msg in query(prompt=prompt, options=options):
    if isinstance(msg, ResultMessage):
        total_cost += msg.total_cost_usd or 0.0
        if total_cost > budget_limit:
            logger.warning(f"Budget exceeded: ${total_cost:.4f} > ${budget_limit}")
            # Cancel agent, emit CostUpdate event to TUI
            break
```

### Textual v7.0.0

**Installed**: v7.0.0 — latest stable
**Key capabilities**:
- **Reactive attributes**: `reactive()` with `watch_*` methods — auto-refresh UI on state change
- **Workers**: `@work` decorator, `run_worker()` — async background tasks that don't block UI
- **CSS styling**: Full TCSS (Textual CSS) system with selectors, pseudo-classes, animations
- **Widgets**: DataTable, RichLog, Tree, Input, Tabs/TabbedContent, ProgressBar, Digits, Static, Markdown
- **Layout**: Horizontal, Vertical, Grid, Dock, VerticalScroll, HorizontalScroll
- **Events**: Key bindings, mouse, focus, custom messages
- **Command palette**: Built-in fuzzy command search (Ctrl+P)
- **Themes**: Built-in dark/light themes

**Critical pattern for our use case** — streaming SDK output to TUI:
```python
@work(exclusive=True)
async def stream_agent(self, agent_name: str, prompt: str, options: ClaudeCodeOptions) -> None:
    """Background worker that streams agent output to a RichLog widget."""
    log = self.query_one(f"#agent-{agent_name}", RichLog)
    total_cost = 0.0
    async for message in query(prompt=prompt, options=options):
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, TextBlock):
                    log.write(block.text)  # Real-time update
                elif isinstance(block, ToolUseBlock):
                    log.write(f"[tool]{block.name}[/tool]")
        elif isinstance(message, ResultMessage):
            total_cost += message.total_cost_usd or 0.0
            self.post_message(CostUpdate(agent_name, total_cost))
            self.notify(f"Agent {agent_name} complete: ${total_cost:.4f}")
```

### Existing Codebase Assessment

| Component | Current State | Reuse? | Transform To |
|-----------|--------------|--------|-------------|
| `agent.py` | Sequential 4-phase orchestrator | Refactor | Agent registry + phase pipeline |
| `client.py` | `query()` wrapper with security | Refactor | Multi-client manager |
| `progress.py` | JSON file tracking | Keep + extend | Add SQLite backend |
| `researcher.py` | Web research with Firecrawl | Keep | Integrate as research agent |
| `security.py` | Bash allowlisting | Keep | Wire into SDK hooks properly |
| `prompts.py` | Template loading | Keep | Add agent-specific prompts |
| `prompts/` | 4 phase prompts | Keep + extend | Add orchestrator prompts |

---

## 3. System Architecture

### 3.1 High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                          TUI LAYER (Textual v7)                     │
│  ┌──────────┐ ┌──────────────┐ ┌──────────┐ ┌────────────────────┐ │
│  │ Agent    │ │ Streaming    │ │ Progress │ │ Cost / Session     │ │
│  │ Registry │ │ Log Panels   │ │ Tracker  │ │ Dashboard          │ │
│  │ (Tree)   │ │ (RichLog x N)│ │ (Table)  │ │ (Digits + Bars)    │ │
│  └────┬─────┘ └──────┬───────┘ └────┬─────┘ └────────┬───────────┘ │
│       │              │              │                 │             │
│       └──────────────┴──────────────┴─────────────────┘             │
│                              │                                      │
│                    ┌─────────▼──────────┐                           │
│                    │  Event Bus (Textual │                           │
│                    │  Messages + Reactive│                           │
│                    │  Attributes)        │                           │
│                    └─────────┬──────────┘                           │
├──────────────────────────────┼──────────────────────────────────────┤
│                    ORCHESTRATION LAYER                               │
│  ┌─────────────────┐  ┌─────┴─────┐  ┌──────────────────────────┐  │
│  │ Agent Manager   │  │ Phase     │  │ Worker Pool              │  │
│  │ (create, track, │  │ Pipeline  │  │ (Textual @work workers   │  │
│  │  cancel agents) │  │ (R→E→P→C) │  │  one per active agent)   │  │
│  └────────┬────────┘  └─────┬─────┘  └────────────┬─────────────┘  │
│           │                 │                      │                │
│           └─────────────────┴──────────────────────┘                │
│                              │                                      │
├──────────────────────────────┼──────────────────────────────────────┤
│                    SDK LAYER (claude-code-sdk v0.0.25)               │
│  ┌───────────────┐  ┌───────┴──────┐  ┌───────────────────────┐    │
│  │ query()       │  │ query() +    │  │ Custom MCP Tools      │    │
│  │ (one-off)     │  │ resume=id    │  │ (MCP server configs)  │    │
│  │               │  │ (multi-turn) │  │                       │    │
│  └───────┬───────┘  └──────┬───────┘  └───────────┬───────────┘    │
│          │                 │                      │                │
│          └─────────────────┴──────────────────────┘                │
│                              │                                      │
│  ┌──────────────────────────┴──────────────────────────────────┐   │
│  │ ClaudeCodeOptions                                          │   │
│  │ (model, tools, can_use_tool, hooks, MCP servers,           │   │
│  │  permission_mode, max_turns, session resume, streaming)     │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                              │                                      │
├──────────────────────────────┼──────────────────────────────────────┤
│                    PERSISTENCE LAYER                                │
│  ┌────────────────┐  ┌──────┴──────┐  ┌──────────────────────────┐ │
│  │ SQLite + FTS5  │  │ JSON State  │  │ File System              │ │
│  │ (memory, logs, │  │ (progress,  │  │ (.autonomous-coder/      │ │
│  │  conversations)│  │  features)  │  │  plans, checkpoints)     │ │
│  └────────────────┘  └─────────────┘  └──────────────────────────┘ │
├──────────────────────────────────────────────────────────────────────┤
│                    EXTERNAL SERVICES                                │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ │
│  │ Serena   │ │ Context7 │ │Firecrawl │ │Sequential│ │ Custom   │ │
│  │ MCP      │ │ MCP      │ │ MCP      │ │ Thinking │ │ MCP      │ │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘ └──────────┘ │
└─────────────────────────────────────────────────────────────────────┘
```

### 3.2 TUI Layout Design

```
┌─────────────────────────────────────────────────────────────────────┐
│ [Header] Autonomous Coder v2.0  │ Model: sonnet-4.5 │ $0.1234 │ ⏱ │
├────────────────┬────────────────────────────────────────────────────┤
│ AGENTS         │ ACTIVE AGENT OUTPUT                    [Tabs]      │
│ ┌────────────┐ │ ┌─[Research]──[Explore]──[Plan]──[Code]─────────┐ │
│ │ ▶ Research │ │ │                                                │ │
│ │   Explore  │ │ │  Streaming output from the currently           │ │
│ │   Planner  │ │ │  selected agent appears here in real-time.     │ │
│ │   Coder    │ │ │                                                │ │
│ │ ──────────│ │ │  [Tool: Bash] Running: npm install...          │ │
│ │ Subagents: │ │ │  [Tool: Write] Created: src/auth.ts           │ │
│ │   reviewer │ │ │  [Tool: Read] Reading: package.json           │ │
│ │   tester   │ │ │                                                │ │
│ │            │ │ │  Claude: I've implemented the authentication   │ │
│ │            │ │ │  module with JWT tokens...                     │ │
│ │            │ │ │                                                │ │
│ └────────────┘ │ └────────────────────────────────────────────────┘ │
├────────────────┼────────────────────────────────────────────────────┤
│ PROGRESS       │ TASK DETAILS                                      │
│ ┌────────────┐ │ ┌──────────────────────────────────────────────┐  │
│ │ Phase: Code│ │ │ Task 3/7: Add JWT middleware                 │  │
│ │ ████░░ 43% │ │ │ Status: In Progress                         │  │
│ │            │ │ │ Files: src/middleware/auth.ts                 │  │
│ │ Tasks:     │ │ │ Dependencies: [1, 2] ✓                       │  │
│ │ ✓ 1. Setup │ │ │ Estimated cost: $0.05                        │  │
│ │ ✓ 2. Models│ │ │                                              │  │
│ │ ▶ 3. Auth  │ │ │ Git: 2 commits (a1b2c3d, e4f5g6h)           │  │
│ │ ○ 4. Routes│ │ └──────────────────────────────────────────────┘  │
│ │ ○ 5. Tests │ │                                                   │
│ └────────────┘ │                                                   │
├────────────────┴────────────────────────────────────────────────────┤
│ [Footer] ⌨ q:Quit │ p:Pause │ r:Resume │ c:Cancel │ /:Command    │
└─────────────────────────────────────────────────────────────────────┘
```

### 3.3 Component Specifications

#### A. `app.py` — Main Textual Application

```python
class AutonomousCoderApp(App):
    """Main TUI application."""

    CSS_PATH = "styles.tcss"
    BINDINGS = [
        ("q", "quit", "Quit"),
        ("p", "pause", "Pause"),
        ("r", "resume", "Resume"),
        ("c", "cancel_agent", "Cancel"),
        ("slash", "command_palette", "Command"),
        ("tab", "cycle_agents", "Next Agent"),
    ]

    # Reactive state — auto-updates UI
    current_phase = reactive("idle")
    total_cost = reactive(0.0)
    active_agents = reactive(0)
    progress_pct = reactive(0.0)

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal():
            yield AgentTree(id="agent-tree")        # Left sidebar
            with Vertical(id="main-area"):
                yield AgentTabs(id="agent-tabs")    # Tabbed agent output
                with Horizontal(id="bottom-area"):
                    yield ProgressPanel(id="progress")
                    yield TaskDetail(id="task-detail")
        yield Footer()
```

#### B. `orchestrator.py` — Agent Orchestration Engine

```python
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Protocol

# --- Inter-phase data handoff ---

@dataclass
class PhaseContext:
    phase_name: str
    input_data: dict[str, Any]  # output from previous phase
    config: PhaseConfig
    budget_remaining: float

@dataclass
class PhaseResult:
    phase_name: str
    output_data: dict[str, Any]
    cost_incurred: float
    duration_seconds: float
    success: bool
    error: str | None = None

class PhaseRunner(Protocol):
    """Each phase implements this interface."""
    async def run(self, context: PhaseContext) -> PhaseResult: ...

# --- Textual message types (replaces custom EventBus) ---

class AgentStarted(Message):
    def __init__(self, agent_name: str, phase: str) -> None:
        self.agent_name = agent_name
        self.phase = phase
        super().__init__()

class AgentOutput(Message):
    def __init__(self, agent_name: str, content: str, block_type: str = "text") -> None:
        self.agent_name = agent_name
        self.content = content
        self.block_type = block_type
        super().__init__()

class AgentCompleted(Message):
    def __init__(self, agent_name: str, result: PhaseResult) -> None:
        self.agent_name = agent_name
        self.result = result
        super().__init__()

class AgentError(Message):
    def __init__(self, agent_name: str, error: str) -> None:
        self.agent_name = agent_name
        self.error = error
        super().__init__()

class CostUpdate(Message):
    def __init__(self, agent_name: str, total_cost: float) -> None:
        self.agent_name = agent_name
        self.total_cost = total_cost
        super().__init__()

class SecurityBlock(Message):
    def __init__(self, agent_name: str, tool: str, reason: str) -> None:
        self.agent_name = agent_name
        self.tool = tool
        self.reason = reason
        super().__init__()

# --- Orchestrator ---

class AgentOrchestrator:
    """Manages the lifecycle of sequential phase agents."""

    def __init__(self, app: AutonomousCoderApp, config: OrchestratorConfig):
        self.app = app
        self.config = config
        self.agents: dict[str, AgentInstance] = {}
        self.phase_runners: list[PhaseRunner] = []
        self.total_cost: float = 0.0
        self.budget_limit: float = config.total_budget

    async def start(self, task: str) -> None:
        """Run phases sequentially, passing output forward."""
        context = PhaseContext(
            phase_name="init",
            input_data={"task": task},
            config=self.config.phases[0],
            budget_remaining=self.budget_limit,
        )
        for phase_runner in self.phase_runners:
            self.app.post_message(PhaseStarted(context.phase_name))
            result = await phase_runner.run(context)
            self.total_cost += result.cost_incurred
            self.app.post_message(PhaseCompleted(result))

            if not result.success:
                self.app.post_message(AgentError(context.phase_name, result.error or "Unknown"))
                break

            # Chain output → next phase input
            next_phase_idx = self.phase_runners.index(phase_runner) + 1
            if next_phase_idx < len(self.phase_runners):
                context = PhaseContext(
                    phase_name=self.config.phases[next_phase_idx].name,
                    input_data=result.output_data,
                    config=self.config.phases[next_phase_idx],
                    budget_remaining=self.budget_limit - self.total_cost,
                )

    async def stream_agent(self, agent: AgentInstance, prompt: str):
        """Stream agent output to TUI via Textual messages."""
        agent_cost = 0.0
        async for message in query(prompt=prompt, options=agent.options):
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock):
                        self.app.post_message(AgentOutput(agent.name, block.text, "text"))
                    elif isinstance(block, ToolUseBlock):
                        self.app.post_message(AgentOutput(agent.name, block.name, "tool"))
            elif isinstance(message, ResultMessage):
                agent_cost += message.total_cost_usd or 0.0
                self.total_cost += message.total_cost_usd or 0.0
                self.app.post_message(CostUpdate(agent.name, self.total_cost))
                if self.total_cost > self.budget_limit:
                    self.app.post_message(AgentError(agent.name, f"Budget exceeded: ${self.total_cost:.2f}"))
                    break
```

**Structured output enforcement** (since `output_format` does not exist):
Each phase's system prompt includes JSON format instructions with examples. Phase runner validates output with Pydantic:
```python
# In system prompt: "Return your findings as JSON: {\"files\": [...], \"summary\": \"...\"}"
# In phase runner:
raw_output = result_message.result  # string from final ResultMessage
try:
    validated = PhaseOutputModel.model_validate_json(raw_output)
except ValidationError:
    # Fall back to extracting JSON from markdown code blocks
    validated = extract_json_from_response(raw_output, PhaseOutputModel)
```

#### C. `agent_instance.py` — Individual Agent Wrapper

```python
@dataclass
class AgentInstance:
    """Represents a running agent with its configuration and state."""

    name: str
    role: str  # research, explore, plan, code, review
    options: ClaudeCodeOptions
    session_id: str | None = None
    status: AgentStatus = AgentStatus.IDLE
    cost: float = 0.0
    turns: int = 0
    started_at: datetime | None = None

    def get_options(self) -> ClaudeCodeOptions:
        """Build options with agent-specific configuration."""
        return ClaudeCodeOptions(
            model=self.model_for_role(),
            system_prompt=self.system_prompt(),
            allowed_tools=self.tools_for_role(),
            mcp_servers=self.mcp_for_role(),
            max_turns=self.max_turns_for_role(),
            can_use_tool=self.security_callback(),
            permission_mode="acceptEdits",
            cwd=str(self.project_path),
            include_partial_messages=True,
            hooks={
                "PreToolUse": [HookMatcher(matcher="*", hooks=[self.log_tool_use])],
            },
        )
```

#### D. `widgets/` — Custom Textual Widgets

| Widget | Purpose | Data Source |
|--------|---------|-------------|
| `AgentTree` | Sidebar tree of agents with status icons | `orchestrator.agents` |
| `AgentTabs` | Tabbed RichLog panels per agent | Agent stream events |
| `ProgressPanel` | Phase indicator + task progress bar | `progress_tracker` |
| `TaskDetail` | Current task info, files, deps, cost | `progress_tracker` |
| `CostDisplay` | Real-time cost in Digits widget | `ResultMessage.total_cost_usd` |
| `StreamingLog` | Rich-formatted agent output log | `AssistantMessage.content` |

#### E. `memory.py` — SQLite Persistence Layer

```python
class AgentMemory:
    """SQLite + FTS5 memory for agent conversations and context."""

    def __init__(self, db_path: Path):
        self.db = sqlite3.connect(str(db_path))
        self._init_schema()

    def _init_schema(self):
        self.db.execute("PRAGMA journal_mode=WAL")  # Safe concurrent reads from TUI workers
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY,
                session_id TEXT NOT NULL,
                agent_name TEXT NOT NULL,
                role TEXT,  -- user, assistant, system
                content TEXT NOT NULL,
                cost_usd REAL DEFAULT 0,
                tokens_in INTEGER DEFAULT 0,
                tokens_out INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE VIRTUAL TABLE IF NOT EXISTS conversations_fts
            USING fts5(content, agent_name, session_id, content=conversations, content_rowid=id);

            -- FTS5 sync triggers (keep full-text index in sync with conversations table)
            CREATE TRIGGER IF NOT EXISTS conversations_ai AFTER INSERT ON conversations BEGIN
                INSERT INTO conversations_fts(rowid, content, agent_name, session_id)
                VALUES (new.id, new.content, new.agent_name, new.session_id);
            END;
            CREATE TRIGGER IF NOT EXISTS conversations_ad AFTER DELETE ON conversations BEGIN
                INSERT INTO conversations_fts(conversations_fts, rowid, content, agent_name, session_id)
                VALUES ('delete', old.id, old.content, old.agent_name, old.session_id);
            END;
            CREATE TRIGGER IF NOT EXISTS conversations_au AFTER UPDATE ON conversations BEGIN
                INSERT INTO conversations_fts(conversations_fts, rowid, content, agent_name, session_id)
                VALUES ('delete', old.id, old.content, old.agent_name, old.session_id);
                INSERT INTO conversations_fts(rowid, content, agent_name, session_id)
                VALUES (new.id, new.content, new.agent_name, new.session_id);
            END;

            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY,
                session_id TEXT,
                title TEXT NOT NULL,
                status TEXT DEFAULT 'pending',
                phase TEXT,
                dependencies TEXT,  -- JSON array
                commit_hash TEXT,
                started_at TIMESTAMP,
                completed_at TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                task_description TEXT,
                status TEXT DEFAULT 'active',
                total_cost REAL DEFAULT 0,
                total_turns INTEGER DEFAULT 0,
                started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP
            );
        """)

    def search(self, query: str, limit: int = 20) -> list[dict]:
        """Full-text search across conversations."""
        return self.db.execute(
            "SELECT * FROM conversations_fts WHERE conversations_fts MATCH ? LIMIT ?",
            (query, limit)
        ).fetchall()

    def get_context_for_agent(self, agent_name: str, limit: int = 50) -> list[dict]:
        """Get recent context for an agent."""
        return self.db.execute(
            "SELECT * FROM conversations WHERE agent_name = ? ORDER BY created_at DESC LIMIT ?",
            (agent_name, limit)
        ).fetchall()
```

---

## 4. Data Flow

### 4.1 SDK Message → TUI Widget Flow

```
SDK query() with ClaudeCodeOptions
    │
    ▼ async for message in ...
    │
    ├── SystemMessage (subtype='init')
    │   └── Extract: session_id, plugins, commands
    │       └── Update: AgentTree status, session display
    │
    ├── AssistantMessage
    │   ├── TextBlock
    │   │   └── post_message(AgentOutput(name, text, "text"))
    │   ├── ThinkingBlock
    │   │   └── post_message(AgentOutput(name, thinking, "thinking"))
    │   ├── ToolUseBlock
    │   │   └── post_message(AgentOutput(name, tool_name, "tool"))
    │   │       └── TaskDetail.update_current_tool(block.name)
    │   └── ToolResultBlock
    │       └── post_message(AgentOutput(name, result_summary, "result"))
    │
    ├── ResultMessage
    │   └── Extract: cost (total_cost_usd), duration_ms, num_turns, session_id, result
    │       ├── post_message(CostUpdate(name, accumulated_cost))
    │       ├── post_message(AgentCompleted(name, phase_result))
    │       └── Memory.save_session_result()
    │
    └── StreamEvent (if include_partial_messages=True)
        └── event dict inspected at runtime (uuid, session_id, parent_tool_use_id)
            └── post_message(AgentOutput(name, partial_text, "partial"))
```

### 4.2 Agent Lifecycle Flow

```
User Input (task description)
    │
    ▼
Orchestrator.start(task)
    │
    ├── Phase 1: RESEARCH
    │   ├── Spawn: ResearchAgent (query() — one-off, no state needed)
    │   ├── MCP: Firecrawl (web search), Context7 (library docs)
    │   ├── Output: PhaseResult with recommendations, library docs, skills
    │   └── Worker: @work(exclusive=True, name="research")
    │
    ├── Phase 2: EXPLORE
    │   ├── Spawn: ExplorerAgent (query() with Serena MCP)
    │   ├── MCP: Serena (AST analysis, symbols, references)
    │   ├── Input: PhaseContext from Research output
    │   ├── Output: PhaseResult with codebase map, relevant files, architecture
    │   └── Worker: @work(exclusive=True, name="explore")
    │
    ├── Phase 3: PLAN
    │   ├── Spawn: PlannerAgent (query() with sequential-thinking)
    │   ├── Input: PhaseContext from Research + Exploration results
    │   ├── Output: PhaseResult with task list, dependencies, files, estimates
    │   └── Worker: @work(exclusive=True, name="plan")
    │
    └── Phase 4: CODE (sequential task execution — v1)
        ├── Spawn: CoderAgent (query() per task — sequential, not parallel)
        ├── Review: Separate query() call with reviewer system prompt after each task
        ├── MCP: All servers available
        ├── Output: PhaseResult with file changes, commits, verification
        └── Worker: @work(exclusive=True, name="code")
        │
        NOTE: Parallel code agents deferred to v2 (requires file-level
        locking and agent-to-file assignment to prevent conflicts)
```

---

## 5. SDK Integration Patterns

### 5.1 Agent Factory

Each agent role gets its own `ClaudeCodeOptions` instance. There is NO `agents` parameter — subagents are separate `query()` calls.

```python
from claude_code_sdk import ClaudeCodeOptions, query
from claude_code_sdk._internal.hooks import HookMatcher

class AgentFactory:
    """Creates configured ClaudeCodeOptions for each agent role."""

    BASE_MCP = {
        "serena": {"command": "uvx", "args": ["serena"], "env": {...}},
        "sequential-thinking": {"command": "npx", "args": ["-y", "@modelcontextprotocol/server-sequential-thinking"]},
        "Context7": {"command": "npx", "args": ["-y", "@upstash/context7-mcp"]},
        "firecrawl-mcp": {"command": "npx", "args": ["-y", "firecrawl-mcp"], "env": {...}},
    }

    ROLE_CONFIG = {
        "research": {
            "model": "claude-sonnet-4-5-20250514",
            "tools": ["WebSearch", "WebFetch", "Read", "Grep", "Glob"],
            "mcp": ["firecrawl-mcp", "Context7"],
            "budget_limit": 0.50,  # Manual tracking, not an SDK field
            "max_turns": 15,
        },
        "explore": {
            "model": "claude-sonnet-4-5-20250514",
            "tools": ["Read", "Grep", "Glob", "mcp__serena__*"],
            "mcp": ["serena"],
            "budget_limit": 0.50,
            "max_turns": 20,
        },
        "plan": {
            "model": "claude-opus-4-6-20250605",
            "tools": ["Read", "Grep", "Glob", "mcp__sequential-thinking__*"],
            "mcp": ["sequential-thinking", "serena"],
            "budget_limit": 1.00,
            "max_turns": 10,
        },
        "code": {
            "model": "claude-sonnet-4-5-20250514",
            "tools": ["Read", "Write", "Edit", "Bash", "Grep", "Glob"],
            "mcp": ["serena", "Context7"],
            "budget_limit": 2.00,
            "max_turns": 30,
        },
        # Reviewer and tester are separate query() calls, NOT subagents
        "reviewer": {
            "model": "claude-sonnet-4-5-20250514",
            "tools": ["Read", "Grep", "Glob"],
            "mcp": ["serena"],
            "budget_limit": 0.25,
            "max_turns": 10,
        },
    }

    def create_options(self, role: str, project_path: Path, security_callback) -> ClaudeCodeOptions:
        """Build ClaudeCodeOptions for a specific agent role."""
        config = self.ROLE_CONFIG[role]
        return ClaudeCodeOptions(
            model=config["model"],
            allowed_tools=config["tools"],
            mcp_servers=[self.BASE_MCP[k] for k in config["mcp"]],
            max_turns=config["max_turns"],
            cwd=str(project_path),
            permission_mode="acceptEdits",
            can_use_tool=security_callback,  # Real security via callback
            include_partial_messages=True,
            hooks={
                "PreToolUse": [HookMatcher(matcher="*", hooks=[log_tool_use_hook])],
            },
        )

    def get_budget_limit(self, role: str) -> float:
        """Get manual budget limit for a role (NOT an SDK field)."""
        return self.ROLE_CONFIG[role]["budget_limit"]


# --- Usage: each agent = separate query() call ---

factory = AgentFactory()

# Research agent
research_options = factory.create_options("research", project_path, security_callback)
research_budget = factory.get_budget_limit("research")
research_cost = 0.0

async for msg in query(prompt=research_prompt, options=research_options):
    if isinstance(msg, ResultMessage):
        research_cost += msg.total_cost_usd or 0.0
        if research_cost > research_budget:
            break  # Budget exceeded — stop agent

# Code agent, then reviewer as separate call (NOT a subagent parameter)
code_options = factory.create_options("code", project_path, security_callback)
async for msg in query(prompt=code_prompt, options=code_options):
    ...

# Review is a completely separate query() call
reviewer_options = factory.create_options("reviewer", project_path, security_callback)
async for msg in query(prompt=f"Review these changes: {code_output}", options=reviewer_options):
    ...
```

### 5.2 Security Integration (Correct SDK Pattern)

The existing codebase does client-side bash validation which doesn't actually prevent execution. The SDK provides TWO mechanisms with distinct purposes:

**1. `can_use_tool` callback — PRIMARY security mechanism (blocks tool execution)**

```python
from claude_code_sdk import (
    ClaudeCodeOptions,
    PermissionResultAllow,
    PermissionResultDeny,
    ToolPermissionContext,
)

async def security_callback(
    tool_name: str,
    tool_input: dict,
    ctx: ToolPermissionContext,
) -> PermissionResultAllow | PermissionResultDeny:
    """Called BEFORE every tool execution. Return Allow or Deny."""

    if tool_name == "Bash":
        command = tool_input.get("command", "")
        is_allowed, reason = is_command_allowed(command)  # Existing security.py logic
        if not is_allowed:
            return PermissionResultDeny(
                behavior="deny",
                message=f"Blocked: {reason}",
                interrupt=False,  # Don't kill the agent, just deny this tool
            )

    if tool_name == "Write":
        path = tool_input.get("file_path", "")
        if is_protected_path(path):
            return PermissionResultDeny(
                behavior="deny",
                message=f"Protected path: {path}",
                interrupt=False,
            )

    return PermissionResultAllow(
        behavior="allow",
        updated_input=None,       # Can modify tool input before execution
        updated_permissions=None,  # Can modify permissions for future calls
    )

# Wire into ClaudeCodeOptions:
options = ClaudeCodeOptions(
    can_use_tool=security_callback,  # Called for EVERY tool use
    ...
)
```

**2. `hooks` — OBSERVABILITY only (logging, metrics, TUI updates)**

Hooks are for monitoring, NOT security enforcement. Use them to feed the TUI with real-time tool activity.

```python
async def log_tool_use_hook(
    input_data: dict,
    tool_use_id: str | None,
    context: HookContext,
) -> dict:
    """PreToolUse hook — logs tool activity to TUI (does NOT enforce security)."""
    tool_name = input_data.get("tool_name", "unknown")
    # Post to TUI for display
    app.post_message(AgentOutput(agent_name, f"Using: {tool_name}", "tool"))
    return {}  # Empty dict = allow (hooks should NOT block; use can_use_tool for that)

async def track_metrics_hook(
    input_data: dict,
    tool_use_id: str | None,
    context: HookContext,
) -> dict:
    """PostToolUse hook — tracks tool execution metrics."""
    tool_name = input_data.get("tool_name", "unknown")
    duration = input_data.get("duration_ms", 0)
    metrics_collector.record(tool_name, duration)
    return {}

# Wire into ClaudeCodeOptions:
options = ClaudeCodeOptions(
    hooks={
        "PreToolUse": [HookMatcher(matcher="*", hooks=[log_tool_use_hook])],
        "PostToolUse": [HookMatcher(matcher="*", hooks=[track_metrics_hook])],
    },
    ...
)
```

**Migration path from existing `security.py`**:
The existing `is_command_allowed()` function in `security.py` is reused as-is inside the `can_use_tool` callback. This moves enforcement from client-side (bypassable) to SDK-level (enforced before tool execution).

---

## 6. File Structure (Target)

```
autonomous-coder/
├── app.py                    # Textual App entry point
├── styles.tcss               # TUI CSS styling (Phase 3 deliverable — placeholder in Phase 1)
├── orchestrator.py            # Agent orchestration engine + PhaseRunner protocol
├── agent_factory.py           # Agent configuration factory (ClaudeCodeOptions per role)
├── agent_instance.py          # Agent instance dataclass + budget tracking
├── messages.py                # Textual Message subclasses (replaces custom EventBus)
├── memory.py                  # SQLite + FTS5 persistence (WAL mode)
├── widgets/
│   ├── __init__.py
│   ├── agent_tree.py          # Agent sidebar tree
│   ├── agent_tabs.py          # Tabbed agent output panels
│   ├── streaming_log.py       # Rich-formatted streaming log
│   ├── progress_panel.py      # Phase + task progress
│   ├── task_detail.py         # Current task info
│   └── cost_display.py        # Real-time cost tracking (manual budget accumulation)
├── agents/                    # Agent role configurations
│   ├── __init__.py
│   ├── research.py            # Research agent (refactored from researcher.py)
│   ├── explorer.py            # Explorer agent
│   ├── planner.py             # Planner agent
│   └── coder.py               # Coder agent (reviewer = separate query() call, not subagent)
├── prompts/                   # (existing, extended)
│   ├── researcher_prompt.md
│   ├── explorer_prompt.md
│   ├── planner_prompt.md
│   ├── coder_prompt.md
│   └── orchestrator_prompt.md # NEW
├── client.py                  # (refactored) SDK client utilities
├── progress.py                # (refactored) Progress tracking
├── security.py                # (kept) Reused inside can_use_tool callback
├── config.py                  # NEW: Orchestrator configuration + budget limits
├── __init__.py                # (updated) Package exports
├── __main__.py                # NEW: python -m autonomous_coder (delegates to app.py)
│                              # NOTE: existing agent.py remains as legacy CLI entry point
│                              # until TUI is stable, then agent.py becomes a thin wrapper
├── commands/
│   └── autonomous-code.md     # (existing) Slash command
├── plans/                     # Plan documents
└── .autonomous-coder/         # Runtime state
    ├── memory.db              # SQLite database (WAL mode)
    ├── progress.json          # Current progress state
    └── feature_list.json      # Task tracking
```

---

## 7. Implementation Plan

### Phase 1: Foundation (Core Framework)
**Files**: `app.py`, `styles.tcss` (placeholder), `widgets/`, `messages.py`, `__main__.py`, `config.py`
- Textual App skeleton with layout
- All custom widgets (initially with mock data)
- Textual Message subclasses (AgentStarted, AgentOutput, AgentCompleted, CostUpdate, SecurityBlock, etc.)
- CSS styling placeholder (full styling is Phase 3 deliverable)
- Key bindings and command palette
- Entry point: `python -m autonomous_coder` (coexists with existing `agent.py`)

### Phase 2: SDK Integration (Agent Engine)
**Files**: `orchestrator.py`, `agent_factory.py`, `agent_instance.py`
- Agent factory creating `ClaudeCodeOptions` per role (no `agents` parameter)
- Orchestrator with PhaseRunner protocol and sequential phase pipeline
- PhaseContext/PhaseResult dataclasses for inter-phase data handoff
- `can_use_tool` callback as primary security mechanism (reusing `security.py`)
- Hooks for observability only (logging tool calls to TUI, tracking metrics)
- Manual budget tracking via `ResultMessage.total_cost_usd` accumulation
- Structured output enforcement via system prompt + Pydantic validation
- Worker management (spawn, track, cancel)

### Phase 3: Persistence (Memory + State)
**Files**: `memory.py`, `progress.py` (refactored), `styles.tcss` (full styling)
- SQLite schema with WAL mode and FTS5 + sync triggers
- Conversation logging from agent streams
- Session management (save, resume via `resume=session_id`)
- Cost tracking aggregation across phases
- Full TCSS styling for the TUI layout

### Phase 4: Agent Refactoring
**Files**: `agents/`, `client.py` (refactored), `prompts/`
- Refactor existing agent logic into role-specific PhaseRunner implementations
- Proper `ClaudeCodeOptions` per role (model, tools, MCP, budget limits)
- Review agent as separate `query()` call (not a subagent parameter)
- System prompt composition per phase with JSON output examples

### Phase 5: Polish & Integration
- Error recovery and retry logic
- Agent cancellation and pause/resume
- Session resumption from SQLite via `resume=session_id`
- Cost budget warnings and configurable limits per role
- Theme customization
- Migration: `agent.py` becomes thin wrapper delegating to TUI app

---

## 8. Risk Analysis

| Risk | Impact | Mitigation |
|------|--------|------------|
| SDK streaming may not support partial messages well | Laggy UI | Use `include_partial_messages=True`, fall back to complete messages |
| Multiple concurrent `query()` calls may hit rate limits | Agent failures | Stagger with semaphore, sequential phases in v1 (parallel deferred to v2) |
| Textual worker exceptions kill the app | Crash | Wrap all workers in try/except, emit AgentError messages to log |
| SQLite concurrent writes from multiple workers | Data corruption | Use WAL mode (`PRAGMA journal_mode=WAL`), single writer thread with queue |
| MCP server startup latency (npx downloads) | Slow start | Pre-warm MCP servers, show loading indicators |
| No SDK budget enforcement (`max_budget_usd` doesn't exist) | Cost overrun | Manual tracking via `ResultMessage.total_cost_usd` accumulation with configurable limits |
| No structured output format (`output_format` doesn't exist) | Parse failures | Enforce via system prompt with JSON examples + Pydantic validation with fallback extraction |
| `can_use_tool` callback errors crash the agent | Security bypass | Wrap callback in try/except, deny on error (fail-closed) |

---

## 9. Unresolved Questions

1. **~~Parallel coding agents~~** (RESOLVED): Sequential execution for v1. Parallel with file-level locking deferred to v2. Simplest approach avoids file conflicts and is easier to debug.

2. **Session persistence granularity**: Should we persist every message to SQLite in real-time, or batch at the end of each agent run? Real-time is more resilient but adds I/O overhead. WAL mode mitigates write contention.

3. **Budget allocation**: Should the total budget be split evenly across phases, or should later phases (code) get more? Suggested split: Research 10%, Explore 10%, Plan 15%, Code 65%. Budget enforcement is manual via `ResultMessage.total_cost_usd`.

4. **~~Subagent visibility~~** (RESOLVED): Reviewer output appears as a separate tab since it's a separate `query()` call, not a nested subagent. Each agent gets its own tab in the TUI.

5. **Structured output reliability**: System prompt + Pydantic validation may fail on complex outputs. Need a robust fallback strategy (regex extraction from markdown code blocks, retry with simpler prompt).

6. **`can_use_tool` error handling**: If the security callback itself throws an exception, should the agent be killed or should the tool be denied? Recommend fail-closed (deny on error).

---

## 10. RALPLAN-DR Summary

### Principles
1. **SDK fidelity**: Every code sample uses ONLY verified `ClaudeCodeOptions` fields from v0.0.25
2. **Separation of concerns**: `can_use_tool` for security, `hooks` for observability, Textual messages for UI updates
3. **Sequential-first**: v1 uses sequential phase execution; parallel is a v2 enhancement
4. **Manual over phantom**: Budget tracking, structured output, and model fallback are all handled in application code, not phantom SDK fields
5. **Composable phases**: PhaseRunner protocol allows adding/reordering phases without touching the orchestrator

### Decision Drivers
1. **Correctness**: Must use only real SDK API surface — no fabricated fields
2. **Simplicity**: Sequential phases, Textual built-in message system, manual budget tracking
3. **Observability**: Every agent action visible in TUI via Textual Message subclasses

### Viable Options

**Option A: Monolithic Orchestrator (CHOSEN)**
- Single `AgentOrchestrator` class with internal `PhaseRunner` protocol
- Phases run sequentially, each getting a `PhaseContext` from the previous
- Budget tracked manually via `ResultMessage.total_cost_usd` accumulation
- Pros: Simple, debuggable, no coordination overhead, correct SDK usage
- Cons: No parallel phases, single point of failure

**Option B: Distributed Agent Mesh**
- Each phase is an independent service/process communicating via message queue
- Pros: True parallelism, fault isolation, horizontal scaling
- Cons: Massive complexity for a TUI app, overkill for 4 sequential phases
- INVALIDATED: Complexity far exceeds benefit for a local TUI tool with 4 phases

### ADR: Architecture Decision Record

- **Decision**: Monolithic orchestrator with PhaseRunner protocol, sequential execution, manual budget tracking
- **Drivers**: SDK API reality (no `agents` param, no `max_budget_usd`), simplicity, debuggability
- **Alternatives considered**: Distributed agent mesh (invalidated — overkill), parallel phase execution (deferred to v2)
- **Why chosen**: Matches actual SDK capabilities, minimizes moving parts, allows incremental enhancement
- **Consequences**: v1 is sequential (slower for large tasks), budget enforcement is best-effort (checked between turns, not mid-turn)
- **Follow-ups**: v2 adds parallel code agents with file locking; evaluate SDK updates for native budget/subagent support

---

**END OF PHASE A ARCHITECTURE DOCUMENT — Revision 2 (Post-Critic)**
**Next step**: Your review and approval before any implementation begins.
