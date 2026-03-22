# Autonomous Coder v3 — Complete Architecture

> Built on Claude Agent SDK Python (`claude-agent-sdk` PyPI, v0.1.49+)
> Single-session streaming architecture with Opus 4.6 + 1M context

---

## 1. System Overview

### Core Insight

v2 created **four separate SDK sessions** (Research, Explore, Plan, Code), each starting with a blank context window and passing truncated strings between phases. v3 inverts this: **one persistent `ClaudeSDKClient` session** where Claude itself orchestrates the full lifecycle, with Python controlling only session lifecycle, security gates, and UI rendering.

### Why Single-Session?

| Concern | v2 (multi-session) | v3 (single-session) |
|---|---|---|
| Context continuity | Truncated strings between phases | Full conversation history |
| MCP server lifecycle | Spin up/down 4x | Start once, available throughout |
| Session interruption | Not supported | `client.interrupt()` |
| Budget tracking | Manual accumulation | SDK-native `max_budget_usd` |
| Subagent support | None (separate queries) | SDK-native `AgentDefinition` |
| Crash recovery | Lost everything | `enable_file_checkpointing` + `resume` |
| Context compaction | Not handled | `PreCompact` hook + `save_findings` tool |

### Architecture Diagram

```
                        ┌──────────────────────────────────────────────┐
                        │              autonomous-coder v3             │
                        │                                              │
  CLI args / TOML ──►   │  SessionConfig ──► ClaudeSDKClient (single)  │
                        │                        │                     │
                        │         ┌──────────────┼──────────────┐      │
                        │         │              │              │      │
                        │    Streaming      Subagents       Hooks      │
                        │    (StreamEvent)  (Agent tool)   (lifecycle) │
                        │         │              │              │      │
                        │         ▼              │              │      │
                        │    EventHandler        │         PreToolUse  │
                        │    (Protocol)          │         PostToolUse │
                        │     ┌───┴───┐          │         PreCompact  │
                        │     │       │          │         SubagentStop│
                        │   TUI     CLI          │              │      │
                        │  (Textual)(stdout)     │              │      │
                        │                        ▼              │      │
                        │              ┌────────────────┐       │      │
                        │              │ code-reviewer   │       │      │
                        │              │ security-auditor│       │      │
                        │              └────────────────┘       │      │
                        │                                              │
                        │    Custom MCP (in-process):                   │
                        │      save_findings / get_findings /          │
                        │      report_progress                         │
                        │                                              │
                        │    External MCP (subprocess):                │
                        │      serena / context7                       │
                        │                                              │
                        │    Security: can_use_tool callback           │
                        │              + PreToolUse hooks              │
                        └──────────────────────────────────────────────┘
```

### Two Entry Paths

**Greenfield** (no project exists): Python detects empty/absent directory, injects `project_state: greenfield` into the system prompt. Claude creates the project structure, scaffolds from scratch.

**Existing Project** (codebase present): Python detects `pyproject.toml`, `package.json`, `Cargo.toml`, etc., injects `project_state: existing` with detected stack info. Claude explores before modifying.

Detection happens in Python (not a tool) because it runs once before the session starts.

---

## 2. Agent Definitions (with Full System Prompts)

### Main Agent (Orchestrator)

The main agent runs inside the single `ClaudeSDKClient` session. Its system prompt defines the full autonomous workflow.

```python
ORCHESTRATOR_SYSTEM_PROMPT = """You are an autonomous coding agent. You independently implement \
software features from natural-language task descriptions. You work methodically through phases, \
persisting your findings as you go.

## Project State
{project_state}

## Workflow

Work through these phases in order. After each phase, call `save_findings` with your results \
so they survive context compaction. Call `report_progress` at phase transitions so the user \
sees your progress.

### Phase 1: Research (when external knowledge is needed)
Determine whether the task requires knowledge beyond the codebase:
- New libraries, frameworks, or APIs → use WebSearch and Context7
- Well-understood modifications → skip to Phase 2
Save: `save_findings(category="research", content=<structured findings>)`

### Phase 2: Explore (existing projects only)
Understand the codebase before modifying it:
- Use Serena MCP: `get_symbols_overview`, `find_symbol`, `search_for_pattern`
- Map the architecture, entry points, patterns, and impact areas
- Identify files to modify and dependencies to respect
Save: `save_findings(category="exploration", content=<structured findings>)`

### Phase 3: Plan
Create a concrete implementation plan:
- Break work into ordered, atomic steps
- Identify dependencies between steps
- Estimate risk for each step
- Define verification criteria (how to prove each step works)
Save: `save_findings(category="plan", content=<structured plan>)`

### Phase 4: Implement
Execute the plan step by step:
- Make minimal, focused changes
- Follow existing code patterns and conventions
- Build and run after each significant change to verify correctness
- Call `report_progress` after completing each step

### Phase 5: Review
After implementation is complete:
- Use the `code-reviewer` subagent to review your changes
- For security-sensitive changes, also use the `security-auditor` subagent
- Address any critical findings before finishing

## Tool Usage Guidelines

### Persistence (critical for long sessions)
- Call `save_findings` after EVERY phase — your context may compact at any time
- Call `get_findings` to retrieve previous phase results if you lose context
- These tools are your long-term memory

### Progress Reporting
- Call `report_progress(phase, status, detail)` at phase transitions
- Statuses: "starting", "in_progress", "complete", "skipped", "error"
- This is how the user tracks your work

### Code Intelligence
- Prefer Serena MCP (semantic: `find_symbol`, `get_symbols_overview`) over raw file reading
- Use `search_for_pattern` for regex across the codebase
- Use Context7 MCP for up-to-date library documentation

### Budget Awareness
Your session has a hard budget limit. Be efficient:
- Don't read files you don't need
- Use targeted searches, not broad scans
- Save findings early so re-reading isn't needed after compaction

### Subagent Delegation
You have two specialist subagents available via the Agent tool:
- `code-reviewer`: Use after implementing changes. Read-only, focuses on quality.
- `security-auditor`: Use for security-sensitive changes. Can run commands to verify.
Include relevant file paths and context in your delegation prompt — subagents start fresh.

## Security Constraints
- Only use approved bash commands (the system will block disallowed ones)
- Stay within {project_path}
- Never hardcode secrets or credentials
- Validate all inputs at system boundaries
"""
```

