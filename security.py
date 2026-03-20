"""
Security module for the Autonomous Coder skill.

Provides defense-in-depth security through:
- Bash command allowlisting
- PreToolUse hook validation
- Permission scoping
"""

from typing import Any

# Allowed bash commands - curated list of safe development commands
ALLOWED_COMMANDS = {
    # Package managers
    "npm", "npx", "yarn", "pnpm", "bun",
    "pip", "pip3", "pipx", "poetry", "uv", "uvx",
    "cargo", "rustup",
    "gem", "bundle",
    "go", "gofmt",
    "composer",
    "nuget", "dotnet",
    "brew",  # macOS package manager

    # Version control
    "git",

    # Build tools
    "make", "cmake", "ninja",
    "gradle", "gradlew", "./gradlew",
    "mvn", "./mvnw",
    "ant",
    "bazel",

    # Runtimes and compilers
    "node", "deno", "bun",
    "python", "python3",
    "ruby", "irb",
    "go", "gofmt", "goimports",
    "rustc", "cargo",
    "java", "javac", "kotlin", "kotlinc",
    "swift", "swiftc",
    "gcc", "g++", "clang", "clang++",

    # Testing frameworks
    "jest", "vitest", "mocha", "ava", "tap",
    "pytest", "unittest", "nose2",
    "rspec", "minitest",
    "go", "test",  # go test
    "cargo", "test",  # cargo test

    # Linters and formatters
    "eslint", "prettier", "biome",
    "tsc", "typescript",
    "black", "ruff", "isort", "flake8", "mypy", "pylint", "pyright",
    "rubocop",
    "rustfmt", "clippy",
    "golangci-lint",
    "shellcheck",

    # Shell utilities (safe subset)
    "echo", "printf",
    "cat", "head", "tail", "less", "more",
    "ls", "pwd", "cd",
    "mkdir", "rmdir",
    "cp", "mv",
    "touch",
    "find", "grep", "awk", "sed",
    "wc", "sort", "uniq", "diff",
    "which", "whereis", "type",
    "env", "printenv",
    "date", "cal",
    "true", "false",
    "test", "[",

    # Development utilities
    "curl", "wget",  # for downloading dependencies
    "jq", "yq",  # JSON/YAML processing
    "tar", "unzip", "zip", "gzip", "gunzip",
    "openssl",  # for certificate operations
    "ssh-keygen",  # for SSH key generation

    # Container tools (read-only operations)
    "docker", "podman",
    "kubectl",

    # Database clients (for migrations/queries)
    "psql", "mysql", "sqlite3", "mongosh",
    "redis-cli",

    # Cloud CLIs (for deployments)
    "aws", "gcloud", "az", "vercel", "netlify", "fly",

    # Process management
    "kill", "pkill",  # for stopping dev servers
    "ps", "top", "htop",
    "lsof",
}

# Dangerous patterns that should never be allowed
DANGEROUS_PATTERNS = [
    "rm -rf /",
    "rm -rf /*",
    "rm -rf ~",
    "rm -rf $HOME",
    "> /dev/sda",
    "mkfs",
    "dd if=",
    ":(){:|:&};:",  # fork bomb
    "chmod 777",
    "chmod -R 777",
    "sudo rm",
    "sudo chmod",
    "sudo chown",
    "curl | sh",
    "curl | bash",
    "wget | sh",
    "wget | bash",
    "eval $(",
    "base64 -d |",
]


def is_command_allowed(command: str) -> tuple[bool, str]:
    """
    Check if a bash command is allowed to execute.

    Args:
        command: The bash command to validate

    Returns:
        Tuple of (is_allowed, reason)
    """
    if not command or not command.strip():
        return False, "Empty command"

    # Check for dangerous patterns first
    command_lower = command.lower()
    for pattern in DANGEROUS_PATTERNS:
        if pattern.lower() in command_lower:
            return False, f"Dangerous pattern detected: {pattern}"

    # Extract the base command (first word)
    parts = command.strip().split()
    if not parts:
        return False, "Could not parse command"

    base_command = parts[0]

    # Handle path-prefixed commands (e.g., /usr/bin/git -> git)
    if "/" in base_command:
        base_command = base_command.split("/")[-1]

    # Handle ./script execution
    if base_command.startswith("./"):
        # Allow common wrapper scripts
        script_name = base_command[2:]
        if script_name in {"gradlew", "mvnw", "node_modules/.bin"}:
            return True, f"Allowed wrapper script: {script_name}"
        # For other scripts, check if they're in node_modules/.bin
        if "node_modules/.bin" in command:
            return True, "Allowed node_modules binary"
        return False, f"Disallowed script execution: {base_command}"

    # Check against allowlist
    if base_command in ALLOWED_COMMANDS:
        return True, f"Allowed command: {base_command}"

    return False, f"Command not in allowlist: {base_command}"


async def bash_security_hook(
    tool_input: dict[str, Any],
) -> dict[str, Any] | None:
    """
    PreToolUse hook for validating bash commands.

    This hook is called before every Bash tool use to validate
    that the command is in the allowlist.

    Args:
        tool_input: The tool input containing the command

    Returns:
        None to allow the command, or a dict with 'error' to block it
    """
    command = tool_input.get("command", "")

    is_allowed, reason = is_command_allowed(command)

    if is_allowed:
        return None  # Allow the command to proceed

    # Block the command with an explanation
    return {
        "error": f"Command blocked by security policy: {reason}",
        "blocked_command": command,
        "suggestion": "Use an allowed command from the security allowlist",
    }


def get_security_permissions(project_path: str) -> dict[str, Any]:
    """
    Get the security permissions configuration for Claude SDK.

    Args:
        project_path: Path to the project directory

    Returns:
        Permissions dictionary for ClaudeCodeOptions
    """
    return {
        "defaultMode": "acceptEdits",
        "allow": [
            # File operations scoped to project
            f"Read({project_path}/**)",
            f"Write({project_path}/**)",
            f"Edit({project_path}/**)",
            f"Glob({project_path}/**)",
            f"Grep({project_path}/**)",
            # Also allow relative paths
            "Read(./**)",
            "Write(./**)",
            "Edit(./**)",
            "Glob(./**)",
            "Grep(./**)",
            # Bash with hook validation
            "Bash(*)",
            # Serena MCP tools
            "mcp__serena__get_symbols_overview",
            "mcp__serena__find_symbol",
            "mcp__serena__find_referencing_symbols",
            "mcp__serena__search_for_pattern",
            "mcp__serena__list_dir",
            "mcp__serena__read_file",
            "mcp__serena__replace_content",
            "mcp__serena__replace_symbol_body",
            "mcp__serena__insert_after_symbol",
            "mcp__serena__insert_before_symbol",
            "mcp__serena__create_text_file",
            "mcp__serena__execute_shell_command",
            # Puppeteer MCP tools (for browser testing)
            "mcp__puppeteer__*",
        ],
    }


def get_sandbox_settings() -> dict[str, Any]:
    """
    Get the sandbox configuration.

    Returns:
        Sandbox settings dictionary
    """
    return {
        "enabled": True,
        "autoAllowBashIfSandboxed": True,
    }


# Export the security configuration
__all__ = [
    "ALLOWED_COMMANDS",
    "DANGEROUS_PATTERNS",
    "is_command_allowed",
    "bash_security_hook",
    "get_security_permissions",
    "get_sandbox_settings",
]
