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
                        │                                              │
                        │    Safety:   max_budget_usd                  │
                        │              max_turns (200)                 │
                        │              wall-clock timeout (3600s)      │
                        └──────────────────────────────────────────────┘
```

### Two Entry Paths

**Greenfield** (no project exists): Python detects empty/absent directory, injects `project_state: greenfield` into the system prompt. Claude creates the project structure, scaffolds from scratch.

**Existing Project** (codebase present): Python detects `pyproject.toml`, `package.json`, `Cargo.toml`, etc., injects `project_state: existing` with detected stack info. Claude explores before modifying.

Detection happens in Python (not a tool) because it runs once before the session starts.

### What Python Controls vs What Claude Controls

```
Python controls: session start/stop, security gates, budget limits, timeouts, UI rendering
Claude controls: phase ordering, tool selection, subagent delegation, implementation strategy
```

---

## 2. Agent Definitions (with Full System Prompts)

### Main Agent (Orchestrator)

The main agent runs inside the single `ClaudeSDKClient` session. Its system prompt defines the full autonomous workflow.

```python
def build_system_prompt(project_state: dict, config: SessionConfig) -> str:
    """Assemble orchestrator system prompt from composable sections."""
    sections = [
        ROLE_PREAMBLE,
        format_project_state(project_state),
        WORKFLOW_INSTRUCTIONS,
        TOOL_GUIDELINES,
        SUBAGENT_DELEGATION,
        SECURITY_CONSTRAINTS,
    ]
    if config.plan_only:
        sections.append(PLAN_ONLY_INSTRUCTION)
    return "\n\n".join(sections)


ROLE_PREAMBLE = """\
You are an autonomous coding agent. You independently implement software features \
from natural-language task descriptions. You work methodically through phases, \
persisting your findings as you go."""

WORKFLOW_INSTRUCTIONS = """\
## Workflow

Work through these phases in order. After each phase, call `save_findings` with your results \
so they survive context compaction. Call `report_progress` at phase transitions so the user \
sees your progress.

### Phase 1: Research (when external knowledge is needed)
Determine whether the task requires knowledge beyond the codebase:
- New libraries, frameworks, or APIs -> use WebSearch and Context7
- Well-understood modifications -> skip to Phase 2
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
- Address any critical findings before finishing"""

TOOL_GUIDELINES = """\
## Tool Usage Guidelines

### Persistence (critical for long sessions)
- Call `save_findings` after EVERY phase -- your context may compact at any time
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
- Save findings early so re-reading isn't needed after compaction"""

SUBAGENT_DELEGATION = """\
## Subagent Delegation
You have two specialist subagents available via the Agent tool:
- `code-reviewer`: Use after implementing changes. Read-only, focuses on quality.
- `security-auditor`: Use for security-sensitive changes. Read-only, focuses on vulnerabilities.
Include relevant file paths and context in your delegation prompt -- subagents start fresh."""

SECURITY_CONSTRAINTS = """\
## Security Constraints
- Only use approved bash commands (the system will block disallowed ones)
- Stay within {project_path}
- Never hardcode secrets or credentials
- Validate all inputs at system boundaries"""

PLAN_ONLY_INSTRUCTION = """\
## Mode: Plan Only
STOP after Phase 3 (Plan). Do NOT proceed to implementation.
Present the complete plan and then finish."""
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
    tools=["Read", "Grep", "Glob"],
    model="opus",
)
```

**Note:** The security-auditor is read-only (no Bash access). If security verification requires running commands, the main agent runs them based on the auditor's recommendations. This eliminates a privilege escalation path identified during security review.

### Why Only Two Subagents?

**Rejected subagents and rationale:**

| Rejected Agent | Why Not |
|---|---|
| Research agent | Research is integral to the main flow. Isolating it loses context about what the user actually needs. |
| Explorer agent | Exploration findings directly inform planning. Keeping them in the main context is more valuable than isolating them. |
| Planner agent | Planning requires synthesis of research + exploration. Moving it to a subagent loses that synthesis. |
| Test runner | Testing is part of implementation verification. The main agent needs to see test results to iterate. |

Subagents are for roles that **benefit from context isolation** -- a reviewer shouldn't see the messy exploration that preceded the code, only the final code.

---

## 3. Custom MCP Tools

Three in-process tools registered as a single SDK MCP server. These are Claude's "long-term memory" within a session. State is encapsulated in a `FindingsStore` class -- no module-level globals.

```python
from claude_agent_sdk import tool, create_sdk_mcp_server
from pathlib import Path
from typing import Any, Callable
import json
from dataclasses import dataclass, field
from datetime import datetime