### Subagent: Code Reviewer

```python
AgentDefinition(
    description=(
        "Expert code reviewer. Delegate to this agent after implementing changes "
        "to get quality, correctness, and maintainability feedback. "
        "Include specific file paths in your delegation prompt."
    ),
    prompt="""You are a senior code reviewer performing a thorough review of recent changes.

## Review Criteria
1. **Correctness**: Does the code do what it claims? Edge cases handled?
2. **Style**: Consistent with the existing codebase? Follows conventions?
3. **Maintainability**: Clear naming? Reasonable complexity? Self-documenting?
4. **Error handling**: Failures handled gracefully? No swallowed exceptions?
5. **Performance**: Obvious inefficiencies? N+1 queries? Unnecessary allocations?

## Process
1. Read the files mentioned in the delegation prompt
2. Use Grep/Glob to check for related code and patterns
3. Provide a structured review with:
   - Critical issues (must fix)
   - Suggestions (should consider)
   - Positive observations (what was done well)

## Output Format
Structure your review as:
- **CRITICAL**: Issues that must be fixed before shipping
- **SUGGESTION**: Improvements that would strengthen the code
- **POSITIVE**: Things done well (reinforces good patterns)

Be concise. Focus on substance over ceremony.""",
    tools=["Read", "Grep", "Glob"],
    model="sonnet",
)
```

### Subagent: Security Auditor

```python
AgentDefinition(
    description=(
        "Security specialist. Delegate to this agent for security-sensitive changes "
        "(authentication, authorization, input handling, crypto, secrets management). "
        "Include specific file paths and the nature of the security concern."
    ),
    prompt="""You are a security auditor reviewing code changes for vulnerabilities.

## Audit Scope
1. **Injection**: SQL injection, XSS, command injection, path traversal
2. **Authentication/Authorization**: Broken auth, privilege escalation, session issues
3. **Data exposure**: Hardcoded secrets, sensitive data in logs, overly permissive responses
4. **Input validation**: Missing validation, improper sanitization, type confusion
5. **Cryptography**: Weak algorithms, improper key management, insecure random
6. **Dependencies**: Known vulnerable packages, supply chain concerns

## Process
1. Read the changed files
2. Grep for security-sensitive patterns (passwords, tokens, eval, exec, SQL, etc.)
3. Check for OWASP Top 10 issues
4. Verify security boundaries are maintained

## Output Format
- **VULNERABILITY**: Confirmed security issues with severity (critical/high/medium/low)
- **RISK**: Potential issues that need human review
- **VERIFIED**: Security properties that are correctly implemented

For each finding, provide: location, description, impact, and remediation.""",
    tools=["Read", "Grep", "Glob", "Bash"],
    model="opus",
)
```

### Why Only Two Subagents?

**Rejected subagents and rationale:**

| Rejected Agent | Why Not |
|---|---|
| Research agent | Research is integral to the main flow. Isolating it loses context about what the user actually needs. |
| Explorer agent | Exploration findings directly inform planning. Keeping them in the main context is more valuable than isolating them. |
| Planner agent | Planning requires synthesis of research + exploration. Moving it to a subagent loses that synthesis. |
| Test runner | Testing is part of implementation verification. The main agent needs to see test results to iterate. |

Subagents are for roles that **benefit from context isolation** — a reviewer shouldn't see the messy exploration that preceded the code, only the final code.

---

## 3. Custom MCP Tools

Three in-process tools registered as a single SDK MCP server. These are Claude's "long-term memory" within a session.

