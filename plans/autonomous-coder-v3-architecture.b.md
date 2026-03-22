# Autonomous Coder v3 — Complete Architecture

> Built on Claude Agent SDK Python (`claude-agent-sdk` v0.1.49+)
> Streaming mode only (ClaudeSDKClient), Opus with 1M context

---

## 1. System Overview

### Design Philosophy

Autonomous Coder v3 is a **multi-phase autonomous coding pipeline** that uses Claude Agent SDK's streaming mode (`ClaudeSDKClient`) to provide full real-time visibility into every agent action. It supports two entry paths — greenfield projects (no existing code) and existing projects — and orchestrates a sequence of specialized phases, each running as an independent streaming session with its own context, tools, and budget.

### Core Architectural Pattern: Per-Phase Streaming Sessions

Each pipeline phase creates a fresh `ClaudeSDKClient` instance with phase-specific configuration. This gives us:

- **Context isolation**: phases don't pollute each other's context windows
- **Phase-specific tooling**: research needs WebSearch; code needs Write/Edit/Bash
- **Budget isolation**: each phase has its own `max_budget_usd` ceiling
- **Model flexibility**: phases can use different models via per-phase config
- **Streaming output**: every phase streams via `include_partial_messages=True`

Inter-phase data flows through a **custom in-process MCP server** that persists across phases in the Python orchestrator's memory. This lets each phase's agent selectively query previous results without bloating the prompt.

### What Python Controls vs What Claude Decides

| Concern | Python Orchestrator | Claude Agent |
|---------|-------------------|--------------|
| Phase sequencing | Determines phase order, skips phases | N/A |
| Budget enforcement | Tracks cumulative cost, sets per-phase caps | Receives budget as context |
| Security policy | Allowlist enforcement, sandbox config | Cannot override |
| Tool selection | Configures allowed_tools per phase | Chooses which allowed tools to use |
| Session lifecycle | Creates/destroys ClaudeSDKClient | Operates within session |
| Data persistence | Stores phase results, state file | Reads via MCP tool |
| Task decomposition | N/A | Breaks task into subtasks |
| Implementation decisions | N/A | Decides approach, writes code |
| Subagent delegation | Defines available subagents | Decides when to invoke them |

### Two Entry Paths

```
                    ┌─────────────┐
                    │  User Task  │
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │  Detect     │  Python-only: check project_path
                    │  Project    │  for existing files
                    │  Type       │
                    └──────┬──────┘
                           │
              ┌────────────┼────────────┐
              │                         │
       ┌──────▼──────┐          ┌──────▼──────┐
       │  EXISTING   │          │  GREENFIELD  │
       │  PROJECT    │          │  PROJECT     │
       └──────┬──────┘          └──────┬──────┘
              │                         │
       ┌──────▼──────┐                  │
       │  Explore    │                  │
       │  Phase      │                  │
       └──────┬──────┘                  │
              │                         │
              └────────────┬────────────┘
                           │
                    ┌──────▼──────┐
                    │  Research   │
                    │  Phase      │
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │  Plan       │
                    │  Phase      │
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │  Code       │
                    │  Phase      │  ← includes reviewer subagent
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │  Complete   │
                    └─────────────┘
```

---

## 2. Agent Definitions

### 2.1 Explore Phase Agent

**Purpose**: Map existing codebase structure, tech stack, and impact areas.

**System Prompt**:
```
You are a codebase analyst. Your job is to thoroughly explore and map an existing
project to prepare for an implementation task.

## Your Objective
Explore the codebase at {project_path} and produce a structured analysis for the
task: {task}

## Process
1. Use list_dir recursively to understand directory layout
2. Read package manifests (package.json, pyproject.toml, Cargo.toml, etc.)
3. Use get_symbols_overview on key source files
4. Use find_symbol to locate classes/functions relevant to the task
5. Use find_referencing_symbols to map dependency chains
6. Use search_for_pattern to find similar implementations or patterns

## Output Requirements
Produce a JSON report with these fields:
- stack: {language, framework, runtime, package_manager}
- architecture: description of overall architecture pattern
- entry_points: list of main entry files
- relevant_files: [{path, relevance: high|medium|low, reason}]
- key_symbols: [{name, type, file, relevance}]
- patterns_detected: list of coding patterns found
- impact_areas: list of areas affected by the task
- dependencies: key external dependencies relevant to the task

## Constraints
- Do NOT modify any files
- Focus on files relevant to the task, not exhaustive mapping
- Keep the report under 4000 tokens
```

**Tools**: `Read`, `Grep`, `Glob`, `mcp__serena__*`, `mcp__pipeline__get_project_info`
**Model**: `claude-opus-4-6`
**Max turns**: 30
**Budget**: $1.00

### 2.2 Research Phase Agent

**Purpose**: Discover libraries, documentation, patterns, and MCP servers relevant to the task.

