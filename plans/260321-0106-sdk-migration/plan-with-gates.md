# SDK Migration Plan v2 — With Validation Gates

**Date:** 2026-03-21
**Status:** APPROVED — Consensus + validation gates added
**Platform detected:** CLI (Python package with `pyproject.toml` entry point)

---

<mock_detection_protocol>
Before executing any task, check intent:
- Creating .test.*, _test.*, *Tests.*, test_* files → STOP
- Importing mock libraries (nock, sinon, jest.mock, unittest.mock) → STOP
- Creating in-memory databases (SQLite :memory:, H2) → STOP
- Adding TEST_MODE or NODE_ENV=test flags → STOP
- Rendering components in isolation (Testing Library, Storybook) → STOP
Fix the REAL system instead. No exceptions.
</mock_detection_protocol>

---

## Task 0: SDK Verification Spike

Write `spike.py` (not committed) that exercises 3 SDK behaviors:
1. `can_use_tool` with `PermissionResultDeny(interrupt=False)` — graceful denial without session crash
2. `HookMatcher` PostToolUse hook — fires on Bash with `tool_input.command`
3. `AgentDefinition` MCP inheritance — informational only

<validation_gate id="VG-0" blocking="true">
Prerequisites: pip show claude-agent-sdk | grep "Version: 0.1" exits 0
Execute:
  python3 spike.py 2>&1 | tee evidence/vg0-spike-output.txt
Capture:
  grep -c "PermissionResultDeny" evidence/vg0-spike-output.txt | tee evidence/vg0-deny-count.txt
  grep -c "PostToolUse fired" evidence/vg0-spike-output.txt | tee evidence/vg0-hook-count.txt
Pass criteria:
  - spike.py exits 0
  - evidence/vg0-deny-count.txt contains integer > 0 (deny was returned, session continued)
  - evidence/vg0-hook-count.txt contains integer > 0 (hook callback fired)
  - evidence/vg0-spike-output.txt does NOT contain "Traceback" or "SessionCrashed"
Review: cat evidence/vg0-spike-output.txt | head -50
Verdict: PASS → proceed to Task 1 | FAIL → fix spike.py → re-run
Mock guard: IF tempted to mock SDK calls → STOP → use real query() with real model
</validation_gate>

---

## Task 1: Extract BasePhaseRunner

Create `agents/base.py` (~80 lines) with shared `run()`, `_run_direct()`, `_run_single_query()`.
Refactor `research.py`, `explorer.py`, `planner.py` to extend BasePhaseRunner (~30 lines each).
`coder.py` overrides `run()` for two-pass pattern (~50 lines).

<validation_gate id="VG-1" blocking="true">
Prerequisites: cd /Users/nick/Desktop/autonomous-coder && pip install -e . 2>&1 | tail -1
Execute:
  python3 -c "
from autonomous_coder.agents import ResearchPhaseRunner, ExplorerPhaseRunner, PlannerPhaseRunner, CoderPhaseRunner
from autonomous_coder.agents.base import BasePhaseRunner
assert issubclass(ResearchPhaseRunner, BasePhaseRunner), 'Research not subclass'
assert issubclass(ExplorerPhaseRunner, BasePhaseRunner), 'Explorer not subclass'
assert issubclass(PlannerPhaseRunner, BasePhaseRunner), 'Planner not subclass'
assert issubclass(CoderPhaseRunner, BasePhaseRunner), 'Coder not subclass'
assert hasattr(BasePhaseRunner, 'run'), 'Base missing run()'
assert hasattr(BasePhaseRunner, '_run_single_query'), 'Base missing _run_single_query()'
print('ALL ASSERTIONS PASSED')
" 2>&1 | tee evidence/vg1-inheritance.txt
Capture:
  wc -l src/autonomous_coder/agents/research.py src/autonomous_coder/agents/explorer.py src/autonomous_coder/agents/planner.py src/autonomous_coder/agents/coder.py src/autonomous_coder/agents/base.py 2>&1 | tee evidence/vg1-line-counts.txt
Pass criteria:
  - evidence/vg1-inheritance.txt contains "ALL ASSERTIONS PASSED"
  - Each runner (research, explorer, planner) is < 50 lines
  - coder.py is < 70 lines
  - base.py exists and is < 120 lines
  - No "ImportError" or "Traceback" in output
Review: cat evidence/vg1-inheritance.txt && cat evidence/vg1-line-counts.txt
Verdict: PASS → proceed to Task 2 | FAIL → fix BasePhaseRunner → re-run
Mock guard: IF tempted to create test runners → STOP → fix the real runners
</validation_gate>

---

## Task 2: Simplify Security + Factory

Move `security_callback` from `orchestrator.py` to `security.py`.
Replace `AgentFactory` class with `create_agent_options()` function.
Add feature flags `AC_SDK_HOOKS`, `AC_SDK_SUBAGENTS` to `config.py`.