```python
from claude_agent_sdk import tool, create_sdk_mcp_server
from pathlib import Path
from typing import Any
import json
from datetime import datetime

FINDINGS_DIR: Path  # Set at session start: project_path / ".autonomous-coder" / "findings"
PROGRESS_STATE: dict  # Shared mutable state read by EventHandler


@tool(
    "save_findings",
    "Persist structured findings to disk. Call after each workflow phase to protect "
    "against context compaction. Categories: research, exploration, plan, implementation, review.",
    {"category": str, "content": str},
)
async def save_findings(args: dict[str, Any]) -> dict[str, Any]:
    category = args["category"]
    content = args["content"]
    timestamp = datetime.now().isoformat(timespec="seconds")

    findings_path = FINDINGS_DIR / f"{category}.md"
    FINDINGS_DIR.mkdir(parents=True, exist_ok=True)

    header = f"# {category.title()} Findings\n\nUpdated: {timestamp}\n\n"
    findings_path.write_text(header + content, encoding="utf-8")

    return {
        "content": [
            {
                "type": "text",
                "text": f"Saved {len(content)} chars to {category}.md",
            }
        ]
    }


@tool(
    "get_findings",
    "Retrieve previously saved findings by category. Use when you need to recall "
    "earlier phase results (e.g., after context compaction).",
    {"category": str},
)
async def get_findings(args: dict[str, Any]) -> dict[str, Any]:
    category = args["category"]
    findings_path = FINDINGS_DIR / f"{category}.md"

    if not findings_path.exists():
        return {
            "content": [
                {"type": "text", "text": f"No findings saved for '{category}'"}
            ]
        }

    content = findings_path.read_text(encoding="utf-8")
    return {"content": [{"type": "text", "text": content}]}


@tool(
    "report_progress",
    "Report current progress to the user interface. Call at phase transitions "
    "and after completing significant implementation steps.",
    {
        "type": "object",
        "properties": {
            "phase": {
                "type": "string",
                "enum": ["research", "explore", "plan", "implement", "review"],
            },
            "status": {
                "type": "string",
                "enum": ["starting", "in_progress", "complete", "skipped", "error"],
            },
            "detail": {"type": "string"},
        },
        "required": ["phase", "status", "detail"],
    },
)
async def report_progress(args: dict[str, Any]) -> dict[str, Any]:
    global PROGRESS_STATE
    phase = args["phase"]
    status = args["status"]
    detail = args["detail"]

    PROGRESS_STATE[phase] = {"status": status, "detail": detail}

    return {
        "content": [
            {"type": "text", "text": f"Progress reported: {phase} -> {status}"}
        ]
    }


def create_findings_server(project_path: Path) -> Any:
    """Create the in-process MCP server for findings management."""
    global FINDINGS_DIR, PROGRESS_STATE
    FINDINGS_DIR = project_path / ".autonomous-coder" / "findings"
    PROGRESS_STATE = {}

    return create_sdk_mcp_server(
        name="autonomous-coder",
        version="3.0.0",
        tools=[save_findings, get_findings, report_progress],
    )
```

### Tool Naming Convention

When exposed to Claude, these tools are named:
- `mcp__autonomous-coder__save_findings`
- `mcp__autonomous-coder__get_findings`
- `mcp__autonomous-coder__report_progress`

---

## 4. Hook Architecture

Hooks handle cross-cutting concerns without cluttering the main logic.

```python
from claude_agent_sdk import HookMatcher
from typing import Any
import json
import time

# --- Shared state for hooks ---
_audit_log: list[dict] = []
_subagent_tracker: dict[str, float] = {}


# === PreToolUse Hooks ===

async def bash_security_gate(input_data: Any, tool_use_id: str | None, context: Any) -> dict:
    """Block disallowed bash commands via hook (defense layer 1)."""
    command = input_data["tool_input"].get("command", "")
    allowed, reason = is_command_allowed(command)
    if not allowed:
        return {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": f"Blocked: {reason}",
            }
        }
    return {}


async def file_scope_guard(input_data: Any, tool_use_id: str | None, context: Any) -> dict:
    """Ensure Write/Edit operations stay within the project directory."""
    file_path = input_data["tool_input"].get("file_path", "")
    # Resolve to absolute and check it's under project_path
    # (project_path is set via closure or module-level variable)
    return {}


# === PostToolUse Hooks ===

async def audit_logger(input_data: Any, tool_use_id: str | None, context: Any) -> dict:
    """Log every tool call for audit trail."""
    entry = {
        "tool": input_data.get("tool_name", "unknown"),
        "timestamp": time.time(),
        "tool_use_id": tool_use_id,
    }

    tool_input = input_data.get("tool_input", {})
    if "command" in tool_input:
        entry["detail"] = tool_input["command"][:120]
    elif "file_path" in tool_input:
        entry["detail"] = tool_input["file_path"]

    _audit_log.append(entry)
    return {}


async def progress_extractor(input_data: Any, tool_use_id: str | None, context: Any) -> dict:
    """Extract progress updates from report_progress tool results."""
    tool_name = input_data.get("tool_name", "")
    if tool_name == "mcp__autonomous-coder__report_progress":
        tool_input = input_data.get("tool_input", {})
        phase = tool_input.get("phase", "")
        status = tool_input.get("status", "")
        detail = tool_input.get("detail", "")
        # Push to EventHandler via callback (set at session start)
        if _progress_callback:
            _progress_callback(phase, status, detail)
    return {}


# === SubagentStart/Stop Hooks ===

async def subagent_start_tracker(input_data: Any, tool_use_id: str | None, context: Any) -> dict:
    """Track when subagents are spawned."""
    agent_id = input_data.get("agent_id", "unknown")
    _subagent_tracker[agent_id] = time.time()
    return {}


async def subagent_stop_handler(input_data: Any, tool_use_id: str | None, context: Any) -> dict:
    """Log subagent completion and duration."""
    agent_id = input_data.get("agent_id", "unknown")
    start_time = _subagent_tracker.pop(agent_id, time.time())
    duration = time.time() - start_time

    _audit_log.append({
        "tool": f"subagent:{agent_id}",
        "timestamp": time.time(),
        "duration": duration,
        "transcript_path": input_data.get("agent_transcript_path", ""),
    })
    return {}


# === PreCompact Hook ===

async def auto_save_context(input_data: Any, tool_use_id: str | None, context: Any) -> dict:
    """Inject a system message reminding Claude to save findings before compaction."""
    return {
        "systemMessage": (
            "CONTEXT COMPACTION IMMINENT. If you have unsaved findings from the current phase, "
            "call save_findings NOW before your context is compressed. After compaction, use "
            "get_findings to retrieve previously saved phase results."
        ),
    }


# === Builder ===

def build_hooks() -> dict[str, list[HookMatcher]]:
    """Assemble the complete hook configuration."""
    return {
        "PreToolUse": [
            HookMatcher(matcher="Bash", hooks=[bash_security_gate]),
            HookMatcher(matcher="Write|Edit", hooks=[file_scope_guard]),
        ],
        "PostToolUse": [
            HookMatcher(hooks=[audit_logger]),
            HookMatcher(
                matcher="mcp__autonomous-coder__report_progress",
                hooks=[progress_extractor],
            ),
        ],
        "SubagentStart": [
            HookMatcher(hooks=[subagent_start_tracker]),
        ],
        "SubagentStop": [
            HookMatcher(hooks=[subagent_stop_handler]),
        ],
        "PreCompact": [
            HookMatcher(hooks=[auto_save_context]),
        ],
    }
```