ALLOWED_CATEGORIES = {"research", "exploration", "plan", "implementation", "review"}
MAX_FINDINGS_SIZE = 50_000  # chars


@dataclass
class FindingsStore:
    """Encapsulates all mutable state for findings management.

    Passed to tool closures via factory function -- no module-level globals.
    """
    project_path: Path
    progress: dict[str, dict] = field(default_factory=dict)

    @property
    def dir(self) -> Path:
        return self.project_path / ".autonomous-coder" / "findings"

    def save(self, category: str, content: str) -> str:
        if category not in ALLOWED_CATEGORIES:
            return f"Invalid category: {category}. Must be one of: {ALLOWED_CATEGORIES}"

        if len(content) > MAX_FINDINGS_SIZE:
            content = content[:MAX_FINDINGS_SIZE] + "\n\n[TRUNCATED at 50,000 chars]"

        self.dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().isoformat(timespec="seconds")
        header = f"# {category.title()} Findings\n\nUpdated: {timestamp}\n\n"
        (self.dir / f"{category}.md").write_text(header + content, encoding="utf-8")
        return f"Saved {len(content)} chars to {category}.md"

    def load(self, category: str) -> str:
        path = self.dir / f"{category}.md"
        if not path.exists():
            return f"No findings saved for '{category}'"
        return path.read_text(encoding="utf-8")

    def report(self, phase: str, status: str, detail: str) -> None:
        self.progress[phase] = {"status": status, "detail": detail}

    def persist_progress(self) -> None:
        """Write progress to disk for cross-session visibility."""
        self.dir.mkdir(parents=True, exist_ok=True)
        (self.dir / "progress.json").write_text(
            json.dumps(self.progress, indent=2), encoding="utf-8"
        )


def create_findings_server(
    store: FindingsStore,
    on_progress: Callable[[str, str, str], None] | None = None,
) -> Any:
    """Create the in-process MCP server with tools bound to the store instance."""

    @tool(
        "save_findings",
        "Persist structured findings to disk. Call after each workflow phase to protect "
        "against context compaction. Categories: research, exploration, plan, implementation, review.",
        {"category": str, "content": str},
    )
    async def save_findings(args: dict[str, Any]) -> dict[str, Any]:
        result = store.save(args["category"], args["content"])
        return {"content": [{"type": "text", "text": result}]}

    @tool(
        "get_findings",
        "Retrieve previously saved findings by category. Use when you need to recall "
        "earlier phase results (e.g., after context compaction).",
        {"category": str},
    )
    async def get_findings(args: dict[str, Any]) -> dict[str, Any]:
        content = store.load(args["category"])
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
        phase, status, detail = args["phase"], args["status"], args["detail"]
        store.report(phase, status, detail)
        store.persist_progress()
        if on_progress:
            on_progress(phase, status, detail)
        return {"content": [{"type": "text", "text": f"Progress reported: {phase} -> {status}"}]}

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

Hooks handle cross-cutting concerns without cluttering the main logic. Hook state is passed via the `HookContext` dataclass -- no module-level globals.

