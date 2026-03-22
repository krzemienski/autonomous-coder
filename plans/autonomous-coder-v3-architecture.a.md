# Autonomous Coder v3 — Complete Architecture

> Built on `claude-agent-sdk` v0.1.49+ (PyPI: `claude-agent-sdk`)
> Model: `claude-opus-4-6` with 1M context (`betas=["context-1m-2025-08-07"]`)
> Mode: ClaudeSDKClient streaming (NEVER single-message `query()`)

---

## 1. System Overview

### Design Philosophy

**"Let Claude drive, Python provides guardrails."**

v3 inverts the control flow from v2. Instead of Python orchestrating a rigid Research → Explore → Plan → Code pipeline with separate sessions, v3 creates a **single long-lived ClaudeSDKClient session** where Claude acts as the orchestrator. Claude decides when to invoke specialist subagents based on the task, the project state, and its own reasoning.

Python's responsibilities are narrow and well-defined:
1. **Session lifecycle** — create the ClaudeSDKClient, run the streaming loop, handle shutdown
2. **Security enforcement** — `can_use_tool` callback, bash allowlist, sandbox settings
3. **Output routing** — transform StreamEvents into UI updates (TUI or CLI)
4. **Project detection** — determine greenfield vs existing project, inject context
5. **Budget guardrails** — `max_budget_usd` + custom tool for Claude visibility

### Two Entry Paths

| Path | Detection | Behavior |
|------|-----------|----------|
| **Greenfield** | `project_path` has no recognized project markers | System prompt tells Claude to scaffold from scratch |
| **Existing Project** | `project_path` contains `package.json`, `pyproject.toml`, `Cargo.toml`, `go.mod`, `.git`, `src/`, etc. | System prompt tells Claude to analyze first, then modify |

Detection is a pure Python function — no AI needed. The result is injected into the system prompt before the session starts.

### Architecture Diagram

```
┌─────────────────────────────────────────────────────┐
│                    User Interface                    │
│          ┌──────────────┬──────────────┐            │
│          │  Textual TUI │   CLI Mode   │            │
│          └──────┬───────┴──────┬───────┘            │
│                 │   OutputEvent Protocol  │           │
├─────────────────┼────────────────────────┼───────────┤
│                 ▼                        ▼           │
│  ┌──────────────────────────────────────────────┐   │
│  │             session.py (core loop)            │   │
│  │  ClaudeSDKClient + StreamEvent processing     │   │
│  └──────────────────────┬───────────────────────┘   │
│                         │                            │
│  ┌──────────────────────▼───────────────────────┐   │
│  │         ClaudeAgentOptions (Opus, 1M)         │   │
│  │  ┌─────────┬──────────┬──────────┬────────┐  │   │
│  │  │ agents  │  hooks   │can_use_  │  mcp_  │  │   │
│  │  │ (5 defs)│(security)│ tool     │servers │  │   │
│  │  └────┬────┴────┬─────┴────┬─────┴───┬────┘  │   │
│  └───────┼─────────┼──────────┼─────────┼───────┘   │
│          │         │          │         │            │
│          ▼         ▼          ▼         ▼            │
│  ┌──────────┐ ┌────────┐ ┌────────┐ ┌──────────┐   │
│  │Subagents │ │Security│ │Permis- │ │ serena   │   │
│  │researcher│ │ hooks  │ │sion    │ │ context7 │   │
│  │explorer  │ │ audit  │ │callback│ │ seq-think│   │
│  │planner   │ │ cost   │ │(bash   │ │ ac-tools │   │
│  │coder     │ │        │ │ allow) │ │ (custom) │   │
│  │reviewer  │ │        │ │        │ │          │   │
│  └──────────┘ └────────┘ └────────┘ └──────────┘   │
└─────────────────────────────────────────────────────┘
```

---

## 2. Agent Definitions

All five subagents are defined via `AgentDefinition` and passed to `ClaudeAgentOptions.agents`. Claude (the orchestrator) invokes them via the `Agent` tool when it determines the task requires specialist capabilities.

### 2.1 Orchestrator (Parent Agent)

The parent is NOT a subagent — it is the ClaudeSDKClient itself. Its system prompt defines its orchestration role.

**System Prompt:**

```python
ORCHESTRATOR_SYSTEM_PROMPT = """\
You are an autonomous coding agent. You receive a task and a project directory, \
then independently research, explore, plan, implement, and verify the solution.

## Your Workflow

You have five specialist subagents. Use them in whatever order the task demands:

1. **researcher** — Web research, library docs, MCP discovery. Use when you need \
external knowledge (new frameworks, API docs, best practices).
2. **explorer** — Codebase analysis via Serena. Use to understand project structure, \
find symbols, trace dependencies. Essential for existing projects.
3. **planner** — Implementation planning with sequential thinking. Use to break \
complex tasks into ordered steps with dependencies and risks.
4. **coder** — Implementation. The ONLY agent that can modify files or run commands. \
Always pass it the full context it needs: plan, relevant files, conventions.
5. **reviewer** — Code review. Use after implementation to catch bugs, security \
issues, and style violations.

## Entry Path: {entry_path}

{entry_path_instructions}

## Project Context

{project_context}

## Rules

- You MUST use subagents for their specialties. Do NOT try to code directly — \
you lack Write/Edit/Bash tools. Delegate to the coder subagent.
- When invoking a subagent, include ALL context it needs in your prompt to it. \
Subagents cannot see your conversation history.
- After the coder implements changes, ALWAYS invoke the reviewer to verify quality.
- Track progress with the ac-tools MCP. Call get_project_context at the start \
and track_progress after each major step.
- Monitor budget with get_budget_status. If >75% spent, prioritize core functionality.
- For greenfield projects: research first, then plan, then code.
- For existing projects: explore first, then plan, then code.
- NEVER skip the review step.

## Completion Criteria

You are done when:
1. The task is fully implemented (coder confirmed)
2. The code has been reviewed (reviewer confirmed)
3. You have summarized what was done, what files changed, and any caveats
"""
```