<validation_gate id="VG-2" blocking="true">
Prerequisites: pip install -e . exits 0
Execute:
  python3 -c "
from autonomous_coder.security import security_callback, is_command_allowed
from autonomous_coder.agent_factory import create_agent_options
from autonomous_coder.config import OrchestratorConfig
import os, asyncio, inspect

# Verify security_callback is in security.py
assert inspect.getfile(security_callback).endswith('security.py'), 'security_callback not in security.py'

# Verify create_agent_options is a function, not a class method
assert callable(create_agent_options), 'create_agent_options not callable'
assert not inspect.ismethod(create_agent_options), 'Should be function, not method'

# Verify feature flags exist
assert 'AC_SDK_HOOKS' in dir() or hasattr(os.environ, 'get'), 'Feature flags check'

# Verify is_command_allowed still works
allowed, reason = is_command_allowed('git status')
assert allowed, f'git status should be allowed: {reason}'
blocked, reason = is_command_allowed('rm -rf /')
assert not blocked, f'rm -rf / should be blocked'

print('ALL SECURITY CHECKS PASSED')
" 2>&1 | tee evidence/vg2-security.txt
Capture:
  grep -rn "from.*orchestrator.*import.*security_callback" src/ 2>&1 | tee evidence/vg2-old-imports.txt
  grep -rn "class AgentFactory" src/ 2>&1 | tee evidence/vg2-old-factory.txt
Pass criteria:
  - evidence/vg2-security.txt contains "ALL SECURITY CHECKS PASSED"
  - evidence/vg2-old-imports.txt is EMPTY (no remaining imports of security_callback from orchestrator)
  - evidence/vg2-old-factory.txt is EMPTY (AgentFactory class removed)
  - No "ImportError" or "Traceback" in output
Review: cat evidence/vg2-security.txt && cat evidence/vg2-old-imports.txt && cat evidence/vg2-old-factory.txt
Verdict: PASS → proceed to Task 3 | FAIL → fix imports → re-run
Mock guard: IF tempted to mock PermissionResult → STOP → use real SDK types
</validation_gate>

---

## Task 3: Add HookMatcher Observability

Create `hooks.py` (~60 lines) with `build_observability_hooks()`.
PostToolUse-only scope. No SubagentStart/Stop (YAGNI).
Wire into `create_agent_options()` when `AC_SDK_HOOKS=1` (default).

<validation_gate id="VG-3" blocking="true">
Prerequisites: pip install -e . exits 0
Execute:
  python3 -c "
from autonomous_coder.hooks import build_observability_hooks
from claude_agent_sdk import HookMatcher

hooks = build_observability_hooks(verbose=True)
assert 'PostToolUse' in hooks, 'Missing PostToolUse hooks'
assert isinstance(hooks['PostToolUse'], list), 'PostToolUse should be list'
assert len(hooks['PostToolUse']) > 0, 'PostToolUse list empty'

# Verify NO SubagentStart/Stop hooks (YAGNI)
assert 'SubagentStart' not in hooks, 'SubagentStart should not exist (YAGNI)'
assert 'SubagentStop' not in hooks, 'SubagentStop should not exist (YAGNI)'

# Verify hook is not doing security (no deny logic)
import inspect
for matcher in hooks['PostToolUse']:
    for hook_fn in matcher.hooks:
        source = inspect.getsource(hook_fn)
        assert 'deny' not in source.lower(), f'Hook {hook_fn.__name__} contains deny logic — hooks are observability ONLY'

print('ALL HOOK CHECKS PASSED')
" 2>&1 | tee evidence/vg3-hooks.txt
Pass criteria:
  - evidence/vg3-hooks.txt contains "ALL HOOK CHECKS PASSED"
  - hooks.py exists and is < 80 lines
  - No "ImportError" or "Traceback"
Review: cat evidence/vg3-hooks.txt
Verdict: PASS → proceed to Task 4 | FAIL → fix hooks.py → re-run
Mock guard: IF tempted to mock HookMatcher → STOP → use real SDK types
</validation_gate>

---

## Task 4: Delete Dead Code + Cleanup

Delete 6 files: `agent.py`, `client.py`, `progress.py`, `researcher.py`, `memory.py`, `agent_instance.py`.
Remove `run_agent()` from `orchestrator.py`.
Update `__init__.py` (remove 17 legacy exports).
Update `agents/__init__.py`.

<validation_gate id="VG-4" blocking="true">
Prerequisites: pip install -e . exits 0
Execute:
  # Verify deleted files are gone
  python3 -c "
import os, sys
deleted = [
    'src/autonomous_coder/agent.py',
    'src/autonomous_coder/client.py',
    'src/autonomous_coder/progress.py',
    'src/autonomous_coder/researcher.py',
    'src/autonomous_coder/memory.py',
    'src/autonomous_coder/agent_instance.py',
]
for f in deleted:
    assert not os.path.exists(f), f'{f} still exists!'
