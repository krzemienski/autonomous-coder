# Critic Review: TUI Agent Orchestration System Plan

**Date**: 2026-03-19
**Plan**: `/Users/nick/Desktop/autonomous-coder/plans/260319-1940-tui-agent-orchestrator/plan.md`
**Mode**: RALPLAN Deliberate (consensus planning)
**Review Mode**: Started THOROUGH, **escalated to ADVERSARIAL** (see justification)

---

## VERDICT: REJECT

**Overall Assessment**: The plan is built on a foundation of fabricated SDK API references. Eleven out of eleven "key" `ClaudeAgentOptions` fields that the plan claims exist (`fallback_model`, `max_budget_usd`, `max_thinking_tokens`, `agents`, `fork_session`, `enable_file_checkpointing`, `output_format`, `betas`, `sandbox`, `setting_sources`, `permissions`) **do not exist** in the installed `claude-code-sdk v0.0.25`. The class is actually called `ClaudeCodeOptions`, not `ClaudeAgentOptions`. The entire agent factory, budget management, subagent definitions, structured output, and security hook integration patterns are based on an API that does not exist. This is not a matter of tweaking details — the core SDK integration layer, which constitutes approximately 60% of the plan's substance, must be redesigned from scratch.

**Pre-commitment Predictions**:
1. *SDK API accuracy* — Predicted likely issues with claimed SDK fields. **Confirmed: catastrophic.** 11/11 claimed fields are fabricated.
2. *Security hook migration path* — Predicted the plan would under-specify migration from existing broken pattern. **Confirmed: the proposed hook signature is wrong.**
3. *Inter-phase data flow* — Predicted vagueness in how phase outputs feed into next phase. **Confirmed: unspecified.**
4. *EventBus interface* — Predicted missing formal definition. **Confirmed.**
5. *Failure mode coverage* — Predicted incomplete. **Confirmed: multiple critical scenarios missing.**

---

## Critical Findings (blocks execution)

### 1. FABRICATED SDK API — `ClaudeAgentOptions` does not exist
- **Confidence**: HIGH
- **Evidence**: The SDK exports `ClaudeCodeOptions`, not `ClaudeAgentOptions`. Verified:
  ```
  python3 -c "from claude_code_sdk import ClaudeAgentOptions"
  → ImportError: cannot import name 'ClaudeAgentOptions'
  ```
  The plan references `ClaudeAgentOptions` throughout (lines 47-97, 343, 567-579) as the central configuration object. Every code sample in the plan uses this nonexistent class.
