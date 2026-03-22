# AUTONOMOUS-CODER v3: Architecture Design + 5 Critiques

## PURPOSE
Research + Design. Produce a complete architecture document for autonomous-coder v3 built on the Claude Agent SDK Python library (`claude-agent-sdk` PyPI, v0.1.49+), then produce 5 independent architectural critiques.

## OUTPUT FORMAT
Write two files:
1. `autonomous-coder-v3-architecture.md` — the complete architecture document
2. `autonomous-coder-v3-critiques.md` — 5 independent critiques from different perspectives

---

## MANDATORY RESEARCH PHASE

Before designing ANYTHING, you MUST read the following sources completely. Do not skim. Do not assume.

### SDK Documentation (read ALL via WebFetch)
- https://platform.claude.com/docs/en/agent-sdk/python — Full Python API reference
- https://platform.claude.com/docs/en/agent-sdk/streaming-vs-single-mode — Streaming vs single message (WE USE STREAMING ONLY)
- https://platform.claude.com/docs/en/agent-sdk/permissions — Permission modes, can_use_tool, allow/deny rules
- https://platform.claude.com/docs/en/agent-sdk/user-input — CanUseTool callback, PermissionResultAllow/Deny
- https://platform.claude.com/docs/en/agent-sdk/hooks — HookMatcher, PreToolUse, PostToolUse, SubagentStart/Stop, Stop, PreCompact
- https://platform.claude.com/docs/en/agent-sdk/file-checkpointing — enable_file_checkpointing, rewind_files
- https://platform.claude.com/docs/en/agent-sdk/structured-outputs — output_format, JSON Schema, Pydantic
- https://platform.claude.com/docs/en/agent-sdk/modifying-system-prompts — system_prompt, SystemPromptPreset, append, CLAUDE.md
- https://platform.claude.com/docs/en/agent-sdk/mcp — MCP servers (stdio, SSE, HTTP, SDK in-process)
- https://platform.claude.com/docs/en/agent-sdk/custom-tools — @tool decorator, create_sdk_mcp_server
- https://platform.claude.com/docs/en/agent-sdk/subagents — AgentDefinition, Agent tool, inheritance, parallel execution
- https://platform.claude.com/docs/en/agent-sdk/slash-commands — Slash commands in SDK
- https://platform.claude.com/docs/en/agent-sdk/skills — Skills (SKILL.md), setting_sources, Skill tool
- https://platform.claude.com/docs/en/agent-sdk/cost-tracking — ResultMessage.total_cost_usd, usage tracking
- https://platform.claude.com/docs/en/agent-sdk/todo-tracking — Todo tracking
- https://platform.claude.com/docs/en/agent-sdk/plugins — SdkPluginConfig, local plugins
- https://platform.claude.com/docs/en/agent-sdk/streaming-output — include_partial_messages, StreamEvent