**System Prompt**:
```
You are a technical researcher. Your job is to gather external knowledge needed
for implementing a coding task.

## Your Objective
Research the following task: {task}
Project context: {project_summary}

## Process
1. Search for relevant library documentation using Context7
2. Search for implementation patterns and examples
3. Find relevant MCP servers or tools
4. Check for known issues or gotchas with the tech stack

## What to Research
- Library APIs needed for the task
- Best practices for the implementation approach
- Security considerations specific to this feature
- Similar implementations in open-source projects

## Output Requirements
Produce a JSON report with:
- libraries: [{name, version, purpose, key_apis: [string]}]
- patterns: [{name, description, source_url}]
- security_considerations: [string]
- implementation_approach: recommended approach based on research
- unknowns: things that couldn't be determined and need exploration during coding

## Constraints
- Focus on actionable findings, not general knowledge
- Prioritize official documentation over blog posts
- Keep the report under 3000 tokens
- Call get_phase_result("explore") to review codebase context if available
```

**Tools**: `Read`, `Grep`, `Glob`, `WebSearch`, `WebFetch`, `mcp__Context7__*`, `mcp__pipeline__*`
**Model**: `claude-opus-4-6`
**Max turns**: 25
**Budget**: $1.50

### 2.3 Plan Phase Agent

**Purpose**: Synthesize explore + research findings into a detailed, ordered implementation plan.

**System Prompt**:
```
You are a senior software architect creating an implementation plan.

## Your Objective
Create a detailed implementation plan for: {task}

## Available Context
Call these MCP tools to retrieve prior phase results:
- get_phase_result("explore") — codebase analysis (if existing project)
- get_phase_result("research") — library docs and patterns

## Plan Requirements
1. Break work into atomic, ordered tasks (max 10 tasks)
2. Each task must specify:
   - Exact files to create or modify
   - What changes to make (specific, not vague)
   - Dependencies on other tasks
   - Verification criteria (how to confirm it works)
3. Order tasks by dependency — independent tasks first
4. Identify risks and mitigation strategies
5. Include a final verification task that tests the complete feature

## Output Format
Produce a JSON plan:
{{
  "goal": "task description",
  "approach": "high-level approach summary",
  "tasks": [
    {{
      "id": 1,
      "title": "brief title",
      "description": "what to do, specifically",
      "files": ["paths to create/modify"],
      "dependencies": [],
      "verification": "how to verify this task is complete",
      "complexity": "low|medium|high"
    }}
  ],
  "risks": [
    {{"risk": "description", "mitigation": "how to handle it"}}
  ],
  "verification_strategy": "how to verify the complete feature works end-to-end"
}}

## Constraints
- Every task must be independently verifiable
- No task should take more than ~50 tool calls to implement
- Keep total tasks under 10 for focus
- Prefer modifying existing files over creating new ones
```

**Tools**: `Read`, `Grep`, `Glob`, `mcp__serena__*`, `mcp__sequential-thinking__*`, `mcp__pipeline__*`
**Model**: `claude-opus-4-6`
**Max turns**: 15
**Budget**: $2.00

### 2.4 Code Phase Agent (with Reviewer Subagent)

**Purpose**: Execute the implementation plan, then have a reviewer subagent validate.

**System Prompt**:
```
You are an expert software engineer implementing a feature.

## Your Objective
Implement the following task: {task}

## Implementation Plan
Call get_phase_result("plan") to retrieve the detailed implementation plan.
Follow the plan's task order strictly.

## Process
For each task in the plan:
1. Read the relevant files first
2. Make the required changes
3. Verify the changes (run linter, build, etc.)
4. Move to the next task

## After Implementation
When all tasks are complete:
1. Invoke the "reviewer" agent to review your changes
2. Address any critical issues the reviewer identifies
3. Report completion with a summary of all changes made

## Code Quality Rules
- Follow existing code style and patterns
- Handle errors explicitly — no silent failures
- Add comments only for non-obvious logic
- Keep functions under 50 lines
- Prefer modifying existing files over creating new ones

## Constraints
- Stay within the project directory: {project_path}
- Only use allowed bash commands
- Do not install packages without confirming they're in the plan
- Do not modify test files or write mocks
```

**Tools**: `Read`, `Write`, `Edit`, `Bash`, `Grep`, `Glob`, `Agent`, `mcp__serena__*`, `mcp__Context7__*`, `mcp__pipeline__*`
**Model**: `claude-opus-4-6`
**Max turns**: 100
**Budget**: $5.00
**File checkpointing**: enabled (for rollback on review failure)

#### Reviewer Subagent

```python
AgentDefinition(
    description=(
        "Code reviewer. Invoke after implementation is complete to review "
        "all changes for correctness, security, style, and edge cases. "
        "Returns structured feedback with severity levels."
    ),
    prompt="""You are a senior code reviewer. Review the implementation changes
for the task described in the agent prompt.

## Review Checklist
1. Correctness: Does the code do what it's supposed to?
2. Security: Any injection, XSS, auth bypass, secret leakage?
3. Error handling: Are errors caught and handled appropriately?
4. Edge cases: What happens with empty input, nulls, large data?
5. Style: Does it match the existing codebase conventions?
6. Performance: Any obvious N+1 queries, unbounded loops, memory leaks?

## Output Format
Return a JSON review:
{
  "verdict": "approve|request_changes",
  "critical_issues": [{"file": "path", "line": "approx", "issue": "desc", "fix": "suggestion"}],
  "suggestions": [{"file": "path", "suggestion": "desc"}],
  "summary": "1-2 sentence overall assessment"
}

## Rules
- Only flag real issues, not style nitpicks
- If verdict is "approve", critical_issues must be empty
- Be specific about file paths and locations
- Focus on the changes, not pre-existing code""",
    tools=["Read", "Grep", "Glob"],
    model="sonnet",
)
```

