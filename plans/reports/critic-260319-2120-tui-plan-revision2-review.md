# Critic Review: TUI Plan Revision 2

**Date**: 2026-03-19
**Reviewer**: Critic (RALPLAN consensus loop, DELIBERATE mode, iteration 2)
**Plan**: `/Users/nick/Desktop/autonomous-coder/plans/260319-1940-tui-agent-orchestrator/plan.md`
**Prior reviews**: Critic REJECT (iteration 1), Architect APPROVE with 2 conditions (iteration 2)
**Review Mode**: THOROUGH (no escalation to ADVERSARIAL warranted)

---

## Verdict: APPROVE

---

## Overall Assessment

The revision is a thorough and honest response to all 8 findings from my iteration 1 REJECT. The catastrophic SDK fabrication problem (11 phantom fields, wrong class name, wrong hook signatures) has been completely resolved. Every `ClaudeCodeOptions` field used in the plan is verified against the actual v0.0.25 SDK. The plan now explicitly lists which fields DO NOT exist (lines 96-106), designs manual workarounds for missing features (budget tracking, structured output), and correctly separates `can_use_tool` (security) from `hooks` (observability). The inter-phase data handoff is specified via `PhaseContext`/`PhaseResult` dataclasses, the EventBus is replaced with Textual's native Message system, and parallel code agents are cleanly deferred to v2.

Two issues remain: the `HookMatcher` import path is wrong (uses a private internal module that does not exist), and the Architect's two conditions (`mcp_servers` type, `settings` comment) are valid. These are all trivial fixes that do not affect the architecture. The plan is ready for implementation once these are corrected.

---

## Pre-commitment Predictions

Before detailed investigation, I predicted the following problem areas for a revision addressing 11 fabricated SDK fields:

1. **Incomplete phantom field removal** -- Predicted some phantom references might survive in prose or code comments. **Result: CLEAN.** Lines 96-106 explicitly enumerate all removed fields with strikethrough. No phantom fields appear in any code sample.

2. **`can_use_tool` callback accuracy** -- Predicted the corrected security callback might have wrong types or return values. **Result: CORRECT.** The `security_callback` signature (line 784-788) matches the verified SDK type exactly: `(str, dict, ToolPermissionContext) -> PermissionResultAllow | PermissionResultDeny`.

3. **Import path errors** -- Predicted that correcting class names might introduce wrong import paths. **Result: ONE FOUND.** Line 671 uses `from claude_code_sdk._internal.hooks import HookMatcher` which fails at import time. The correct path is `from claude_code_sdk import HookMatcher`.

4. **Residual `ClaudeAgentOptions` references** -- Predicted some might survive find-and-replace. **Result: CLEAN.** Searched the entire document; zero occurrences of `ClaudeAgentOptions`.

5. **Architect conditions unaddressed** -- Predicted the Architect's conditions might be missed since they came in parallel. **Result: CONFIRMED OUTSTANDING.** Both conditions (mcp_servers type, settings comment) remain unfixed in the plan text, which is expected since the Architect review and this Critic review are concurrent.

---

## Iteration 1 Finding Resolution

### Critical 1: `ClaudeAgentOptions` does not exist -- RESOLVED
The revised plan uses `ClaudeCodeOptions` consistently throughout all code samples (lines 49, 150, 477, 670, 725, 817). Zero occurrences of the old fabricated class name remain.

### Critical 2: Eleven fabricated SDK fields -- RESOLVED
Lines 96-106 explicitly list all 11 removed fields with strikethrough formatting and explanations of how each is handled in application code instead. The "IMPORTANT -- Fields that DO NOT exist" section is clear, prominent, and accurate. Every code sample in the plan uses only verified fields.

### Critical 3: Security hook signature wrong -- RESOLVED
The plan now correctly uses `can_use_tool` as the PRIMARY security mechanism (Section 5.2, lines 772-858). The callback signature (line 784-788) matches the SDK exactly. The distinction between `can_use_tool` (enforcement, blocks execution) and `hooks` (observability, logging only) is clearly articulated and consistently applied throughout the document. This section is now the strongest part of the plan.

### Critical 4: Existing security mischaracterized -- RESOLVED
Section 5.2 (line 772) correctly identifies that existing client-side validation "doesn't actually prevent execution" and that `can_use_tool` is the SDK's designated pre-execution gate. The migration path (line 860-861) correctly reuses `is_command_allowed()` from `security.py` inside the new callback. Verified: `security.py:123-168` contains the `is_command_allowed(command) -> tuple[bool, str]` function exactly as described.

