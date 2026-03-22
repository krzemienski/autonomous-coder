# Plan: Make autonomous-coder Installable and Runnable

**Date:** 2026-03-20
**Status:** DRAFT - Revision 2 (incorporating Architect + Critic feedback)
**Complexity:** MEDIUM
**Scope:** 4 tasks across ~4 new/modified files

---

## Context

The `autonomous-coder` project is a Python TUI application built with Textual and claude-agent-sdk. Despite having complete application code (app.py, orchestrator.py, agents/, widgets/, etc.), the project **cannot be installed or run** because it lacks Python packaging infrastructure. The git repo root directory is named `autonomous-coder` (hyphenated), which is invalid as a Python package name. All `.py` files sit at repo root level, using relative imports (e.g., `from .app import ...`) that require the code to be an installed package.

### Key Facts from Codebase Investigation

- **External deps:** `claude-agent-sdk` (PyPI, v0.1.50 latest), `textual` (PyPI)
- **Python features used:** `from __future__ import annotations`, dataclasses, async/await, typing -- compatible with Python 3.10+
- **Package data:** `styles.tcss` (Textual CSS, referenced via `CSS_PATH = "styles.tcss"` in app.py), `prompts/*.md` (5 markdown templates, loaded via `Path(__file__).parent / "prompts"` in prompts.py)
- **Unrelated subdirectory:** `claude-esp-rs/` is a separate Rust project -- must be excluded from Python package
- **Other non-package dirs:** `plans/`, `ai/`, `commands/`, `e2e-evidence/`, `.remember/` -- not Python source
- **Entry point:** `__main__.py` defines `main()` which instantiates `AutonomousCoderApp`
- **Version:** `__version__ = "2.0.0"` in `__init__.py`

---

## Work Objectives

1. Create a `src/autonomous_coder/` package directory (src layout) containing all Python source
2. Add `pyproject.toml` with proper metadata, dependencies, and package data
3. Ensure `pip install .` works from a clean venv
4. Ensure `python -m autonomous_coder` and `python -m autonomous_coder "task"` both work
5. Keep non-code files (README, docs, plans) at repo root

---

## Guardrails

### Must Have
- `pip install -e .` (editable install) works for development
- `pip install .` works for regular install
- `python -m autonomous_coder` launches the TUI
- `styles.tcss` and `prompts/*.md` are included as package data
- All existing relative imports continue to work unchanged
- `.gitignore` updated for new packaging artifacts

### Must NOT Have
- No changes to application logic or imports within the Python source files
- No `setup.py` or `setup.cfg` (modern tooling only)
- No `requirements.txt` (pyproject.toml is the single source of truth)
- No bundling of `claude-esp-rs/`, `plans/`, `ai/`, `commands/`, `e2e-evidence/` in the Python package
- No version pinning of transitive dependencies (only direct deps)

---

## Task Flow

```
Task 1: Create src layout
    |
    v
Task 2: Create pyproject.toml
    |
    v
Task 3: Update .gitignore
    |
    v
Task 4: Validate from clean venv (functional validation)
```

All tasks are sequential -- each depends on the prior.

---

## Detailed TODOs

### Task 1: Create `src/autonomous_coder/` package layout

**Action:** Move all Python source files into `src/autonomous_coder/`.

**Files to move INTO `src/autonomous_coder/`:**
- `__init__.py`
- `__main__.py`
- `app.py`
- `agent.py`
- `agent_factory.py`
- `agent_instance.py`
- `client.py`
- `config.py`
- `memory.py`
- `messages.py`
- `orchestrator.py`
- `progress.py`
- `prompts.py`
- `researcher.py`
- `security.py`
- `styles.tcss`
- `agents/` (entire directory)
- `widgets/` (entire directory)
- `prompts/` (entire directory -- 5 .md template files)

**Files that stay at repo root:**
- `README.md`, `SKILL.md`, `HOW_TO_USE.md`
- `sample_input.json`, `expected_output.json`
- `plans/`, `ai/`, `commands/`, `e2e-evidence/`
- `claude-esp-rs/` (separate Rust project)
- `.gitignore`, `.git/`, `.claude/`
- `pyproject.toml` (created in Task 2)

**Implementation:** Use `git mv` to preserve history.

```bash
mkdir -p src/autonomous_coder
git mv __init__.py __main__.py app.py agent.py agent_factory.py \
       agent_instance.py client.py config.py memory.py messages.py \
       orchestrator.py progress.py prompts.py researcher.py security.py \
       styles.tcss src/autonomous_coder/
git mv agents src/autonomous_coder/agents
git mv widgets src/autonomous_coder/widgets
git mv prompts src/autonomous_coder/prompts

# Add __init__.py to prompts/ so Hatchling auto-discovers it as package data
touch src/autonomous_coder/prompts/__init__.py
git add src/autonomous_coder/prompts/__init__.py
```

