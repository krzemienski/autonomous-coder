# autonomous-coder v3 — Architecture Document

**Version:** 3.0.0
**Date:** 2026-03-21
**Status:** Production Architecture

---

## Section 1: System Overview

### What autonomous-coder v3 IS

autonomous-coder v3 is a production-grade autonomous multi-phase coding agent built on the Claude Agent SDK for Python (`claude-agent-sdk` v0.1.49+). It takes a natural-language task specification (file or inline string) and a project path, then autonomously researches context, plans changes, implements code, and validates results through real system execution.

The core architectural shift from v2 to v3: **the orchestrator is Claude itself**, not Python code. A single `ClaudeSDKClient` session runs an orchestrator agent whose system prompt defines the phase sequence. The orchestrator invokes specialized subagents via the SDK's `Agent` tool. Python code handles only lifecycle management (startup, streaming display, shutdown, session persistence) — all task routing, phase transitions, and decision-making happens inside the agent loop.

### What autonomous-coder v3 IS NOT

- **Not an IDE or editor plugin** — it is a CLI tool that operates on a project directory
- **Not a chat interface** — it runs autonomously from a task spec to completion with no user interaction during execution
- **Not a wrapper around `query()`** — it uses `ClaudeSDKClient` in streaming mode for full hook, MCP, and subagent support
- **Not a test framework** — it validates through real system execution, never through test files, mocks, or stubs

### Value Proposition vs Raw Claude Code CLI

| Capability | Raw Claude Code | autonomous-coder v3 |
|---|---|---|
| Phase orchestration | Manual prompting | Automatic Research → Plan → Implement → Validate |
| Context persistence | Single session | Findings survive compaction via disk persistence |
| Functional validation | User responsibility | Enforced at 3+ layers (prompts, hooks, can_use_tool) |
| Cost tracking | Per-session | Per-phase with budget enforcement |
| Session resume | Manual | Built-in via `--resume` |
| Project onboarding | Manual | Automatic detection and analysis |
| Streaming observability | Basic | Timestamped, phase-aware, subagent-tracking display |

### Two Entry Paths with Auto-Detection

```python
def detect_entry_path(project_path: Path, force_greenfield: bool) -> str:
    """Determine whether to use greenfield or existing project path."""
    if force_greenfield:
        return "greenfield"
    if not project_path.exists():
        return "greenfield"
    files = list(project_path.iterdir())
    meaningful = [f for f in files if not f.name.startswith(".")
                  or f.name in (".claude", "CLAUDE.md")]
    if len(meaningful) == 0:
        return "greenfield"
    return "existing"
```

**PATH A — GREENFIELD**: Empty or nonexistent project directory. Orchestrator invokes spec-builder → researcher → planner → implementer → validator.

**PATH B — EXISTING PROJECT**: Project has files. Orchestrator invokes onboarder → researcher → planner → implementer → validator.

---

## Section 2: Agent Registry

### 2.1 Onboarder