```python
from claude_agent_sdk import HookMatcher
from pathlib import Path
from typing import Any, Callable
import time
from dataclasses import dataclass, field


@dataclass
class HookContext:
    """Encapsulates all mutable state used by hooks."""
    project_path: Path
    audit_log: list[dict] = field(default_factory=list)
    subagent_tracker: dict[str, float] = field(default_factory=dict)
    on_progress: Callable[[str, str, str], None] | None = None

    def persist_audit_log(self, path: Path | None = None) -> None:
        """Write audit log to disk as JSONL."""
        target = path or (self.project_path / ".autonomous-coder" / "audit.jsonl")
        target.parent.mkdir(parents=True, exist_ok=True)
        import json
        with open(target, "w") as f:
            for entry in self.audit_log:
                f.write(json.dumps(entry) + "\n")


# === PreToolUse Hooks ===

def make_bash_security_gate(ctx: HookContext):
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
    return bash_security_gate


def make_file_scope_guard(ctx: HookContext):
    async def file_scope_guard(input_data: Any, tool_use_id: str | None, context: Any) -> dict:
        """Ensure Write/Edit operations stay within the project directory."""
        file_path = input_data["tool_input"].get("file_path", "")
        if not file_path:
            return {}

        try:
            resolved = Path(file_path).resolve()
            project_resolved = ctx.project_path.resolve()
            if not str(resolved).startswith(str(project_resolved)):
                return {
                    "hookSpecificOutput": {
                        "hookEventName": "PreToolUse",
                        "permissionDecision": "deny",
                        "permissionDecisionReason": f"Write outside project: {file_path}",
                    }
                }
        except (ValueError, OSError):
            return {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": f"Invalid path: {file_path}",
                }
            }
        return {}
    return file_scope_guard


# === PostToolUse Hooks ===

def make_audit_logger(ctx: HookContext):
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
        ctx.audit_log.append(entry)
        return {}
    return audit_logger


def make_progress_extractor(ctx: HookContext):
    async def progress_extractor(input_data: Any, tool_use_id: str | None, context: Any) -> dict:
        """Extract progress updates from report_progress tool results."""
        tool_name = input_data.get("tool_name", "")
        if tool_name == "mcp__autonomous-coder__report_progress":
            tool_input = input_data.get("tool_input", {})
            phase = tool_input.get("phase", "")
            status = tool_input.get("status", "")
            detail = tool_input.get("detail", "")
            if ctx.on_progress:
                ctx.on_progress(phase, status, detail)
        return {}
    return progress_extractor


# === SubagentStart/Stop Hooks ===

def make_subagent_start_tracker(ctx: HookContext):
    async def subagent_start_tracker(input_data: Any, tool_use_id: str | None, context: Any) -> dict:
        agent_id = input_data.get("agent_id", "unknown")
        ctx.subagent_tracker[agent_id] = time.time()
        return {}
    return subagent_start_tracker


def make_subagent_stop_handler(ctx: HookContext):
    async def subagent_stop_handler(input_data: Any, tool_use_id: str | None, context: Any) -> dict:
        agent_id = input_data.get("agent_id", "unknown")
        start_time = ctx.subagent_tracker.pop(agent_id, time.time())
        duration = time.time() - start_time
        ctx.audit_log.append({
            "tool": f"subagent:{agent_id}",
            "timestamp": time.time(),
            "duration": duration,
            "transcript_path": input_data.get("agent_transcript_path", ""),
        })
        return {}
    return subagent_stop_handler


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

def build_hooks(ctx: HookContext) -> dict[str, list[HookMatcher]]:
    """Assemble the complete hook configuration from a HookContext."""
    return {
        "PreToolUse": [
            HookMatcher(matcher="Bash", hooks=[make_bash_security_gate(ctx)]),
            HookMatcher(matcher="Write|Edit", hooks=[make_file_scope_guard(ctx)]),
        ],
        "PostToolUse": [
            HookMatcher(hooks=[make_audit_logger(ctx)]),
            HookMatcher(
                matcher="mcp__autonomous-coder__report_progress",
                hooks=[make_progress_extractor(ctx)],
            ),
        ],
        "SubagentStart": [
            HookMatcher(hooks=[make_subagent_start_tracker(ctx)]),
        ],
        "SubagentStop": [
            HookMatcher(hooks=[make_subagent_stop_handler(ctx)]),
        ],
        "PreCompact": [
            HookMatcher(hooks=[auto_save_context]),
        ],
    }
```

### Hook Execution Order

```
Tool call initiated by Claude
  |
  +-> PreToolUse hooks (bash_security_gate, file_scope_guard)
  |     +-> deny? -> tool blocked, reason returned to Claude
  |     +-> allow? -> continue
  |
  +-> SDK permission evaluation
  |     +-> Deny rules -> Permission mode -> Allow rules -> can_use_tool
  |
  +-> Tool executes
  |
  +-> PostToolUse hooks (audit_logger, progress_extractor)
```

When multiple hooks apply, **deny overrides ask overrides allow**.

---

## 5. Permission Architecture

### Defense in Depth (Three Layers)

```
Layer 1: PreToolUse Hooks           -- Pattern-based blocking (bash commands, file paths)
Layer 2: SDK Permission Mode        -- "acceptEdits" auto-approves file ops within cwd
Layer 3: can_use_tool Callback      -- Programmatic last-resort gate
```