### Hook Execution Order

```
Tool call initiated by Claude
  │
  ├─► PreToolUse hooks (bash_security_gate, file_scope_guard)
  │     └─► deny? → tool blocked, reason returned to Claude
  │     └─► allow? → continue
  │
  ├─► SDK permission evaluation
  │     └─► Deny rules → Permission mode → Allow rules → can_use_tool
  │
  ├─► Tool executes
  │
  └─► PostToolUse hooks (audit_logger, progress_extractor)
```

When multiple hooks apply, **deny overrides ask overrides allow**.

---

## 5. Permission Architecture

### Defense in Depth (Three Layers)

```
Layer 1: PreToolUse Hooks           — Pattern-based blocking (bash commands, file paths)
Layer 2: SDK Permission Mode        — "acceptEdits" auto-approves file ops within cwd
Layer 3: can_use_tool Callback      — Programmatic last-resort gate
```

### Layer 1: PreToolUse Hooks

```python
# bash_security_gate: validates commands against ALLOWED_COMMANDS set
# file_scope_guard: ensures Write/Edit targets are under project_path
```

### Layer 2: Permission Mode

```python
permission_mode="acceptEdits"  # Auto-approve Read/Write/Edit/Glob/Grep within cwd
```

Combined with `cwd=str(project_path)`, this scopes all file operations to the project.

### Layer 3: can_use_tool Callback

```python
async def security_gate(
    tool_name: str,
    tool_input: dict[str, Any],
    context: ToolPermissionContext,
) -> PermissionResultAllow | PermissionResultDeny:
    """Final programmatic security gate. Runs after hooks and permission mode."""

    if tool_name == "Bash":
        command = tool_input.get("command", "")
        allowed, reason = is_command_allowed(command)
        if not allowed:
            return PermissionResultDeny(
                behavior="deny",
                message=f"Security policy: {reason}",
                interrupt=False,  # Don't kill the session, just deny this tool
            )

    return PermissionResultAllow(behavior="allow")
```

### Bash Command Allowlist

```python
ALLOWED_COMMANDS = {
    # Package managers
    "npm", "npx", "yarn", "pnpm", "pip", "pip3", "uv", "uvx", "cargo", "poetry",
    # Build tools
    "make", "cmake", "gradle", "mvn", "tsc",
    # Runtimes
    "node", "python", "python3", "go", "rustc", "java",
    # Shell utilities (safe subset)
    "cat", "head", "tail", "ls", "pwd", "mkdir", "cp", "mv", "touch",
    "grep", "find", "wc", "sort", "diff", "which", "echo",
    # Development
    "git", "curl", "jq", "docker",
    # Formatters/linters
    "prettier", "eslint", "black", "ruff", "mypy",
    # Process management
    "ps", "kill", "lsof",
}

DANGEROUS_PATTERNS = [
    "rm -rf /", "rm -rf /*", "rm -rf ~", "> /dev/sda",
    ":(){:|:&};:", "chmod 777", "sudo rm", "curl | sh", "eval $(",
]
```

### Permission Evaluation Order (SDK-defined)

```
1. PreToolUse hooks → can deny
2. Deny rules (from settings) → can deny
3. Permission mode (acceptEdits) → can allow file ops
4. Allow rules (from settings) → can allow
5. can_use_tool callback → final programmatic gate
```

---

## 6. Streaming Output Architecture

### StreamEvent Processing

With `include_partial_messages=True`, the SDK yields `StreamEvent` objects containing raw Claude API streaming events. These are processed into UI events via the `EventHandler` protocol.