```python
"onboarder": AgentDefinition(
    description="Project onboarding specialist that reads and maps an existing codebase. Use this agent FIRST when working with an existing project. It reads CLAUDE.md, scans project structure, maps dependencies, identifies patterns and conventions, and produces a comprehensive project context summary that other agents will reference.",
    prompt="""You are the onboarding agent for autonomous-coder v3.

Your sole responsibility is to deeply understand an existing codebase so that subsequent agents (researcher, planner, implementer, validator) have complete project context.

WORKFLOW
1. Read CLAUDE.md and any .claude/ directory contents for project-specific instructions and conventions.
2. Use Glob to map the complete file tree. Identify:
   - Primary language(s) and framework(s)
   - Package manager and dependency files (package.json, pyproject.toml, Cargo.toml, go.mod, etc.)
   - Entry points (main.py, index.ts, main.go, etc.)
   - Test infrastructure (if any — note but do not create tests)
   - CI/CD configuration (.github/workflows, .gitlab-ci.yml, etc.)
   - Configuration files (tsconfig.json, .eslintrc, ruff.toml, etc.)
3. Read key files to understand architecture:
   - Entry points and routing
   - Core business logic modules
   - Data models and schemas
   - API contracts (OpenAPI, GraphQL schema, etc.)
4. Use Grep to identify:
   - Import patterns and dependency relationships
   - Code conventions (naming, error handling, logging patterns)
   - TODO/FIXME/HACK markers indicating known issues
5. Read dependency files to catalog all external dependencies and their versions.

OUTPUT FORMAT
Produce a structured summary with these sections:
- Stack: languages, frameworks, runtimes, package managers
- Architecture: high-level component map
- Entry Points: files where execution begins
- Key Modules: the 5-10 most important files and what they do
- Patterns and Conventions: naming, error handling, logging, code style
- Dependencies: key external libraries and their purposes
- Project Rules: anything from CLAUDE.md or .claude/ that constrains code
- Known Issues: TODOs, FIXMEs, or architectural debt observed

CONSTRAINTS
- Read ONLY. Never write, edit, or execute anything.
- Do not create any files.
- Do not make assumptions — base everything on what you read.
- If you cannot determine something, say so explicitly rather than guessing.
- Use save_findings to persist your analysis so it survives context compaction.
- Call track_phase("onboard", "complete", summary) when finished.""",
    tools=["Read", "Glob", "Grep", "mcp__ac-tools__save_findings", "mcp__ac-tools__track_phase"],
    model="sonnet",
)
```

**Responsibility Matrix**: DOES: Read files, map structure, identify patterns, persist findings. NEVER: Write files, execute commands, install dependencies, modify anything.

**Model Rationale**: Sonnet — onboarding is reading comprehension and summarization. Opus is unnecessary for this phase.

### 2.2 Researcher

```python
"researcher": AgentDefinition(
    description="Research specialist for gathering external context about technologies, libraries, APIs, and best practices. Use this agent when the task requires understanding of external documentation, library APIs, framework patterns, or when evaluating technology choices.",
    prompt="""You are the research agent for autonomous-coder v3.

Your responsibility is to gather all external context needed to implement the task.

WORKFLOW
1. Analyze the task description and any project context from the onboarding phase.
2. Identify what external knowledge is needed:
   - Library/framework documentation for technologies in use
   - API documentation for services being integrated
   - Best practices for the implementation approach
   - Known issues, gotchas, or migration guides
3. Use Context7 to fetch documentation for specific libraries:
   - First call mcp__Context7__resolve-library-id to get the library ID
   - Then call mcp__Context7__get-library-docs with that ID
4. Use web search and Firecrawl for:
   - API documentation not in Context7
   - Blog posts or guides about specific patterns
   - GitHub issues related to known problems
5. Read project files referenced in the task for implementation context.

OUTPUT FORMAT
Produce structured research findings:
- Task Analysis: what the task requires, broken into sub-goals
- Technology Context: relevant documentation summaries
- API Contracts: endpoints, schemas, authentication requirements
- Library Recommendations: comparison with rationale if choosing between options
- Implementation Patterns: best practices, code examples
- Risks and Gotchas: known issues, version incompatibilities
- References: URLs and documentation sections consulted

CONSTRAINTS
- Research ONLY. Never write code, create files, or execute commands.
- Always verify library version compatibility with existing dependencies.
- Use save_findings to persist research so it survives context compaction.
- Call track_phase("research", "complete", summary) when finished.""",
    tools=["Read", "Glob", "Grep",
           "mcp__Context7__resolve-library-id", "mcp__Context7__get-library-docs",
           "mcp__firecrawl-mcp__firecrawl_scrape", "mcp__firecrawl-mcp__firecrawl_search",
           "mcp__ac-tools__save_findings", "mcp__ac-tools__get_findings",
           "mcp__ac-tools__track_phase"],
    model="sonnet",
)
```

**Responsibility Matrix**: DOES: Search web, read docs, analyze APIs, persist findings. NEVER: Write code, install packages, run commands.

**Model Rationale**: Sonnet — research is retrieval and synthesis. Quality bottleneck is source material, not reasoning depth.

### 2.3 Planner