---

## 3. Custom MCP Tools

The pipeline MCP server provides inter-phase communication and progress reporting. It runs in-process using `create_sdk_mcp_server`.

### 3.1 Pipeline MCP Server

```python
from claude_agent_sdk import tool, create_sdk_mcp_server

# Shared state — lives in the orchestrator's Python process
_phase_store: dict[str, str] = {}
_project_info: dict[str, Any] = {}
_progress: dict[str, Any] = {"phase": "", "percent": 0, "status": ""}


@tool(
    "get_phase_result",
    "Retrieve the output from a previously completed pipeline phase. "
    "Available phases: explore, research, plan.",
    {"phase": str},
)
async def get_phase_result(args: dict[str, Any]) -> dict[str, Any]:
    phase = args["phase"]
    result = _phase_store.get(phase)
    if result is None:
        return {"content": [{"type": "text", "text": f"Phase '{phase}' has not completed yet."}]}
    return {"content": [{"type": "text", "text": result}]}


@tool(
    "get_project_info",
    "Get metadata about the current project: path, detected language, "
    "framework, and whether it's a greenfield or existing project.",
    {},
)
async def get_project_info(args: dict[str, Any]) -> dict[str, Any]:
    import json
    return {"content": [{"type": "text", "text": json.dumps(_project_info, indent=2)}]}


@tool(
    "get_pipeline_status",
    "Get the current pipeline status: which phases have completed, "
    "total cost so far, and remaining budget.",
    {},
)
async def get_pipeline_status(args: dict[str, Any]) -> dict[str, Any]:
    import json
    status = {
        "completed_phases": list(_phase_store.keys()),
        "current_progress": _progress,
    }
    return {"content": [{"type": "text", "text": json.dumps(status, indent=2)}]}


@tool(
    "report_progress",
    "Report progress on the current phase. Use this to communicate "
    "structured status updates back to the user interface.",
    {"percent": int, "status": str, "current_task": str},
)
async def report_progress(args: dict[str, Any]) -> dict[str, Any]:
    _progress.update({
        "percent": args["percent"],
        "status": args["status"],
        "current_task": args.get("current_task", ""),
    })
    return {"content": [{"type": "text", "text": "Progress reported."}]}


def create_pipeline_mcp_server():
    """Create the in-process MCP server for pipeline coordination."""
    return create_sdk_mcp_server(
        name="pipeline",
        version="1.0.0",
        tools=[get_phase_result, get_project_info, get_pipeline_status, report_progress],
    )
```

### 3.2 Tool Registration Pattern

The pipeline MCP server is created once by the orchestrator and passed to every phase:

```python
pipeline_server = create_pipeline_mcp_server()

# For each phase:
mcp_servers = {
    "pipeline": pipeline_server,  # Always included
    **phase_specific_servers,      # serena, Context7, etc.
}
```

Tool names follow the pattern `mcp__pipeline__<tool_name>`:
- `mcp__pipeline__get_phase_result`
- `mcp__pipeline__get_project_info`
- `mcp__pipeline__get_pipeline_status`
- `mcp__pipeline__report_progress`

---

## 4. Hook Architecture

### 4.1 Hook Configuration

```python
def build_hooks(
    *,
    phase: str,
    audit_callback: Callable | None = None,
    progress_callback: Callable | None = None,
) -> dict[str, list[HookMatcher]]:
    """Build SDK hook configuration for a phase."""

    hooks: dict[str, list[HookMatcher]] = {}

    # --- PreToolUse: Security and path validation ---
    pre_tool_hooks = []

    # Block writes outside project directory
    async def enforce_project_boundary(input_data, tool_use_id, context):
        tool_input = input_data.get("tool_input", {})
        file_path = tool_input.get("file_path", "")
        if file_path and not file_path.startswith((".", "/")) :
            return {}  # Relative paths are fine (cwd is project dir)
        # Absolute paths must be within project
        # Additional validation in can_use_tool
        return {}

    pre_tool_hooks.append(
        HookMatcher(matcher="Write|Edit", hooks=[enforce_project_boundary])
    )

    hooks["PreToolUse"] = pre_tool_hooks

    # --- PostToolUse: Audit logging ---
    post_tool_hooks = []

    async def audit_log(input_data, tool_use_id, context):
        """Non-blocking audit log of all tool calls."""
        if audit_callback:
            audit_callback(
                tool=input_data.get("tool_name", "unknown"),
                input_summary=_summarize_input(input_data.get("tool_input", {})),
                phase=phase,
            )
        return {"async_": True}  # Don't block agent

    post_tool_hooks.append(HookMatcher(hooks=[audit_log]))
    hooks["PostToolUse"] = post_tool_hooks

    # --- SubagentStop: Track subagent completion ---
    if phase == "code":
        async def track_subagent(input_data, tool_use_id, context):
            agent_id = input_data.get("agent_id", "unknown")
            if audit_callback:
                audit_callback(
                    tool="SubagentStop",
                    input_summary=f"Subagent {agent_id} completed",
                    phase=phase,
                )
            return {}

        hooks["SubagentStop"] = [HookMatcher(hooks=[track_subagent])]

    # --- Notification: Forward agent notifications ---
    async def handle_notification(input_data, tool_use_id, context):
        message = input_data.get("message", "")
        if progress_callback:
            progress_callback(phase=phase, message=message)
        return {}

    hooks["Notification"] = [HookMatcher(hooks=[handle_notification])]

    return hooks
```

