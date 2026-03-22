"""Defense-in-depth security: allowlist + argument validators + can_use_tool gate.

Three layers:
  1. PreToolUse hooks (pattern-based blocking)
  2. SDK permission mode (acceptEdits scopes file ops to cwd)
  3. can_use_tool callback (programmatic last-resort gate)
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from claude_agent_sdk import PermissionResultAllow, PermissionResultDeny


# === Dangerous patterns (always blocked) ===

DANGEROUS_PATTERNS = [
    "rm -rf /", "rm -rf /*", "rm -rf ~", "rm -rf $HOME",
    "> /dev/sda", "mkfs", "dd if=",
    ":(){:|:&};:",  # fork bomb
    "chmod 777", "chmod -R 777",
    "sudo rm", "sudo chmod", "sudo chown",
    "curl | sh", "curl | bash", "wget | sh", "wget | bash",
    "eval $(", "base64 -d |", "| bash", "| sh",
]


# === Command argument validators ===

def _validate_git(args: str) -> tuple[bool, str]:
    if "push" in args and "--force" in args:
        return False, "git force-push not allowed"
    if "push" in args:
        parts = args.split()
        if "push" in parts:
            idx = parts.index("push")
            if idx + 1 < len(parts) and parts[idx + 1] not in ("origin", "-u"):
                return False, f"git push to '{parts[idx + 1]}' not allowed (only origin)"
    return True, ""


def _validate_node(args: str) -> tuple[bool, str]:
    if "-e" in args.split() or "--eval" in args:
        return False, "node -e/--eval not allowed"
    return True, ""


def _validate_python(args: str) -> tuple[bool, str]:
    if "-c" in args.split():
        return False, "python -c not allowed"
    return True, ""


def _validate_curl(args: str) -> tuple[bool, str]:
    if any(f in args for f in ("--data", "-d", "--upload-file", "-T")):
        if "localhost" not in args and "127.0.0.1" not in args:
            return False, "curl POST/upload to external URLs not allowed"
    return True, ""


def _validate_docker(args: str) -> tuple[bool, str]:
    parts = args.split()
    if not parts:
        return False, "docker subcommand required"
    if parts[0] not in ("build", "run", "ps", "images", "logs", "stop"):
        return False, f"docker {parts[0]} not allowed"
    if parts[0] == "run" and "--privileged" in args:
        return False, "docker run --privileged not allowed"
    return True, ""


COMMANDS_REQUIRING_VALIDATION: dict[str, Any] = {
    "git": _validate_git,
    "node": _validate_node,
    "python": _validate_python,
    "python3": _validate_python,
    "curl": _validate_curl,
    "docker": _validate_docker,
}


# === Base allowlist (no argument validation needed) ===

ALLOWED_COMMANDS = {
    # Package managers
    "npm", "npx", "yarn", "pnpm", "bun",
    "pip", "pip3", "pipx", "poetry", "uv", "uvx",
    "cargo", "rustup", "gem", "bundle", "go", "composer",
    # Build tools
    "make", "cmake", "ninja", "gradle", "gradlew", "./gradlew",
    "mvn", "./mvnw", "tsc",
    # Runtimes / compilers
    "deno", "ruby", "swift", "swiftc", "rustc",
    "java", "javac", "gcc", "g++", "clang", "clang++",
    # Linters / formatters
    "eslint", "prettier", "biome", "black", "ruff", "isort",
    "flake8", "mypy", "pylint", "pyright", "rubocop",
    "rustfmt", "clippy", "golangci-lint", "shellcheck",
    # Testing
    "jest", "vitest", "mocha", "pytest",
    # Shell utilities (safe subset)
    "echo", "printf", "cat", "head", "tail", "less",
    "ls", "pwd", "mkdir", "rmdir", "cp", "mv", "touch",
    "find", "grep", "awk", "sed", "wc", "sort", "uniq", "diff",
    "which", "whereis", "type", "env", "printenv", "date", "true", "false",
    # Dev utilities
    "wget", "jq", "yq", "tar", "unzip", "zip", "gzip",
    "openssl", "ssh-keygen",
    # Process management
    "kill", "pkill", "ps", "lsof",
    # Cloud CLIs
    "aws", "gcloud", "az", "vercel", "netlify", "fly",
    # Database clients
    "psql", "mysql", "sqlite3", "mongosh", "redis-cli",
}


def is_command_allowed(
    command: str,
    extra_allowed: set[str] | None = None,
) -> tuple[bool, str]:
    """Check if a bash command passes the security policy.

    Returns (is_allowed, reason).
    """
    if not command or not command.strip():
        return False, "Empty command"

    command_lower = command.lower()
    for pattern in DANGEROUS_PATTERNS:
        if pattern.lower() in command_lower:
            return False, f"Dangerous pattern: {pattern}"

    parts = command.strip().split()
    base = parts[0].split("/")[-1] if parts else ""

    # Handle ./script wrappers
    if base.startswith("./"):
        script = base[2:]
        if script in ("gradlew", "mvnw"):
            return True, f"Allowed wrapper: {script}"
        if "node_modules/.bin" in command:
            return True, "Allowed node_modules binary"
        return False, f"Script execution not allowed: {base}"

    # Commands requiring argument validation
    if base in COMMANDS_REQUIRING_VALIDATION:
        rest = command.strip()[len(base):].strip()
        return COMMANDS_REQUIRING_VALIDATION[base](rest)

    # Base allowlist
    all_allowed = ALLOWED_COMMANDS | (extra_allowed or set())
    if base in all_allowed:
        return True, f"Allowed: {base}"

    return False, f"Not in allowlist: {base}"


async def security_gate(
    tool_name: str,
    tool_input: dict[str, Any],
    context: Any,
) -> PermissionResultAllow | PermissionResultDeny:
    """can_use_tool callback — final programmatic security gate.

    Runs after hooks and permission mode evaluation.
    """
    if tool_name == "Bash":
        command = tool_input.get("command", "")
        allowed, reason = is_command_allowed(command)
        if not allowed:
            return PermissionResultDeny(
                behavior="deny",
                message=f"Security policy: {reason}",
                interrupt=False,
            )

    return PermissionResultAllow(behavior="allow")