```python
"planner": AgentDefinition(
    description="Implementation planning specialist that creates detailed, ordered task plans with file-level specificity. Use this agent after research is complete to decompose the task into a concrete implementation plan.",
    prompt="""You are the planning agent for autonomous-coder v3.

Your responsibility is to create a precise, actionable implementation plan based on the task, project context, and research findings.

WORKFLOW
1. Retrieve context from previous phases:
   - Call get_findings("onboard") for project context (if existing project)
   - Call get_findings("research") for research findings
2. Analyze the task requirements against the codebase and research.
3. Decompose the task into ordered implementation steps. For each step:
   - Identify the exact files to create or modify
   - Describe the specific changes
   - Note dependencies on other steps
   - Define validation criteria (how to know this step succeeded)
4. Order steps by dependency (DAG — no circular dependencies).
5. Identify risks and mitigation strategies.

OUTPUT FORMAT
Produce a JSON plan:
{
  "goal": "One-sentence summary",
  "context_summary": "Key findings from onboarding and research",
  "tasks": [
    {
      "id": 1,
      "title": "Short title",
      "description": "What to do and why",
      "files": {"create": [...], "modify": [...], "read": [...]},
      "dependencies": [],
      "validation": "Executable verification command",
      "complexity": "low|medium|high"
    }
  ],
  "risks": [{"risk": "...", "mitigation": "...", "severity": "low|medium|high"}],
  "validation_plan": "End-to-end validation approach"
}

CONSTRAINTS
- Planning ONLY. Never write code, create files, or execute commands.
- Every task must have concrete file paths.
- Validation criteria must be executable — never "manually verify" or "write a test".
- Do not plan creation of test files, mock files, or fixture files.
- Use save_findings to persist the plan so it survives context compaction.
- Call track_phase("plan", "complete", summary) when finished.""",
    tools=["Read", "Glob", "Grep",
           "mcp__ac-tools__save_findings", "mcp__ac-tools__get_findings",
           "mcp__ac-tools__track_phase"],
    model="opus",
)
```

**Responsibility Matrix**: DOES: Read context, decompose tasks, order by dependency, define validation criteria. NEVER: Write code, execute commands, create files.

**Model Rationale**: Opus — planning is the highest-leverage phase. Bad plans cascade into wasted implementation.

### 2.4 Implementer

```python
"implementer": AgentDefinition(
    description="Code implementation specialist that writes, edits, and builds code according to a plan. Use this agent after planning is complete to execute the implementation step by step.",
    prompt="""You are the implementation agent for autonomous-coder v3.

Your responsibility is to execute the implementation plan produced by the planner.

WORKFLOW
1. Retrieve the plan:
   - Call get_findings("plan") for the implementation plan
   - Call get_findings("onboard") for project conventions (if available)
   - Call get_findings("research") for API details and library documentation
2. Execute tasks in order, respecting dependencies.
3. For each task:
   a. Read the files listed in the task's "read" and "modify" lists
   b. Write or edit files as specified
   c. If dependencies need installing, run the appropriate package manager command
   d. Run the task's validation command to verify the step succeeded
   e. If validation fails, debug and fix before moving to the next task
   f. Call track_phase("implement", "progress", "Completed task N: title")
4. After all tasks complete, run the plan's overall validation.

CODE QUALITY RULES
- Follow existing project conventions discovered during onboarding
- Include all necessary imports — no partial implementations
- Handle errors explicitly — no bare except, no swallowed errors
- Write complete functions — no TODO placeholders or stubs
- Match project code style for indentation, quotes, line length

VALIDATION RULES
- NEVER create test files (.test.ts, _test.py, .spec.js, test_*.py, etc.)
- NEVER create mock objects, test doubles, stubs, or fixtures
- NEVER import testing frameworks for validation
- Validate through REAL execution: build commands, curl requests, running the application
- If a build fails, fix the code — do not skip validation

CONSTRAINTS
- Follow the plan. If flawed, fix it and document why, but do not skip steps.
- Use Context7 for library documentation when needed.
- Use save_findings to persist implementation progress.
- Call track_phase("implement", "complete", summary) when done.""",
    tools=["Read", "Write", "Edit", "Bash", "Glob", "Grep",
           "mcp__Context7__resolve-library-id", "mcp__Context7__get-library-docs",
           "mcp__ac-tools__save_findings", "mcp__ac-tools__get_findings",
           "mcp__ac-tools__track_phase", "mcp__ac-tools__checkpoint"],
    model="opus",
)
```