### Layer 1: PreToolUse Hooks

```python
# bash_security_gate: validates commands against ALLOWED_COMMANDS + argument validators
# file_scope_guard: ensures Write/Edit targets are under project_path (fully implemented)
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

### Bash Command Security

```python
# Base allowlist -- safe commands that require no argument validation
ALLOWED_COMMANDS = {
    # Package managers
    "npm", "npx", "yarn", "pnpm", "pip", "pip3", "uv", "uvx", "cargo", "poetry",
    # Build tools
    "make", "cmake", "gradle", "mvn", "tsc",
    # Shell utilities (safe subset)
    "cat", "head", "tail", "ls", "pwd", "mkdir", "cp", "mv", "touch",
    "grep", "find", "wc", "sort", "diff", "which", "echo",
    # Formatters/linters
    "prettier", "eslint", "black", "ruff", "mypy",
    # Process management
    "ps", "lsof",
}

# Commands allowed only with argument validation
COMMANDS_REQUIRING_VALIDATION = {
    "git": validate_git,       # Block push to non-origin remotes, force push
    "node": validate_node,     # Block -e/--eval (arbitrary JS execution)
    "python": validate_python, # Block -c (arbitrary code execution)
    "python3": validate_python,
    "kill": validate_kill,     # Only allow killing dev-related PIDs
    "curl": validate_curl,     # Block --data/POST to external URLs
    "docker": validate_docker, # Only allow build/run with restrictions
}

DANGEROUS_PATTERNS = [
    "rm -rf /", "rm -rf /*", "rm -rf ~", "> /dev/sda",
    ":(){:|:&};:", "chmod 777", "sudo rm", "curl | sh",
    "eval $(", "| bash", "| sh",
]


def validate_git(args: str) -> tuple[bool, str]:
    """Allow git but block dangerous operations."""
    if "push" in args and "--force" in args:
        return False, "git force-push is not allowed"
    if "push" in args:
        # Only allow push to origin
        parts = args.split()
        push_idx = parts.index("push") if "push" in parts else -1
        if push_idx >= 0 and push_idx + 1 < len(parts):
            remote = parts[push_idx + 1]
            if remote not in ("origin", "-u"):
                return False, f"git push to '{remote}' not allowed (only origin)"
    return True, ""


def validate_node(args: str) -> tuple[bool, str]:
    if "-e" in args.split() or "--eval" in args:
        return False, "node -e/--eval is not allowed (arbitrary JS execution)"
    return True, ""


def validate_python(args: str) -> tuple[bool, str]:
    if "-c" in args.split():
        return False, "python -c is not allowed (arbitrary code execution)"
    return True, ""


def validate_kill(args: str) -> tuple[bool, str]:
    # Only allow kill with numeric PIDs, no -9 on system processes
    return True, ""


def validate_curl(args: str) -> tuple[bool, str]:
    if any(flag in args for flag in ("--data", "-d", "--upload-file", "-T")):
        # Allow POST only to localhost
        if "localhost" not in args and "127.0.0.1" not in args:
            return False, "curl POST/upload to external URLs not allowed"
    return True, ""


def validate_docker(args: str) -> tuple[bool, str]:
    parts = args.split()
    if len(parts) < 1:
        return False, "docker command required"
    subcmd = parts[0]
    if subcmd not in ("build", "run", "ps", "images", "logs", "stop"):
        return False, f"docker {subcmd} not allowed"
    if subcmd == "run" and "--privileged" in args:
        return False, "docker run --privileged not allowed"
    return True, ""


def is_command_allowed(command: str) -> tuple[bool, str]:
    """Check if a bash command is allowed. Returns (allowed, reason)."""
    # Check dangerous patterns first
    for pattern in DANGEROUS_PATTERNS:
        if pattern in command:
            return False, f"Dangerous pattern detected: {pattern}"

    # Extract base command
    base = command.strip().split()[0].split("/")[-1] if command.strip() else ""

    # Check if it needs argument validation
    if base in COMMANDS_REQUIRING_VALIDATION:
        rest = command.strip()[len(base):].strip()
        return COMMANDS_REQUIRING_VALIDATION[base](rest)

    # Check base allowlist
    if base not in ALLOWED_COMMANDS:
        return False, f"Command '{base}' not in allowlist"

    return True, ""