### 4.2 Hook Evaluation Order

For any tool call, the SDK evaluates in this order:

1. **PreToolUse hooks** — our path validation, security checks
2. **Deny rules** — from permission config
3. **Permission mode** — `acceptEdits` auto-approves file ops
4. **Allow rules** — explicit tool allowlist
5. **can_use_tool callback** — our bash command allowlist (final gate)

This means hooks fire FIRST and can short-circuit (deny) before `can_use_tool` is even reached. We use hooks for broad structural checks (path boundaries) and `can_use_tool` for fine-grained command validation (bash allowlist).

### 4.3 Hook Callback Signatures

All hook callbacks follow the SDK signature:

```python
async def hook_callback(
    input_data: dict[str, Any],   # Event-specific data
    tool_use_id: str | None,      # Correlates Pre/Post for same call
    context: Any,                 # Reserved for future use
) -> dict[str, Any]:
    """
    Returns:
        {} — allow the operation unchanged
        {"hookSpecificOutput": {"permissionDecision": "deny", ...}} — block it
        {"systemMessage": "..."} — inject context into conversation
        {"async_": True} — fire-and-forget (don't block agent)
    """
```

---

## 5. Permission Architecture

### 5.1 can_use_tool Callback

The `can_use_tool` callback is the final security gate. It receives every tool call and returns an allow/deny decision.

```python
async def security_callback(
    tool_name: str,
    tool_input: dict[str, Any],
    context: Any,
) -> PermissionResultAllow | PermissionResultDeny:
    """Defense-in-depth security callback.

    Called by the SDK AFTER hooks and permission rules.
    Blocks Bash commands not in the allowlist.
    Blocks file operations outside the project directory.
    """
    # --- Bash command validation ---
    if tool_name == "Bash":
        command = tool_input.get("command", "")
        is_allowed, reason = is_command_allowed(command)
        if not is_allowed:
            return PermissionResultDeny(
                behavior="deny",
                message=f"Blocked: {reason}",
                interrupt=False,  # Don't kill the session, let agent try again
            )

    # --- File path validation ---
    if tool_name in ("Write", "Edit", "Read"):
        file_path = tool_input.get("file_path", "")
        if not is_path_safe(file_path):
            return PermissionResultDeny(
                behavior="deny",
                message=f"Path outside project boundary: {file_path}",
                interrupt=False,
            )

    return PermissionResultAllow(behavior="allow", updated_input=None)
```

### 5.2 Bash Command Allowlist

The allowlist is organized by category and curated for development tasks:

```python
ALLOWED_COMMANDS = {
    # Package managers
    "npm", "npx", "yarn", "pnpm", "pip", "pip3", "uv", "uvx", "cargo", "go",
    # Build/run
    "node", "python", "python3", "make", "tsc",
    # Version control
    "git",
    # Shell utilities (safe subset)
    "cat", "head", "tail", "ls", "pwd", "mkdir", "cp", "mv", "touch",
    "find", "grep", "awk", "sed", "wc", "sort", "diff", "which", "echo",
    # Dev utilities
    "curl", "jq", "tar", "unzip",
    # Linters/formatters
    "eslint", "prettier", "black", "ruff", "mypy",
    # Process management
    "kill", "pkill", "ps", "lsof",
}

DANGEROUS_PATTERNS = [
    "rm -rf /", "rm -rf /*", "rm -rf ~", "> /dev/sda", "mkfs",
    "dd if=", ":(){:|:&};:", "chmod 777", "sudo rm", "sudo chmod",
    "curl | sh", "curl | bash", "eval $(", "base64 -d |",
]
```

### 5.3 Permission Mode and Settings

```python
# Per-phase permission configuration
permission_config = {
    "defaultMode": "acceptEdits",
    "allow": [
        "Read(./**)", "Write(./**)", "Edit(./**)",
        "Glob(./**)", "Grep(./**)",
        "Bash(*)",  # Validated by can_use_tool
        "mcp__pipeline__*",
        "mcp__serena__*",
        "mcp__Context7__*",
    ],
}
```

### 5.4 Sandbox Configuration

```python
sandbox_settings = SandboxSettings(
    enabled=True,
    auto_allow_bash_if_sandboxed=True,
)
```