### Major 5: Package name confusion -- RESOLVED
Line 34 now reads `**Package**: 'claude-code-sdk' (renamed from 'claude-agent-sdk')`. The naming direction is stated clearly, the class name matches the installed package, and there is no confusion between current and hypothetical future package names.

### Major 6: EventBus undefined -- RESOLVED
The EventBus has been completely replaced with Textual's native `Message` subclasses (Section 3.3B, lines 346-384). Six concrete message types are defined: `AgentStarted`, `AgentOutput`, `AgentCompleted`, `AgentError`, `CostUpdate`, `SecurityBlock`. Each has typed constructor parameters. The architecture diagram (line 198-199) labels this as "Event Bus (Textual Messages + Reactive Attributes)". This is a clean, idiomatic solution.

### Major 7: Inter-phase data handoff unspecified -- RESOLVED
`PhaseContext` and `PhaseResult` dataclasses (lines 327-340) define the handoff contract. The orchestrator's `start()` method (lines 399-426) chains output from each phase into the next phase's input via `context = PhaseContext(... input_data=result.output_data ...)`. The structured output enforcement section (lines 446-457) explains how JSON output is extracted and validated with Pydantic since `output_format` does not exist.

### Major 8: Parallel code agents with no conflict management -- RESOLVED
Line 657-658 explicitly states: "NOTE: Parallel code agents deferred to v2 (requires file-level locking and agent-to-file assignment to prevent conflicts)". The Code phase worker (line 655) uses `@work(exclusive=True)` for sequential execution. Unresolved Question #1 (line 979) is marked as RESOLVED with rationale.

---

## RALPLAN Criteria Evaluation

### 1. Principle-Option Consistency: PASS

The plan's 5 stated principles (Section 10, lines 996-1000) are now consistently upheld:

- Principle 1 ("SDK fidelity"): Every code sample uses only verified `ClaudeCodeOptions` fields. The phantom field list (lines 96-106) is an explicit guard against this. One minor violation: `HookMatcher` import path uses a private module (see Minor Findings), but the class itself and its usage are correct.
- Principle 2 ("Separation of concerns"): `can_use_tool` for security, `hooks` for observability -- consistently applied in every code sample.
- Principle 3 ("Sequential-first"): The orchestrator loop (line 407) is a straightforward `for phase_runner in self.phase_runners`. Parallel is explicitly deferred.
- Principle 4 ("Manual over phantom"): Budget tracking (lines 121-132), structured output (lines 446-457), and model selection (lines 683-719) are all handled in application code with no phantom SDK fields.
- Principle 5 ("Composable phases"): `PhaseRunner` protocol (lines 342-344) is clean and extensible.

### 2. Fair Alternatives: PASS

Two options are presented (lines 1009-1027):
- Option A (Monolithic Orchestrator): Chosen, with honest assessment of cons ("No parallel phases, single point of failure").
- Option B (Distributed Agent Mesh): Genuinely explored, then correctly invalidated as overkill for a local TUI with 4 sequential phases.

The Architect noted a missing Option C (incremental `rich.live` enhancement over existing `agent.py`). This is a valid observation but not a gating issue -- the plan's chosen approach is defensible, and the ADR (lines 1023-1029) documents the decision rationale. The Architect's recommendation to add Option C is good practice but does not indicate unfair alternative exploration.

### 3. Risk Mitigation Clarity: PASS

The risk table (Section 8, lines 964-974) identifies 8 concrete risks, each with a specific mitigation:
- Rate limits: Stagger with semaphore, sequential v1
- Worker crashes: try/except wrapping, AgentError messages
- SQLite concurrency: WAL mode
- Budget overrun: Manual tracking via `ResultMessage.total_cost_usd`
- Structured output: System prompt + Pydantic validation + fallback extraction
- Security callback errors: Fail-closed (deny on error)

Critically, NONE of these mitigations reference phantom SDK features. Every mitigation is implementable with the actual SDK + standard Python. This was the catastrophic failure in iteration 1, and it is fully resolved.

### 4. Testable Acceptance Criteria: PASS

Each phase has concrete deliverables:
- Phase 1: "Textual App skeleton with layout" + "Entry point: `python -m autonomous_coder`"
- Phase 2: "Agent factory creating `ClaudeCodeOptions` per role" + "`can_use_tool` callback as primary security mechanism"
- Phase 3: "SQLite schema with WAL mode and FTS5 + sync triggers"
- Phase 4: "Refactor existing agent logic into role-specific PhaseRunner implementations"
- Phase 5: "Session resumption from SQLite via `resume=session_id`"