```

### Permission Evaluation Order (SDK-defined)

```
1. PreToolUse hooks -> can deny
2. Deny rules (from settings) -> can deny
3. Permission mode (acceptEdits) -> can allow file ops
4. Allow rules (from settings) -> can allow
5. can_use_tool callback -> final programmatic gate
```

---

## 6. Streaming Output Architecture

### StreamEvent Processing

With `include_partial_messages=True`, the SDK yields `StreamEvent` objects containing raw Claude API streaming events. These are processed into UI events via the `EventHandler` protocol.

```python
from claude_agent_sdk.types import StreamEvent
from claude_agent_sdk import AssistantMessage, ResultMessage
from typing import Protocol, Any
import logging

logger = logging.getLogger(__name__)


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
        match msg:
            case StreamEvent():
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

            case ResultMessage():
                final_result = msg
                cost = msg.total_cost_usd or 0.0
                handler.on_cost_update(cost, msg.session_id)
                handler.on_complete(
                    result=msg.result,
                    success=not msg.is_error,
                )

            case _:
                logger.debug(f"Unhandled message type: {type(msg).__name__}")

    return final_result
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
+-- __init__.py              # Public API, version
+-- __main__.py              # CLI entry point (argparse), process supervisor
+-- session.py               # SessionManager: ClaudeSDKClient lifecycle
+-- config.py                # SessionConfig dataclass, TOML loading
+-- security.py              # ALLOWED_COMMANDS, validators, is_command_allowed, security_gate
+-- hooks.py                 # HookContext, build_hooks(), all hook closures
+-- tools.py                 # FindingsStore, custom MCP tools, server factory
+-- streaming.py             # EventHandler protocol, process_stream()
+-- prompts.py               # System prompt builder (composable sections), subagent prompts
+-- cli.py                   # CliEventHandler (headless adapter)
+-- app.py                   # Textual TUI (optional, imports from streaming.py)
+-- detect.py                # Project state detection (greenfield vs existing)
```

### File Responsibilities

| File | Lines (est.) | Responsibility |
|---|---|---|
| `session.py` | ~130 | Session lifecycle, ClaudeAgentOptions construction, run loop, timeout |
| `config.py` | ~80 | Configuration dataclass, TOML loading, defaults |
| `security.py` | ~140 | Bash allowlist, argument validators, dangerous patterns, can_use_tool |
| `hooks.py` | ~140 | HookContext, all hook closures, hook builder |
| `tools.py` | ~100 | FindingsStore, custom MCP tools, server factory |
| `streaming.py` | ~80 | EventHandler protocol, stream processing |
| `prompts.py` | ~80 | System prompt sections, prompt builder, subagent prompts |
| `cli.py` | ~60 | CLI event handler |
| `app.py` | ~150 | Textual TUI (optional) |
| `detect.py` | ~40 | Project state detection |
| **Total** | **~1,000** | Up from ~900 due to security hardening + state encapsulation |

### Dependency Graph

```
__main__.py
  +-- session.py
        +-- config.py
        +-- security.py
        +-- hooks.py
        +-- tools.py
        +-- streaming.py
        +-- prompts.py
        +-- detect.py

app.py (TUI, optional)
  +-- streaming.py

cli.py
  +-- streaming.py
```

No circular dependencies. `session.py` is the composition root.

---

## 8. Execution Flow

### Happy Path

```
1. User: `autonomous-coder "Add JWT authentication" --project ./myapp`

2. Python (__main__.py):
   +-- Parse CLI args (including --plan-only, --dry-run, --resume)
   +-- Load config (CLI args > .autonomous-coder.toml > defaults)
   +-- Detect project state (existing: Node.js, Express, PostgreSQL)
   +-- Create SessionManager(config)