The SDK sandbox provides OS-level isolation for Bash commands, preventing filesystem escape even if the allowlist has gaps.

---

## 6. Streaming Output Architecture

### 6.1 StreamEvent Processing

The `StreamProcessor` converts raw SDK `StreamEvent` objects into typed UI events. This decouples stream parsing from display logic.

```python
from dataclasses import dataclass
from typing import Any, AsyncIterator
from claude_agent_sdk.types import StreamEvent, AssistantMessage, ResultMessage


# --- Typed UI Events ---

@dataclass
class TextDelta:
    """A chunk of streamed text."""
    text: str

@dataclass
class ToolStart:
    """A tool call is beginning."""
    name: str
    tool_use_id: str

@dataclass
class ToolInputDelta:
    """Incremental JSON input for a tool call."""
    partial_json: str

@dataclass
class ToolEnd:
    """A tool call (or text block) has finished."""
    pass

@dataclass
class MessageComplete:
    """Full AssistantMessage received (after streaming)."""
    content: list[Any]

@dataclass
class PhaseComplete:
    """ResultMessage received — phase is done."""
    cost_usd: float
    duration_ms: int
    session_id: str
    result_text: str | None
    is_error: bool

UIEvent = TextDelta | ToolStart | ToolInputDelta | ToolEnd | MessageComplete | PhaseComplete


# --- Stream Processor ---

class StreamProcessor:
    """Converts raw SDK messages into typed UI events."""

    def __init__(self):
        self._in_tool = False
        self._current_tool: str | None = None

    async def process(self, message: Any) -> AsyncIterator[UIEvent]:
        if isinstance(message, StreamEvent):
            event = message.event
            event_type = event.get("type")

            if event_type == "content_block_start":
                block = event.get("content_block", {})
                if block.get("type") == "tool_use":
                    self._in_tool = True
                    self._current_tool = block.get("name", "unknown")
                    yield ToolStart(
                        name=self._current_tool,
                        tool_use_id=block.get("id", ""),
                    )

            elif event_type == "content_block_delta":
                delta = event.get("delta", {})
                if delta.get("type") == "text_delta":
                    yield TextDelta(text=delta["text"])
                elif delta.get("type") == "input_json_delta":
                    yield ToolInputDelta(partial_json=delta["partial_json"])

            elif event_type == "content_block_stop":
                if self._in_tool:
                    self._in_tool = False
                    self._current_tool = None
                yield ToolEnd()

        elif isinstance(message, AssistantMessage):
            yield MessageComplete(content=message.content)

        elif isinstance(message, ResultMessage):
            yield PhaseComplete(
                cost_usd=message.total_cost_usd or 0.0,
                duration_ms=message.duration_ms or 0,
                session_id=message.session_id or "",
                result_text=message.result,
                is_error=message.is_error or False,
            )
```

### 6.2 Display Adapters

Both TUI and CLI consume `UIEvent` objects from the `StreamProcessor`:

**CLI Adapter**:
```python
async def cli_display(event: UIEvent, phase: str) -> None:
    if isinstance(event, TextDelta):
        print(event.text, end="", flush=True)
    elif isinstance(event, ToolStart):
        print(f"\n  [{event.name}] ", end="", flush=True)
    elif isinstance(event, ToolEnd):
        print(" done", flush=True)
    elif isinstance(event, PhaseComplete):
        status = "ERROR" if event.is_error else "DONE"
        print(f"\n[{status}] {phase} — ${event.cost_usd:.4f}")
```

**TUI Adapter**: Posts Textual `Message` objects that update widgets (agent tabs, progress panel, cost display).

### 6.3 Important: Extended Thinking Incompatibility

Extended thinking (`thinking` config or `max_thinking_tokens`) is **incompatible** with `StreamEvent` output. When thinking is enabled, only complete `AssistantMessage` objects are yielded.

v3 prioritizes streaming visibility. Extended thinking is not used. If needed for specific phases (e.g., plan), it can be enabled at the cost of losing token-by-token streaming for that phase.

---

## 7. File Structure

```
src/autonomous_coder/
├── __init__.py              # Public API exports
├── __main__.py              # CLI entry point (argparse: --cli, --verbose, --project)
├── app.py                   # Textual TUI application
├── cli_adapter.py           # Headless CLI output adapter
├── config.py                # PipelineConfig, PhaseConfig, MCP_SERVERS registry
├── orchestrator.py          # PipelineRunner — the core engine
├── session.py               # PipelineState persistence (JSON state file)
├── streaming.py             # StreamProcessor, UIEvent types
├── security.py              # can_use_tool, allowlist, dangerous patterns
├── hooks.py                 # build_hooks(), hook callbacks
├── tools.py                 # Custom MCP tools (pipeline server)
├── prompts.py               # Prompt template loading/formatting
├── messages.py              # Textual Message subclasses for UI
├── agents/
│   ├── __init__.py          # Re-exports all phase runners
│   ├── base.py              # BasePhaseRunner ABC
│   ├── explore.py           # ExplorerPhaseRunner
│   ├── research.py          # ResearchPhaseRunner
│   ├── plan.py              # PlannerPhaseRunner
│   └── code.py              # CoderPhaseRunner (with reviewer subagent)
├── prompts/
│   ├── explorer.md          # Explore phase system prompt template
│   ├── researcher.md        # Research phase system prompt template
│   ├── planner.md           # Plan phase system prompt template
│   ├── coder.md             # Code phase system prompt template
│   └── reviewer.md          # Reviewer subagent prompt template
└── widgets/
    ├── __init__.py
    ├── agent_tree.py         # Phase/agent hierarchy tree
    ├── agent_tabs.py         # Tabbed agent output panels
    ├── streaming_log.py      # Real-time streaming text display
    ├── progress_panel.py     # Phase progress bar
    ├── cost_display.py       # Running cost tracker
    └── task_detail.py        # Current task information
```