### Cookbook Implementations (read ALL locally)
- /Users/nick/Desktop/claude-cookbooks/claude_agent_sdk/research_agent/agent.py
- /Users/nick/Desktop/claude-cookbooks/claude_agent_sdk/chief_of_staff_agent/agent.py
- /Users/nick/Desktop/claude-cookbooks/claude_agent_sdk/chief_of_staff_agent/CLAUDE.md
- /Users/nick/Desktop/claude-cookbooks/claude_agent_sdk/chief_of_staff_agent/.claude/agents/*.md
- /Users/nick/Desktop/claude-cookbooks/claude_agent_sdk/chief_of_staff_agent/.claude/hooks/*.py
- /Users/nick/Desktop/claude-cookbooks/claude_agent_sdk/observability_agent/agent.py
- /Users/nick/Desktop/claude-cookbooks/claude_agent_sdk/site_reliability_agent/sre_mcp_server.py
- /Users/nick/Desktop/claude-cookbooks/claude_agent_sdk/site_reliability_agent/infra_setup.py

### Original Quickstart Reference (read ALL)
- /tmp/claude-quickstarts/autonomous-coding/agent.py
- /tmp/claude-quickstarts/autonomous-coding/client.py
- /tmp/claude-quickstarts/autonomous-coding/security.py
- /tmp/claude-quickstarts/autonomous-coding/progress.py
- /tmp/claude-quickstarts/autonomous-coding/prompts.py
- /tmp/claude-quickstarts/autonomous-coding/README.md

### Current Codebase (read ALL Python files in src/)
- /Users/nick/Desktop/autonomous-coder/src/autonomous_coder/*.py
- /Users/nick/Desktop/autonomous-coder/src/autonomous_coder/agents/*.py
- /Users/nick/Desktop/autonomous-coder/src/autonomous_coder/widgets/*.py
- /Users/nick/Desktop/autonomous-coder/pyproject.toml

### User's Claude Code Configuration (understand patterns)
- /Users/nick/.claude/CLAUDE.md — global rules and philosophy
- /Users/nick/.claude/rules/*.md — all rule files (workflow, search-protocol, patterns, git, etc.)
- /Users/nick/.claude/skills/functional-validation/ — THE functional validation skill (read SKILL.md completely)
- /Users/nick/.claude/skills/plan/ — planning skill (read SKILL.md completely)
- /Users/nick/CLAUDE.md — project-level CLAUDE.md

---

## VERIFIED SDK KNOWLEDGE (ground truth from official docs)

### Architecture Constraint: ALWAYS ClaudeSDKClient, NEVER Single Message Mode

Single message mode (`query(prompt="string")`) does NOT support:
- Hooks
- Custom MCP tools (require streaming input)
- Image attachments
- Dynamic message queueing
- Real-time interruption

We ALWAYS use `ClaudeSDKClient` for full capability access.

### ClaudeAgentOptions (complete dataclass)
```python
@dataclass
class ClaudeAgentOptions:
    tools: list[str] | ToolsPreset | None = None
    allowed_tools: list[str] = field(default_factory=list)
    system_prompt: str | SystemPromptPreset | None = None
    mcp_servers: dict[str, McpServerConfig] | str | Path = field(default_factory=dict)
    permission_mode: PermissionMode | None = None  # "default"|"acceptEdits"|"plan"|"bypassPermissions"
    continue_conversation: bool = False
    resume: str | None = None
    max_turns: int | None = None
    max_budget_usd: float | None = None
    disallowed_tools: list[str] = field(default_factory=list)
    model: str | None = None
    fallback_model: str | None = None
    betas: list[SdkBeta] = field(default_factory=list)  # ["context-1m-2025-08-07"]
    output_format: dict[str, Any] | None = None  # structured outputs
    cwd: str | Path | None = None
    settings: str | None = None
    add_dirs: list[str | Path] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    can_use_tool: CanUseTool | None = None
    hooks: dict[HookEvent, list[HookMatcher]] | None = None
    agents: dict[str, AgentDefinition] | None = None
    setting_sources: list[SettingSource] | None = None  # ["user", "project", "local"]
    sandbox: SandboxSettings | None = None
    plugins: list[SdkPluginConfig] = field(default_factory=list)
    thinking: ThinkingConfig | None = None
    effort: Literal["low", "medium", "high", "max"] | None = None
    include_partial_messages: bool = False  # MUST be True for streaming output
    enable_file_checkpointing: bool = False
    fork_session: bool = False
    user: str | None = None
```

### AgentDefinition (4 fields ONLY)
```python
@dataclass
class AgentDefinition:
    description: str  # when to use this agent
    prompt: str       # system prompt
    tools: list[str] | None = None  # inherits all if omitted
    model: Literal["sonnet", "opus", "haiku", "inherit"] | None = None
```
- NO mcp_servers field. Subagents inherit parent MCP servers.
- Subagents CANNOT spawn subagents (no "Agent" in their tools).
- Subagent transcripts survive parent context compaction.
- Tool name is "Agent" (renamed from "Task" in v2.1.63).

### Message Types
```python
Message = UserMessage | AssistantMessage | SystemMessage | ResultMessage | StreamEvent

# ResultMessage fields:
subtype: str, duration_ms: int, duration_api_ms: int, is_error: bool,
num_turns: int, session_id: str, total_cost_usd: float | None,
usage: dict | None, result: str | None, structured_output: Any

# StreamEvent (when include_partial_messages=True):
uuid: str, session_id: str, event: dict, parent_tool_use_id: str | None
# event types: message_start, content_block_start, content_block_delta,
#              content_block_stop, message_delta, message_stop
```

### Hook Events
```python
HookEvent = Literal[
    "PreToolUse", "PostToolUse", "PostToolUseFailure",
    "UserPromptSubmit", "Stop", "SubagentStop", "PreCompact",
    "Notification", "SubagentStart", "PermissionRequest"
]

# Hook callback signature:
async def hook(input_data: dict, tool_use_id: str | None, context: HookContext) -> dict

# PreToolUse can deny:
return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny", "permissionDecisionReason": "..."}}

# Hooks can inject system messages:
return {"systemMessage": "Remember: ..."}
```

### can_use_tool (permission callback)
```python
async def can_use_tool(tool_name: str, input_data: dict, context: ToolPermissionContext) -> PermissionResult

PermissionResultAllow(behavior="allow", updated_input=dict|None, updated_permissions=list|None)
PermissionResultDeny(behavior="deny", message="...", interrupt=False)  # interrupt=False = graceful denial
```

### Custom MCP Tools
```python
@tool("name", "description", {"param": type})
async def my_tool(args: dict) -> dict:
    return {"content": [{"type": "text", "text": "result"}]}

server = create_sdk_mcp_server(name="my-server", version="1.0.0", tools=[my_tool])
# Wire into ClaudeAgentOptions(mcp_servers={"my-server": server})
# Access as: mcp__my-server__name
# REQUIRES streaming input mode (ClaudeSDKClient, NOT string prompt)
```

### Permission Evaluation Order
1. Hooks (PreToolUse) — can allow, deny, or continue
2. Deny rules (disallowed_tools) — always blocks, even in bypassPermissions
3. Permission mode — bypassPermissions approves everything not denied
4. Allow rules (allowed_tools) — auto-approve matched tools
5. can_use_tool callback — final decision for unresolved tools

### ClaudeSDKClient Methods
```python
async with ClaudeSDKClient(options) as client:
    await client.query(prompt)           # send query (string or async generator)
    async for msg in client.receive_response():  # stream responses
    await client.interrupt()             # stop mid-execution
    await client.set_permission_mode(mode)  # change permissions dynamically
    await client.set_model(model)        # change model mid-session
    await client.add_mcp_server(name, config)   # hot-add MCP server
    await client.remove_mcp_server(name)        # hot-remove MCP server
    await client.rewind_files(checkpoint_uuid)  # restore files to checkpoint
    await client.get_mcp_status()        # check MCP server health
```

---

## DESIGN REQUIREMENTS

### Core Philosophy (non-negotiable)
1. NEVER create mocks, stubs, test doubles, or test files
2. ALWAYS functionally validate through real system execution
3. ALWAYS research and gather context BEFORE attempting implementation
4. NEVER claim completion without evidence (screenshots, logs, build output)
5. YAGNI / KISS / DRY
6. Full streaming visibility — user sees every token, every tool call, every subagent event in real-time
7. Opus with 1M token context (`betas=["context-1m-2025-08-07"]`)

### Two Distinct Entry Paths
1. **Greenfield**: No existing project. autonomous-coder becomes a spec builder — research, design, scaffold, implement, validate.
2. **Existing Project**: Project exists. autonomous-coder onboards first — reads CLAUDE.md, scans codebase structure, understands patterns/conventions/dependencies — THEN plans and executes the requested task.

### What autonomous-coder v3 Controls (Python code)
- Phase transitions (Python for-loop using ClaudeSDKClient multi-turn)
- Agent definitions (programmatic AgentDefinition per role)
- Tool permissions (can_use_tool callback for security)
- Observability (hooks for every lifecycle event — PreToolUse, PostToolUse, SubagentStart/Stop)
- Streaming output (include_partial_messages=True, StreamEvent processing for real-time display)
- Cost tracking (per-phase via ResultMessage, per-subagent via TaskNotificationMessage)
- File checkpointing (enable_file_checkpointing=True for rollback)
- Session resume (--resume flag, session_id persistence)
- Custom MCP tools (track_phase, save_findings, get_findings for context-compaction-safe data)
- Structured outputs (output_format with Pydantic schemas for typed phase results)
- Skills and plugins (setting_sources, SdkPluginConfig for extensibility)

### What Claude Controls (inside the agent loop)
- Which tools to call and when
- Which subagents to spawn (based on AgentDefinition descriptions)
- How to interpret research findings
- How to break down implementation tasks
- How to validate results
- When to call custom MCP tools (track_phase, save_findings)

### Functional Validation Integration
The user's current Claude Code setup has a `functional-validation` skill at `~/.claude/skills/functional-validation/`. This skill enforces:
- Build and run the REAL system
- Validate through actual user interfaces
- Capture and verify evidence before claiming completion
- Never write mocks, stubs, test doubles, or test files

In v3, this philosophy must be enforced through MULTIPLE mechanisms:
- **System prompt**: Encode the rules directly
- **CLAUDE.md**: Persistent context the agent loads via setting_sources
- **Hooks**: PreToolUse hook that blocks Write/Edit to test files (*.test.*, *_test.*, test_*)
- **can_use_tool**: Custom permission logic that enforces validation-before-completion
- **Custom MCP tools**: `validate_task` tool that requires evidence artifacts before marking a task complete
- **Structured outputs**: Phase results must include `evidence` field

### CLI Interface
```
autonomous-coder <task-spec-file> --project <path>
  --model <model>                    # orchestrator model (default: claude-opus-4-6)
  --research-model <model>           # researcher subagent model
  --implement-model <model>          # implementer subagent model
  --max-turns <int>                  # max agent loop turns (default: 200)
  --max-budget <float>               # cost ceiling in USD (default: 50.0)
  --effort <low|medium|high|max>     # thinking effort
  --verbose / -v                     # show all streaming output
  --resume <session-id>              # resume previous session
  --greenfield                       # force greenfield mode (skip onboarding)
  --dry-run                          # plan mode only, no execution
```

Also support inline task:
```
autonomous-coder --task "Add user authentication" --project ~/myapp
```

### Streaming CLI Output (real-time, never blank)
From the moment the user presses Enter:
```
[00:00.0] Session starting... (session_id: abc123)
[00:00.1] MCP servers connecting...
[00:00.3]   context7: connected (4 tools)
[00:00.5]   firecrawl: connected (2 tools)
[00:00.7]   serena: connected (12 tools)
[00:00.8]   ac-tools: connected (3 tools) [in-process]
[00:01.0] Agent initialized (model: claude-opus-4-6, 1M context)

═══════════════════════════════════════════════════
  PHASE 1/4: ONBOARDING (existing project detected)
═══════════════════════════════════════════════════
[00:01.2] Reading CLAUDE.md...
[00:01.5] Scanning project structure...
[00:02.3] Tool: Glob — **/*.py (found 47 files)
[00:02.8] Tool: Read — src/main.py
[00:03.1] Tool: Read — pyproject.toml
...
[00:15.0] Phase 1 complete ($0.12, 14.0s)