These are verifiable by running the application and inspecting the outputs. The plan does not include mock/test-based criteria, consistent with the project's functional validation mandate.

### 5. Concrete Verification Steps: PASS

The streaming pattern (lines 148-165) shows a concrete, runnable code sample for SDK-to-TUI integration. The security callback (lines 784-814) is a complete, correct implementation. The manual budget tracking (lines 121-132) is directly executable. The SQLite schema (lines 516-569) includes CREATE TABLE statements, FTS5 virtual table, and sync triggers.

All verification steps now use real API patterns. The `query()` -> `AssistantMessage` -> `TextBlock`/`ToolUseBlock` -> `ResultMessage` message flow (lines 592-621) matches the actual SDK message types.

### 6. Pre-Mortem Quality (Deliberate): PASS

While the plan does not have an explicitly labeled "Pre-Mortem" section, the Risk Analysis (Section 8) covers the substantive pre-mortem territory with 8 failure scenarios. The Unresolved Questions (Section 9) add 3 more uncertainty areas. Together these cover:
- SDK streaming failures (partial message support)
- Rate limiting under concurrent queries
- Worker crash propagation
- SQLite write contention
- MCP server startup latency
- Budget overrun without SDK enforcement
- Structured output parsing failures
- Security callback crash leading to bypass

Each has a concrete mitigation. The coverage is adequate for deliberate mode.

### 7. Expanded Test Plan Quality (Deliberate): PASS (weak but acceptable)

The plan does not have a dedicated "Expanded Test Plan" section. However, the phased implementation plan (Section 7) implicitly defines a build-and-validate sequence: Phase 1 delivers a working TUI skeleton (functional validation: does the app launch?), Phase 2 integrates the SDK (functional validation: does a single agent stream output?), Phase 3 adds persistence (functional validation: does data survive app restart?), Phase 4 refactors agents (functional validation: does the full pipeline complete a task?), Phase 5 adds polish (functional validation: can a session be paused and resumed?).

This is consistent with the project's "no mocks, no test files" mandate. The plan does not reference phantom API in any verification context.

---

## Remaining Issues

These are not blocking but should be fixed before or during early implementation:

### 1. `HookMatcher` import path is wrong (MINOR -- would cause ImportError)

**Evidence**: Plan line 671:
```python
from claude_code_sdk._internal.hooks import HookMatcher
```
Verified: `from claude_code_sdk._internal.hooks import HookMatcher` raises `ModuleNotFoundError: No module named 'claude_code_sdk._internal.hooks'`. The correct import is `from claude_code_sdk import HookMatcher` (verified working).

This appears once in the plan (line 671, in AgentFactory). All other HookMatcher usages are inline within `ClaudeCodeOptions(hooks={...})` constructor calls and don't show the import statement. 

**Fix**: Change line 671 to `from claude_code_sdk import HookMatcher`.

### 2. `mcp_servers` passed as list, SDK expects dict (Architect Condition 1 -- MINOR)

**Evidence**: Plan line 728:
```python
mcp_servers=[self.BASE_MCP[k] for k in config["mcp"]],
```
Verified: `mcp_servers` type is `dict[str, McpStdioServerConfig | ...] | str | Path`. The plan's `BASE_MCP` (lines 676-681) is correctly structured as a dict with named keys, but `create_options()` converts it to a list via list comprehension.

**Fix**: Change to `mcp_servers={k: self.BASE_MCP[k] for k in config["mcp"]}`.

Note: The SDK does accept raw dicts at runtime (verified: constructing `ClaudeCodeOptions(mcp_servers={"test": {"command": "echo", "args": ["hi"]}})` succeeds). So the raw dict values in `BASE_MCP` are fine -- only the list-vs-dict container type needs fixing.

### 3. `settings` comment shows dict, actual type is `str | None` (Architect Condition 2 -- TRIVIAL)

**Evidence**: Plan line 86: `# settings={"key": "val"}`. Actual type: `str | None`.

**Fix**: Change to `# settings="path/to/settings"` or remove the comment.

### 4. `MCPServerConfig(...)` referenced in table but does not exist (TRIVIAL)

**Evidence**: Plan line 68 in the comparison table shows `mcp_servers=[MCPServerConfig(...)]`. There is no `MCPServerConfig` class in the SDK (verified: `ImportError`). The actual type is `McpStdioServerConfig` (importable from `claude_code_sdk.types`, not from public `claude_code_sdk`). However, all actual code samples in the plan use raw dicts for MCP configs, which works at runtime. This is only a table notation issue.

