# SDK Migration Plan v2: autonomous-coder

**Date:** 2026-03-21
**Version:** 2 (revised per Architect + Critic feedback)
**Status:** APPROVED — Consensus reached (Planner → Architect → Critic, 2 iterations)
**Complexity:** MEDIUM (down from HIGH — scope reduced to refactoring, not rewrite)
**Scope:** Refactor pipeline internals using verified SDK primitives; preserve architecture

---

## Context

The autonomous-coder project runs a sequential Research -> Explore -> Plan -> Code pipeline via `orchestrator.py` using `query()` per phase with separate `ClaudeAgentOptions`. This architecture is **correct and battle-tested**: it provides deterministic phase ordering, typed contracts (`PhaseContext` -> `PhaseResult`), explicit error handling, pause/resume, and budget tracking.

### What v1 of this plan got wrong

The v1 plan proposed replacing the sequential `query()` loop with a single `query()` call + `AgentDefinition` subagents + `HookMatcher` hooks. The Architect and Critic identified three fatal problems:

1. **`AgentDefinition` does NOT support `mcp_servers`** — it only has 4 fields (`description`, `prompt`, `tools`, `model`). Per-role MCP assignment (serena for explore, firecrawl for research) is impossible via subagents. The v1 architecture was built on a falsified assumption.

2. **Single-query prompt-based orchestration trades determinism for hope** — the current `run_pipeline()` for-loop is a state machine with typed contracts, explicit error handling, and pause/resume. Replacing it with "tell Claude to use subagents in order" moves control flow into probabilistic prompt compliance.

3. **`can_use_tool` -> `HookMatcher` security switch is a downgrade** — `can_use_tool` returns `PermissionResultDeny(interrupt=False)` for graceful denial without killing the session. `HookMatcher` hooks cannot replicate this behavior.

### What v2 actually does

This plan keeps the sequential `query()` architecture (Option B) and focuses on three genuine wins that eliminate real code debt without introducing speculative risk:

1. **Extract `BasePhaseRunner`** — The 4 phase runners (`research.py`, `explorer.py`, `planner.py`, `coder.py`) share ~80% identical code (time tracking, try/except, `run_query()` delegation, `_run_direct()` fallback, `PhaseResult` construction). Extract this into a base class to reduce ~600 lines to ~200.

2. **Migrate security to `can_use_tool`** — The `security_callback` in `orchestrator.py` already uses `can_use_tool` correctly. But it's wired through `AgentFactory.create_options()` which conditionally attaches it. Simplify: always use `can_use_tool` on `ClaudeAgentOptions` directly, remove the factory indirection.

3. **Delete dead code** — V1 (`agent.py`, `client.py`, `progress.py`, `researcher.py`), unused `memory.py`, and the TUI can all go. These are unambiguously dead.

4. **Add `HookMatcher` for observability only** — Use SDK hooks for audit logging (tool calls, phase timing) as a *supplement* to the existing message dispatch, not a replacement.

5. **Add feature flag for future `AgentDefinition` adoption** — When the SDK adds `mcp_servers` to `AgentDefinition` (or we verify MCP inheritance), we can migrate incrementally.

---

## What We Preserve (unchanged)

- `orchestrator.py` — `AgentOrchestrator.run_pipeline()` sequential for-loop, `PhaseContext`/`PhaseResult` contracts, pause/resume/cancel
- `messages.py` — 9 Textual Message types (decouple from Textual base class)
- `cli_adapter.py` — `CliAdapter.post_message()` dispatch + printers
- `config.py` — `OrchestratorConfig`, `RoleConfig`, `MCP_SERVERS` registry
- `security.py` — `is_command_allowed()`, `ALLOWED_COMMANDS`, `DANGEROUS_PATTERNS`
- `prompts.py` — All template loading and prompt builders
- `__main__.py` — CLI/TUI entry point dispatch
- Pipeline flow: Research -> Explore -> Plan -> Code with dict-merge data passing

## What We Drop

- `agent.py` (590 lines) — V1 orchestrator, fully superseded by `orchestrator.py`
- `client.py` (~150 lines) — V1 `AutonomousCoderClient` wrapper
- `progress.py` (~120 lines) — V1 `ProgressTracker`
- `researcher.py` (~100 lines) — V1 `ResearchPhase`, duplicate of `agents/research.py`
- `memory.py` (~200 lines) — SQLite+FTS5 store never wired into pipeline
- `agent_instance.py` (93 lines) — Manual lifecycle tracking (replaced by `run_query()`)