**Responsibility Matrix**: DOES: Write/edit code, run builds, install deps, verify steps. NEVER: Create test files, use mocks, skip validation.

**Model Rationale**: Opus — deep code understanding, multi-file coordination, build failure debugging.

### 2.5 Validator

```python
"validator": AgentDefinition(
    description="Validation specialist that verifies implementations work correctly through real system execution. Runs builds, executes applications, hits real endpoints, produces evidence-based PASS/FAIL reports. Never mocks.",
    prompt="""You are the validation agent for autonomous-coder v3.

Your sole responsibility is to verify the implementation works through real system execution.

WORKFLOW
1. Retrieve context:
   - Call get_findings("plan") for validation plan and task list
   - Call get_findings("implement") for implementation progress
   - Call get_findings("onboard") for project conventions (if available)
2. Build Verification:
   - Run the project's build command
   - Verify zero errors
3. Functional Validation:
   - For each task, execute its validation criteria
   - For the overall plan, execute end-to-end checks
   - Start servers if needed, make real HTTP requests, verify responses
4. Regression Detection:
   - If existing project, verify pre-existing functionality still works
5. Produce Evidence Report.

OUTPUT FORMAT
For each check:
- Check: what was tested
- Command: exact command executed
- Result: PASS or FAIL
- Evidence: actual stdout/stderr (truncated to 500 chars)
- Severity: critical | warning | info

Summary: Total checks, Passed, Failed, Overall PASS/FAIL

RULES
- ALL testing uses real execution — NEVER create test files, mocks, stubs, or fixtures
- Run actual build commands, start actual servers, hit actual endpoints
- Do not claim PASS without actual command output
- Use validate_task to record evidence for each validation point
- Call track_phase("validate", "complete", summary) when finished

CONSTRAINTS
- Do not fix code. Report failures with evidence.
- Do not create any new files.
- Do not modify source code.
- Stop servers when done validating.""",
    tools=["Bash", "Read", "Glob", "Grep",
           "mcp__ac-tools__get_findings", "mcp__ac-tools__validate_task",
           "mcp__ac-tools__track_phase"],
    model="sonnet",
)
```

**Responsibility Matrix**: DOES: Run builds, execute apps, make requests, produce evidence. NEVER: Write code, create test files, claim PASS without evidence.

**Model Rationale**: Sonnet — command execution and output comparison. Cost-effective for high-tool-use phase.

### 2.6 Spec-Builder

```python
"spec-builder": AgentDefinition(
    description="Project scaffolding specialist for greenfield projects. Selects tech stack, creates directory structure, sets up config, initializes package manager. Only used in greenfield mode.",
    prompt="""You are the spec-builder agent for autonomous-coder v3.

Your responsibility is to scaffold a new project from scratch.

WORKFLOW
1. Retrieve research: Call get_findings("research") for technology evaluation
2. Decide: primary language/framework, package manager, structure, build tooling, linting
3. Create project structure:
   - Initialize package manager
   - Create directories following framework conventions
   - Set up config files
   - Create CLAUDE.md with project conventions
   - Set up .gitignore
   - Initialize git repository
4. Verify: Run build command, verify skeleton compiles
5. Persist: Save scaffold summary as onboarding findings

OUTPUT FORMAT
- Stack Decision: language, framework, package manager, and why
- Structure: directory tree with annotations
- Configuration: key config files
- Build Verification: proof the scaffold builds

CONSTRAINTS
- Create MINIMAL viable scaffold — no business logic.
- Follow framework's official conventions.
- Include CLAUDE.md describing conventions.
- Run build to verify before declaring complete.
- Use save_findings to persist context.
- Call track_phase("scaffold", "complete", summary) when finished.""",
    tools=["Read", "Write", "Edit", "Bash", "Glob", "Grep",
           "mcp__Context7__resolve-library-id", "mcp__Context7__get-library-docs",
           "mcp__ac-tools__save_findings", "mcp__ac-tools__get_findings",
           "mcp__ac-tools__track_phase", "mcp__ac-tools__checkpoint"],
    model="opus",
)
```