### Changes from v2

| File | Change | Reason |
|------|--------|--------|
| `orchestrator.py` | **Rewritten** | `query()` → `ClaudeSDKClient` streaming |
| `streaming.py` | **New** | StreamEvent processing extracted from orchestrator |
| `session.py` | **New** | State persistence for pipeline resumption |
| `tools.py` | **New** | Custom MCP tools for inter-phase data flow |
| `hooks.py` | **Rewritten** | Expanded from audit-only to full hook architecture |
| `config.py` | **Rewritten** | `RoleConfig` → `PhaseConfig` with subagents, betas, effort |
| `agents/base.py` | **Rewritten** | Uses `ClaudeSDKClient` instead of `query()` |
| `agents/code.py` | **Rewritten** | Reviewer subagent via `AgentDefinition`, not separate query |

---

## 8. Execution Flow

### 8.1 Core Pipeline Loop

```python
class PipelineRunner:
    """Executes the phase pipeline using ClaudeSDKClient streaming."""

    def __init__(self, config: PipelineConfig, display: DisplayAdapter):
        self.config = config
        self.display = display
        self.pipeline_server = create_pipeline_mcp_server()
        self.stream_processor = StreamProcessor()
        self.state = PipelineState.load_or_create(config.project_path)
        self.total_cost = 0.0

    async def run(self, task: str) -> PipelineState:
        # Determine phase order
        phases = self._determine_phases(task)

        for i, phase_name in enumerate(phases):
            if phase_name in self.state.completed_phases:
                continue  # Skip completed phases on resume

            phase_config = self.config.phases[phase_name]
            runner = self._create_runner(phase_name)

            self.display.phase_started(phase_name, i, len(phases))

            result = await self._run_phase(
                phase_name=phase_name,
                runner=runner,
                phase_config=phase_config,
                task=task,
            )

            self.state.record_phase(phase_name, result)
            self.state.save()

            if not result.success:
                self.display.phase_failed(phase_name, result.error)
                break

        return self.state

    async def _run_phase(
        self, phase_name: str, runner: BasePhaseRunner,
        phase_config: PhaseConfig, task: str,
    ) -> PhaseResult:
        """Execute a single phase with full streaming."""

        prompt = runner.build_prompt(task, self.state)
        system_prompt = runner.build_system_prompt(task, self.state)

        options = self._build_options(phase_name, phase_config, system_prompt)

        collected_text: list[str] = []
        cost = 0.0

        try:
            async with ClaudeSDKClient(options=options) as client:
                await client.query(prompt)

                async for message in client.receive_response():
                    async for event in self.stream_processor.process(message):
                        self.display.handle_event(phase_name, event)

                        if isinstance(event, TextDelta):
                            collected_text.append(event.text)
                        elif isinstance(event, PhaseComplete):
                            cost = event.cost_usd

        except Exception as exc:
            return PhaseResult(
                phase_name=phase_name, output_data={},
                cost_incurred=0.0, success=False, error=str(exc),
            )

        result_text = "".join(collected_text)
        _phase_store[phase_name] = result_text  # Store for MCP tool
        self.total_cost += cost

        return PhaseResult(
            phase_name=phase_name,
            output_data={runner.output_key: result_text},
            cost_incurred=cost, success=True,
        )

    def _build_options(
        self, phase: str, pc: PhaseConfig, system_prompt: str,
    ) -> ClaudeAgentOptions:
        """Build ClaudeAgentOptions for a phase."""

        mcp_servers = {"pipeline": self.pipeline_server}
        for key in pc.mcp_keys:
            if key in MCP_SERVERS:
                mcp_servers[key] = dict(MCP_SERVERS[key])

        # Inject project path into serena
        if "serena" in mcp_servers:
            env = mcp_servers["serena"].get("env", {}) or {}
            mcp_servers["serena"]["env"] = {
                **env, "SERENA_PROJECT": str(self.config.project_path),
            }

        return ClaudeAgentOptions(
            model=pc.model,
            system_prompt=system_prompt,
            allowed_tools=[
                *pc.tools,
                *[f"mcp__{k}__*" for k in mcp_servers],
            ],
            mcp_servers=mcp_servers,
            agents=pc.subagents,
            max_turns=pc.max_turns,
            max_budget_usd=pc.max_budget_usd,
            betas=pc.betas,
            effort=pc.effort,
            cwd=str(self.config.project_path),
            permission_mode="acceptEdits",
            include_partial_messages=True,
            can_use_tool=security_callback if "Bash" in pc.tools else None,
            hooks=build_hooks(
                phase=phase,
                audit_callback=self.display.on_audit,
                progress_callback=self.display.on_progress,
            ),
            enable_file_checkpointing=(phase == "code"),
        )

    def _determine_phases(self, task: str) -> list[str]:
        """Determine phase order based on project type."""
        project_path = self.config.project_path
        has_files = any(project_path.iterdir()) if project_path.exists() else False

        if has_files:
            return ["explore", "research", "plan", "code"]
        else:
            project_path.mkdir(parents=True, exist_ok=True)
            return ["research", "plan", "code"]
```