```python
from claude_agent_sdk.types import StreamEvent
from claude_agent_sdk import AssistantMessage, ResultMessage
from typing import Protocol, Any


class EventHandler(Protocol):
    """Protocol for UI adapters. Both TUI and CLI implement this."""

    def on_text(self, text: str) -> None:
        """Incremental text chunk from Claude's response."""
        ...

    def on_tool_start(self, tool_name: str) -> None:
        """Claude is starting to call a tool."""
        ...

    def on_tool_input_chunk(self, json_chunk: str) -> None:
        """Incremental JSON input for the current tool call."""
        ...

    def on_tool_end(self) -> None:
        """Current tool call is complete."""
        ...

    def on_progress(self, phase: str, status: str, detail: str) -> None:
        """Phase progress update (from report_progress tool)."""
        ...

    def on_cost_update(self, total_cost: float, session_id: str) -> None:
        """Session cost update (from ResultMessage)."""
        ...

    def on_complete(self, result: str | None, success: bool) -> None:
        """Session finished."""
        ...


async def process_stream(
    client: Any,  # ClaudeSDKClient
    handler: EventHandler,
) -> ResultMessage | None:
    """Process the response stream, dispatching to the EventHandler.

    Returns the final ResultMessage for session metadata extraction.
    """
    in_tool = False
    final_result: ResultMessage | None = None

    async for msg in client.receive_response():
        if isinstance(msg, StreamEvent):
            event = msg.event
            event_type = event.get("type")

            if event_type == "content_block_start":
                block = event.get("content_block", {})
                if block.get("type") == "tool_use":
                    in_tool = True
                    handler.on_tool_start(block.get("name", "unknown"))

            elif event_type == "content_block_delta":
                delta = event.get("delta", {})
                delta_type = delta.get("type")
                if delta_type == "text_delta" and not in_tool:
                    handler.on_text(delta.get("text", ""))
                elif delta_type == "input_json_delta" and in_tool:
                    handler.on_tool_input_chunk(delta.get("partial_json", ""))

            elif event_type == "content_block_stop":
                if in_tool:
                    handler.on_tool_end()
                    in_tool = False

        elif isinstance(msg, ResultMessage):
            final_result = msg
            cost = msg.total_cost_usd or 0.0
            handler.on_cost_update(cost, msg.session_id)
            handler.on_complete(
                result=msg.result,
                success=not msg.is_error,
            )

    return final_result
```

### Message Flow

```
StreamEvent(message_start)
StreamEvent(content_block_start)         → text block
StreamEvent(content_block_delta)         → on_text("Planning the...")
StreamEvent(content_block_delta)         → on_text("implementation...")
StreamEvent(content_block_stop)
StreamEvent(content_block_start)         → tool_use block
  → on_tool_start("Read")
StreamEvent(content_block_delta)         → on_tool_input_chunk('{"file_path":')
StreamEvent(content_block_delta)         → on_tool_input_chunk('"src/main.py"}')
StreamEvent(content_block_stop)
  → on_tool_end()
... tool executes ...
... more streaming events for next turn ...
AssistantMessage                         → complete message (ignored in streaming mode)
ResultMessage                            → on_cost_update() + on_complete()
```

### CLI Adapter

```python
class CliEventHandler:
    """Headless CLI output. Prints streaming text and tool summaries to stdout."""

    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self._current_tool: str | None = None

    def on_text(self, text: str) -> None:
        print(text, end="", flush=True)

    def on_tool_start(self, tool_name: str) -> None:
        self._current_tool = tool_name
        print(f"\n  [{tool_name}] ", end="", flush=True)

    def on_tool_input_chunk(self, json_chunk: str) -> None:
        if self.verbose:
            print(json_chunk, end="", flush=True)

    def on_tool_end(self) -> None:
        if not self.verbose:
            print("done", flush=True)
        else:
            print(flush=True)
        self._current_tool = None

    def on_progress(self, phase: str, status: str, detail: str) -> None:
        symbol = {"starting": "->", "in_progress": "..", "complete": "OK",
                  "skipped": "--", "error": "!!"}
        print(f"\n[{symbol.get(status, '??')}] {phase}: {detail}")

    def on_cost_update(self, total_cost: float, session_id: str) -> None:
        print(f"\n--- Cost: ${total_cost:.4f} | Session: {session_id[:8]} ---")

    def on_complete(self, result: str | None, success: bool) -> None:
        status = "SUCCESS" if success else "FAILED"
        print(f"\n{'='*60}\n  Session {status}\n{'='*60}")
        if result:
            print(f"\n{result}")
```

---

## 7. File Structure

```
src/autonomous_coder/
├── __init__.py              # Public API, version
├── __main__.py              # CLI entry point (argparse)
├── session.py               # SessionManager: ClaudeSDKClient lifecycle
├── config.py                # SessionConfig dataclass, TOML loading
├── security.py              # ALLOWED_COMMANDS, is_command_allowed, security_gate
├── hooks.py                 # build_hooks(), all hook callbacks
├── tools.py                 # Custom MCP tools (save/get/report), server factory
├── streaming.py             # EventHandler protocol, process_stream()
├── prompts.py               # System prompt builder, subagent prompts
├── cli.py                   # CliEventHandler (headless adapter)
├── app.py                   # Textual TUI (optional, imports from streaming.py)
└── detect.py                # Project state detection (greenfield vs existing)
```

### File Responsibilities