**Allowed Tools (orchestrator only):**

```python
ORCHESTRATOR_TOOLS = [
    "Read", "Grep", "Glob",                    # Read-only codebase access
    "Agent",                                     # Invoke subagents
    "mcp__ac-tools__get_project_context",       # Custom: project detection
    "mcp__ac-tools__track_progress",            # Custom: progress tracking
    "mcp__ac-tools__get_budget_status",         # Custom: budget monitoring
]
```

The orchestrator deliberately lacks Write, Edit, and Bash. All mutations go through the coder subagent with full security enforcement.

### 2.2 Researcher Subagent

```python
AgentDefinition(
    description=(
        "Web research specialist. Use for discovering libraries, reading API docs, "
        "finding MCP servers, checking best practices, and gathering external knowledge "
        "before implementation. Returns structured research findings."
    ),
    prompt="""\
You are a research specialist for a coding project.

Your job is to gather external knowledge that will inform implementation:
- Library documentation and API references
- Best practices and design patterns
- Existing implementations and examples on GitHub
- MCP server availability for the task domain

## Tools Available
- WebSearch / WebFetch for web research
- Context7 MCP for library documentation (resolve-library-id, then query-docs)
- Read / Grep / Glob for checking what already exists in the project

## Output Format

Provide a structured report:

### Research Findings
1. **Libraries & Frameworks**: name, version, key APIs, installation
2. **Best Practices**: relevant patterns for this task
3. **Reference Implementations**: links and key takeaways
4. **MCP Servers**: any relevant servers to install
5. **Recommendations**: prioritized approach for implementation

Be concise. Focus on actionable intelligence, not exhaustive surveys.\
""",
    tools=[
        "Read", "Grep", "Glob", "WebSearch", "WebFetch",
        "mcp__context7__resolve-library-id",
        "mcp__context7__query-docs",
    ],
    model="sonnet",
)
```

### 2.3 Explorer Subagent

```python
AgentDefinition(
    description=(
        "Codebase analysis specialist using Serena. Use to understand project "
        "structure, map symbols, trace dependencies, find patterns, and identify "
        "impact areas before modifying code. Essential for existing projects."
    ),
    prompt="""\
You are a codebase exploration specialist with access to Serena, a semantic \
code analysis tool.

Your job is to deeply understand the existing codebase and report findings \
that will guide implementation.

## Exploration Strategy
1. **Structure**: list_dir to understand layout, find entry points
2. **Symbols**: get_symbols_overview on key files, find_symbol for specifics
3. **Dependencies**: find_referencing_symbols to trace call chains
4. **Patterns**: search_for_pattern to find conventions and similar code
5. **Impact**: identify files that need modification and what might break

## Output Format

Provide a structured report:

### Codebase Analysis
1. **Tech Stack**: language, framework, build system, dependencies
2. **Architecture**: how the code is organized, key abstractions
3. **Relevant Symbols**: classes, functions, types related to the task
4. **Patterns & Conventions**: naming, error handling, file organization
5. **Impact Areas**: files to modify, files that might break, integration points
6. **Risks**: potential issues, deprecated APIs, tight coupling\
""",
    tools=[
        "Read", "Grep", "Glob",
        "mcp__serena__get_symbols_overview",
        "mcp__serena__find_symbol",
        "mcp__serena__find_referencing_symbols",
        "mcp__serena__search_for_pattern",
        "mcp__serena__list_dir",
        "mcp__serena__read_file",
    ],
    model="sonnet",
)
```

### 2.4 Planner Subagent

```python
AgentDefinition(
    description=(
        "Implementation planning specialist. Use to break complex tasks into "
        "ordered, atomic steps with dependencies, risks, and verification criteria. "
        "Uses sequential thinking for rigorous multi-step reasoning."
    ),
    prompt="""\
You are an implementation planning specialist. You receive a task description \
and context (research findings, codebase analysis), and produce a detailed, \
ordered implementation plan.

## Planning Process
1. Use sequential thinking to reason through the approach
2. Break work into atomic, independently verifiable steps
3. Identify dependencies between steps
4. Assess risks and define mitigation strategies
5. Define verification criteria for each step

## Output Format

### Implementation Plan

```json
{
  "goal": "what we're building",
  "approach": "high-level strategy",
  "steps": [
    {
      "id": 1,
      "title": "step title",
      "description": "what to do and how",
      "files": ["files to create or modify"],
      "dependencies": [],
      "verification": "how to verify this step worked",
      "risk": "low|medium|high",
      "risk_mitigation": "how to handle if this goes wrong"
    }
  ],
  "risks": ["global risks"],
  "estimated_complexity": "low|medium|high"
}
```

## Rules
- Steps MUST be ordered so dependencies are satisfied
- Each step MUST have clear verification criteria
- Keep steps atomic — one concern per step
- Include a final integration/smoke-test step\
""",
    tools=[
        "Read", "Grep", "Glob",
        "mcp__sequential-thinking__sequentialthinking",
    ],
    model="opus",
)
```