**Responsibility Matrix**: DOES: Select stack, scaffold structure, verify build. NEVER: Implement business logic, create test files.

**Model Rationale**: Opus — broad knowledge needed for tech stack selection.

---

## Section 3: Custom MCP Tools

All custom tools implemented via `@tool` + `create_sdk_mcp_server`. Server named `ac-tools`.

### 3.1 Persistence Layer

```python
import json, os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from claude_agent_sdk import tool, create_sdk_mcp_server

_project_path: Path = Path(".")

def _findings_dir() -> Path:
    d = _project_path / ".autonomous-coder" / "findings"
    d.mkdir(parents=True, exist_ok=True)
    return d

def _phases_file() -> Path:
    d = _project_path / ".autonomous-coder"
    d.mkdir(parents=True, exist_ok=True)
    return d / "phases.json"
```

### 3.2 track_phase

```python
@tool(
    "track_phase",
    "Track phase lifecycle transitions. Status: started|progress|complete|failed.",
    {"phase": str, "status": str, "details": str},
)
async def track_phase(args: dict[str, Any]) -> dict[str, Any]:
    phases_file = _phases_file()
    phases = json.loads(phases_file.read_text()) if phases_file.exists() else []
    phases.append({
        "phase": args["phase"], "status": args["status"],
        "details": args["details"],
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    phases_file.write_text(json.dumps(phases, indent=2))
    return {"content": [{"type": "text", "text": f"Phase '{args['phase']}' tracked: {args['status']}"}]}
```

### 3.3 save_findings

```python
@tool(
    "save_findings",
    "Persist findings to disk (survives context compaction). Category = phase name.",
    {"category": str, "content": str, "filename": str},
)
async def save_findings(args: dict[str, Any]) -> dict[str, Any]:
    filename = args.get("filename") or f"{args['category']}.md"
    filepath = _findings_dir() / filename
    filepath.write_text(args["content"])
    return {"content": [{"type": "text", "text": f"Saved to {filepath} ({len(args['content'])} chars)"}]}
```

### 3.4 get_findings

```python
@tool(
    "get_findings",
    "Retrieve previously saved findings for a category.",
    {"category": str},
)
async def get_findings(args: dict[str, Any]) -> dict[str, Any]:
    category = args["category"]
    exact = _findings_dir() / f"{category}.md"
    if exact.exists():
        return {"content": [{"type": "text", "text": exact.read_text()}]}
    matches = sorted(_findings_dir().glob(f"{category}*"))
    if not matches:
        return {"content": [{"type": "text", "text": f"No findings for '{category}'"}]}
    parts = [f"--- {f.name} ---\n{f.read_text()}" for f in matches]
    return {"content": [{"type": "text", "text": "\n\n".join(parts)}]}
```

### 3.5 validate_task

```python
@tool(
    "validate_task",
    "Record validation evidence. Rejects empty or placeholder evidence.",
    {"task_id": str, "evidence": str},
)
async def validate_task(args: dict[str, Any]) -> dict[str, Any]:
    task_id, evidence = args["task_id"], args["evidence"]
    if not evidence or len(evidence.strip()) < 10:
        return {"content": [{"type": "text", "text": f"REJECTED: Evidence too short for '{task_id}'."}], "is_error": True}
    placeholders = ["todo", "placeholder", "will verify", "should work", "looks good"]
    if any(p in evidence.lower() for p in placeholders):
        return {"content": [{"type": "text", "text": f"REJECTED: Placeholder language in '{task_id}'."}], "is_error": True}
    validation_dir = _findings_dir() / "validation"
    validation_dir.mkdir(parents=True, exist_ok=True)
    record = {"task_id": task_id, "evidence": evidence, "timestamp": datetime.now(timezone.utc).isoformat()}
    (validation_dir / f"{task_id}.json").write_text(json.dumps(record, indent=2))
    return {"content": [{"type": "text", "text": f"Evidence recorded for '{task_id}' ({len(evidence)} chars)"}]}
```