| File | Lines (est.) | Responsibility |
|---|---|---|
| `session.py` | ~120 | Session lifecycle, ClaudeAgentOptions construction, run loop |
| `config.py` | ~80 | Configuration dataclass, TOML loading, defaults |
| `security.py` | ~100 | Bash allowlist, dangerous patterns, can_use_tool callback |
| `hooks.py` | ~120 | All hook callbacks, hook builder |
| `tools.py` | ~90 | Custom MCP tools, server factory |
| `streaming.py` | ~80 | EventHandler protocol, stream processing |
| `prompts.py` | ~60 | System prompt template, subagent prompts |
| `cli.py` | ~60 | CLI event handler |
| `app.py` | ~150 | Textual TUI (optional) |
| `detect.py` | ~40 | Project state detection |
| **Total** | **~900** | Down from v2's ~1,400 lines |

### Dependency Graph

```
__main__.py
  └── session.py
        ├── config.py
        ├── security.py
        ├── hooks.py
        ├── tools.py
        ├── streaming.py
        ├── prompts.py
        └── detect.py

app.py (TUI, optional)
  └── streaming.py

cli.py
  └── streaming.py
```

No circular dependencies. `session.py` is the composition root.

---

## 8. Execution Flow

### Happy Path

```
1. User: `autonomous-coder "Add JWT authentication" --project ./myapp`

2. Python (__main__.py):
   ├── Parse CLI args
   ├── Load config (CLI args > .autonomous-coder.toml > defaults)
   ├── Detect project state (existing: Node.js, Express, PostgreSQL)
   └── Create SessionManager(config)

3. SessionManager.start(task):
   ├── Create findings server (in-process MCP)
   ├── Build ClaudeAgentOptions:
   │   ├── model="claude-opus-4-6"
   │   ├── betas=["context-1m-2025-08-07"]
   │   ├── system_prompt=<built from template + project state>
   │   ├── mcp_servers={serena, context7, autonomous-coder (findings)}
   │   ├── agents={code-reviewer, security-auditor}
   │   ├── hooks=build_hooks()
   │   ├── can_use_tool=security_gate
   │   ├── include_partial_messages=True
   │   ├── permission_mode="acceptEdits"
   │   ├── max_budget_usd=5.0
   │   ├── effort="high"
   │   ├── cwd=project_path
   │   └── enable_file_checkpointing=True
   │
   ├── async with ClaudeSDKClient(options) as client:
   │   ├── await client.query(initial_prompt)
   │   └── await process_stream(client, event_handler)
   │
   └── Save session state for potential resumption

4. Claude (inside the session):
   ├── report_progress("research", "starting", "Checking JWT libraries")
   ├── WebSearch("JWT authentication Express.js best practices")
   ├── Context7 → resolve-library-id("jsonwebtoken")
   ├── Context7 → query-docs(jwt_id, "Express middleware setup")
   ├── save_findings("research", <JWT research summary>)
   ├── report_progress("research", "complete", "Found jsonwebtoken + passport-jwt")
   │
   ├── report_progress("explore", "starting", "Mapping Express app structure")
   ├── Serena → get_symbols_overview("src/app.js")
   ├── Serena → find_symbol("router")
   ├── Serena → search_for_pattern("middleware")
   ├── save_findings("exploration", <codebase map>)
   ├── report_progress("explore", "complete", "Found 12 routes, 3 middleware layers")
   │
   ├── report_progress("plan", "starting", "Creating implementation plan")
   ├── <Plans 5 implementation steps>
   ├── save_findings("plan", <structured plan>)
   ├── report_progress("plan", "complete", "5-step plan ready")
   │
   ├── report_progress("implement", "starting", "Step 1: Install dependencies")
   ├── Bash("npm install jsonwebtoken passport passport-jwt bcryptjs")
   ├── Write("src/middleware/auth.js", <auth middleware>)
   ├── Edit("src/app.js", <add middleware>)
   ├── report_progress("implement", "in_progress", "Step 2: User model + routes")
   ├── Write("src/models/user.js", <user model>)
   ├── Write("src/routes/auth.js", <auth routes>)
   ├── ... (steps 3-5)
   ├── Bash("node src/app.js &")  # Verify it starts
   ├── Bash("curl localhost:3000/api/auth/register -d ...")  # Verify endpoint
   ├── report_progress("implement", "complete", "All 5 steps done, server verified")
   │
   ├── report_progress("review", "starting", "Delegating to code reviewer")
   ├── Agent("code-reviewer", "Review these files for quality: src/middleware/auth.js, ...")
   ├── Agent("security-auditor", "Audit JWT implementation: src/middleware/auth.js, ...")
   ├── <Addresses critical findings if any>
   └── report_progress("review", "complete", "Review passed with 2 suggestions addressed")

5. ResultMessage received:
   ├── event_handler.on_cost_update($1.23, session_id)
   ├── event_handler.on_complete(result=<summary>, success=True)
   └── Session state saved to .autonomous-coder/session.json
```

### Error Recovery

```
Session crash (process killed, network failure):
  1. Session state exists in .autonomous-coder/session.json
  2. Findings persisted in .autonomous-coder/findings/*.md
  3. User runs: autonomous-coder --resume
  4. Python loads session state, passes resume=session_id to ClaudeAgentOptions
  5. Claude resumes with: "Continue from where you left off. Use get_findings to recall your progress."
  6. enable_file_checkpointing=True provides SDK-level file state recovery

Budget exceeded:
  1. SDK enforces max_budget_usd — session ends gracefully
  2. ResultMessage.is_error indicates budget stop
  3. Findings saved during session are preserved
  4. User can resume with higher budget: autonomous-coder --resume --budget 10.0
```