### 2.5 Coder Subagent

```python
AgentDefinition(
    description=(
        "Implementation specialist. The ONLY agent that can modify files and run "
        "commands. Use for writing code, running builds, installing dependencies, "
        "and executing the implementation plan. Always provide full context."
    ),
    prompt="""\
You are an expert software engineer implementing code changes.

You have full read-write access to the codebase and can run shell commands. \
You also have Serena for semantic code operations and Context7 for library docs.

## Implementation Guidelines
1. Read before writing — understand what exists before changing it
2. Use Serena's semantic tools (replace_symbol_body, insert_after_symbol) for \
   precise modifications when possible
3. Run builds/linters after changes to catch errors immediately
4. Follow existing code patterns and conventions
5. Handle errors explicitly — no silent failures
6. Keep changes minimal and focused

## Security
- Only run commands in the allowed set (package managers, build tools, git, etc.)
- Stay within the project directory
- Never expose secrets or credentials
- Never run destructive commands (rm -rf /, etc.)

## Completion
When done, report:
1. Files created or modified (with brief description of each change)
2. Build/lint status
3. Any issues or caveats
4. Suggestions for follow-up\
""",
    tools=[
        # Built-in file tools
        "Read", "Write", "Edit", "Bash", "Grep", "Glob",
        # Serena read tools
        "mcp__serena__get_symbols_overview",
        "mcp__serena__find_symbol",
        "mcp__serena__find_referencing_symbols",
        "mcp__serena__search_for_pattern",
        "mcp__serena__list_dir",
        "mcp__serena__read_file",
        # Serena write tools
        "mcp__serena__replace_content",
        "mcp__serena__replace_symbol_body",
        "mcp__serena__insert_after_symbol",
        "mcp__serena__insert_before_symbol",
        "mcp__serena__create_text_file",
        "mcp__serena__execute_shell_command",
        # Context7 for docs
        "mcp__context7__resolve-library-id",
        "mcp__context7__query-docs",
    ],
    model="inherit",  # Uses parent's Opus for maximum capability
)
```

### 2.6 Reviewer Subagent

```python
AgentDefinition(
    description=(
        "Code review specialist. Use after implementation to check for bugs, "
        "security vulnerabilities, style violations, missing error handling, "
        "and adherence to the implementation plan."
    ),
    prompt="""\
You are a senior code reviewer. Examine the recently modified files and provide \
actionable feedback.

## Review Checklist
1. **Correctness**: Does the code do what the plan specified?
2. **Security**: SQL injection, XSS, command injection, secret exposure?
3. **Error Handling**: Are errors caught and handled? Edge cases covered?
4. **Style**: Does it follow existing conventions? Is it readable?
5. **Performance**: Any obvious inefficiencies? N+1 queries? Unbounded loops?
6. **Completeness**: Anything missing from the plan? Any TODO/FIXME left?

## Output Format

### Code Review

**Verdict**: APPROVED | CHANGES_REQUESTED | CRITICAL_ISSUES

**Issues Found** (ordered by severity):
1. [CRITICAL/HIGH/MEDIUM/LOW] file:line — description and fix suggestion

**Positive Observations**:
- What was done well

**Recommendations**:
- Suggestions for improvement (non-blocking)\
""",
    tools=[
        "Read", "Grep", "Glob",
        "mcp__serena__get_symbols_overview",
        "mcp__serena__find_symbol",
        "mcp__serena__find_referencing_symbols",
        "mcp__serena__search_for_pattern",
        "mcp__serena__list_dir",
        "mcp__serena__read_file",
    ],
    model="sonnet",
)
```

---

## 3. Custom MCP Tools

Three custom tools implemented via `@tool` decorator and served in-process via `create_sdk_mcp_server`.

### 3.1 get_project_context

