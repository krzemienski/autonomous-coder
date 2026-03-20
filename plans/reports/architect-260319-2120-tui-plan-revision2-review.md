# Architect Review: TUI Plan Revision 2

**Date**: 2026-03-19
**Reviewer**: Architect (RALPLAN consensus loop, iteration 2)
**Plan**: `/Users/nick/Desktop/autonomous-coder/plans/260319-1940-tui-agent-orchestrator/plan.md`
**Prior review**: Critic REJECT (iteration 1) — 4 critical, 4 major findings

---

## Overall Assessment

The revision is a dramatic improvement over iteration 1. The Planner has addressed all four critical findings from the Critic's REJECT: `ClaudeAgentOptions` is replaced with the correct `ClaudeCodeOptions`, all 11 phantom fields are removed with explicit "does NOT exist" annotations (lines 96-106), hook signatures are corrected, and the security architecture correctly distinguishes `can_use_tool` (enforcement) from `hooks` (observability). The four major findings are also resolved: package naming confusion is cleared up, `EventBus` is replaced by Textual's native `Message` subclasses, inter-phase data handoff is specified via `PhaseContext`/`PhaseResult` dataclasses, and parallel code agents are deferred to v2. The plan now reads as an implementable architecture document built on verified SDK facts.

That said, several secondary SDK accuracy issues remain, and the plan's greatest risk is no longer API fabrication but rather **under-specification of failure modes and recovery** in a system where multiple sequential `query()` calls depend on each other's output. The architecture is sound in the happy path; the unhappy path needs more rigor.

---

## Steelman Antithesis

**The strongest argument against this approach**: This plan adds significant complexity (SQLite persistence, Textual TUI, agent factory, phase pipeline, custom widgets) to a system that currently works as a simple sequential script. The existing `agent.py` (594 lines) accomplishes the same four-phase workflow with straightforward `async for` loops and `print()` statements. The proposed architecture introduces at minimum 15 new files, a reactive UI framework, a database layer, and an orchestration abstraction -- all for a tool used by a single developer on their local machine.

The counter-argument is: "We need real-time visibility into agent execution, cost tracking, and session persistence." But these can be achieved incrementally. A `rich.live` dashboard (no Textual) over the existing `agent.py` provides streaming output. A simple `total_cost += msg.total_cost_usd` accumulator (which the plan itself shows is trivial) provides cost tracking. A JSON file (which already exists as `progress.json`) provides session persistence.

The risk is classic second-system effect: the plan reimagines the entire system when the stated goals (visibility, cost tracking, persistence) could be achieved by augmenting the existing 594-line orchestrator with 200-300 lines of additions. The full TUI rewrite is the right long-term direction, but the plan does not justify why the incremental approach was rejected. This omission weakens the RALPLAN-DR decision record.

---

## Tradeoff Tensions

### 1. Monolithic Textual App vs. Layered CLI Enhancement