## What We Transform

- `agents/research.py`, `explorer.py`, `planner.py`, `coder.py` — Extract shared logic into `BasePhaseRunner`, each becomes ~30-40 lines
- `agent_factory.py` — Simplify to a module-level function (no class needed)
- `orchestrator.py` — Remove `run_agent()` (unused), remove `AgentInstance` imports, add `HookMatcher` observability hooks
- `messages.py` — Decouple from `textual.message.Message` base class to plain dataclasses (optional, enables headless use without textual import)

---

## Guardrails

### Must Have
- `autonomous-coder --cli "task" --project path` works identically to today
- `--verbose` flag produces equivalent output (phase banners, tool calls, costs, summary)
- Security allowlist blocks the same commands via `can_use_tool` with `PermissionResultDeny(interrupt=False)`
- All 4 MCP servers remain available per role as configured in `RoleConfig.mcp_keys`
- Phase ordering is deterministic (Python for-loop, not prompt-based)
- Cost tracking via `ResultMessage.total_cost_usd` with per-phase granularity
- Budget enforcement (total + per-role caps)
- Typed phase contracts: `PhaseContext` -> `PhaseResult` with explicit error handling
- Pause/resume/cancel control interface

### Must NOT Have
- No single-query architecture (sequential `query()` per phase is correct)
- No `HookMatcher` for security decisions (keep `can_use_tool` for defense in depth)
- No removal of `messages.py` or `cli_adapter.py` (keep the observer pattern)
- No test files, mocks, or stubs
- No reliance on unverified SDK features (`AgentDefinition.mcp_servers` does not exist)

---

## Task Flow

```
Task 0: SDK Verification Spike (de-risk)
    |
    v
Task 1: Extract BasePhaseRunner (reduce boilerplate)
    |
    v
Task 2: Simplify security + factory (can_use_tool migration)
    |
    v
Task 3: Add HookMatcher observability (audit logging)
    |
    v
Task 4: Delete dead code + cleanup (V1, memory, agent_instance)
    |
    v
Task 5: Functional validation (end-to-end CLI test)
```

---

## Consensus Refinements (Iteration 2)

**From Architect v2 (APPROVE):**
1. `run_agent()` deletion is already explicit in Task 4 — confirmed safe, zero callers
2. YAGNI SubagentStart/Stop hooks — Task 3 scoped to PostToolUse only, do NOT define unused hook functions
3. `_run_direct()` fallback: evaluate during Task 1 — if no external callers, absorb into BasePhaseRunner or drop entirely

**From Critic v2 (APPROVE):**
1. `__init__.py` must be updated alongside Task 4 deletions — it imports from 5 of the 6 deleted modules and exports 17 legacy symbols in `__all__`
2. Feature flags (AC_SDK_HOOKS, AC_SDK_SUBAGENTS) should be implemented as runtime environment variables checked in `config.py`, not just documentation markers
3. Consider preserving `memory.py` as dormant (remove from `__init__.py` exports but keep file) if SQLite persistence is a planned future feature — decision deferred to implementation
4. Task 0 spike should specify concrete verification: write a minimal script exercising `can_use_tool` + `HookMatcher`, not just import checks

---

## Task 0: SDK Verification Spike

**Goal:** Confirm or deny three SDK behaviors before any code changes.

**Verification targets:**
1. Does `can_use_tool` work correctly when set directly on `ClaudeAgentOptions` (not via factory conditional)? Confirm `PermissionResultDeny(interrupt=False)` gracefully denies without killing the session.
2. Does `HookMatcher` with `tool_name="Bash"` fire on every Bash tool use? Confirm hook receives `tool_input` with `command` field.
3. Does `AgentDefinition` subagent inherit parent's `mcp_servers`? (Informational — determines future migration path, not blocking.)

**Method:** Write a minimal script (`spike.py`, not committed) that:
- Creates `ClaudeAgentOptions` with `can_use_tool=security_callback` and one MCP server
- Runs `query()` with a prompt that triggers Bash + a blocked command
- Attaches a `HookMatcher` PostToolUse hook and logs to stdout
- If subagent test: adds an `AgentDefinition` and checks if it can access parent MCP tools