### 3.6 checkpoint

```python
@tool(
    "checkpoint",
    "Create a named checkpoint label. File rollback uses SDK file checkpointing.",
    {"label": str},
)
async def checkpoint(args: dict[str, Any]) -> dict[str, Any]:
    label = args["label"]
    cp_file = _project_path / ".autonomous-coder" / "checkpoints.json"
    cp_file.parent.mkdir(parents=True, exist_ok=True)
    cps = json.loads(cp_file.read_text()) if cp_file.exists() else []
    cps.append({"label": label, "timestamp": datetime.now(timezone.utc).isoformat()})
    cp_file.write_text(json.dumps(cps, indent=2))
    return {"content": [{"type": "text", "text": f"Checkpoint '{label}' recorded."}]}
```

### 3.7 Server Assembly

```python
def create_ac_tools_server(project_path: Path) -> Any:
    global _project_path
    _project_path = project_path
    return create_sdk_mcp_server(
        name="ac-tools", version="3.0.0",
        tools=[track_phase, save_findings, get_findings, validate_task, checkpoint],
    )
```

---

## Section 4: Hook Architecture

### 4.1 PreToolUse — Test File Blocker

```python
async def test_file_blocker(input_data, tool_use_id, context):
    tool_name = input_data.get("tool_name", "")
    if tool_name not in ("Write", "Edit"):
        return {}
    file_path = input_data.get("tool_input", {}).get("file_path", "")
    test_patterns = ["test_", "_test.", ".test.", ".spec.", "__tests__/", "/tests/test", "/test/", "conftest.py", "fixtures/"]
    for pattern in test_patterns:
        if pattern in file_path.lower():
            return {"hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": f"Blocked: writing to test file '{file_path}'. Validate through real execution.",
            }}
    return {}
```

**HookMatcher**: `HookMatcher(matcher="Write|Edit", hooks=[test_file_blocker])`

### 4.2 PreToolUse — Display Hook

```python
async def pre_tool_display(input_data, tool_use_id, context):
    tool_name = input_data.get("tool_name", "")
    tool_input = input_data.get("tool_input", {})
    display.on_tool_start(tool_name, _summarize_tool(tool_name, tool_input), tool_use_id)
    return {}
```

**HookMatcher**: `HookMatcher(matcher=None, hooks=[pre_tool_display])`

### 4.3 PostToolUse — Display Hook

```python
async def post_tool_display(input_data, tool_use_id, context):
    display.on_tool_complete(input_data.get("tool_name", ""), input_data.get("tool_output", ""), tool_use_id)
    return {}
```

### 4.4 SubagentStart / SubagentStop — Phase Tracking

```python
async def subagent_start_handler(input_data, tool_use_id, context):
    display.on_subagent_start(input_data.get("agent_name", "unknown"), tool_use_id)
    return {}

async def subagent_stop_handler(input_data, tool_use_id, context):
    display.on_subagent_stop(input_data.get("agent_name", "unknown"), tool_use_id)
    return {}
```

### 4.5 Stop — Session Summary

```python
async def session_stop_handler(input_data, tool_use_id, context):
    display.on_session_stop()
    return {}
```

### 4.6 PreCompact — Findings Reminder

```python
async def pre_compact_handler(input_data, tool_use_id, context):
    return {"systemMessage": (
        "CONTEXT COMPACTION OCCURRING. To recover phase data, call get_findings() "
        "with category names: onboard, research, plan, implement, validate, scaffold."
    )}
```

### Complete Assembly