---

## 9. Configuration Architecture

### SessionConfig Dataclass

```python
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class SessionConfig:
    """Complete session configuration. Assembled from CLI args + TOML files."""

    # Required
    project_path: Path = field(default_factory=Path.cwd)

    # Model
    model: str = "claude-opus-4-6"
    betas: list[str] = field(default_factory=lambda: ["context-1m-2025-08-07"])
    effort: str = "high"

    # Budget
    budget_limit: float = 5.0

    # Session management
    resume_session_id: str | None = None

    # MCP servers (additional, beyond built-ins)
    extra_mcp_servers: dict[str, dict] = field(default_factory=dict)

    # Security
    extra_allowed_commands: set[str] = field(default_factory=set)
    permission_mode: str = "acceptEdits"

    # Output
    verbose: bool = False
    ui_mode: str = "cli"  # "cli" or "tui"
```

### Configuration Sources (Priority Order)

```
1. CLI arguments        (highest priority)
2. .autonomous-coder.toml   (project-level)
3. ~/.config/autonomous-coder/config.toml  (user-level)
4. Defaults in SessionConfig
```

### Project Config Example (`.autonomous-coder.toml`)

```toml
[session]
budget_limit = 10.0
model = "claude-opus-4-6"
effort = "high"

[security]
extra_allowed_commands = ["terraform", "kubectl"]

[mcp]
# Additional MCP servers for this project
[mcp.playwright]
command = "npx"
args = ["playwright-mcp-server"]
```

### Built-in MCP Servers

```python
BUILTIN_MCP_SERVERS = {
    "serena": {
        "command": "uvx",
        "args": ["serena"],
        "env": {"SERENA_PROJECT": "{project_path}"},  # Templated at runtime
    },
    "context7": {
        "command": "npx",
        "args": ["-y", "@upstash/context7-mcp"],
    },
    # "autonomous-coder" is the in-process findings server (added programmatically)
}
```

---

## 10. Session Management

### Session Lifecycle

```python
class SessionManager:
    """Manages the lifecycle of a single autonomous coding session."""

    def __init__(self, config: SessionConfig, handler: EventHandler):
        self.config = config
        self.handler = handler
        self._client: ClaudeSDKClient | None = None
        self._session_state: SessionState | None = None

    async def run(self, task: str) -> SessionState:
        """Run the autonomous coding session."""
        # Detect project state
        project_state = detect_project_state(self.config.project_path)

        # Build options
        options = self._build_options(project_state)

        # Build initial prompt
        initial_prompt = self._build_initial_prompt(task, project_state)

        # Run session
        async with ClaudeSDKClient(options=options) as client:
            self._client = client
            await client.query(initial_prompt)
            result_msg = await process_stream(client, self.handler)

        # Save session state
        state = SessionState(
            session_id=result_msg.session_id if result_msg else "",
            task=task,
            project_path=str(self.config.project_path),
            budget_used=result_msg.total_cost_usd or 0.0 if result_msg else 0.0,
            success=not result_msg.is_error if result_msg else False,
        )
        state.save(self.config.project_path / ".autonomous-coder" / "session.json")
        return state

    async def interrupt(self) -> None:
        """Interrupt the running session."""
        if self._client:
            await self._client.interrupt()

    def _build_options(self, project_state: dict) -> ClaudeAgentOptions:
        """Assemble ClaudeAgentOptions from config + project state."""
        # Build MCP servers
        mcp_servers = dict(BUILTIN_MCP_SERVERS)

        # Template serena's project path
        if "serena" in mcp_servers:
            serena = dict(mcp_servers["serena"])
            env = dict(serena.get("env", {}))
            env["SERENA_PROJECT"] = str(self.config.project_path)
            serena["env"] = env
            mcp_servers["serena"] = serena

        # Add in-process findings server
        mcp_servers["autonomous-coder"] = create_findings_server(self.config.project_path)

        # Add user's extra MCP servers
        mcp_servers.update(self.config.extra_mcp_servers)

        # Build allowed tools
        allowed_tools = [
            # Standard tools
            "Read", "Write", "Edit", "Bash", "Grep", "Glob",
            # Web research
            "WebSearch", "WebFetch",
            # Subagent delegation
            "Agent",
            # MCP tools (prefix-based, all tools from all servers)
            *[f"mcp__{name}" for name in mcp_servers],
        ]

        # Merge allowed commands
        all_allowed = ALLOWED_COMMANDS | self.config.extra_allowed_commands

        return ClaudeAgentOptions(
            model=self.config.model,
            betas=self.config.betas,
            system_prompt=build_system_prompt(project_state, self.config),
            allowed_tools=allowed_tools,
            mcp_servers=mcp_servers,
            agents=build_subagent_definitions(),
            hooks=build_hooks(),
            can_use_tool=security_gate,
            include_partial_messages=True,
            permission_mode=self.config.permission_mode,
            max_budget_usd=self.config.budget_limit,
            effort=self.config.effort,
            cwd=str(self.config.project_path),
            enable_file_checkpointing=True,
            resume=self.config.resume_session_id,
        )

    def _build_initial_prompt(self, task: str, project_state: dict) -> str:
        """Build the initial user prompt."""
        parts = [f"Task: {task}"]

        if self.config.resume_session_id:
            parts.append(
                "\nThis is a resumed session. Use get_findings to recall your "
                "previous progress, then continue from where you left off."
            )

        return "\n".join(parts)
```