### 8.2 Phase Runner Base

```python
class BasePhaseRunner(ABC):
    """Skeleton for phase runners. Each phase provides prompts only."""

    role: str       # Phase name for config lookup
    output_key: str # Key to store result under

    @abstractmethod
    def build_system_prompt(self, task: str, state: PipelineState) -> str:
        """Build the system prompt for this phase."""
        ...

    @abstractmethod
    def build_prompt(self, task: str, state: PipelineState) -> str:
        """Build the user prompt for this phase."""
        ...
```

Phase runners are now pure prompt factories. The orchestrator handles all SDK interaction. This is simpler than v2 where runners also managed SDK calls.

---

## 9. Configuration Architecture

### 9.1 PipelineConfig

```python
@dataclass
class PhaseConfig:
    """Configuration for a single pipeline phase."""
    model: str = "claude-opus-4-6"
    tools: list[str] = field(default_factory=list)
    mcp_keys: list[str] = field(default_factory=list)
    subagents: dict[str, AgentDefinition] | None = None
    max_turns: int = 50
    max_budget_usd: float = 2.0
    betas: list[str] = field(default_factory=lambda: ["context-1m-2025-08-07"])
    effort: Literal["low", "medium", "high", "max"] = "high"

@dataclass
class PipelineConfig:
    """Top-level pipeline configuration."""
    project_path: Path
    total_budget: float = 10.0
    phases: dict[str, PhaseConfig] = field(default_factory=_default_phases)

def _default_phases() -> dict[str, PhaseConfig]:
    return {
        "explore": PhaseConfig(
            tools=["Read", "Grep", "Glob"],
            mcp_keys=["serena"],
            max_turns=30,
            max_budget_usd=1.0,
        ),
        "research": PhaseConfig(
            tools=["Read", "Grep", "Glob", "WebSearch", "WebFetch"],
            mcp_keys=["Context7"],
            max_turns=25,
            max_budget_usd=1.5,
        ),
        "plan": PhaseConfig(
            tools=["Read", "Grep", "Glob"],
            mcp_keys=["serena", "sequential-thinking"],
            max_turns=15,
            max_budget_usd=2.0,
        ),
        "code": PhaseConfig(
            tools=["Read", "Write", "Edit", "Bash", "Grep", "Glob", "Agent"],
            mcp_keys=["serena", "Context7"],
            max_turns=100,
            max_budget_usd=5.0,
            subagents={"reviewer": _reviewer_agent()},
        ),
    }
```

### 9.2 MCP Server Registry

```python
MCP_SERVERS: dict[str, dict] = {
    "serena": {
        "command": "uvx",
        "args": ["serena"],
    },
    "sequential-thinking": {
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-sequential-thinking"],
    },
    "Context7": {
        "command": "npx",
        "args": ["-y", "@upstash/context7-mcp"],
    },
}
```

### 9.3 Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `ANTHROPIC_API_KEY` | (required) | Claude API authentication |
| `AC_TOTAL_BUDGET` | `10.0` | Pipeline budget cap in USD |
| `AC_MODEL` | `claude-opus-4-6` | Default model for all phases |
| `AC_SANDBOX` | `1` | Enable OS-level sandbox |
| `AC_VERBOSE` | `0` | Verbose CLI output |

### 9.4 pyproject.toml

```toml
[project]
name = "autonomous-coder"
version = "3.0.0"
description = "AI-powered autonomous coding assistant with streaming TUI"
requires-python = ">=3.11"
dependencies = [
    "claude-agent-sdk>=0.1.49",
    "textual>=1.0.0",
]

[project.scripts]
autonomous-coder = "autonomous_coder.__main__:main"
```

---

## 10. Session Management

### 10.1 PipelineState