```python
from claude_agent_sdk import tool, create_sdk_mcp_server
import json
from pathlib import Path
from typing import Any

# Module-level state (shared across tool calls within a session)
_session_state = {
    "progress": [],
    "total_cost": 0.0,
    "budget_usd": 5.0,
}


PROJECT_MARKERS = {
    "package.json": "Node.js",
    "pyproject.toml": "Python",
    "Cargo.toml": "Rust",
    "go.mod": "Go",
    "pom.xml": "Java (Maven)",
    "build.gradle": "Java (Gradle)",
    "Gemfile": "Ruby",
    "composer.json": "PHP",
    "Package.swift": "Swift",
    "CMakeLists.txt": "C/C++",
}

FRAMEWORK_MARKERS = {
    "next.config": "Next.js",
    "nuxt.config": "Nuxt",
    "vite.config": "Vite",
    "angular.json": "Angular",
    "svelte.config": "SvelteKit",
    "remix.config": "Remix",
    "astro.config": "Astro",
    "django": "Django",
    "flask": "Flask",
    "fastapi": "FastAPI",
}


@tool(
    "get_project_context",
    "Detect project type, language, framework, and structure. "
    "Call this first to understand what you're working with.",
    {"project_path": str},
)
async def get_project_context(args: dict[str, Any]) -> dict[str, Any]:
    project_path = Path(args["project_path"])

    if not project_path.exists():
        return _text_result(json.dumps({
            "is_greenfield": True,
            "reason": "Project directory does not exist",
        }, indent=2))

    # Detect project markers
    detected_languages = []
    for marker, language in PROJECT_MARKERS.items():
        if (project_path / marker).exists():
            detected_languages.append(language)

    # Count source files
    source_extensions = {".py", ".js", ".ts", ".tsx", ".rs", ".go", ".java", ".rb", ".swift"}
    source_files = []
    for ext in source_extensions:
        source_files.extend(project_path.rglob(f"*{ext}"))
    # Limit traversal depth to avoid huge repos
    source_count = min(len(source_files), 10000)

    is_greenfield = len(detected_languages) == 0 and source_count == 0
    has_git = (project_path / ".git").exists()

    # Detect framework
    detected_frameworks = []
    for marker, framework in FRAMEWORK_MARKERS.items():
        for f in project_path.iterdir():
            if marker in f.name:
                detected_frameworks.append(framework)
                break

    # Key entry points
    entry_points = []
    for candidate in ["main.py", "app.py", "index.ts", "index.js", "main.rs",
                       "main.go", "App.tsx", "src/index.ts", "src/main.py"]:
        if (project_path / candidate).exists():
            entry_points.append(candidate)

    result = {
        "is_greenfield": is_greenfield,
        "languages": detected_languages,
        "frameworks": detected_frameworks,
        "has_git": has_git,
        "source_file_count": source_count,
        "entry_points": entry_points,
        "project_path": str(project_path),
    }

    return _text_result(json.dumps(result, indent=2))
```

### 3.2 track_progress

```python
@tool(
    "track_progress",
    "Record a completed action. Call after each major step "
    "(researched, explored, planned, coded, reviewed).",
    {
        "action": str,       # "researched" | "explored" | "planned" | "coded" | "reviewed"
        "summary": str,      # Brief description of what was accomplished
    },
)
async def track_progress(args: dict[str, Any]) -> dict[str, Any]:
    import time
    entry = {
        "action": args["action"],
        "summary": args["summary"],
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    _session_state["progress"].append(entry)

    return _text_result(json.dumps({
        "recorded": entry,
        "total_steps": len(_session_state["progress"]),
        "history": _session_state["progress"],
    }, indent=2))
```

### 3.3 get_budget_status

```python
@tool(
    "get_budget_status",
    "Check remaining budget. Call periodically to avoid overspending.",
    {"project_path": str},  # Unused but required for schema
)
async def get_budget_status(args: dict[str, Any]) -> dict[str, Any]:
    spent = _session_state["total_cost"]
    budget = _session_state["budget_usd"]
    remaining = max(0.0, budget - spent)
    percent_used = (spent / budget * 100) if budget > 0 else 0

    warning = None
    if percent_used > 90:
        warning = "CRITICAL: >90% budget consumed. Wrap up immediately."
    elif percent_used > 75:
        warning = "WARNING: >75% budget consumed. Prioritize core functionality."
    elif percent_used > 50:
        warning = "NOTE: >50% budget consumed. Be efficient."

    return _text_result(json.dumps({
        "spent_usd": round(spent, 4),
        "budget_usd": budget,
        "remaining_usd": round(remaining, 4),
        "percent_used": round(percent_used, 1),
        "warning": warning,
    }, indent=2))


def _text_result(text: str) -> dict[str, Any]:
    """Helper: wrap text in MCP tool response format."""
    return {"content": [{"type": "text", "text": text}]}


def build_custom_tools(budget_usd: float = 5.0) -> dict:
    """Create the in-process MCP server with all custom tools.

    Returns a McpSdkServerConfig suitable for ClaudeAgentOptions.mcp_servers.
    """
    _session_state["budget_usd"] = budget_usd
    return create_sdk_mcp_server(
        name="ac-tools",
        version="3.0.0",
        tools=[get_project_context, track_progress, get_budget_status],
    )
```

### Cost Tracking Integration

The `_session_state["total_cost"]` is updated from the streaming loop in `session.py` whenever a `ResultMessage` is received. This keeps the custom MCP tool synchronized with actual spending:

```python
# In session.py streaming loop:
if isinstance(msg, ResultMessage) and msg.total_cost_usd:
    from .tools import _session_state
    _session_state["total_cost"] = msg.total_cost_usd
```

---

## 4. Hook Architecture

Hooks provide observability and additional security validation. They run at well-defined points in the SDK lifecycle.

### 4.1 PreToolUse: Bash Security