═══════════════════════════════════════════════════
  PHASE 2/4: RESEARCH
═══════════════════════════════════════════════════
[00:15.1] >> Subagent: researcher (technology-evaluation)
[00:15.2]    Tool: WebSearch — "fastapi authentication best practices 2026"
[00:16.5]    Tool: WebFetch — https://fastapi.tiangolo.com/...
[00:18.0] << Subagent complete (researcher, $0.08, 2.9s)
[00:18.1] >> Subagent: researcher (codebase-analysis)
[00:18.2]    Tool: Read — src/auth/...
...
[00:25.0] save_findings("research", ...) — saved to .autonomous-coder/findings/research.md
[00:25.1] Phase 2 complete ($0.35, 10.1s)

═══════════════════════════════════════════════════
  PHASE 3/4: PLAN + IMPLEMENT
═══════════════════════════════════════════════════
[00:25.2] >> Subagent: planner
...
[00:30.0] save_findings("plan", ...) — saved to .autonomous-coder/findings/plan.md
[00:30.1] >> Subagent: implementer
[00:30.2]    Tool: Edit — src/auth/router.py
[00:31.5]    Tool: Write — src/auth/middleware.py
[00:33.0]    Tool: Bash — pip install python-jose
...
[00:45.0] Phase 3 complete ($1.20, 19.9s)