**Acceptance Criteria:**
- [ ] `src/autonomous_coder/__init__.py` exists with `__version__ = "2.0.0"`
- [ ] `src/autonomous_coder/__main__.py` exists with `main()` function
- [ ] `src/autonomous_coder/agents/` contains 4 phase runner .py files + `__init__.py`
- [ ] `src/autonomous_coder/widgets/` contains 6 widget .py files + `__init__.py`
- [ ] `src/autonomous_coder/prompts/` contains 5 .md template files + `__init__.py`
- [ ] `src/autonomous_coder/styles.tcss` exists
- [ ] No `.py` files remain at repo root (except inside `claude-esp-rs/`)
- [ ] No import statements inside any `.py` file were changed
- [ ] `README.md`, `SKILL.md`, `HOW_TO_USE.md` remain at repo root

---

### Task 2: Create `pyproject.toml`

**Action:** Create `pyproject.toml` at repo root with build system, metadata, dependencies, package data, and entry points.

**File:** `/autonomous-coder/pyproject.toml` (new)

**Contents specification:**

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "autonomous-coder"
version = "2.0.0"
description = "AI-powered autonomous coding assistant with TUI dashboard"
readme = "README.md"
license = "MIT"
requires-python = ">=3.10"
dependencies = [
    "claude-agent-sdk>=0.1.40",
    "textual>=1.0.0",
]

[project.scripts]
autonomous-coder = "autonomous_coder.__main__:main"

[tool.hatch.build.targets.wheel]
packages = ["src/autonomous_coder"]
```

**Key decisions:**
- **Build backend: Hatchling** -- modern, fast, supports src layout natively, no extra config for package data discovery
- **Python >=3.10** -- codebase uses `from __future__ import annotations`, dataclasses, match-compatible patterns
- **Dependency floors only** -- `>=0.1.0` for claude-agent-sdk, `>=0.40.0` for textual (no upper bounds to avoid resolution conflicts)
- **CLI entry point** -- `autonomous-coder` command maps to `autonomous_coder.__main__:main`
- **Package data** -- Hatchling auto-includes non-Python files in the package directory (styles.tcss, prompts/*.md) by default

**Acceptance Criteria:**
- [ ] `pyproject.toml` exists at repo root
- [ ] `[build-system]` specifies hatchling
- [ ] `[project]` has name, version, description, requires-python, dependencies
- [ ] `[project.scripts]` defines the `autonomous-coder` CLI entry point
- [ ] `[tool.hatch.build.targets.wheel]` points to `src/autonomous_coder`
- [ ] No `setup.py` or `setup.cfg` exists

---

### Task 3: Update `.gitignore`

**Action:** Add standard Python packaging artifacts to `.gitignore`.

**Additions:**
```gitignore
# Packaging
*.egg-info/    # already present, but verify
dist/          # already present, but verify
build/         # already present, but verify