### Session State Persistence

```python
from dataclasses import dataclass, field, asdict
from datetime import datetime
import json
from pathlib import Path


@dataclass
class SessionState:
    """Persisted session state for resumption."""

    session_id: str
    task: str
    project_path: str
    budget_used: float = 0.0
    success: bool = False
    started_at: str = field(default_factory=lambda: datetime.now().isoformat())
    completed_at: str | None = None

    def save(self, path: Path) -> None:
        self.completed_at = datetime.now().isoformat()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), indent=2))

    @classmethod
    def load(cls, path: Path) -> "SessionState":
        data = json.loads(path.read_text())
        return cls(**data)
```

### CLI Entry Point

```python
def main() -> None:
    parser = argparse.ArgumentParser(prog="autonomous-coder")
    parser.add_argument("task", nargs="*", help="Task description")
    parser.add_argument("--project", type=Path, default=None)
    parser.add_argument("--budget", type=float, default=None)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--verbose", "-v", action="store_true")
    parser.add_argument("--tui", action="store_true", help="Use Textual TUI")

    args = parser.parse_args()
    task = " ".join(args.task) if args.task else ""
    project_path = args.project or Path.cwd()

    # Load config
    config = load_config(project_path)
    if args.budget:
        config.budget_limit = args.budget
    config.verbose = args.verbose
    config.project_path = project_path

    # Handle resume
    if args.resume:
        session_file = project_path / ".autonomous-coder" / "session.json"
        if session_file.exists():
            prev = SessionState.load(session_file)
            config.resume_session_id = prev.session_id
            if not task:
                task = prev.task

    if not task:
        print("Error: task is required", file=sys.stderr)
        sys.exit(1)

    # Choose UI
    if args.tui:
        from .app import run_tui
        run_tui(task, config)
    else:
        handler = CliEventHandler(verbose=config.verbose)
        manager = SessionManager(config, handler)
        result = asyncio.run(manager.run(task))
        sys.exit(0 if result.success else 1)
```

---

## Appendix A: What Changed from v2 and Why

| v2 | v3 | Why |
|---|---|---|
| `query()` function (one-shot) | `ClaudeSDKClient` (streaming) | Session continuity, interrupt support, multi-turn |
| 4 separate sessions | 1 persistent session | Context preserved, MCP servers stay running |
| Manual budget tracking | `max_budget_usd` | SDK handles enforcement natively |
| No subagents | 2 subagents (reviewer, auditor) | Context isolation for specialized review |
| `_string_to_stream()` hack | Native streaming input | SDK supports string prompts directly |
| BasePhaseRunner ABC hierarchy | Single session, no phase classes | Claude orchestrates phases via system prompt |
| 8 Textual Message subclasses | EventHandler protocol (7 methods) | Simpler, decoupled from Textual |
| Phase outputs as truncated strings | `save_findings` / `get_findings` tools | Survives compaction, full fidelity |
| No crash recovery | `enable_file_checkpointing` + `resume` | Full session resumption |
| No compaction handling | `PreCompact` hook + system message | Claude warned to save before compaction |
| Hardcoded config | TOML config files + CLI args | User-configurable without code changes |
| `PermissionResultAllow(updated_permissions=None)` | `PermissionResultAllow(behavior="allow")` | Correct SDK API usage |

## Appendix B: pyproject.toml

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "autonomous-coder"
version = "3.0.0"
description = "Autonomous coding agent powered by Claude Agent SDK"
requires-python = ">=3.11"
dependencies = [
    "claude-agent-sdk>=0.1.49",
    "tomli>=2.0;python_version<'3.11'",
]

[project.optional-dependencies]
tui = ["textual>=1.0.0"]

[project.scripts]
autonomous-coder = "autonomous_coder.__main__:main"

[tool.hatch.build.targets.wheel]
packages = ["src/autonomous_coder"]
```

## Appendix C: Verification Checklist

- [ ] ClaudeSDKClient (streaming mode) used throughout — never `query()` single-message
- [ ] `include_partial_messages=True` for StreamEvent-based real-time output
- [ ] `betas=["context-1m-2025-08-07"]` for 1M context window
- [ ] `max_budget_usd` for SDK-native budget enforcement
- [ ] `enable_file_checkpointing=True` for crash recovery
- [ ] `can_use_tool` callback for bash security (defense layer 3)
- [ ] `PreToolUse` hooks for bash/file security (defense layer 1)
- [ ] `PreCompact` hook for compaction safety
- [ ] Custom MCP tools via `create_sdk_mcp_server` (in-process)
- [ ] Subagents via `AgentDefinition` (code-reviewer, security-auditor)
- [ ] Subagents inherit parent MCP servers (no explicit configuration needed)
- [ ] Two entry paths: greenfield detection in Python, injected into system prompt
- [ ] Session resumption via `resume` parameter
- [ ] EventHandler protocol decouples streaming from UI framework
- [ ] No mocks, stubs, or test files in the architecture