═══════════════════════════════════════════════════
  PHASE 4/4: VALIDATE
═══════════════════════════════════════════════════
[00:45.1] >> Subagent: validator
[00:45.2]    Tool: Bash — python -m pytest (NO — blocked by hook: no test files)
[00:45.3]    Tool: Bash — uvicorn src.main:app --port 8000 &
[00:46.0]    Tool: Bash — curl http://localhost:8000/auth/login -d '{"user":"test"}'
[00:46.5]    Evidence: HTTP 200, token returned
[00:47.0]    Tool: Bash — curl http://localhost:8000/protected -H 'Authorization: Bearer ...'
[00:47.3]    Evidence: HTTP 200, protected resource accessed
...
[00:50.0] Phase 4 complete ($0.15, 5.0s)

═══════════════════════════════════════════════════
  SESSION COMPLETE
═══════════════════════════════════════════════════
Total cost: $1.82 | Turns: 47 | Duration: 50.0s
Session ID: abc123 (use --resume abc123 to continue)
Findings: .autonomous-coder/findings/
```

---

## ARCHITECTURE DOCUMENT REQUIREMENTS

The architecture document must include:

### 1. System Overview
- What autonomous-coder v3 IS and ISN'T
- Value proposition vs raw Claude Code CLI
- The two entry paths (greenfield vs existing)

### 2. Agent Definitions
For EACH agent, specify:
- Name, description (for AgentDefinition)
- System prompt (full text)
- Tools list
- Model selection with rationale
- What this agent is responsible for
- What this agent must NEVER do

Proposed agents:
- **onboarder** — reads project structure, CLAUDE.md, dependencies; produces project context summary
- **researcher** — web search, documentation retrieval, library evaluation
- **planner** — task decomposition, dependency mapping, file-level change plan
- **implementer** — code writing/editing, dependency installation, build verification
- **validator** — functional validation with real execution, evidence collection
- **spec-builder** (greenfield only) — project scaffolding, initial structure, tech stack selection

### 3. Custom MCP Tools
- `track_phase(phase, status, details)` — phase lifecycle tracking
- `save_findings(category, content, filename)` — persist data to disk (survives compaction)
- `get_findings(category)` — retrieve persisted data
- `validate_task(task_id, evidence)` — requires evidence artifacts before marking complete
- `checkpoint(label)` — manual checkpoint for rollback

### 4. Hook Architecture
For EACH hook event, specify what fires and why:
- PreToolUse: security guard (bash allowlist) + tool logger + test file blocker
- PostToolUse: audit logger + timing tracker
- SubagentStart: subagent lifecycle logger
- SubagentStop: subagent completion logger with cost
- Stop: session complete handler
- PreCompact: save critical context before compaction

### 5. Permission Architecture
- can_use_tool callback: bash allowlist with PermissionResultDeny(interrupt=False)
- permission_mode: acceptEdits (auto-approve file operations)
- disallowed_tools: NotebookEdit (not needed)
- How permissions propagate to subagents

### 6. Streaming Output Architecture
- include_partial_messages=True
- StreamEvent processing for real-time text display
- content_block_start/delta/stop for tool call tracking
- How to show subagent progress (parent_tool_use_id)
- Terminal UI: timestamps, indentation for subagents, color coding

### 7. File Structure
Propose the complete Python package structure with line count estimates.

### 8. Execution Flow
Step-by-step for both paths:
- Greenfield: CLI → options assembly → spec-builder phase → research → plan → implement → validate
- Existing: CLI → options assembly → onboard phase → research → plan → implement → validate

### 9. Configuration Architecture
- AutonomousCoderConfig dataclass
- Per-agent model selection
- MCP server registry
- Budget management (total + per-phase)

### 10. Session Management
- Session ID capture from SystemMessage
- Resume via --resume flag
- File checkpointing for rollback
- Findings persistence (.autonomous-coder/findings/)

---

## 5 ARCHITECTURAL CRITIQUES

After producing the architecture document, produce 5 INDEPENDENT critiques, each from a different perspective:

### Critique 1: Security Reviewer
- Are there any security holes in the permission architecture?
- Can subagents bypass the bash allowlist?
- Are MCP server credentials properly scoped?
- Can the agent escape the project directory?

### Critique 2: Production Operations
- What happens when the agent runs for 30+ minutes?
- How does context compaction affect phase continuity?
- What's the failure recovery story?
- How does cost tracking work across resumed sessions?

### Critique 3: Developer Experience
- Is the CLI intuitive?
- Is the streaming output useful or overwhelming?
- How does error reporting work?
- Can a developer understand what went wrong from the output alone?

### Critique 4: Architecture Purist
- Are there unnecessary abstractions?
- Does the code follow KISS/YAGNI?
- Could any agents be consolidated?
- Is the hook architecture over-engineered?

### Critique 5: Competitive Analysis
- How does this compare to Cursor, Windsurf, Aider, OpenHands?
- What capabilities are unique?
- What's missing that competitors have?
- What's the moat?

Each critique must include:
- 3-5 specific concerns
- Severity rating (critical / warning / info)
- Concrete recommendation for each concern

---

## EXECUTION INSTRUCTIONS

1. Read ALL sources listed in the research phase
2. Produce the architecture document (write to architecture file)
3. Produce the 5 critiques (write to critiques file)
4. Produce SUMMARY.md with executive overview