```python
from claude_agent_sdk import HookMatcher

async def bash_security_hook(input_data, tool_use_id, context):
    """Block dangerous bash commands. Allowlist approach."""
    if input_data.get("tool_name") != "Bash":
        return {}

    command = input_data.get("tool_input", {}).get("command", "")

    # Check dangerous patterns first
    for pattern in DANGEROUS_PATTERNS:
        if pattern.lower() in command.lower():
            return {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": f"Dangerous pattern: {pattern}",
                }
            }

    # Extract base command and check allowlist
    base_cmd = command.strip().split()[0].split("/")[-1] if command.strip() else ""
    if base_cmd not in ALLOWED_COMMANDS:
        return {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": f"Command not in allowlist: {base_cmd}",
            }
        }

    return {}
```

### 4.2 PreToolUse: Serena Shell Command Security

```python
async def serena_shell_security_hook(input_data, tool_use_id, context):
    """Block dangerous commands via Serena's execute_shell_command."""
    if input_data.get("tool_name") != "mcp__serena__execute_shell_command":
        return {}

    command = input_data.get("tool_input", {}).get("command", "")
    for pattern in DANGEROUS_PATTERNS:
        if pattern.lower() in command.lower():
            return {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": f"Blocked via Serena: {pattern}",
                }
            }
    return {}
```

### 4.3 PostToolUse: Audit Logger

```python
async def audit_logger(input_data, tool_use_id, context):
    """Log every tool call for audit trail."""
    import time
    tool_name = input_data.get("tool_name", "unknown")
    tool_input = input_data.get("tool_input", {})

    # Extract a brief summary
    summary = ""
    if "command" in tool_input:
        summary = tool_input["command"][:100]
    elif "file_path" in tool_input:
        summary = tool_input["file_path"]
    elif "pattern" in tool_input:
        summary = f"pattern: {tool_input['pattern'][:60]}"

    # Check if this is from a subagent
    agent_id = input_data.get("agent_id", "orchestrator")

    print(f"  [{time.strftime('%H:%M:%S')}] [{agent_id}] {tool_name}: {summary}")
    return {}
```

### 4.4 SubagentStart / SubagentStop: Lifecycle Tracking

```python
async def on_subagent_start(input_data, tool_use_id, context):
    """Log when a subagent begins execution."""
    agent_type = input_data.get("agent_type", "unknown")
    print(f"\n  >> Subagent starting: {agent_type}")
    return {}


async def on_subagent_stop(input_data, tool_use_id, context):
    """Log when a subagent completes."""
    agent_id = input_data.get("agent_id", "unknown")
    transcript_path = input_data.get("agent_transcript_path", "")
    print(f"  << Subagent complete: {agent_id}")
    if transcript_path:
        print(f"     Transcript: {transcript_path}")
    return {}
```

### 4.5 Hook Registration

```python
def build_hooks() -> dict[str, list[HookMatcher]]:
    """Build the complete hook configuration."""
    return {
        "PreToolUse": [
            HookMatcher(matcher="Bash", hooks=[bash_security_hook]),
            HookMatcher(
                matcher="mcp__serena__execute_shell_command",
                hooks=[serena_shell_security_hook],
            ),
        ],
        "PostToolUse": [
            HookMatcher(hooks=[audit_logger]),  # No matcher = all tools
        ],
        "SubagentStart": [
            HookMatcher(hooks=[on_subagent_start]),
        ],
        "SubagentStop": [
            HookMatcher(hooks=[on_subagent_stop]),
        ],
    }
```

---

## 5. Permission Architecture

Defense in depth with 4 layers evaluated in SDK order:

### Layer 1: Hooks (PreToolUse)

Runs first. `bash_security_hook` and `serena_shell_security_hook` can deny before any other check.

### Layer 2: Deny Rules (disallowed_tools)

Not used in v3 (subagent tool restrictions are more granular).

### Layer 3: Permission Mode

```python
permission_mode = "acceptEdits"  # Auto-approve file operations within cwd
```

Combined with `cwd=str(project_path)` and sandbox settings, this scopes all file operations to the project directory.

### Layer 4: can_use_tool Callback

Last line of defense. Catches anything the hooks missed:

```python
async def security_callback(
    tool_name: str,
    tool_input: dict,
    ctx: Any,
) -> PermissionResultAllow | PermissionResultDeny:
    """Defense-in-depth: final security check before any tool executes."""

    if tool_name == "Bash":
        command = tool_input.get("command", "")
        base_cmd = command.strip().split()[0].split("/")[-1] if command.strip() else ""

        # Dangerous pattern check
        for pattern in DANGEROUS_PATTERNS:
            if pattern.lower() in command.lower():
                return PermissionResultDeny(
                    message=f"Blocked: dangerous pattern '{pattern}'",
                    interrupt=False,
                )

        # Allowlist check
        if base_cmd not in ALLOWED_COMMANDS:
            return PermissionResultDeny(
                message=f"Blocked: '{base_cmd}' not in allowlist",
                interrupt=False,
            )

    if tool_name == "mcp__serena__execute_shell_command":
        command = tool_input.get("command", "")
        for pattern in DANGEROUS_PATTERNS:
            if pattern.lower() in command.lower():
                return PermissionResultDeny(
                    message=f"Blocked via Serena: '{pattern}'",
                    interrupt=False,
                )

    return PermissionResultAllow(updated_input=None)
```