| Dimension | Full TUI Rewrite (Chosen) | Incremental CLI Enhancement |
|-----------|---------------------------|----------------------------|
| Time to first value | 4-5 phases of development | Days (add `rich.live` to existing `agent.py`) |
| Visibility | Excellent (multi-pane, tabs, reactive) | Good (streaming panels, cost counter) |
| Complexity | High (15+ new files, Textual CSS, widget tree) | Low (modify existing files) |
| Testability | Hard (Textual's `pilot` API, async workers) | Easy (same `async for` loops) |
| Maintainability | Better long-term (separation of concerns) | Worse long-term (monolith growth) |
| Risk of stall | High (TUI framework learning curve, integration bugs) | Low (familiar patterns) |

Reasonable architects would genuinely disagree here. The plan chooses maximum ambition but does not acknowledge the incremental alternative as a valid first step.

### 2. Sequential-Then-Parallel vs. Sequential-Only

The plan correctly defers parallel code agents to v2, but the `PhaseRunner` protocol and orchestrator are designed with sequential execution assumptions baked in (`for phase_runner in self.phase_runners`). When v2 arrives, the orchestrator will need significant restructuring to support fan-out/fan-in within a phase. A `PhaseRunner` that returns `list[PhaseResult]` (one per parallel agent) would be more forward-compatible, but adds complexity now. This is a genuine tension with no obviously correct answer.

---

## SDK Accuracy Audit

### Verified Correct (plan matches SDK reality)

| Claim | Verified Against |
|-------|-----------------|
| Class name `ClaudeCodeOptions` | `from claude_code_sdk import ClaudeCodeOptions` -- OK |
| `model`, `system_prompt`, `append_system_prompt`, `cwd` | `inspect.signature(ClaudeCodeOptions)` -- all exist |
| `allowed_tools`, `disallowed_tools` | Exist as `list[str]` with factory defaults |
| `can_use_tool` callback signature `(str, dict, ToolPermissionContext) -> Allow\|Deny` | Matches SDK type annotation exactly |
| `permission_mode` literals `"default"\|"acceptEdits"\|"plan"\|"bypassPermissions"` | Matches `Literal` type |
| `continue_conversation`, `resume`, `max_turns` | All exist with correct types |
| `include_partial_messages` | Exists as `bool`, default `False` |
| `hooks` dict with `PreToolUse`/`PostToolUse` keys | Matches SDK `Literal` union (also valid: `UserPromptSubmit`, `Stop`, `SubagentStop`, `PreCompact`) |
| `HookMatcher(matcher=..., hooks=[...])` | Matches signature: `matcher: str\|None`, `hooks: list[Callable]` |
| `PermissionResultAllow(behavior="allow", ...)` | Correct -- `updated_input` and `updated_permissions` are optional |
| `PermissionResultDeny(behavior="deny", message=..., interrupt=...)` | Correct fields and types |
| `ResultMessage.total_cost_usd` (float\|None) | Verified, plus `duration_ms`, `num_turns`, `session_id`, `is_error`, `result` |
| Phantom fields list (lines 96-106) | All correctly identified as nonexistent |
| `No MCPServerConfig` -- must use typed configs | `MCPServerConfig` is not importable; `McpStdioServerConfig` exists |
| `No StreamEvent` as public type | Confirmed: `from claude_code_sdk import StreamEvent` fails |
| Budget tracking is manual (no `max_budget_usd`) | Correct; plan's manual accumulation pattern is the right approach |

### Issues Found

**Issue 1: `mcp_servers` type mismatch (MEDIUM severity)**

The plan (line 68, 677-681) passes `mcp_servers` as a **list** of dicts:
```python
mcp_servers=[self.BASE_MCP[k] for k in config["mcp"]],
```

The actual SDK type is a **dict keyed by server name**, not a list:
```python
mcp_servers: dict[str, McpStdioServerConfig | McpSSEServerConfig | McpHttpServerConfig | McpSdkServerConfig] | str | Path
```

The `AgentFactory.BASE_MCP` (line 676) is correctly structured as a dict with named keys, but `create_options()` converts it to a list via list comprehension. The correct pattern:
```python
mcp_servers={k: self.BASE_MCP[k] for k in config["mcp"]}  # dict, not list
```

Additionally, the values should be typed `McpStdioServerConfig` instances (with `type="stdio"` field), not raw dicts. The SDK may or may not accept raw dicts at runtime (depends on whether it does structural typing), but the plan's code samples are inconsistent with the declared type. The existing `client.py:93-116` has the same issue (passes raw dicts), so this is a pre-existing problem the plan inherits.

**Issue 2: `settings` type is `str | None`, not `dict` (LOW severity)**

The plan's comment (line 86) says `# settings={"key": "val"}` suggesting it's a dict. The actual type is `str | None`. This is only in a comment for an unused field, so impact is minimal, but it perpetuates the kind of inaccuracy the Critic flagged.

**Issue 3: Hook return type semantics (LOW severity)**

The plan shows hooks returning `{}` (empty dict) to mean "allow" (lines 837, 848). This is technically valid because `HookJSONOutput` is a `TypedDict` with all optional keys (`__required_keys__` is `frozenset()`). An empty dict is a valid `HookJSONOutput` that means "no blocking decision." However, this is not documented in the plan -- an executor might wonder whether `{}` or `None` or some other sentinel is the correct "allow" return value. The plan should add a one-line comment: `# Empty dict = no blocking decision (all HookJSONOutput keys are optional)`.

**Issue 4: `HookContext` is sparse (INFORMATIONAL)**

The plan references `HookContext` in hook signatures (line 829) but never uses it. `HookContext` has only one field: `signal: Any | None`. The plan correctly ignores it, but should note that `HookContext` provides an abort signal for cooperative cancellation, which could be useful for the "pause/cancel agent" TUI feature (Phase 5).

**Issue 5: Missing `duration_api_ms` from ResultMessage (INFORMATIONAL)**

The plan's message type documentation (line 115) lists `ResultMessage: session_id, total_cost_usd, duration_ms, num_turns, usage, is_error, result` but omits `duration_api_ms` which exists on the actual type. Not a bug, but incomplete documentation.

---

## Principle Violation Check

### Plan's Own Stated Principles (Section 10, lines 996-1000)

1. **"SDK fidelity: Every code sample uses ONLY verified ClaudeCodeOptions fields"** -- MOSTLY MET. The `mcp_servers` list-vs-dict type mismatch (Issue 1 above) violates this principle. All other field usage is correct.

2. **"Separation of concerns: can_use_tool for security, hooks for observability"** -- FULLY MET. The plan is clear and consistent on this throughout. Section 5.2 (lines 772-858) is the strongest section of the document.

3. **"Sequential-first: v1 uses sequential phase execution"** -- FULLY MET. The orchestrator `start()` method (line 399-426) is a clean sequential loop with PhaseContext chaining.

4. **"Manual over phantom: Budget tracking, structured output, model fallback handled in application code"** -- FULLY MET. The manual budget pattern (lines 121-132) and Pydantic validation fallback (lines 449-457) are well-specified.

5. **"Composable phases: PhaseRunner protocol allows adding/reordering"** -- PARTIALLY MET. The `PhaseRunner` protocol (line 342-344) is clean, but the orchestrator hardcodes phase ordering via `self.phase_runners: list[PhaseRunner]` with sequential iteration. Reordering requires changing the list order, which is composable. Adding a new phase is straightforward. However, conditional phase execution (skip explore if task is trivial) is not supported without modifying the orchestrator.

### YAGNI / KISS / DRY Check

- **YAGNI concern**: The full `widgets/` directory (6 custom widgets) may be premature for Phase 1. The plan says widgets start "with mock data" -- consider whether a single `RichLog` widget per agent is sufficient for Phase 1, with custom widgets added when real data flows arrive.
- **DRY concern**: The `AgentFactory.ROLE_CONFIG` dict (lines 683-719) duplicates some configuration that could be derived (e.g., MCP server assignment per role is a policy that could be centralized).
- **KISS satisfied**: The PhaseRunner protocol, Textual Message subclasses, and manual budget tracking are all appropriately simple.

---

## Specific Recommendations

1. **Fix `mcp_servers` to use dict, not list** (Priority: HIGH, Effort: trivial). Change `AgentFactory.create_options()` line 728 from list comprehension to dict comprehension. Also use typed `McpStdioServerConfig(type="stdio", command=..., args=..., env=...)` instead of raw dicts for type safety. Reference: SDK expects `dict[str, McpStdioServerConfig | ...]`.

2. **Add incremental alternative to RALPLAN-DR decision record** (Priority: MEDIUM, Effort: low). Acknowledge the `rich.live` + existing `agent.py` alternative as Option C. Explain why the full TUI rewrite was chosen over incremental enhancement. This strengthens the ADR and preempts "why not just add a progress bar?" questions.

3. **Specify Phase 1 widget scope more tightly** (Priority: MEDIUM, Effort: low). Phase 1 should deliver the app skeleton with `RichLog` panels and reactive state, not all 6 custom widgets. Custom widgets (`AgentTree`, `ProgressPanel`, `TaskDetail`, `CostDisplay`) should move to Phase 3 alongside CSS styling. This reduces Phase 1 scope and gets to "first working TUI" faster.

4. **Add error recovery specification for phase failures** (Priority: MEDIUM, Effort: medium). The orchestrator's `start()` method (line 413) breaks on phase failure. Specify: (a) should a failed Research phase skip to Explore with degraded context? (b) should a failed Explore phase retry with a different prompt? (c) what state is persisted on failure for resumption? The existing `agent.py` handles this (lines 118-119: "Research phase encountered issues, continuing anyway...") -- the new plan should match or improve this behavior.

5. **Document hook return value semantics** (Priority: LOW, Effort: trivial). Add a comment in the hook examples explaining that `{}` means "allow" because all `HookJSONOutput` keys are optional. Also note that `HookContext.signal` can be used for cooperative cancellation.

6. **Fix `settings` comment** (Priority: LOW, Effort: trivial). Line 86: change `# settings={"key": "val"}` to `# settings="path/to/settings.json"` to match the actual `str | None` type.

7. **Consider `HookContext.signal` for agent cancellation** (Priority: LOW, Effort: medium). The "pause/cancel agent" feature (Phase 5) could leverage `HookContext.signal` for cooperative cancellation rather than killing the worker externally. Worth noting in the risk analysis even if deferred.

---

## Synthesis

The plan's core architecture (sequential PhaseRunner pipeline, Textual Message-based event system, `can_use_tool` for security, manual budget tracking) is sound and correctly built on the actual SDK surface. To preserve these strengths while addressing weaknesses:

1. **Keep the PhaseRunner protocol and Textual Message architecture** -- these are well-designed and correctly decouple orchestration from presentation.

2. **Phase the TUI delivery more aggressively** -- Phase 1 should be a minimal Textual app with `RichLog` panels and `Header`/`Footer`, proving the SDK-to-TUI streaming pipeline works. Custom widgets arrive in Phase 3. This reduces risk of "big bang" integration failure.

3. **Add an Option C to the ADR** acknowledging the incremental `rich.live` approach. Even if rejected, documenting why the full rewrite is preferred strengthens the decision.

4. **Fix the `mcp_servers` type** from list to dict before implementation begins -- this is the only remaining SDK accuracy issue that would cause a runtime error.

5. **Carry forward the existing error recovery behavior** from `agent.py` (continue on research failure, abort on explore/plan failure) into the `AgentOrchestrator.start()` method explicitly.

---

## Verdict

**APPROVE with conditions**

The revision successfully addresses all critical and major findings from the Critic's iteration 1 REJECT. The SDK API surface is now accurately represented with one remaining type issue (`mcp_servers` list vs dict). The architecture is implementable, the security model is correctly layered, and the inter-phase data flow is well-specified.

**Conditions for unconditional approval** (should be addressed before implementation begins):

1. Fix `mcp_servers` from list to dict in `AgentFactory.create_options()` -- this would cause a runtime error as-is
2. Fix `settings` comment from dict to string type

**Recommended but not blocking**:

3. Add Option C (incremental enhancement) to the RALPLAN-DR decision record
4. Tighten Phase 1 widget scope to minimal viable TUI
5. Specify error recovery behavior for phase failures
6. Document hook return value semantics

The plan is ready for implementation once the two blocking conditions are resolved. These are trivial fixes (< 5 minutes of editing) and do not require architectural rethinking.

---

## References

- `/Users/nick/Desktop/autonomous-coder/plans/260319-1940-tui-agent-orchestrator/plan.md` — Full revised plan (1034 lines)
- `/Users/nick/Desktop/autonomous-coder/plans/reports/oh-my-claudecode:critic-260319-2047-tui-orchestrator-plan-review.md` — Critic's iteration 1 REJECT
- `/Users/nick/Desktop/autonomous-coder/client.py:131-137` — Existing SDK usage with raw dict `mcp_servers` (same type issue the plan inherits)
- `/Users/nick/Desktop/autonomous-coder/client.py:172-184` — Existing client-side security (bypassable ToolUseBlock filtering)
- `/Users/nick/Desktop/autonomous-coder/security.py:123-168` — `is_command_allowed()` function reused in plan's `can_use_tool` callback
- `/Users/nick/Desktop/autonomous-coder/security.py:201-244` — `get_security_permissions()` returns dict with `permissions` key that does NOT exist on `ClaudeCodeOptions` (pre-existing bug in current codebase)
- `/Users/nick/Desktop/autonomous-coder/agent.py:83-174` — Existing sequential four-phase orchestrator (the code being replaced)
- `/Users/nick/Desktop/autonomous-coder/agent.py:118-119` — Existing error recovery: research failure continues, explore/plan failure aborts
- SDK verification: `claude-code-sdk v0.0.25` installed at `/Users/nick/Library/Python/3.12/lib/python/site-packages`