**Fix**: Change the table entry to `mcp_servers={"name": {...}}` to match actual usage.

---

## Architect Conditions Assessment

**Condition 1** (`mcp_servers` should be dict not list): **Valid and should be fixed.** This would cause a runtime type error or unexpected behavior. The fix is a one-character change (list comprehension `[` to dict comprehension `{`). Non-blocking for architectural approval.

**Condition 2** (`settings` comment shows dict but type is `str | None`): **Valid but trivial.** This is a comment for an unused field. Zero runtime impact. Non-blocking.

Neither condition should block approval. Both are fixable in under 1 minute during implementation kickoff.

---

## What's Missing (Gap Analysis)

1. **Error recovery on phase failure**: The orchestrator's `start()` method (line 413) breaks on phase failure. The existing `agent.py:118-119` continues past research failures ("continuing anyway..."). The plan should specify equivalent behavior. The Architect flagged this as recommendation #4. Not blocking, but the executor will need to make a judgment call without guidance.

2. **Worker error propagation semantics**: The risk table says "Wrap all workers in try/except, emit AgentError" but no code sample demonstrates this pattern with Textual's `@work` decorator. The executor will need to research Textual's worker error handling.

3. **MCP server failure graceful degradation**: No specification for what happens when Serena, Firecrawl, or Context7 fail to start. Should the agent proceed without MCP tools, or abort?

4. **Incremental alternative in ADR**: The Architect correctly notes that Option C (incremental `rich.live` over existing `agent.py`) is a valid alternative that should be documented in the ADR, even if rejected. This strengthens the decision record.

These are all reasonable gaps for a Phase A architecture document. None block implementation -- they represent decisions that can be made during Phase 2 (SDK Integration) when the real behavior is observable.

---

## Multi-Perspective Notes

**Executor**: "I can implement this plan. Every code sample uses real SDK classes and fields. The `AgentFactory`, `PhaseRunner`, and security callback are copy-pasteable starting points. I need to fix the `HookMatcher` import and `mcp_servers` type, but those are obvious and will show up as immediate import/type errors. The main area where I'll need to make judgment calls is error recovery -- the plan tells me what to build but not how to handle mid-phase failures."

**Stakeholder**: "The scope is ambitious (15+ new files, Textual TUI, SQLite persistence) for what is currently a working 594-line script. But the architecture is sound, the phasing is incremental, and the existing `agent.py` is preserved as a fallback until the TUI is stable (line 903). The risk is time-to-value, not technical correctness."

**Skeptic**: "The revision is dramatically better than iteration 1. My strongest remaining concern is that the plan's `PhaseRunner` protocol is designed for sequential execution only. When v2 parallel agents arrive, the orchestrator will need restructuring. But this is explicitly acknowledged (line 657-658, line 979) and is a reasonable v1-vs-v2 tradeoff."

---

## Verdict Justification

**APPROVE**. The revision resolves all 4 critical and all 4 major findings from iteration 1. The SDK API surface is now accurately represented -- every field, type, callback signature, and return type in the plan has been independently verified against the installed `claude-code-sdk v0.0.25`. The architecture is implementable, the security model is correctly layered, and the inter-phase data flow is well-specified.

The review operated in **THOROUGH mode** throughout. No escalation to ADVERSARIAL was warranted because:
- Zero critical findings discovered
- Only 1 minor finding that would cause a runtime error (HookMatcher import path)
- No pattern suggesting systemic issues -- the remaining issues are isolated, trivial, and easily caught during implementation

**Realist Check**: The 4 remaining issues (HookMatcher import, mcp_servers type, settings comment, MCPServerConfig table notation) would all manifest as immediate, obvious errors during implementation (ImportError, type mismatch). They have near-zero blast radius -- an executor would fix each one in under 30 seconds upon encountering it. No data loss, security, or architectural risk.

The Architect's 2 conditions are valid, non-blocking, and represent less than 1 minute of editing. All 4 remaining issues combined represent less than 5 minutes of fixes.

---

*Ralplan summary row:*
- Principle/Option Consistency: **PASS** -- Plan upholds all 5 stated principles; SDK fidelity verified against actual v0.0.25 API
- Alternatives Depth: **PASS** -- Two options genuinely explored; missing Option C noted but not gating
- Risk/Verification Rigor: **PASS** -- All 8 mitigations reference real SDK features and standard Python patterns; zero phantom API references
- Deliberate Additions: **PASS** -- Risk analysis covers 8 failure scenarios with concrete mitigations; phased implementation defines functional validation checkpoints