# src layout
src/*.egg-info/
```

**Acceptance Criteria:**
- [ ] `.gitignore` includes `src/*.egg-info/` pattern
- [ ] Existing entries for `dist/`, `build/`, `*.egg-info/` are preserved

---

### Task 4: Functional Validation from Clean Venv

**Action:** Create a fresh virtual environment, install the package, and verify all entry points work.

**Validation script:**
```bash
# 1. Create clean venv
python3 -m venv /tmp/test-autonomous-coder
source /tmp/test-autonomous-coder/bin/activate

# 2. Install from source
cd /path/to/autonomous-coder
pip install .

# 3. Verify package is installed
pip show autonomous-coder
# Expected: Name: autonomous-coder, Version: 2.0.0

# 4. Verify module entry point (launch TUI briefly)
cd /tmp  # IMPORTANT: cd away from repo root to prove src layout works
timeout 5 python -m autonomous_coder "test" 2>&1 || true
# Expected: TUI attempts to launch (may error without API key — that's OK)

# 5. Verify CLI entry point
timeout 5 autonomous-coder "test" 2>&1 || true
# Expected: Same behavior as python -m

# 6. Verify package data is included
python -c "from autonomous_coder.config import OrchestratorConfig; print('config OK')"
python -c "from pathlib import Path; import autonomous_coder; p = Path(autonomous_coder.__file__).parent / 'styles.tcss'; assert p.exists(), f'{p} missing'; print('styles.tcss OK')"
python -c "from pathlib import Path; import autonomous_coder; p = Path(autonomous_coder.__file__).parent / 'prompts'; assert p.is_dir(), f'{p} missing'; assert len(list(p.glob('*.md'))) >= 4, 'prompt templates missing'; print('prompts OK')"

# 7. Verify prompt template loading (smoke test with correct 2-arg signature)
python -c "from autonomous_coder.prompts import get_researcher_prompt; r = get_researcher_prompt('test task', '/tmp'); assert len(r) > 0; print('prompt loading OK')"

# 8. Verify editable install
pip install -e .
python -c "import autonomous_coder; print(autonomous_coder.__version__)"

# 9. Cleanup
deactivate
rm -rf /tmp/test-autonomous-coder
```

**Known limitation:** The legacy `ensure_prompt_templates_exist()` function in `prompts.py` writes to `Path(__file__).parent / "prompts"`. On non-editable installs, this path is inside site-packages and may be read-only. The TUI entry point (`__main__.py` → `app.py`) does NOT call this function, so the primary use case is unaffected. The legacy `AutonomousCoderAgent` class does call it. This is documented as a follow-up refactor (use `importlib.resources`).

**Acceptance Criteria:**
- [ ] `pip install .` succeeds with zero errors
- [ ] `pip show autonomous-coder` shows version 2.0.0
- [ ] `python -m autonomous_coder` launches (or exits gracefully if no API key)
- [ ] `autonomous-coder` CLI command works identically
- [ ] `styles.tcss` is accessible at the installed package location
- [ ] `prompts/` directory with all 5 .md files is accessible at installed package location
- [ ] `pip install -e .` also succeeds

---

## Success Criteria

1. A developer can clone the repo, run `pip install .`, and launch with `python -m autonomous_coder`
2. All existing imports work without modification
3. Package data (styles.tcss, prompts/*.md) is correctly bundled
4. The package is structured for eventual PyPI publishing

---

## RALPLAN-DR Summary

### Principles

1. **Zero application code changes** -- packaging must wrap existing code, not modify it
2. **Modern Python packaging** -- pyproject.toml only, no legacy setup.py/setup.cfg
3. **Src layout** -- isolates package from repo root to prevent accidental imports of uninstalled code
4. **Minimal dependency specification** -- floor versions only, no upper bounds, no transitive pins
5. **History preservation** -- use `git mv` so file history is tracked through the restructuring

### Decision Drivers

1. **Correctness** -- the package must actually install and run from a clean venv (the entire point)
2. **Simplicity** -- fewest new files and configuration, leverage build backend defaults
3. **Future-proofing** -- structure should support PyPI publishing, entry points, and optional deps later

### Viable Options

#### Option A: Src Layout with Hatchling (RECOMMENDED)

Move all Python source to `src/autonomous_coder/`, use Hatchling build backend.

| Pros | Cons |
|------|------|
| Src layout prevents "it works uninstalled" false positives | Requires moving all .py files (one-time cost) |
| Hatchling auto-discovers package data (tcss, md) | Slightly less common than setuptools |
| Minimal config (~20 lines of pyproject.toml) | Developers must `pip install -e .` before running |
| Clean separation: repo root has docs, src/ has code | |
| Modern best practice endorsed by PyPA | |

#### Option B: Flat Layout with Setuptools

Rename repo directory or add a top-level `autonomous_coder/` alongside existing files, use setuptools backend.

| Pros | Cons |
|------|------|
| Setuptools is most widely known | Flat layout risks importing uninstalled code during development |
| No file moves needed if we nest inside a new dir | Must explicitly configure `package_data` for .tcss and .md files |
| | Repo root becomes cluttered with both docs AND a nested package dir |
| | `find_packages` can accidentally include `claude-esp-rs` or `plans` |
| | Setuptools requires more config for non-standard layouts |

**Invalidation rationale:** Flat layout creates a known footgun where `python -m autonomous_coder` can appear to work from the repo root without installation (because Python adds CWD to sys.path), making it impossible to truly validate the packaging is correct. This is precisely the class of bug that caused all prior "functional validation" to be fraudulent. Src layout eliminates this entirely.

#### Option C: Flat Layout with Hatchling (no src/)

Keep files at repo root, configure Hatchling to treat root as the package.

| Pros | Cons |
|------|------|
| No file moves | Same CWD-on-sys.path false positive problem as Option B |
| Simple initial setup | `claude-esp-rs/`, `plans/`, `ai/` must be explicitly excluded |
| | Root-level `__init__.py` makes the REPO itself look like a package |
| | Hatchling's auto-discovery would try to include non-package directories |

**Invalidation rationale:** Same sys.path false positive issue as Option B. Additionally, having `__init__.py` at repo root with Hatchling's auto-discovery creates ambiguity about what constitutes the package, requiring extensive exclusion rules.

### ADR

- **Decision:** Option A -- Src layout with Hatchling
- **Drivers:** Correctness (eliminates false-positive installs), simplicity (auto package data), future-proofing (PyPA best practice)
- **Alternatives considered:** Flat layout with setuptools (Option B), flat layout with Hatchling (Option C)
- **Why chosen:** Only option that structurally prevents the CWD-on-sys.path false positive that made all prior validation fraudulent. Hatchling requires minimal config and auto-includes package data.
- **Consequences:** All Python source moves to `src/autonomous_coder/`. Developers must run `pip install -e .` before development. Git history preserved via `git mv`.
- **Follow-ups:** Update README installation instructions. Consider adding `[project.optional-dependencies]` for dev tools (ruff, etc.) later. Consider PyPI publishing workflow.