### Layer 5: Subagent Tool Restrictions

Each subagent's `tools` field whitelist is the coarsest but most reliable layer. Even if all other security layers had bugs, the researcher subagent physically cannot call `Write` or `Bash` because those tools are not in its `tools` list.

### Sandbox Configuration

```python
sandbox = {
    "enabled": True,
    "autoAllowBashIfSandboxed": True,
}
```

OS-level isolation for bash commands within the sandbox.

---

## 6. Streaming Output Architecture

### StreamEvent Processing

The streaming loop receives three types of messages. `StreamEvent` provides real-time token streaming. `AssistantMessage` provides complete turn results. `ResultMessage` provides session metadata and costs.

```python
# In session.py:

from claude_agent_sdk.types import StreamEvent

async def process_stream(client, output_handler):
    """Process the streaming response and dispatch to output handler."""
    current_tool = None
    in_tool = False

    async for msg in client.receive_response():
        if isinstance(msg, StreamEvent):
            event = msg.event
            event_type = event.get("type")
            parent = msg.parent_tool_use_id  # Non-None = from subagent

            if event_type == "content_block_start":
                cb = event.get("content_block", {})
                if cb.get("type") == "tool_use":
                    current_tool = cb.get("name")
                    in_tool = True
                    output_handler.on_tool_start(current_tool, parent)

            elif event_type == "content_block_delta":
                delta = event.get("delta", {})
                if delta.get("type") == "text_delta" and not in_tool:
                    output_handler.on_text(delta.get("text", ""), parent)

            elif event_type == "content_block_stop":
                if in_tool:
                    output_handler.on_tool_done(current_tool, parent)
                    current_tool = None
                    in_tool = False

        elif isinstance(msg, ResultMessage):
            cost = msg.total_cost_usd or 0.0
            output_handler.on_cost(cost)

            # Sync cost to custom MCP tool state
            from .tools import _session_state
            _session_state["total_cost"] = cost

            if msg.result:
                output_handler.on_complete(msg.result)
```

### OutputHandler Protocol

```python
from typing import Protocol, runtime_checkable

@runtime_checkable
class OutputHandler(Protocol):
    """Interface for receiving session output events."""

    def on_text(self, text: str, parent_id: str | None = None) -> None:
        """Streaming text chunk from agent or subagent."""
        ...

    def on_tool_start(self, tool_name: str, parent_id: str | None = None) -> None:
        """A tool call is beginning."""
        ...

    def on_tool_done(self, tool_name: str, parent_id: str | None = None) -> None:
        """A tool call completed."""
        ...

    def on_cost(self, total_cost_usd: float) -> None:
        """Updated cost information."""
        ...

    def on_error(self, error: str) -> None:
        """An error occurred."""
        ...

    def on_complete(self, result: str) -> None:
        """Session completed with final result."""
        ...

    def on_subagent_start(self, agent_type: str) -> None:
        """A subagent began execution."""
        ...

    def on_subagent_done(self, agent_id: str) -> None:
        """A subagent completed."""
        ...
```

---

## 7. File Structure

```
src/autonomous_coder/
├── __init__.py              # Package exports, version
├── __main__.py              # CLI arg parsing → dispatch to TUI or CLI
├── config.py                # SessionConfig dataclass, MCP server registry, defaults
├── session.py               # Core: build options, create ClaudeSDKClient, run stream loop
├── agents.py                # AgentDefinition factory: build_agent_definitions()
├── tools.py                 # Custom MCP tools: get_project_context, track_progress, budget
├── security.py              # can_use_tool callback, ALLOWED_COMMANDS, DANGEROUS_PATTERNS
├── hooks.py                 # Hook callbacks: bash security, audit, subagent lifecycle
├── prompts.py               # build_system_prompt(): entry path detection, prompt assembly
├── output.py                # OutputHandler protocol definition
├── cli.py                   # CLI OutputHandler: prints to stdout
├── tui/
│   ├── __init__.py
│   ├── app.py               # Textual App: composes widgets, subscribes to OutputHandler
│   └── widgets.py           # AgentTree, StreamingLog, ProgressBar, CostDisplay
└── py.typed                 # PEP 561 marker
```

**Key differences from v2:**
- No `agents/` directory with PhaseRunner subclasses — replaced by `agents.py` with `AgentDefinition` factories
- No `orchestrator.py` — replaced by `session.py` (much simpler: no phase management, no pipeline state)
- No `messages.py` (Textual Messages) — replaced by `output.py` (OutputHandler protocol)
- No `agent_factory.py` — options are built directly in `session.py`
- No `cli_adapter.py` — replaced by `cli.py` (simpler: just implements OutputHandler)
- TUI is a subpackage instead of mixed into root

---

## 8. Execution Flow

### 8.1 CLI Entry

```
User runs: autonomous-coder --cli "Add user authentication"
                      │
                      ▼
              __main__.py: parse args
                      │
                      ▼
              config.py: SessionConfig(
                  project_path=Path.cwd(),
                  model="claude-opus-4-6",
                  budget_usd=5.0,
                  betas=["context-1m-2025-08-07"]
              )
                      │
                      ▼
              cli.py: CliOutputHandler(verbose=True)
                      │
                      ▼
              session.py: run_session(config, task, output_handler)
```