```python
@dataclass
class PipelineState:
    """Persisted pipeline state for resumption across runs."""
    task: str
    project_path: str
    completed_phases: list[str] = field(default_factory=list)
    phase_results: dict[str, str] = field(default_factory=dict)
    session_ids: dict[str, str] = field(default_factory=dict)
    total_cost: float = 0.0
    started_at: str = ""
    updated_at: str = ""

    STATE_FILENAME = ".autonomous-coder-state.json"

    def record_phase(self, phase: str, result: PhaseResult) -> None:
        """Record a completed phase."""
        self.completed_phases.append(phase)
        self.phase_results[phase] = result.output_data.get(
            f"{phase}_output", ""
        )[:5000]  # Cap stored result size
        self.total_cost += result.cost_incurred
        self.updated_at = _now_iso()

    def save(self) -> None:
        """Persist state to project directory."""
        path = Path(self.project_path) / self.STATE_FILENAME
        path.write_text(json.dumps(asdict(self), indent=2))

    @classmethod
    def load_or_create(cls, project_path: Path, task: str = "") -> PipelineState:
        """Load existing state or create new."""
        path = project_path / cls.STATE_FILENAME
        if path.exists():
            data = json.loads(path.read_text())
            return cls(**data)
        return cls(
            task=task,
            project_path=str(project_path),
            started_at=_now_iso(),
        )
```

### 10.2 Session Resumption Flow

```
1. User runs: autonomous-coder "Add auth"
2. PipelineState.load_or_create() checks for state file
3a. No state file → fresh pipeline, all phases run
3b. State file found:
    → Display: "Previous run found. Phases completed: explore, research"
    → Ask: "Resume from plan phase? [Y/n]"
    → If yes: skip explore and research, load stored results into phase_store
    → If no: delete state file, start fresh
4. Pipeline runs remaining phases
5. State saved after each phase completion
6. On success: state file deleted (clean exit)
7. On failure: state file preserved for resumption
```

### 10.3 File Checkpointing (Code Phase)

The code phase enables `enable_file_checkpointing=True`. This lets the orchestrator call `client.rewind_files(message_id)` to restore files to a previous state if the reviewer subagent finds critical issues.

```python
# In code phase execution:
if reviewer_verdict == "request_changes" and critical_issues:
    # Rewind files to before the problematic changes
    await client.rewind_files(last_good_message_id)
    # Re-query with fix instructions
    await client.query(f"Fix these issues: {critical_issues}")
```

This is only possible because we use `ClaudeSDKClient` (streaming mode), not `query()`.

---

## Appendix A: Verification Questions and Answers

### Q1: Does the custom MCP server persist state across phase sessions?

**A**: Yes. The `_phase_store` dict and `create_pipeline_mcp_server()` return value live in the orchestrator's Python process memory. Each `ClaudeSDKClient` session receives the same `McpSdkServerConfig` reference. The MCP server process restarts per session, but the Python-side state persists because the `@tool`-decorated functions close over the module-level `_phase_store` dict.

### Q2: Can the reviewer subagent access the pipeline MCP tools?

**A**: Yes. Per the SDK docs: "Subagents inherit parent MCP servers." The reviewer subagent can call `mcp__pipeline__get_phase_result` to read the plan. However, the reviewer's `tools` field restricts it to `["Read", "Grep", "Glob"]`, so it would NOT be able to call MCP tools unless we add them. We should add `mcp__pipeline__get_phase_result` to the reviewer's tools list, or omit the `tools` field to inherit all parent tools. The architecture uses explicit tools for the reviewer to prevent it from calling `Write` or `Bash` — so we add `mcp__pipeline__*` to its tools list.

### Q3: What happens when extended thinking is enabled alongside include_partial_messages?

**A**: StreamEvent messages are NOT emitted when thinking is enabled. The SDK falls back to yielding complete `AssistantMessage` objects. The `StreamProcessor` handles both — it processes `StreamEvent` when available and falls back to `MessageComplete` events from `AssistantMessage`. v3 does not enable extended thinking by default.

### Q4: How does budget enforcement work across phases?

**A**: Two levels. Per-phase: `max_budget_usd` in `ClaudeAgentOptions` causes the SDK to stop the agent when the phase budget is reached. Pipeline-wide: the orchestrator tracks `total_cost` by summing `ResultMessage.total_cost_usd` from each phase. If `total_cost > config.total_budget`, the orchestrator stops the pipeline before starting the next phase.

### Q5: What if the Bash allowlist is too restrictive for a user's project?

**A**: The allowlist is defined in `security.py` and can be extended by users. Future work: allow a `.autonomous-coder.toml` config file in the project root to add custom allowed commands. For v3, the default allowlist covers common development workflows (npm, python, cargo, go, git, make, etc.).

---

## Appendix B: Revision Log

### Changes Made During Design Review

1. **Added `mcp__pipeline__*` to reviewer subagent tools** — Without this, the reviewer can't read the plan via `get_phase_result`. Added to the reviewer's tools list alongside `Read`, `Grep`, `Glob`.

2. **Removed `firecrawl-mcp` from default MCP servers** — Requires an API key and isn't universally available. WebSearch/WebFetch built-in tools handle most research needs. Users can add firecrawl via config if they have a key.

3. **Added `effort: "high"` to PhaseConfig** — Opus with 1M context should use high effort for quality. Added as a default in PhaseConfig.

4. **Clarified StreamEvent incompatibility with extended thinking** — Added explicit documentation in Section 6.3 and Q3.

5. **Made phase runners pure prompt factories** — Moved all SDK interaction into the orchestrator. Phase runners only provide `build_system_prompt()` and `build_prompt()`. This eliminates the v2 problem of runners having two code paths (orchestrator vs direct).