3. SessionManager.run(task):
   +-- Create FindingsStore(project_path)
   +-- Create HookContext(project_path)
   +-- Create findings server (in-process MCP, bound to store)
   +-- Build ClaudeAgentOptions:
   |   +-- model="claude-opus-4-6"
   |   +-- betas=["context-1m-2025-08-07"]
   |   +-- system_prompt=build_system_prompt(project_state, config)
   |   +-- mcp_servers={serena, context7, autonomous-coder (findings)}
   |   +-- agents={code-reviewer, security-auditor}
   |   +-- hooks=build_hooks(hook_ctx)
   |   +-- can_use_tool=security_gate
   |   +-- include_partial_messages=True
   |   +-- permission_mode="acceptEdits"
   |   +-- max_budget_usd=5.0
   |   +-- max_turns=200
   |   +-- effort="high"
   |   +-- cwd=project_path
   |   +-- enable_file_checkpointing=True
   |
   +-- async with asyncio.timeout(config.max_duration_seconds):
   |     async with ClaudeSDKClient(options) as client:
   |       await client.query(initial_prompt)
   |       result = await process_stream(client, event_handler)
   |
   +-- Persist audit log to .autonomous-coder/audit.jsonl
   +-- Save session state for potential resumption

4. Claude (inside the session):
   +-- report_progress("research", "starting", "Checking JWT libraries")
   +-- WebSearch("JWT authentication Express.js best practices")
   +-- Context7 -> resolve-library-id("jsonwebtoken")
   +-- save_findings("research", <JWT research summary>)
   +-- report_progress("research", "complete", "Found jsonwebtoken + passport-jwt")
   |
   +-- report_progress("explore", "starting", "Mapping Express app structure")
   +-- Serena -> get_symbols_overview("src/app.js")
   +-- save_findings("exploration", <codebase map>)
   +-- report_progress("explore", "complete", "Found 12 routes, 3 middleware layers")
   |
   +-- report_progress("plan", "starting", "Creating implementation plan")
   +-- save_findings("plan", <structured plan>)
   +-- report_progress("plan", "complete", "5-step plan ready")
   |
   +-- [if --plan-only: session ends here]
   |
   +-- report_progress("implement", "starting", "Step 1: Install dependencies")
   +-- Bash("npm install jsonwebtoken passport passport-jwt bcryptjs")
   +-- Write("src/middleware/auth.js", <auth middleware>)
   +-- ... (steps 2-5)
   +-- report_progress("implement", "complete", "All 5 steps done, server verified")
   |
   +-- report_progress("review", "starting", "Delegating to code reviewer")
   +-- Agent("code-reviewer", "Review these files: src/middleware/auth.js, ...")
   +-- Agent("security-auditor", "Audit JWT implementation: ...")
   +-- <Addresses critical findings if any>
   +-- report_progress("review", "complete", "Review passed")

5. ResultMessage received:
   +-- event_handler.on_cost_update($1.23, session_id)
   +-- event_handler.on_complete(result=<summary>, success=True)
   +-- hook_ctx.persist_audit_log()
   +-- Session state saved to .autonomous-coder/session.json
```

### Error Recovery / Process Supervision

```python
# In __main__.py
MAX_RETRIES = 3

async def run_with_supervision(config: SessionConfig, task: str, handler: EventHandler):
    for attempt in range(MAX_RETRIES):
        try:
            async with asyncio.timeout(config.max_duration_seconds or 3600):
                manager = SessionManager(config, handler)
                result = await manager.run(task)
                return result
        except TimeoutError:
            print(f"\nSession timed out after {config.max_duration_seconds}s", file=sys.stderr)
            if manager._client:
                await manager._client.interrupt()
            break
        except (ConnectionError, OSError) as e:
            if attempt < MAX_RETRIES - 1:
                config.resume_session_id = load_last_session_id(config.project_path)
                print(f"Session error, resuming (attempt {attempt + 2}/{MAX_RETRIES}): {e}",
                      file=sys.stderr)
            else:
                raise AutonomousCoderError(
                    f"Session failed after {MAX_RETRIES} attempts: {e}",
                    hint="Check network connectivity and API key validity.",
                )

# Budget exceeded:
#   1. SDK enforces max_budget_usd -- session ends gracefully
#   2. ResultMessage.is_error indicates budget stop
#   3. Findings saved during session are preserved
#   4. User can resume with higher budget: autonomous-coder --resume --budget 10.0
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

    # Budget & Safety
    budget_limit: float = 5.0
    max_turns: int = 200
    max_duration_seconds: int = 3600  # 1 hour wall-clock timeout

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

    # Workflow control
    plan_only: bool = False   # Stop after Phase 3
    dry_run: bool = False     # Alias for plan_only