### 8.2 session.run_session() Detail

```python
async def run_session(
    config: SessionConfig,
    task: str,
    output_handler: OutputHandler,
) -> None:
    """Run a complete autonomous coding session."""

    # 1. Detect project type
    project_context = detect_project(config.project_path)

    # 2. Build system prompt with entry path
    system_prompt = build_system_prompt(
        entry_path="greenfield" if project_context["is_greenfield"] else "existing",
        project_context=project_context,
    )

    # 3. Build agent definitions
    agent_defs = build_agent_definitions()

    # 4. Build custom MCP tools
    custom_tools = build_custom_tools(budget_usd=config.budget_usd)

    # 5. Build MCP server config
    mcp_servers = {**config.mcp_servers, "ac-tools": custom_tools}

    # 6. Assemble options
    options = ClaudeAgentOptions(
        model=config.model,
        system_prompt=system_prompt,
        allowed_tools=ORCHESTRATOR_TOOLS,
        agents=agent_defs,
        mcp_servers=mcp_servers,
        hooks=build_hooks(),
        can_use_tool=security_callback,
        permission_mode="acceptEdits",
        max_turns=config.max_turns,
        max_budget_usd=config.budget_usd,
        betas=config.betas,
        cwd=str(config.project_path),
        sandbox={"enabled": True, "autoAllowBashIfSandboxed": True},
        include_partial_messages=True,
        enable_file_checkpointing=True,
    )

    # 7. Run session
    async with ClaudeSDKClient(options=options) as client:
        await client.query(task)
        await process_stream(client, output_handler)
```

### 8.3 What Claude Does Inside the Session

For an existing project task like "Add user authentication":

```
1. Claude calls get_project_context → learns it's a Next.js app
2. Claude invokes explorer subagent:
   "Explore this Next.js project. Find existing auth-related code,
    middleware, database models, and API routes."
3. Explorer returns codebase analysis
4. Claude invokes researcher subagent:
   "Research NextAuth.js v5 setup for Next.js App Router.
    Find the latest API, configuration, and provider setup."
5. Researcher returns library docs and examples
6. Claude invokes planner subagent:
   "Plan user authentication for this Next.js app.
    Context: [explorer findings]. Library: [researcher findings].
    Use NextAuth.js v5 with credentials + GitHub providers."
7. Planner returns ordered implementation steps
8. Claude invokes coder subagent:
   "Implement the following plan: [full plan].
    Project structure: [explorer findings].
    API reference: [researcher findings].
    Start with step 1: Install dependencies."
9. Coder implements all steps, reports results
10. Claude invokes reviewer subagent:
    "Review the authentication implementation in these files:
     [list of changed files from coder's report].
     Check for: security issues, missing error handling,
     CSRF protection, session management."
11. Reviewer returns verdict
12. If CHANGES_REQUESTED: Claude invokes coder again with fixes
13. Claude calls track_progress for each completed phase
14. Claude produces final summary
```

For a greenfield task like "Create a REST API for a todo app":

```
1. Claude calls get_project_context → learns it's greenfield
2. Claude invokes researcher subagent:
   "Research the best stack for a REST API todo app.
    Consider: Node.js/Express, Python/FastAPI, Go/Gin.
    Evaluate trade-offs for simplicity and production-readiness."
3. Claude invokes planner subagent:
   "Plan a greenfield REST API for a todo app.
    Stack decision: [researcher recommendation].
    Include: project scaffolding, data model, CRUD endpoints,
    error handling, input validation."
4. Claude invokes coder subagent:
   "Create a new project from scratch following this plan: [plan].
    This is a greenfield project — create all files from scratch.
    Start with: project init, dependency installation, directory structure."
5. Claude invokes reviewer subagent
6. Fix cycle if needed
7. Final summary
```

---

## 9. Configuration Architecture

### 9.1 SessionConfig Dataclass

```python
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class SessionConfig:
    """Complete configuration for an autonomous coding session."""

    # Required
    project_path: Path

    # Model
    model: str = "claude-opus-4-6"
    betas: list[str] = field(default_factory=lambda: ["context-1m-2025-08-07"])

    # Budget & Limits
    budget_usd: float = 5.0
    max_turns: int = 200

    # Security
    sandbox_enabled: bool = True

    # Output
    verbose: bool = False

    # MCP Servers (external, not custom tools)
    mcp_servers: dict[str, dict] = field(default_factory=lambda: {
        "serena": {
            "command": "uvx",
            "args": ["serena"],
            "env": {},
        },
        "sequential-thinking": {
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-sequential-thinking"],
        },
        "context7": {
            "command": "npx",
            "args": ["-y", "@upstash/context7-mcp"],
        },
    })
```

### 9.2 Configuration Sources

Priority (highest first):
1. CLI arguments (`--model`, `--budget`, `--project`)
2. Environment variables (`AC_MODEL`, `AC_BUDGET`, `AC_PROJECT`)
3. Project config file (`.autonomous-coder.toml` in project root — future)
4. Defaults in `SessionConfig`

### 9.3 pyproject.toml

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "autonomous-coder"
version = "3.0.0"
description = "AI-powered autonomous coding agent built on Claude Agent SDK"
requires-python = ">=3.11"
dependencies = [
    "claude-agent-sdk>=0.1.49",
    "textual>=1.0.0",
]