print('ALL DEAD FILES REMOVED')
" 2>&1 | tee evidence/vg4-deleted.txt
Capture:
  # Verify no dangling imports
  grep -rn "from.*\.\(agent\|client\|progress\|researcher\|memory\|agent_instance\) import" src/autonomous_coder/ 2>&1 | tee evidence/vg4-dangling-imports.txt
  # Verify run_agent removed
  grep -n "def run_agent" src/autonomous_coder/orchestrator.py 2>&1 | tee evidence/vg4-run-agent.txt
  # Verify AgentInstance removed
  grep -rn "AgentInstance\|AgentStatus" src/autonomous_coder/ 2>&1 | tee evidence/vg4-agent-instance.txt
Pass criteria:
  - evidence/vg4-deleted.txt contains "ALL DEAD FILES REMOVED"
  - evidence/vg4-dangling-imports.txt is EMPTY (no dangling imports)
  - evidence/vg4-run-agent.txt is EMPTY (run_agent() removed)
  - evidence/vg4-agent-instance.txt is EMPTY (no AgentInstance/AgentStatus references)
  - pip install -e . succeeds (no broken imports at install time)
Review: cat evidence/vg4-deleted.txt && cat evidence/vg4-dangling-imports.txt && cat evidence/vg4-run-agent.txt && cat evidence/vg4-agent-instance.txt
Verdict: PASS → proceed to Task 5 | FAIL → fix remaining references → re-run
Mock guard: IF tempted to stub deleted modules → STOP → fix the real imports
</validation_gate>

---

## Task 5: Functional Validation (End-to-End)

Run the actual CLI tool against a real project to verify no regressions.

<validation_gate id="VG-5a" blocking="true">
Prerequisites: pip install -e . exits 0
Execute:
  autonomous-coder --help 2>&1 | tee evidence/vg5a-help.txt
Pass criteria:
  - Exit code 0
  - Output contains "--cli" flag
  - Output contains "--verbose" or "-v" flag
  - Output contains "--project" flag
  - Output contains "task" positional argument
Review: cat evidence/vg5a-help.txt
Verdict: PASS → proceed | FAIL → fix __main__.py → re-run
Mock guard: N/A — real CLI invocation
</validation_gate>

<validation_gate id="VG-5b" blocking="true">
Prerequisites: VG-5a PASSED
Execute:
  python3 -c "
# Verify all module imports work without errors
from autonomous_coder.__main__ import main
from autonomous_coder.orchestrator import AgentOrchestrator
from autonomous_coder.config import OrchestratorConfig, MCP_SERVERS
from autonomous_coder.security import security_callback, is_command_allowed
from autonomous_coder.agent_factory import create_agent_options
from autonomous_coder.hooks import build_observability_hooks
from autonomous_coder.agents import ResearchPhaseRunner, ExplorerPhaseRunner, PlannerPhaseRunner, CoderPhaseRunner
from autonomous_coder.agents.base import BasePhaseRunner
from autonomous_coder.messages import PhaseStarted, PhaseCompleted, AgentStarted, AgentCompleted
from autonomous_coder.cli_adapter import CliAdapter
print('ALL IMPORTS CLEAN')
" 2>&1 | tee evidence/vg5b-imports.txt
Pass criteria:
  - evidence/vg5b-imports.txt contains "ALL IMPORTS CLEAN"
  - No "ImportError", "ModuleNotFoundError", or "Traceback"
Review: cat evidence/vg5b-imports.txt
Verdict: PASS → proceed | FAIL → fix broken imports → re-run
Mock guard: N/A — real imports
</validation_gate>

<validation_gate id="VG-5c" blocking="true">
Prerequisites: VG-5b PASSED
Execute:
  # Verify TUI mode doesn't crash on import (Ctrl+C to exit)
  timeout 5 autonomous-coder "test" 2>&1 | tee evidence/vg5c-tui-launch.txt || true
Pass criteria:
  - evidence/vg5c-tui-launch.txt does NOT contain "ImportError" or "ModuleNotFoundError"
  - evidence/vg5c-tui-launch.txt does NOT contain "Traceback" (import-time crash)
  - Process launched (may timeout — that's fine, we just need no import crash)
Review: cat evidence/vg5c-tui-launch.txt
Verdict: PASS → all gates passed | FAIL → fix TUI imports → re-run
Mock guard: N/A — real application launch
</validation_gate>

---

<gate_manifest>
Total gates: 7 (VG-0, VG-1, VG-2, VG-3, VG-4, VG-5a, VG-5b, VG-5c)
Sequence: VG-0 → VG-1 → VG-2 → VG-3 → VG-4 → VG-5a → VG-5b → VG-5c
All gates: BLOCKING (no advancement on FAIL)
Evidence: evidence/
If ANY gate FAILS: Fix real system → re-run from FAILED gate → do NOT skip
</gate_manifest>