**Acceptance criteria:**
- Written confirmation of each behavior with evidence (stdout logs or error messages)
- Feature flag recommendation documented: `USE_SDK_SUBAGENTS=False` with conditions for enabling
- Results captured in `plans/reports/sdk-spike-results.md`

**Time box:** 1 hour. If any verification is ambiguous, document as "unverified" and proceed conservatively.

---

## Task 1: Extract BasePhaseRunner

**Goal:** Reduce ~600 lines of duplicated phase runner code to ~200 lines via a base class.

### Current duplication pattern

All 4 phase runners (`research.py`, `explorer.py`, `planner.py`, `coder.py`) share this exact structure:

```python
class XPhaseRunner:
    def __init__(self, factory, orchestrator=None): ...   # identical
    async def run(self, context) -> PhaseResult:          # identical skeleton
        start_time = time.time()
        system_prompt = self._build_system_prompt(context)
        prompt = self._build_prompt(context)
        if self.orchestrator is not None:
            try:
                text, cost = await self.orchestrator.run_query(...)
                return PhaseResult(...)                   # identical
            except Exception as e:
                return PhaseResult(success=False, ...)     # identical
        return await self._run_direct(...)                 # identical
    async def _run_direct(self, ...): ...                  # identical (30 lines)
    def _build_system_prompt(self, context): ...           # UNIQUE per phase
    def _build_prompt(self, context): ...                  # UNIQUE per phase
```

### Target design

```python
# agents/base.py (~80 lines)
class BasePhaseRunner:
    """Base class for sequential phase runners.

    Subclasses override only:
    - role: str (the config role key)
    - output_key: str (key in PhaseResult.output_data)
    - _build_system_prompt(context) -> str
    - _build_prompt(context) -> str
    """
    role: str
    output_key: str

    def __init__(self, factory, orchestrator=None): ...
    async def run(self, context) -> PhaseResult: ...       # shared skeleton
    async def _run_direct(self, ...): ...                   # shared fallback

# agents/research.py (~30 lines)
class ResearchPhaseRunner(BasePhaseRunner):
    role = "research"
    output_key = "research_output"
    def _build_system_prompt(self, context): ...
    def _build_prompt(self, context): ...

# agents/explorer.py (~30 lines) — same pattern
# agents/planner.py (~30 lines) — same pattern
# agents/coder.py (~50 lines) — slightly different: has coding + review sub-passes
```

`CoderPhaseRunner` is special — it runs a coding pass followed by a review pass. It overrides `run()` entirely but reuses `_run_query_with_lifecycle()` from the base class for each sub-pass.

### Acceptance criteria
- `BasePhaseRunner` in `agents/base.py` with shared `run()`, `_run_direct()`, `_run_query()`
- Each concrete runner is <50 lines, overriding only `role`, `output_key`, `_build_system_prompt()`, `_build_prompt()`
- `CoderPhaseRunner` overrides `run()` for two-pass coding+review
- `PhaseContext` and `PhaseResult` remain unchanged in `orchestrator.py`
- `__main__.py` still constructs runners the same way
- All existing behavior preserved (same prompts, same MCP servers per role, same budget tracking)

---

## Task 2: Simplify Security + Factory

**Goal:** Clean up the `AgentFactory` indirection and make `can_use_tool` usage more direct.

### Current state
- `security_callback` is defined in `orchestrator.py` as a module-level async function
- `AgentFactory.create_options()` conditionally attaches it: `use_security = security_callback if "Bash" in role_config.tools else None`
- The factory is a class with one real method (`create_options()`) and one trivial method (`get_budget_limit()`)