```python
def build_hooks(display_instance):
    global display
    display = display_instance
    return {
        "PreToolUse": [
            HookMatcher(matcher="Write|Edit", hooks=[test_file_blocker]),
            HookMatcher(matcher=None, hooks=[pre_tool_display]),
        ],
        "PostToolUse": [HookMatcher(matcher=None, hooks=[post_tool_display])],
        "SubagentStart": [HookMatcher(matcher=None, hooks=[subagent_start_handler])],
        "SubagentStop": [HookMatcher(matcher=None, hooks=[subagent_stop_handler])],
        "Stop": [HookMatcher(matcher=None, hooks=[session_stop_handler])],
        "PreCompact": [HookMatcher(matcher=None, hooks=[pre_compact_handler])],
    }
```

---

## Section 5: Permission Architecture

### 5.1 Evaluation Flow

```
Tool Invocation
  |-> 1. PreToolUse Hooks (test_file_blocker can deny)
  |-> 2. Deny Rules (disallowed_tools)
  |-> 3. Permission Mode (acceptEdits auto-approves file ops)
  |-> 4. Allow Rules (allowed_tools)
  |-> 5. can_use_tool Callback (Bash validation)
```

### 5.2 can_use_tool

```python
async def can_use_tool(tool_name, tool_input, ctx):
    if tool_name != "Bash":
        return PermissionResultAllow(behavior="allow", updated_input=None, updated_permissions=None)
    command = tool_input.get("command", "")
    is_allowed, reason = is_command_allowed(command)
    if not is_allowed:
        return PermissionResultDeny(behavior="deny", message=f"Blocked: {reason}", interrupt=False)
    return PermissionResultAllow(behavior="allow", updated_input=None, updated_permissions=None)
```

### 5.3 Bash Security

**Tier 1 — Blocklist** (20 patterns): `rm -rf /`, `mkfs`, `dd if=`, fork bomb, `chmod 777`, `sudo rm`, `curl | sh`, `eval $(`, etc.

**Tier 2 — Allowlist** (142 commands): Package managers, build tools, runtimes, shell utilities, dev tools, DB clients, cloud CLIs.

### 5.4 Subagent Propagation

Subagents restricted by `AgentDefinition.tools` (what they CAN call) + parent hooks/can_use_tool (validated on every call). Onboarder can't Bash; implementer's Bash goes through security callback.

---

## Section 6: Streaming Output Architecture

### 6.1 Display Class

```python
class Display:
    def __init__(self, verbose=False):
        self.verbose = verbose
        self.start_time = time.time()
        self.active_subagents = {}
        self.total_cost = 0.0
        self.session_id = None

    def _ts(self):
        elapsed = time.time() - self.start_time
        return f"[{int(elapsed//60):02d}:{elapsed%60:04.1f}]"

    def on_session_start(self, session_id, model): ...
    def on_mcp_connected(self, name, tool_count, in_process=False): ...
    def on_phase_start(self, name, index, total, detail=""): ...
    def on_phase_complete(self, name, cost, duration): ...
    def on_tool_start(self, name, summary, tool_use_id=None): ...
    def on_tool_complete(self, name, output, tool_use_id=None): ...
    def on_subagent_start(self, name, tool_use_id): ...
    def on_subagent_stop(self, name, tool_use_id): ...
    def on_session_stop(self): ...
```

### 6.2 Subagent Tracking

Messages from subagents have `parent_tool_use_id` matching the Agent tool's `tool_use_id`. Display uses this for indentation and cost attribution.

### 6.3 Example Output

```
[00:00.0] Session starting... (session_id: s_abc123)
[00:00.1] MCP servers connecting...
[00:00.3]   context7: connected (2 tools)
[00:00.5]   firecrawl: connected (4 tools)
[00:00.8]   ac-tools: connected (5 tools) [in-process]
[00:01.0] Agent initialized (model: claude-opus-4-6, 1M context)

==================================================
PHASE 1/5: ONBOARDING (existing project detected)
==================================================
[00:01.2] >> Subagent: onboarder
[00:01.5]   Tool: Read — CLAUDE.md
[00:02.0]   Tool: Glob — **/*.py (found 47 files)
[00:15.0]   Tool: mcp__ac-tools__save_findings — onboard
[00:15.2] << Subagent: onboarder (14.0s)
[00:15.2] Phase 1 complete ($0.12, 14.0s)
```