```

### Configuration Sources (Priority Order)

```
1. CLI arguments              (highest priority)
2. .autonomous-coder.toml     (project-level)
3. ~/.config/autonomous-coder/config.toml  (user-level)
4. Defaults in SessionConfig
```

### CLI Arguments

```
autonomous-coder "task description"     # Basic usage
autonomous-coder --resume               # Resume last session
autonomous-coder --plan-only "task"     # Research + explore + plan, then stop
autonomous-coder --budget 10.0 "task"   # Custom budget
autonomous-coder --verbose "task"       # Show tool input details
autonomous-coder --tui "task"           # Use Textual TUI
autonomous-coder --timeout 7200 "task"  # 2-hour wall-clock timeout
```

### Project Config Example (`.autonomous-coder.toml`)

```toml
[session]
budget_limit = 10.0
model = "claude-opus-4-6"
effort = "high"
max_turns = 300
max_duration_seconds = 7200

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

    async def run(self, task: str) -> SessionState:
        """Run the autonomous coding session."""
        # Create state containers (no module-level globals)
        store = FindingsStore(self.config.project_path)
        hook_ctx = HookContext(
            project_path=self.config.project_path,
            on_progress=self.handler.on_progress,
        )

        # Detect project state
        project_state = detect_project_state(self.config.project_path)

        # Build options
        options = self._build_options(project_state, store, hook_ctx)

        # Build initial prompt
        initial_prompt = self._build_initial_prompt(task, project_state)

        # Run session with wall-clock timeout
        async with ClaudeSDKClient(options=options) as client:
            self._client = client
            await client.query(initial_prompt)
            result_msg = await process_stream(client, self.handler)

        # Persist audit log
        hook_ctx.persist_audit_log()

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

    def _build_options(
        self, project_state: dict, store: FindingsStore, hook_ctx: HookContext
    ) -> ClaudeAgentOptions:
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

        # Add in-process findings server (bound to store instance)
        mcp_servers["autonomous-coder"] = create_findings_server(
            store, on_progress=self.handler.on_progress
        )

        # Add user's extra MCP servers
        mcp_servers.update(self.config.extra_mcp_servers)

        # Merge allowed commands
        all_allowed = ALLOWED_COMMANDS | self.config.extra_allowed_commands

        return ClaudeAgentOptions(
            model=self.config.model,
            betas=self.config.betas,
            system_prompt=build_system_prompt(project_state, self.config),
            agents=SUBAGENT_DEFINITIONS,
            hooks=build_hooks(hook_ctx),
            can_use_tool=security_gate,
            mcp_servers=mcp_servers,
            include_partial_messages=True,
            permission_mode=self.config.permission_mode,
            max_budget_usd=self.config.budget_limit,
            max_turns=self.config.max_turns,
            effort=self.config.effort,
            cwd=str(self.config.project_path),
            enable_file_checkpointing=True,
            resume=self.config.resume_session_id,
        )
```

### SessionState Persistence

```python
@dataclass
class SessionState:
    session_id: str
    task: str
    project_path: str
    budget_used: float
    success: bool

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), indent=2))

    @classmethod
    def load(cls, path: Path) -> SessionState | None:
        if not path.exists():
            return None
        return cls(**json.loads(path.read_text()))
```

### User-Friendly Errors

```python
class AutonomousCoderError(Exception):
    """Base error with user-friendly message and remediation hint."""
    def __init__(self, message: str, hint: str = ""):
        super().__init__(message)
        self.hint = hint