### Target
- Move `security_callback` to `security.py` where it logically belongs (next to `is_command_allowed`)
- Replace `AgentFactory` class with a module-level function `create_agent_options(role, config, system_prompt)` in `agent_factory.py`
- Keep the conditional `can_use_tool` attachment (it's correct — only Bash-using roles need streaming mode)
- Remove `get_budget_limit()` — callers can access `config.roles[role].budget_limit` directly

### Acceptance criteria
- `security_callback` lives in `security.py`, imports `PermissionResultAllow`/`PermissionResultDeny` from SDK
- `agent_factory.py` exports `create_agent_options()` function (not a class)
- `orchestrator.py` imports `security_callback` from `security` (not defined locally)
- `BasePhaseRunner` uses `create_agent_options()` function
- `can_use_tool` still returns `PermissionResultDeny(interrupt=False)` for blocked commands
- No behavioral changes — same commands blocked, same MCP servers attached

---

## Task 3: Add HookMatcher Observability

**Goal:** Add SDK-native audit logging via `HookMatcher` hooks, supplementing (not replacing) the existing message dispatch.

### Design

SDK hooks fire independently of the Python message dispatch system. We add hooks for:

1. **PostToolUse** — Log every tool call with name, duration, and (for Bash) the command
2. **SubagentStart/SubagentStop** — Log agent lifecycle events (currently these don't fire because we don't use SDK subagents, but the hooks are ready for future migration)

Hooks are attached via `ClaudeAgentOptions.hooks` dict, which `AgentFactory.create_options()` already accepts.

### Implementation

```python
# hooks.py (~60 lines, new file)
from claude_agent_sdk import HookMatcher

def build_observability_hooks(*, verbose: bool = False) -> dict:
    """Build SDK hook configuration for audit logging.

    These hooks log to stdout for CLI observability. They do NOT
    make security decisions — that remains in can_use_tool.
    """
    hooks = {}

    # Log all tool calls
    hooks["PostToolUse"] = [{
        "matcher": HookMatcher(),  # match all tools
        "callback": _log_tool_use,
    }]

    return hooks

async def _log_tool_use(tool_name, tool_input, tool_result, context):
    """Audit log: tool name + summary. Never blocks."""
    # Log format matches existing CliAdapter tool output
    ...
    return {}
```

### Integration point

`create_agent_options()` accepts an optional `hooks` parameter and merges observability hooks:

```python
def create_agent_options(role, config, system_prompt, *, hooks=None):
    obs_hooks = build_observability_hooks()
    merged = {**obs_hooks, **(hooks or {})}
    return ClaudeAgentOptions(..., hooks=merged)
```

### Feature flag

```python
# config.py
USE_SDK_HOOKS = os.environ.get("AC_SDK_HOOKS", "1") == "1"
USE_SDK_SUBAGENTS = os.environ.get("AC_SDK_SUBAGENTS", "0") == "1"  # future
```

When `AC_SDK_HOOKS=0`, skip attaching hooks. This allows disabling if hooks cause unexpected behavior.

### Acceptance criteria
- `hooks.py` exists with `build_observability_hooks()` returning SDK hook config
- Hooks fire on PostToolUse and log tool name + summary to stdout
- Hooks do NOT make security decisions (no deny/allow logic)
- `can_use_tool` remains the sole security gate
- Feature flag `AC_SDK_HOOKS` controls hook attachment (default: enabled)
- Feature flag `AC_SDK_SUBAGENTS` exists for future migration (default: disabled)
- Existing `CliAdapter` output is unchanged — hooks add supplementary logging only

---

## Task 4: Delete Dead Code + Cleanup

**Goal:** Remove all confirmed dead code and update package config.

### Files to delete

```
src/autonomous_coder/agent.py          # V1 orchestrator (590 lines)
src/autonomous_coder/client.py         # V1 client wrapper (~150 lines)
src/autonomous_coder/progress.py       # V1 progress tracker (~120 lines)
src/autonomous_coder/researcher.py     # V1 research phase, duplicate (~100 lines)
src/autonomous_coder/memory.py         # SQLite+FTS5, never wired (~200 lines)
src/autonomous_coder/agent_instance.py # Manual lifecycle, replaced by run_query (~93 lines)
```

**Total removed:** ~1,250 lines of dead code.

### Code to update

- `orchestrator.py` — Remove imports of `AgentInstance`, `AgentStatus`. Remove `run_agent()` method (only `run_query()` is used by phase runners). Remove `self.agents` dict tracking. Keep `run_pipeline()`, `run_query()`, `security_callback` (now imported from security.py).
- `__init__.py` — Remove exports of deleted modules
- `pyproject.toml` — No dependency changes needed (textual stays for TUI mode, which still works)

### What we keep (explicitly)
- TUI mode (`app.py`, `widgets/`) — it works, it's a differentiator, removing it is a separate decision
- `messages.py` — still used by both TUI and CliAdapter
- `cli_adapter.py` — still the headless output sink

### Acceptance criteria
- Zero imports from deleted files anywhere in the codebase
- `orchestrator.py` has no `AgentInstance` references
- `run_agent()` method removed (dead — all runners use `run_query()`)
- `autonomous-coder --cli "task" --project path` still works
- `autonomous-coder "task"` (TUI mode) still works
- `pip install -e .` succeeds

---

## Task 5: Functional Validation

**Goal:** Verify end-to-end CLI behavior is unchanged after all refactoring.

### Test scenarios

```bash
# 1. Basic CLI execution
cd /tmp && mkdir test-project && cd test-project && git init
autonomous-coder --cli "Create a Python hello world script" --project .

# 2. Verbose mode
autonomous-coder --cli -v "Add a greeting function that accepts a name" --project .

# 3. Security enforcement
# (Verify blocked commands produce graceful denial, not session crash)

# 4. Help output
autonomous-coder --help

# 5. TUI launch (verify no import errors)
autonomous-coder "test task"
# (Ctrl+C to exit — just verify it launches without import errors)
```

### Acceptance criteria
- Scenario 1: completes with exit code 0, produces phase banners and cost summary
- Scenario 2: verbose output includes timestamps and lifecycle detail
- Scenario 3: blocked command logged as `[BLOCKED]`, session continues
- Scenario 4: help text shows correct usage
- Scenario 5: TUI launches without import errors (visual verification)
- No regressions in phase ordering, budget tracking, or MCP server attachment

---

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| BasePhaseRunner extraction changes behavior | Low | Medium | Each runner's `_build_system_prompt()` and `_build_prompt()` are copy-pasted unchanged. Only the skeleton changes. |
| `security_callback` move breaks imports | Low | Low | Single rename. Grep for all import sites. |
| HookMatcher hooks interfere with can_use_tool | Low | Medium | Hooks are PostToolUse only (fire AFTER tool runs). Security is PreToolUse via can_use_tool. No overlap. |
| Deleting agent_instance.py breaks something | Low | Low | Only imported by orchestrator.py (in `run_agent()` which we also delete). Grep confirms. |
| SDK version bump breaks hooks | Low | Low | Pin `claude-agent-sdk>=0.1.49,<0.2.0`. Feature flag allows disabling hooks. |

---

## RALPLAN-DR Summary

### Principles
1. **Deterministic control flow over prompt-based orchestration** — Python for-loop with typed contracts is more reliable than instructing Claude to follow a phase order
2. **Preserve external interface** — CLI flags, output format, exit codes, TUI must not change
3. **Defense in depth** — `can_use_tool` with `PermissionResultDeny(interrupt=False)` is the security gate; hooks are observability only
4. **DRY within the architecture, not across architectures** — Extract shared patterns (BasePhaseRunner) but do not collapse the architecture itself
5. **Verified SDK surface only** — Every SDK feature used in this plan has been confirmed to exist in v0.1.49

### Decision Drivers
1. **Boilerplate reduction** — 4 phase runners share ~80% identical code; BasePhaseRunner extraction is the highest-value, lowest-risk change
2. **Dead code burden** — ~1,250 lines of V1/unused code that creates confusion and maintenance drag
3. **SDK alignment** — Use real SDK primitives (`can_use_tool`, `HookMatcher`, `ResultMessage`) where they add genuine value, not where they add risk

### Option A: Single-query + AgentDefinition (v1 plan) — INVALIDATED

**Why invalidated:**
- `AgentDefinition` does not support `mcp_servers` — per-role MCP assignment is impossible
- Phase ordering depends on prompt compliance, not deterministic code
- `can_use_tool` -> `HookMatcher` for security is a defense-in-depth downgrade
- Cross-phase data flow (`save_findings`/`get_findings`) depends on MCP inheritance that is unverified
- Collapses typed contracts (`PhaseContext` -> `PhaseResult`) into unstructured prompt responses

### Option B: Sequential query() with BasePhaseRunner extraction — SELECTED

**Pros:**
- Deterministic phase ordering via Python for-loop (proven working)
- Typed contracts preserved (`PhaseContext` -> `PhaseResult`)
- `can_use_tool` security preserved with graceful denial
- ~600 -> ~200 lines via BasePhaseRunner (3x reduction in runner code)
- ~1,250 lines of dead code deleted
- HookMatcher adds SDK-native observability without risk
- Feature flags enable future AgentDefinition migration when SDK supports it
- Messages.py + CliAdapter pattern preserved (enables both TUI and headless modes)

**Cons:**
- Does not demonstrate single-query subagent orchestration (future work)
- Still requires manual `query()` per phase (but this is explicit and debuggable)
- Phase runners remain as separate files (but each is now ~30-50 lines)

### ADR

**Decision:** Option B — Sequential `query()` per phase with `BasePhaseRunner` extraction, `can_use_tool` security, and `HookMatcher` observability.

**Drivers:** Boilerplate reduction (3x in runners), dead code elimination (1,250 lines), SDK alignment with verified primitives only.

**Alternatives considered:** Option A (single-query + AgentDefinition) — invalidated because `AgentDefinition` lacks `mcp_servers` field, phase ordering becomes prompt-dependent, and security mechanism is downgraded.

**Why chosen:** Maximizes code quality improvement (BasePhaseRunner, dead code removal) while preserving operational reliability (deterministic control flow, typed contracts, graceful security denial). Uses only SDK features confirmed to exist.

**Consequences:**
- Phase orchestration remains in Python (not SDK-driven) — this is intentional
- Future `AgentDefinition` migration requires SDK to add `mcp_servers` support
- HookMatcher observability is additive; existing message dispatch unchanged

**Follow-ups:**
- Re-evaluate `AgentDefinition` when SDK adds `mcp_servers` field (tracked via `AC_SDK_SUBAGENTS` flag)
- Consider decoupling `messages.py` from `textual.message.Message` to plain dataclasses (reduces textual dependency for headless-only installs)
- Document the BasePhaseRunner extension pattern for adding new phases

---

## Success Criteria

1. `autonomous-coder --cli "task" --project path` produces working code changes (same as today)
2. `--verbose` output matches current format (phase banners, tool calls, costs, summary)
3. Zero imports from deleted modules (`agent.py`, `client.py`, `progress.py`, `researcher.py`, `memory.py`, `agent_instance.py`)
4. Each phase runner is <50 lines (down from ~140 each)
5. `BasePhaseRunner` consolidates shared run/direct/lifecycle logic
6. `security_callback` lives in `security.py` with `can_use_tool` semantics
7. `HookMatcher` PostToolUse hook fires and logs tool calls
8. Feature flags `AC_SDK_HOOKS` and `AC_SDK_SUBAGENTS` exist with safe defaults
9. TUI mode still launches without import errors
10. `pip install -e .` succeeds

---

## File Inventory: Preserve / Transform / Drop (v2)

| File | Lines | Decision | Rationale |
|------|-------|----------|-----------|
| `__main__.py` | 101 | **KEEP** | Entry point unchanged |
| `orchestrator.py` | 543 | **MODIFY** | Remove `run_agent()`, `AgentInstance` refs; import security from `security.py` |
| `config.py` | 93 | **MODIFY** | Add feature flags (`AC_SDK_HOOKS`, `AC_SDK_SUBAGENTS`) |
| `security.py` | 268 | **MODIFY** | Add `security_callback` (moved from orchestrator.py) |
| `prompts.py` | 524 | **KEEP** | Unchanged |
| `cli_adapter.py` | 168 | **KEEP** | Unchanged |
| `messages.py` | 188 | **KEEP** | Unchanged (decouple from textual is a follow-up) |
| `agent_factory.py` | 87 | **MODIFY** | Class -> function, accept hooks param |
| `agents/base.py` | ~80 | **NEW** | BasePhaseRunner with shared run/direct logic |
| `agents/research.py` | 142->~30 | **MODIFY** | Extend BasePhaseRunner |
| `agents/explorer.py` | ~140->~30 | **MODIFY** | Extend BasePhaseRunner |
| `agents/planner.py` | ~140->~30 | **MODIFY** | Extend BasePhaseRunner |
| `agents/coder.py` | 193->~50 | **MODIFY** | Extend BasePhaseRunner (custom two-pass run) |
| `hooks.py` | ~60 | **NEW** | HookMatcher observability hooks |
| `app.py` | ~300 | **KEEP** | TUI still works |
| `widgets/` | ~600 | **KEEP** | TUI widgets |
| `agent.py` | 590 | **DROP** | V1 orchestrator |
| `client.py` | ~150 | **DROP** | V1 wrapper |
| `progress.py` | ~120 | **DROP** | V1 tracker |
| `researcher.py` | ~100 | **DROP** | V1 duplicate |
| `memory.py` | ~200 | **DROP** | Never used |
| `agent_instance.py` | 93 | **DROP** | Replaced by run_query |

**Net result:** ~4,200 lines -> ~2,800 lines. 26 files -> 20 files. Runner code: ~600 lines -> ~220 lines.
