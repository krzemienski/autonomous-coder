"""Project state detection — greenfield vs existing project."""

from __future__ import annotations

from pathlib import Path

# Marker files that indicate an existing project and its stack
_STACK_MARKERS: dict[str, dict[str, str]] = {
    "package.json": {"ecosystem": "node", "language": "javascript/typescript"},
    "pyproject.toml": {"ecosystem": "python", "language": "python"},
    "Cargo.toml": {"ecosystem": "rust", "language": "rust"},
    "go.mod": {"ecosystem": "go", "language": "go"},
    "pom.xml": {"ecosystem": "java", "language": "java"},
    "build.gradle": {"ecosystem": "java", "language": "java/kotlin"},
    "Gemfile": {"ecosystem": "ruby", "language": "ruby"},
    "composer.json": {"ecosystem": "php", "language": "php"},
    "Package.swift": {"ecosystem": "swift", "language": "swift"},
    "mix.exs": {"ecosystem": "elixir", "language": "elixir"},
}


def detect_project_state(project_path: Path) -> dict:
    """Detect whether a project exists and identify its stack.

    Returns a dict with:
        project_state: "greenfield" or "existing"
        stack: detected ecosystem/language info (empty if greenfield)
        markers_found: list of marker files found
    """
    if not project_path.exists():
        return {"project_state": "greenfield", "stack": {}, "markers_found": []}

    markers_found = []
    stack_info: dict[str, str] = {}

    for marker, info in _STACK_MARKERS.items():
        if (project_path / marker).exists():
            markers_found.append(marker)
            stack_info.update(info)

    if not markers_found:
        # Check for any source files
        has_sources = any(
            project_path.rglob(pat)
            for pat in ("*.py", "*.js", "*.ts", "*.rs", "*.go", "*.java")
        )
        if not has_sources:
            return {"project_state": "greenfield", "stack": {}, "markers_found": []}

    return {
        "project_state": "existing",
        "stack": stack_info,
        "markers_found": markers_found,
    }