[project.optional-dependencies]
dev = [
    "ruff>=0.8.0",
    "mypy>=1.13.0",
]

[project.scripts]
autonomous-coder = "autonomous_coder.__main__:main"

[tool.hatch.build.targets.wheel]
packages = ["src/autonomous_coder"]
```

---

## 10. Session Management

### 10.1 Session Lifecycle

```
CREATE  →  ClaudeSDKClient(options) enters async context manager
            ↓
CONNECT →  client.__aenter__() establishes connection to Claude Code CLI
            ↓
QUERY   →  client.query(task) sends the user's task
            ↓
STREAM  →  async for msg in client.receive_response(): processes all events
            ↓ (optionally)
MULTI   →  client.query(follow_up) sends additional queries in same session
            ↓
CLOSE   →  client.__aexit__() on completion, error, or interrupt
```

### 10.2 Session ID and Resume

```python
# Capture session ID from ResultMessage
session_id = None
async for msg in client.receive_response():
    if isinstance(msg, ResultMessage):
        session_id = msg.session_id

# Later, resume the session:
resume_options = ClaudeAgentOptions(
    resume=session_id,
    # ... same options as before
)
async with ClaudeSDKClient(options=resume_options) as client:
    await client.query("Continue where you left off")
```

### 10.3 Interrupt Handling

```python
# In TUI:
def action_cancel_agent(self) -> None:
    if self._client:
        asyncio.create_task(self._client.interrupt())

# In CLI:
import signal

def setup_signal_handlers(client: ClaudeSDKClient):
    def handler(sig, frame):
        asyncio.get_event_loop().create_task(client.interrupt())
    signal.signal(signal.SIGINT, handler)
```

### 10.4 File Checkpointing

With `enable_file_checkpointing=True`, the SDK tracks file changes. If something goes wrong:

```python
# Rewind all files to state before a specific message
await client.rewind_files(user_message_id)
```

### 10.5 Dynamic Runtime Changes

ClaudeSDKClient supports mid-session changes:

```python
# Switch model (e.g., downgrade to Sonnet when budget is low)
await client.set_model("claude-sonnet-4-5-20250514")

# Change permission mode
await client.set_permission_mode("plan")  # Switch to planning-only mode

# Add/remove MCP servers dynamically
await client.add_mcp_server("puppeteer", {"command": "npx", "args": ["puppeteer-mcp-server"]})
await client.remove_mcp_server("puppeteer")

# Check MCP server health
statuses = await client.get_mcp_status()
```

---

## Appendix A: v2 → v3 Migration Summary

| Aspect | v2 | v3 |
|--------|-----|-----|
| SDK API | `query()` function | `ClaudeSDKClient` (streaming) |
| Orchestration | Python PhaseRunner pipeline | Claude-driven via subagents |
| Phase management | Rigid 4-phase sequence | Flexible, Claude decides order |
| Context passing | Truncated strings between phases | Full context in Agent tool prompts |
| Session continuity | New session per phase | Single session for entire task |
| Interrupt | Manual `_cancelled` flag | `client.interrupt()` |
| Budget control | Manual tracking | `max_budget_usd` + custom tool |
| UI protocol | Textual Messages (9 classes) | OutputHandler (7 methods) |
| Security | `can_use_tool` only | Hooks + `can_use_tool` + tool restrictions |
| File safety | None | `enable_file_checkpointing` + `rewind_files()` |
| Streaming | `include_partial_messages` on AssistantMessage | StreamEvent with full event types |
| Resume | Not supported | `resume=session_id` |

## Appendix B: Verification Questions & Answers

**Q1: Does AgentDefinition.tools actually prevent access to inherited MCP tools?**
A1: Yes. From SDK docs: "Specify tools: agent can only use listed tools." The tools field is a whitelist. MCP servers are inherited (available), but the subagent can only call tools listed in its tools field.

**Q2: Can the orchestrator accidentally bypass coder isolation by using Write/Edit directly?**
A2: No. The orchestrator's `allowed_tools` does not include Write, Edit, or Bash. Even though these tools exist in the SDK, the orchestrator cannot call them because they're not in its allowed list.

**Q3: What happens if a subagent exceeds the budget?**
A3: `max_budget_usd` applies to the entire session including subagent costs. The SDK enforces this automatically. Additionally, Claude can call `get_budget_status` to make proactive decisions.

**Q4: How large can a subagent's result be before it impacts the orchestrator's context?**
A4: With 1M context (beta), this is rarely a concern. Subagent transcripts are stored separately and survive compaction. Only the final result returned to the orchestrator counts against its context window.

**Q5: Is the `execute_shell_command` via Serena MCP a security hole that bypasses bash allowlist?**
A5: Addressed by adding `serena_shell_security_hook` as a PreToolUse hook with matcher `mcp__serena__execute_shell_command`. This applies the same dangerous pattern checks to Serena shell commands. The `can_use_tool` callback also catches this as a second layer.

---

*Architecture version: 3.0.0-alpha*
*SDK target: claude-agent-sdk >= 0.1.49*
*Last updated: 2026-03-21*