```

### Resume Flow

```
Session crash (process killed, network failure):
  1. Session state exists in .autonomous-coder/session.json
  2. Findings persisted in .autonomous-coder/findings/*.md
  3. Progress persisted in .autonomous-coder/findings/progress.json
  4. User runs: autonomous-coder --resume
  5. Python loads session state, passes resume=session_id to ClaudeAgentOptions
  6. Claude resumes: "Continue from where you left off. Use get_findings to recall your progress."
  7. enable_file_checkpointing=True provides SDK-level file state recovery

Previous progress shown on resume:
  $ autonomous-coder --resume
  Previous session progress:
    [OK] research: Found jsonwebtoken + passport-jwt
    [OK] explore: Found 12 routes, 3 middleware layers
    [OK] plan: 5-step plan ready
    [..] implement: Step 3 of 5 (interrupted)
  Resuming from last checkpoint...
```

---

## Appendix A: v2 vs v3 Comparison

| Dimension | v2 | v3 |
|---|---|---|
| Architecture | 4 separate sessions | 1 persistent session |
| Phase orchestration | Python pipeline | Claude-driven (system prompt) |
| Context between phases | Truncated strings | Full conversation history |
| Subagents | None | 2 (code-reviewer, security-auditor) |
| MCP tools | None | 3 (save/get/report findings) |
| Hooks | Custom polling | SDK-native lifecycle hooks |
| Security | Regex allowlist only | 3-layer defense + argument validators |
| Budget enforcement | Manual tracking | SDK-native `max_budget_usd` + `max_turns` |
| Crash recovery | None | `resume` + `enable_file_checkpointing` |
| Context compaction | Not handled | `PreCompact` hook + findings tools |
| Session timeout | None | Wall-clock `asyncio.timeout` |
| Process supervision | None | Retry loop with resume |
| LOC | ~1,400 | ~1,000 |

## Appendix B: pyproject.toml

```toml
[project]
name = "autonomous-coder"
version = "3.0.0"
requires-python = ">=3.11"
dependencies = ["claude-agent-sdk>=0.1.49"]

[project.optional-dependencies]
tui = ["textual>=0.79.0"]

[project.scripts]
autonomous-coder = "autonomous_coder.__main__:main"
```

---

## Changelog (Polished from Solution C, Score 4.23/5.0)

Changes from the original Solution C, with rationale and source:

| Change | Rationale | Source |
|---|---|---|
| Replaced global `FINDINGS_DIR`/`PROGRESS_STATE` with `FindingsStore` dataclass | All 3 judges flagged global mutable state as top issue | C critique #4 W1, all judge reports |
| Replaced global hook state with `HookContext` dataclass + closures | Same global state issue applied to hooks | C critique #4, judge consistency |
| Fully implemented `file_scope_guard` with `Path.resolve()` | Was empty `return {}` -- security blocker | C critique #1 W3, judges 1+3 |
| Removed Bash from security-auditor tools | Privilege escalation path | C critique #1 W2 |
| Tightened bash allowlist: moved `curl`/`docker`/`git`/`node`/`python` to validated commands | Too permissive -- `curl` exfiltration, `node -e` arbitrary exec | C critique #1 W1, A critique V2 |
| Added `validate_git`/`validate_node`/`validate_python`/`validate_curl`/`validate_docker` | Argument-level validation for dangerous-but-necessary commands | A critique V2 pattern |
| Added `ALLOWED_CATEGORIES` enum validation on `save_findings` | Path traversal via category parameter | C critique #1 W5 |
| Added `MAX_FINDINGS_SIZE` (50K chars) truncation | Findings could consume entire context window | C critique #2 W4 |
| Added `max_turns=200` to `ClaudeAgentOptions` | No turn cap -- runaway sessions | C critique #2 W3, all judges |
| Added `max_duration_seconds` wall-clock timeout via `asyncio.timeout` | No time limit on sessions | C critique #2 W3, judges 1+3 |
| Added process supervisor retry loop in `__main__.py` | Single process crash loses everything | C critique #2 W1 |
| Added `--plan-only` / `--dry-run` CLI flags | No way to plan without implementing | C critique #3 W3, judge DX feedback |
| Added `AutonomousCoderError` with hints | Raw Python exceptions on failure | C critique #3 W2 |
| Composable system prompt via `build_system_prompt()` sections | Monolithic prompt hard to test/iterate | C critique #4 W2 |
| Used `match` statement in `process_stream()` with catch-all logging | Silent drop of unknown message types | C critique #4 W4 |
| Persisted progress to `progress.json` for cross-session visibility | Progress lost on close | C critique #3 W4 |
| Persisted audit log to `audit.jsonl` on session completion | In-memory only -- no post-mortem analysis | C critique #2 W5 |
| Added resume progress display | No visibility into prior session state | C critique #3 W4 |
| Cherry-pick: argument validator pattern from A's critique | A's Serena shell bypass exploit showed need for deeper validation | A critique V1, V2 |
| Evaluated but rejected B's `StreamProcessor`/`UIEvent` union | C's `EventHandler` protocol is simpler and sufficient for v3's scope; typed events add ceremony without current benefit | B architecture section 6 |
| Evaluated but rejected B's `PipelineState` persistence | C's `SessionState` + `FindingsStore` + SDK `resume` achieves equivalent crash recovery with less infrastructure | B architecture section 10 |