- **Why this matters**: Every component specification, the agent factory, and all code samples are unusable. An executor following this plan will immediately fail at the first import.
- **Fix**: Replace all references to `ClaudeAgentOptions` with `ClaudeCodeOptions`. Then audit every field usage against the actual signature (see finding #2).

### 2. ELEVEN fabricated SDK fields — the entire options schema is wrong
- **Confidence**: HIGH
- **Evidence**: Tested each field the plan claims (lines 50-96):
  | Plan Claims | Actually Exists? |
  |---|---|
  | `fallback_model` | NO |
  | `max_budget_usd` | NO |
  | `max_thinking_tokens` | NO |
  | `agents` (subagent defs) | NO |
  | `fork_session` | NO |
  | `enable_file_checkpointing` | NO |
  | `output_format` (json_schema) | NO |
  | `betas` (context window) | NO |
  | `sandbox` | NO |
  | `setting_sources` | NO |
  | `permissions` | NO |

  Actual `ClaudeCodeOptions` fields: `allowed_tools`, `system_prompt`, `append_system_prompt`, `mcp_servers`, `permission_mode`, `continue_conversation`, `resume`, `max_turns`, `disallowed_tools`, `model`, `permission_prompt_tool_name`, `cwd`, `settings`, `add_dirs`, `env`, `extra_args`, `debug_stderr`, `can_use_tool`, `hooks`, `user`, `include_partial_messages`.
- **Why this matters**: The agent factory (Section 5.1, lines 510-581) is entirely built on nonexistent fields. Budget management (`max_budget_usd`), subagent spawning (`agents`), structured output (`output_format`), session forking (`fork_session`), and sandbox config (`sandbox`) are all phantoms. These are not minor gaps — they are load-bearing design decisions.
- **Fix**: Redesign the entire agent factory around the actual `ClaudeCodeOptions` fields. Budget management must be implemented manually by tracking `ResultMessage.total_cost_usd`. Subagents must use separate `query()` calls or `ClaudeSDKClient` instances, not an `agents` parameter. Structured output must be enforced via prompt engineering, not a schema parameter. Security permissions must use `can_use_tool` callback, not a `permissions` dict.

### 3. Security hook signature is wrong
- **Confidence**: HIGH
- **Evidence**: Plan Section 5.2 (lines 588-606) proposes:
  ```python
  async def bash_security_hook(
      input_data: dict[str, Any],
      tool_use_id: str | None,
      context: HookContext,
  ) -> dict[str, Any]:
  ```
  Returning `{"hookSpecificOutput": {"permissionDecision": "deny", ...}}`.

  Actual `HookMatcher.hooks` signature requires:
  ```
  Callable[[dict[str, Any], str | None, HookContext], Awaitable[HookJSONOutput]]
  ```
  Where `HookJSONOutput` is a TypedDict with keys: `decision` (Literal['block']), `systemMessage`, `hookSpecificOutput`. The return format `{"permissionDecision": "deny"}` is fabricated — the actual way to block is `{"decision": "block"}`.

  Additionally, the SDK provides `can_use_tool` callback on `ClaudeCodeOptions` which takes `(tool_name: str, tool_input: dict, context: ToolPermissionContext) -> PermissionResultAllow | PermissionResultDeny`. This is the *correct* mechanism for tool-level permission control, and the plan never mentions it.
- **Why this matters**: The entire security layer — the plan's proposed improvement over the existing broken pattern — is itself broken. An executor implementing this will get runtime errors or silently fail to block dangerous commands.
- **Fix**: Use `can_use_tool` callback on `ClaudeCodeOptions` for tool-level permission decisions. Return `PermissionResultDeny(behavior="deny", message="...", interrupt=False)` to block. Use `hooks` with `HookJSONOutput(decision="block")` only if the hook-based approach is preferred, but with the correct return format.

### 4. Existing security is NOT checked "after execution" — the plan mischaracterizes the current code
- **Confidence**: HIGH
- **Evidence**: The Architect's summary says `client.py:173-184` checks commands "AFTER execution." Reading the actual code at `client.py:172-184`:
  ```python
  if isinstance(block, ToolUseBlock):
      if block.name == "Bash":
          validation = await bash_security_hook(block.input)
          if validation is not None:
              yield TextBlock(...)
              continue
      yield block
  ```
  This code runs inside `async for message in query(...)` — it processes messages as they stream from the SDK. The `ToolUseBlock` is received when the SDK *reports* the tool use, but the SDK has **already decided to execute** the tool by this point. The `continue` skips yielding the block to the caller but does NOT prevent execution. So the characterization is partially correct (it cannot prevent execution), but the plan's proposed fix via `hooks` also has the wrong signature (finding #3). The correct fix is `can_use_tool`, which is called BEFORE execution.
- **Why this matters**: Both the diagnosis and the proposed fix are partially wrong. The plan correctly identifies the problem but proposes a solution with incorrect API usage.
- **Fix**: Use `can_use_tool` callback, which is the SDK's designated pre-execution permission gate. Wire `is_command_allowed()` from `security.py` into this callback.

---

## Major Findings (causes significant rework)

### 5. Package name confusion — plan says `claude-code-sdk` was "renamed from `claude-agent-sdk`"
- **Confidence**: HIGH
- **Evidence**: Plan line 32 states: `**Package**: 'claude-code-sdk' (renamed from 'claude-agent-sdk')`. The Architect flagged the opposite direction (renamed TO `claude-agent-sdk`). Actual installed package: `claude-code-sdk v0.0.25`. The plan's confusion about naming direction, combined with the `ClaudeAgentOptions` class name (which looks like it belongs to a hypothetical `claude-agent-sdk`), suggests the plan may have hallucinated API details from a package that doesn't exist yet.
- **Why this matters**: If the plan was written assuming a future renamed API, every code sample is from a nonexistent SDK version. The executor needs to work with the *actually installed* SDK.
- **Fix**: Pin all references to `claude-code-sdk v0.0.25` and its actual API surface. Remove all references to renamed packages.

### 6. `EventBus` is referenced but never defined
- **Confidence**: HIGH
- **Evidence**: Plan line 301: `self.event_bus = EventBus()`, line 317: `self.event_bus.emit(AgentMessage(agent.name, message))`. `EventBus` appears in the file structure (line 619: `event_bus.py`) but has no interface specification — no events defined, no subscription mechanism, no payload types, no error handling semantics.
- **Why this matters**: The EventBus is the glue between the SDK layer and the TUI layer. Without a defined interface, two developers would implement it differently, and the orchestrator-to-widget data flow is unspecified.
- **Fix**: Define: (a) event types enum, (b) event payload dataclasses, (c) subscription/unsubscription API, (d) error propagation semantics, (e) thread-safety guarantees.

### 7. Inter-phase data handoff is unspecified
- **Confidence**: HIGH
- **Evidence**: Plan Section 4.2 (lines 469-501) shows the phase pipeline but never specifies how Research output becomes Explore input or how Explore output becomes Plan input. The existing code (`agent.py:122-123`) does `self.progress.progress["research"] = research_results` and later reads it back, using the `ProgressTracker`'s JSON dict as the handoff mechanism. The plan proposes replacing this with what? The `PhasePipeline` class is mentioned (line 300) but never specified. The pre-mortem Scenario 3 identifies JSON parsing fragility but the plan's mitigation references `output_format={"type": "json_schema", ...}` which **does not exist in the SDK** (finding #2).
- **Why this matters**: This is Decision Driver #3 in the RALPLAN-DR summary. It was explicitly identified as critical, yet the plan provides no concrete solution — only a mitigation that relies on a nonexistent SDK feature.
- **Fix**: Define a `PhaseContext` dataclass for each phase transition. Specify exactly what fields each phase produces and what the next phase consumes. Since `output_format` doesn't exist, enforce structured output via system prompt instructions with JSON schema examples, then validate with Pydantic or manual schema checking.

### 8. Plan proposes `@work(exclusive=True)` per phase but `exclusive=False` for Code — no conflict management
- **Confidence**: MEDIUM
- **Evidence**: Lines 481, 486, 491 show `exclusive=True` for Research/Explore/Plan workers, but line 500 shows `exclusive=False` for Code workers. The plan acknowledges parallel coding agents in Unresolved Question #1 (line 714) but provides no file-locking or conflict detection mechanism. If two code agents modify the same file, the last write wins silently.
- **Why this matters**: The plan lists parallel coding as a feature but provides no mechanism to prevent destructive file conflicts. This will cause silent data loss.
- **Fix**: Either (a) make Code phase sequential (simplest), (b) implement file-level locking, or (c) use git worktrees per agent and merge. The plan must choose one and specify it.

---

## Minor Findings (suboptimal but functional)

1. **SQLite WAL mode not configured**: The risk table (line 706) mentions "Use WAL mode, single writer thread with queue" but the `memory.py` schema (lines 378-415) never sets `PRAGMA journal_mode=WAL`. An executor might miss this.

2. **FTS5 trigger sync missing**: The `conversations_fts` virtual table (line 392) is created but there are no triggers to keep it in sync with the `conversations` table. Inserts to `conversations` won't appear in FTS5 searches.

3. **Model names may be outdated**: Plan uses `claude-sonnet-4-5` and `claude-opus-4-6` in agent factory configs (lines 522-537) but the existing codebase uses `claude-sonnet-4-20250514` (agent.py:51). These may or may not resolve to the same model depending on API aliasing.

4. **Textual CSS file referenced but not specified**: `styles.tcss` (line 262, 661) is listed as a deliverable but has no content specification. The TUI layout wireframe exists but the CSS rules to achieve it are unspecified.

5. **`__main__.py` entry point conflict**: The plan proposes `__main__.py` (line 646, 666) running `python -m autonomous_coder` but the existing `agent.py` already has a `main()` CLI entry point (line 517). The migration/deprecation path is unspecified.

---

## What's Missing

- **`can_use_tool` callback pattern**: The SDK's primary mechanism for pre-execution tool permission (`ClaudeCodeOptions.can_use_tool`) is never mentioned in the plan. This is the correct way to implement security hooks.
- **`ClaudeSDKClient` usage pattern**: The SDK provides a stateful `ClaudeSDKClient` with `connect()`, `query()`, `receive_messages()`, `interrupt()`, `disconnect()` methods. The plan mentions it in the comparison table (line 39-46) but all code samples use `query()` only. The Code phase (which the plan says needs stateful sessions) never shows `ClaudeSDKClient` usage.
- **Worker error handling**: The risk table says "Wrap all workers in try/except" but no code sample shows this pattern. The `@work` decorator's error handling semantics (does it propagate to the app? does it call `worker.cancelled`?) are unspecified.
- **Graceful degradation when MCP servers fail**: No specification for what happens when Serena, Firecrawl, or Context7 MCP servers fail to start or crash mid-session.
- **Session resumption mechanism**: The plan lists "Session resumption from SQLite" (line 694) as a Phase 5 deliverable but doesn't specify what state needs to be captured or how a mid-phase interruption is handled.
- **Cost tracking without `max_budget_usd`**: Since `max_budget_usd` doesn't exist in the SDK, the plan needs a manual cost tracking mechanism using `ResultMessage.total_cost_usd` with manual budget enforcement (abort after threshold). This entire subsystem is missing.
- **Architect's Phase Runner recommendation**: The Architect recommended decomposing the monolithic orchestrator into internal Phase Runners. The plan doesn't address whether this recommendation is accepted or rejected.

---

## Ambiguity Risks

- `"Refactor existing agent logic into role-specific modules"` (Phase 4, line 684) — Interpretation A: Move code from `agent.py` into `agents/research.py`, etc., making `agent.py` a thin wrapper. Interpretation B: Rewrite the agent logic using the new orchestrator patterns, abandoning the existing `AutonomousCoderAgent` class. Risk: Interpretation B is a much larger scope and could break the existing working system before the new one is ready.

- `"Event bus connecting SDK streams to widgets"` (Phase 2, line 672) — Interpretation A: Textual's built-in message system (`self.post_message()`). Interpretation B: A custom pub/sub EventBus class. These have very different implementation complexity and the plan references both patterns without choosing.

---

## Multi-Perspective Notes

- **Executor**: "I cannot implement Phase 2 (SDK Integration) because every code sample uses a class and fields that don't exist. I would need to reverse-engineer the correct API from the SDK source before writing a single line. The plan gives me zero usable code samples."

- **Stakeholder**: "The scope is appropriate and the TUI wireframe is well-thought-out. But I'm concerned that the research phase of *this plan* apparently didn't validate any of its SDK claims against the installed package. If the planning phase can't run `pip show` and `python -c 'import ...'`, how confident are we that the implementation phase will work?"

- **Skeptic**: "The strongest argument against this plan is that it appears to be hallucinated API documentation dressed up as architecture. Eleven phantom fields, a nonexistent class name, and wrong hook signatures suggest the SDK 'research' was fabricated rather than verified. The plan should have been written by someone who ran `python3 -c 'import claude_code_sdk; help(claude_code_sdk.ClaudeCodeOptions)'` first."

---

## RALPLAN Criteria Evaluation

### 1. Principle-Option Consistency: FAIL
- Principle 1 states "Every design decision must be validated against actual Claude Agent SDK capabilities; no speculative features." The plan violates this principle comprehensively — 11 speculative SDK fields, a nonexistent class name, and wrong hook signatures. The chosen option (Monolithic Orchestrator) is built entirely on speculative SDK features.

### 2. Fair Alternatives: PASS (borderline)
- Three options were genuinely explored with honest pros/cons. Option C (Event-Sourced Microkernel) was correctly eliminated as YAGNI. Option B (Phase Runners) received fair treatment and the Architect's synthesis recommendation to use it internally is reasonable. The alternatives analysis itself is solid — it's the implementation details of the chosen option that are fabricated.

### 3. Risk Mitigation Clarity: FAIL
- The risk table (Section 8) identifies real risks but mitigations reference nonexistent SDK features. "Use `max_budget_usd` per agent" — field doesn't exist. "Use `include_partial_messages=True`" — this one actually exists, but the other mitigations are hollow.

### 4. Testable Acceptance Criteria: PASS (weak)
- The expanded test plan includes concrete scenarios (stream a single agent, run full pipeline, cancel mid-stream, resume from SQLite). These are testable in principle, though several assume SDK features that don't exist.

### 5. Concrete Verification Steps: FAIL
- The verification step `python -m autonomous_coder` is concrete, but the integration checkpoints reference nonexistent SDK patterns. "SDK `query()` → Textual worker → RichLog widget" is verifiable. "PreToolUse hook → command validation → deny/allow" uses the wrong hook API and would fail verification.

### 6. Pre-Mortem Quality (Deliberate): PASS
- The three pre-mortem scenarios are realistic, specific, and actionable. Scenario 1 (SDK Streaming Blackout) correctly identifies a real risk. Scenario 2 (Resource Exhaustion) is practical. Scenario 3 (Data Corruption) identifies the fragile JSON parsing pattern from the existing code. However, Scenario 3's mitigation relies on `output_format` which doesn't exist.

### 7. Expanded Test Plan Quality (Deliberate): PASS (weak)
- Covers functional validation, integration checkpoints, E2E scenarios, and observability. The "no mocks, no test files" constraint is respected. However, several integration checkpoints can't be verified as written because they reference nonexistent SDK patterns.

---

## Verdict Justification

**REJECT**. The plan fails 4 of 7 RALPLAN criteria, including a catastrophic failure of Principle-Option Consistency (the first and most important principle is "SDK-First Architecture — no speculative features," yet the entire plan is built on speculative features).

Review **escalated to ADVERSARIAL mode** after discovering Critical Finding #2 (11 fabricated SDK fields). This constitutes a systemic issue, not isolated mistakes. Under adversarial scrutiny, the security hook pattern (Critical Finding #3) and inter-phase data handoff (Major Finding #7) were also found to rely on nonexistent API surface.

**Realist Check**: These findings are NOT theoretical. An executor sitting down to implement Phase 2 would get `ImportError` on the first line of code. There is no mitigating factor — no feature flag, no fallback, no "close enough" API that could be adapted. The class doesn't exist, the fields don't exist, and the hook return format is wrong. Every code sample in Sections 3.3, 5.1, and 5.2 is dead on arrival.

**What would need to change for ITERATE**:
1. Run the actual SDK introspection (`python3 -c "from claude_code_sdk import ClaudeCodeOptions; ..."`) and rebuild all code samples against the real API
2. Replace `ClaudeAgentOptions` with `ClaudeCodeOptions` everywhere
3. Design budget management, subagent spawning, and structured output around what the SDK *actually provides*
4. Use `can_use_tool` callback for security, not fabricated hook return formats
5. Define the EventBus interface
6. Specify inter-phase data flow concretely
7. Address the Architect's Phase Runner recommendation (accept or reject with rationale)

---

## Open Questions (unscored)

1. Is there a newer version of `claude-code-sdk` (or a `claude-agent-sdk` package) that has the claimed fields? The Architect mentioned a rename to `v0.1.49`. If so, the plan should specify the upgrade path and pin the required version. As of this review, only `claude-code-sdk v0.0.25` is installed.

2. Does `ClaudeSDKClient` support concurrent `query()` calls on different session IDs? The plan assumes yes for parallel Code phase agents, but this hasn't been tested.

3. Does `include_partial_messages=True` interact poorly with `max_turns`? If the SDK emits partial messages that count against the turn limit, agents might terminate prematurely.

---

*Ralplan summary row:*
- Principle/Option Consistency: **FAIL** — Plan violates its own Principle 1 ("no speculative features") with 11 fabricated SDK fields
- Alternatives Depth: **PASS** — Three options genuinely explored with honest trade-offs
- Risk/Verification Rigor: **FAIL** — Mitigations reference nonexistent SDK features; verification steps use wrong API
- Deliberate Additions: **PASS (weak)** — Pre-mortem scenarios are realistic; test plan covers categories but references phantom API