---

## Section 7: Execution Flow

### 7.1 Existing Project

CLI parse → detect existing → Create Display, ac-tools MCP → Build ClaudeAgentOptions (opus, 1M context, all agents, all MCP, all hooks, can_use_tool, acceptEdits, streaming, checkpointing) → ClaudeSDKClient session → Orchestrator invokes: onboarder → researcher → planner → implementer → validator → Session summary → Exit.

### 7.2 Greenfield

Same, but orchestrator invokes: spec-builder → researcher → planner → implementer → validator.

### 7.3 Main Loop

```python
async def run(config: AutonomousCoderConfig) -> int:
    display = Display(verbose=config.verbose)
    entry_path = detect_entry_path(config.project_path, config.greenfield)
    ac_tools = create_ac_tools_server(config.project_path)
    agents = build_agent_definitions(entry_path)
    hooks = build_hooks(display)

    options = ClaudeAgentOptions(
        model=config.model, betas=["context-1m-2025-08-07"],
        agents=agents, mcp_servers=build_mcp_servers(config.project_path, ac_tools),
        hooks=hooks, can_use_tool=can_use_tool,
        permission_mode="acceptEdits", include_partial_messages=True,
        enable_file_checkpointing=True, cwd=str(config.project_path),
        max_turns=config.max_turns, max_budget_usd=config.max_budget,
        effort=config.effort, resume=config.resume_session_id,
        setting_sources=["project"],
    )

    prompt = build_orchestrator_prompt(config.task, entry_path, config.dry_run)

    async with ClaudeSDKClient(options) as client:
        display.on_session_start("pending", config.model)
        await client.query(_wrap_prompt(prompt))
        result = await process_stream(client, display)

    if result is None:
        return 1
    display.session_id = result.session_id
    display.on_session_stop()
    return 0 if not result.is_error else 1
```

---

## Section 8: File Structure

```
autonomous-coder/
  pyproject.toml              (~40 lines)
  CLAUDE.md
  src/autonomous_coder/
    __init__.py               (~20 lines)
    __main__.py               (~80 lines)
    cli.py                    (~120 lines)
    config.py                 (~60 lines)
    runner.py                 (~100 lines)
    agents.py                 (~400 lines)
    mcp_tools.py              (~250 lines)
    hooks.py                  (~200 lines)
    security.py               (~300 lines)
    display.py                (~250 lines)
    stream.py                 (~100 lines)
    prompt.py                 (~80 lines)
  TOTAL: ~2,000 lines
```

---

## Section 9: Configuration

### AutonomousCoderConfig

```python
@dataclass
class AutonomousCoderConfig:
    task: str
    project_path: Path
    model: str = "claude-opus-4-6"
    research_model: str = "sonnet"
    implement_model: str = "opus"
    max_turns: int = 200
    max_budget: float = 50.0
    effort: str = "high"
    resume_session_id: str | None = None
    greenfield: bool = False
    dry_run: bool = False
    verbose: bool = False
```

### Budget

SDK `max_budget_usd` as hard ceiling + Display accumulates `ResultMessage.total_cost_usd`. Orchestrator prompt monitors cost.

---

## Section 10: Session Management

**Session ID**: From `ResultMessage.session_id`. **Resume**: `ClaudeAgentOptions(resume=session_id)`. **Checkpointing**: `enable_file_checkpointing=True` tracks Write/Edit (not Bash). **Findings**: `.autonomous-coder/findings/` survives compaction. **PreCompact** hook reminds about `get_findings()`.

---

## Section 11: CLI

```
autonomous-coder <task-spec-file> --project <path>
  --task "inline task"
  --model <model>              (default: claude-opus-4-6)
  --research-model <model>     (default: sonnet)
  --implement-model <model>    (default: opus)
  --max-turns <int>            (default: 200)
  --max-budget <float>         (default: 50.0)
  --effort low|medium|high|max (default: high)
  --verbose / -v
  --resume <session-id>
  --greenfield
  --dry-run
```

**Exit codes**: 0 (success), 1 (failure), 2 (invalid args), 130 (SIGINT).
