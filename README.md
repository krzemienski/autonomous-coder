# Autonomous Coder Skill

An advanced Claude Code Skill that implements a three-phase architecture for autonomous task implementation on existing codebases.

## Overview

The Autonomous Coder skill transforms Claude Code into a fully autonomous coding agent that can:

1. **Explore** - Deep codebase analysis using Serena MCP for semantic understanding
2. **Plan** - Create detailed, dependency-aware implementation plans
3. **Code** - Iteratively implement tasks with verification and testing

Unlike simple code generation, this skill understands your entire codebase context before making any changes.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Autonomous Coder                         │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────┐   ┌─────────────┐   ┌─────────────┐       │
│  │   Explorer  │──▶│   Planner   │──▶│   Coder     │       │
│  │  (Serena)   │   │  (Atomic)   │   │ (Iterative) │       │
│  └─────────────┘   └─────────────┘   └─────────────┘       │
│         │                │                │                 │
│         ▼                ▼                ▼                 │
│  ┌─────────────────────────────────────────────────┐       │
│  │           Progress Tracker (JSON)                │       │
│  │     .autonomous-coder/progress.json             │       │
│  └─────────────────────────────────────────────────┘       │
├─────────────────────────────────────────────────────────────┤
│  Security: OS Sandbox │ Filesystem Restrictions │ Bash Hook │
└─────────────────────────────────────────────────────────────┘
```

## Requirements

### Python Dependencies

```bash
pip install claude-code-sdk
```

### MCP Servers Required

1. **Serena MCP** (Required) - For codebase semantic analysis
   - Provides: `get_symbols_overview`, `find_symbol`, `find_referencing_symbols`, `search_for_pattern`
   - Installation: Follow [Serena MCP setup guide](https://github.com/serena-ai/serena-mcp)

2. **Puppeteer MCP** (Optional) - For browser automation in web projects
   - Provides: Navigation, screenshots, form interaction
   - Installation: Follow [Puppeteer MCP setup guide](https://github.com/anthropics/mcp-server-puppeteer)

## Installation

### Option 1: Personal Installation (Recommended)

```bash
# Navigate to the skill folder
cd path/to/claude-code-skills-factory/generated-skills/autonomous-coder

# Copy to personal skills directory
cp -r . ~/.claude/skills/autonomous-coder/

# Restart Claude Code
```

### Option 2: Project-Level Installation

```bash
# Copy to project skills directory
cp -r . /path/to/your/project/.claude/skills/autonomous-coder/

# Restart Claude Code
```

### Option 3: Python Package Installation

```bash
# Install as Python package (for programmatic use)
cd path/to/claude-code-skills-factory/generated-skills/autonomous-coder
pip install -e .
```

## Quick Start

### Via Slash Command (Recommended)

After installing the skill, use the included slash command:

```
/autonomous-code Add user authentication with JWT tokens
```

### Via Python API

```python
from autonomous_coder import run_autonomous_coder

result = await run_autonomous_coder(
    task="Add user authentication with JWT tokens",
    project_path="/path/to/your/project"
)

if result["success"]:
    print(f"Completed {result['completed_tasks']} tasks")
else:
    print(f"Failed: {result['error']}")
```

### Via CLI

```bash
# Run as CLI tool
python -m autonomous_coder \
    --task "Add user authentication with JWT" \
    --project /path/to/your/project
```

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `ANTHROPIC_API_KEY` | Your Anthropic API key | Required |
| `AUTONOMOUS_CODER_MODEL` | Claude model to use | `claude-sonnet-4-20250514` |
| `AUTONOMOUS_CODER_MAX_TOKENS` | Max tokens per request | `16000` |
| `AUTONOMOUS_CODER_MAX_TURNS` | Max conversation turns | `30` |

### MCP Server Configuration

The skill automatically configures MCP servers. To customize, modify `client.py`:

```python
mcp_servers = {
    "serena": {
        "command": "npx",
        "args": ["-y", "@anthropic/mcp-server-serena"],
        "env": {"PROJECT_PATH": project_path}
    }
}
```

## Security Model

The skill implements defense-in-depth security:

1. **OS Sandbox** - Enabled by default, restricts system access
2. **Filesystem Restrictions** - Limited to project directory
3. **Bash Allowlist** - Only safe commands permitted
4. **Security Hook** - Validates all bash commands before execution

### Allowed Commands

```python
ALLOWED_COMMANDS = [
    "ls", "cat", "head", "tail", "grep", "find", "wc",
    "git", "npm", "npx", "yarn", "pnpm", "bun",
    "python", "python3", "pip", "pip3", "poetry", "uv",
    "node", "tsc", "eslint", "prettier",
    "cargo", "rustc", "rustfmt",
    "go", "gofmt",
    "make", "cmake",
    "pytest", "jest", "vitest", "mocha",
    "echo", "pwd", "which", "env", "printenv",
    "mkdir", "touch", "cp", "mv"
]
```

### Dangerous Patterns (Blocked)

```python
DANGEROUS_PATTERNS = [
    r"rm\s+-rf\s+/",
    r"chmod\s+777",
    r"curl.*\|\s*(bash|sh)",
    r"wget.*\|\s*(bash|sh)",
    r">\s*/etc/",
    r"sudo\s+",
    r":\(\)\s*\{",  # Fork bomb
]
```

## File Structure

```
autonomous-coder/
├── SKILL.md              # Skill definition
├── README.md             # This file
├── HOW_TO_USE.md         # Detailed usage examples
├── __init__.py           # Package initialization
├── agent.py              # Main orchestrator (3-phase workflow)
├── client.py             # Claude SDK client with MCP
├── progress.py           # Progress tracking and persistence
├── prompts.py            # Prompt template loading
├── security.py           # Security hooks and validation
├── prompts/              # Prompt templates
│   ├── explorer_prompt.md
│   ├── planner_prompt.md
│   └── coder_prompt.md
├── sample_input.json     # Example inputs
└── expected_output.json  # Expected outputs
```

## Progress Tracking

The skill maintains state in `.autonomous-coder/progress.json`:

```json
{
  "task": "Add user authentication",
  "phase": "coding",
  "status": "in_progress",
  "exploration_results": {...},
  "plan": {...},
  "completed_tasks": [1, 2],
  "current_task": 3,
  "total_tasks": 5
}
```

This enables:
- **Session Resume** - Continue interrupted work
- **Progress Visibility** - Track completion percentage
- **Rollback Support** - Undo failed tasks

## Troubleshooting

### MCP Server Connection Issues

```bash
# Verify Serena MCP is accessible
npx -y @anthropic/mcp-server-serena --help

# Check Claude Code MCP configuration
cat ~/.claude/mcp_servers.json
```

### Permission Denied Errors

```bash
# Ensure project directory is accessible
ls -la /path/to/your/project

# Check sandbox settings
# Disable sandbox for debugging (not recommended for production)
AUTONOMOUS_CODER_SANDBOX=false python -m autonomous_coder ...
```

### Rate Limiting

The skill automatically handles rate limits with exponential backoff. For heavy usage:

```python
# Increase delay between requests
result = await run_autonomous_coder(
    task="...",
    project_path="...",
    request_delay=2.0  # seconds between API calls
)
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Run tests: `pytest tests/`
5. Submit a pull request

## License

MIT License - See LICENSE file for details.

## Related Skills

- **Prompt Factory** - Generate prompts for any role or industry
- **AWS Solution Architect** - Design AWS architectures
- **Hook Factory** - Create Claude Code hooks
