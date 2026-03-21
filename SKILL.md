---
name: autonomous-coder
description: Autonomous coding agent with web research for MCP discovery, codebase exploration, comprehensive planning, and iterative implementation using Claude Agent SDK (v0.1.49) with multiple MCP integrations
---

# Autonomous Coder

This skill provides an autonomous coding agent capable of working on **existing codebases** (not just greenfield projects). It uses a four-phase architecture (Research → Explorer → Planner → Coder) with web research for MCP discovery, Serena MCP for deep contextual understanding, and Claude Agent SDK for implementation.

## Capabilities

- **Web Research & MCP Discovery**: Discovers relevant MCP servers, skills, and resources BEFORE coding starts
- **Codebase Exploration**: Deep analysis of existing code using Serena MCP's semantic tools
- **Comprehensive Planning**: Creates detailed implementation plans before writing code
- **Iterative Implementation**: Builds features step-by-step with progress tracking
- **Existing Codebase Support**: Works on any project, not just new ones
- **Security-First Execution**: Defense-in-depth with sandbox, filesystem restrictions, bash allowlists
- **Progress Persistence**: Tracks completed work via feature lists and git commits
- **Session Management**: Fresh context windows to prevent context overflow
- **MCP Integration**: Firecrawl for web research, Context7 for library docs, Serena for code understanding, Sequential Thinking for complex reasoning

## Architecture

### Four-Phase Agent Pattern

```
┌──────────────────────────────────────────────────────────────────────────┐
│                        AUTONOMOUS CODER                                  │
├──────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌───────────┐   ┌───────────┐   ┌───────────┐   ┌───────────┐         │
│  │ RESEARCH  │──▶│ EXPLORER  │──▶│  PLANNER  │──▶│   CODER   │         │
│  │           │   │           │   │           │   │           │         │
│  │ • Firecrawl   │ • Serena  │   │ • Task    │   │ • Claude  │         │
│  │   (web    │   │   MCP     │   │   breakdown   │   SDK     │         │
│  │   research)   │ • Symbol  │   │ • Dependency  │ • Iterative│        │
│  │ • Context7│   │   analysis│   │   mapping │   │   sessions│         │
│  │   (library│   │ • Pattern │   │ • Risk    │   │ • Git     │         │
│  │   docs)   │   │   detection   │   assess  │   │   commits │         │
│  │ • MCP     │   │ • Structure   │ • Test    │   │ • Testing │         │
│  │   discovery   │   mapping │   │   strategy│   │           │         │
│  └───────────┘   └───────────┘   └───────────┘   └───────────┘         │
│       │               │               │               │                 │
│       ▼               ▼               ▼               ▼                 │
│  ┌───────────┐   ┌───────────┐   ┌───────────┐   ┌───────────┐         │
│  │   MCP     │   │ Codebase  │   │ plan.json │   │ Completed │         │
│  │ Recommendations  │ Context   │   with tasks  │  Features │         │
│  └───────────┘   └───────────┘   └───────────┘   └───────────┘         │
│                                                                          │
└──────────────────────────────────────────────────────────────────────────┘
```

### Phase 1: Research (Web Research & MCP Discovery)

The Research phase performs web research BEFORE any codebase exploration to discover:

- **MCP Server Discovery**: Finds relevant MCP servers for the task domain
  - For iOS apps: Discovers xc-mcp (iOS simulator control), SwiftUI resources
  - For web apps: Discovers playwright-mcp, browser automation tools
  - For databases: Discovers postgres-mcp, database management tools
  - For APIs: Discovers openapi-mcp, API testing tools

- **Skills & Examples**: Searches for Claude Code skills and automation examples
  - Anthropic quickstarts and official examples
  - Community skills on GitHub
  - Similar implementations and patterns

- **Library Documentation**: Fetches up-to-date docs using Context7 MCP
  - Resolves library IDs for frameworks
  - Retrieves API references and usage guides
  - Finds best practices and migration guides

**Tools Used**:
- **Firecrawl MCP**: `firecrawl_search`, `firecrawl_scrape`, `firecrawl_map`
- **Context7 MCP**: `resolve-library-id`, `get-library-docs`

**Output**: Research report with:
```json
{
  "task_analysis": {
    "domains": ["ios", "mobile"],
    "languages": ["Swift"],
    "frameworks": ["SwiftUI"],
    "platforms": ["iOS"]
  },
  "mcp_servers": [
    {
      "name": "xc-mcp",
      "description": "iOS simulator control and Xcode automation",
      "relevance": "high",
      "installation": {
        "command": "npx",
        "args": ["-y", "@headwayio/xc-mcp"]
      },
      "source_url": "https://github.com/headwayio/xc-mcp"
    }
  ],
  "skills": [...],
  "libraries": [...],
  "recommendations": {
    "must_install": ["xc-mcp for iOS simulator control"],
    "approach": "Use SwiftUI with Combine for reactive architecture"
  }
}
```

### Phase 2: Explorer (Serena MCP)

The Explorer phase uses Serena MCP's semantic tools to build deep understanding:

- **`get_symbols_overview`**: Maps top-level symbols in files
- **`find_symbol`**: Locates specific classes, methods, functions
- **`find_referencing_symbols`**: Traces dependencies and call graphs
- **`search_for_pattern`**: Finds patterns across the codebase
- **`list_dir`**: Understands directory structure
- **`read_file`**: Reads specific file contents when needed

**Output**: Structured codebase context including:
- Technology stack detection
- Key architectural patterns
- Entry points and main flows
- Relevant files for the task
- Potential impact areas

### Phase 3: Planner

The Planner creates a comprehensive implementation plan:

- **Task Breakdown**: Splits work into atomic, testable units
- **Dependency Ordering**: Ensures correct implementation sequence
- **Risk Assessment**: Identifies areas requiring extra care
- **Test Strategy**: Defines verification approach for each task
- **Rollback Points**: Marks safe points for reverting changes

**Output**: `plan.json` with:
```json
{
  "goal": "User's original task description",
  "context_summary": "Key findings from exploration",
  "tasks": [
    {
      "id": 1,
      "title": "Task title",
      "description": "Detailed description",
      "files": ["file1.py", "file2.py"],
      "dependencies": [],
      "test_criteria": "How to verify completion",
      "estimated_complexity": "low|medium|high"
    }
  ],
  "risks": ["Potential issues to watch for"],
  "total_tasks": 5
}
```

### Phase 4: Coder

The Coder implements the plan iteratively:

- **Session-Based**: Each task runs in a fresh context window
- **Progress Tracking**: Updates feature_list.json after each task
- **Git Integration**: Commits after successful task completion
- **Error Recovery**: Handles failures gracefully with context
- **Testing**: Runs tests after implementation when possible

## Input Requirements

The skill accepts:

### Task Description (Required)
A clear description of what to build or modify:
```
"Add user authentication with JWT tokens to the existing Express API"
"Refactor the payment module to use the Strategy pattern"
"Create a new dashboard component that displays analytics data"
```

### Project Path (Required)
Path to the existing codebase:
```
"/path/to/your/project"
```

### Configuration (Optional)
```json
{
  "task": "Description of what to build",
  "project_path": "/path/to/project",
  "config": {
    "max_sessions": 20,
    "auto_commit": true,
    "run_tests": true,
    "model": "claude-sonnet-4-20250514",
    "sandbox_enabled": true
  }
}
```

## Output Formats

### Exploration Report
```json
{
  "stack": {
    "language": "TypeScript",
    "framework": "Express",
    "database": "PostgreSQL",
    "testing": "Jest"
  },
  "architecture": "MVC with service layer",
  "entry_points": ["src/index.ts", "src/app.ts"],
  "relevant_files": [
    {"path": "src/routes/users.ts", "relevance": "high"},
    {"path": "src/middleware/auth.ts", "relevance": "high"}
  ],
  "patterns_detected": ["dependency injection", "middleware chain"],
  "impact_areas": ["authentication", "session management"]
}
```

### Implementation Plan
```json
{
  "goal": "Add JWT authentication",
  "context_summary": "Express API with existing session-based auth",
  "tasks": [
    {
      "id": 1,
      "title": "Install JWT dependencies",
      "description": "Add jsonwebtoken and @types/jsonwebtoken",
      "files": ["package.json"],
      "dependencies": [],
      "test_criteria": "npm install succeeds",
      "estimated_complexity": "low"
    }
  ],
  "risks": ["Breaking existing session auth during migration"],
  "total_tasks": 6
}
```

### Progress Tracking
```json
{
  "completed_tasks": [1, 2, 3],
  "current_task": 4,
  "total_tasks": 6,
  "commits": [
    "abc123: Add JWT dependencies",
    "def456: Create token utilities"
  ],
  "status": "in_progress"
}
```

## How to Use

### Via Slash Command
```
/autonomous-code "Add a GraphQL API layer to the existing REST endpoints"
```

### Via Python API
```python
from autonomous_coder import run_autonomous_coder

result = await run_autonomous_coder(
    task="Add user authentication with JWT",
    project_path="/path/to/project",
    max_sessions=20,
    auto_commit=True
)
```

### Example Tasks

**Feature Addition:**
```
"Add dark mode support to the React application with system preference detection"
```

**Refactoring:**
```
"Refactor the monolithic UserService into separate services: AuthService, ProfileService, SettingsService"
```

**Bug Fix:**
```
"Fix the race condition in the order processing workflow that causes duplicate charges"
```

**Integration:**
```
"Integrate Stripe payment processing replacing the current PayPal implementation"
```

**Testing:**
```
"Add comprehensive unit tests for the order management module with 80% coverage"
```

## Scripts

- **`agent.py`**: Main orchestrator managing the four-phase flow
- **`client.py`**: Claude Agent SDK client with security configuration and MCP setup
- **`security.py`**: Bash command allowlist and PreToolUse hook validation
- **`prompts.py`**: Prompt template loading and formatting utilities
- **`researcher.py`**: Phase 1 - Web research and MCP discovery using Firecrawl and Context7
- **`explorer.py`**: Phase 2 - Codebase exploration using Serena MCP
- **`planner.py`**: Phase 3 - Implementation plan generation
- **`progress.py`**: Progress tracking and persistence utilities

### Prompt Templates

- **`prompts/researcher_prompt.md`**: Instructions for web research and MCP discovery
- **`prompts/explorer_prompt.md`**: Instructions for codebase exploration
- **`prompts/planner_prompt.md`**: Instructions for plan generation
- **`prompts/coder_prompt.md`**: Instructions for implementation sessions

## Security Model

### Defense in Depth

```
┌─────────────────────────────────────────────────────────────────┐
│  SECURITY LAYERS                                                │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Layer 1: OS Sandbox (macOS sandbox-exec / Linux containers)   │
│  ├── Network restrictions                                      │
│  ├── Process isolation                                         │
│  └── Resource limits                                            │
│                                                                 │
│  Layer 2: Filesystem Restrictions                               │
│  ├── Only project directory accessible                         │
│  ├── No access to home directory secrets                       │
│  └── Read/Write/Edit permissions scoped to ./**                │
│                                                                 │
│  Layer 3: Bash Command Allowlist                                │
│  ├── PreToolUse hook validates every bash command              │
│  ├── Only approved commands execute                            │
│  └── Dangerous commands blocked (rm -rf, sudo, etc.)           │
│                                                                 │
│  Layer 4: MCP Tool Restrictions                                 │
│  ├── Only whitelisted MCP tools available                      │
│  ├── Serena tools scoped to project                            │
│  └── Puppeteer limited to localhost                            │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### Allowed Bash Commands

```python
ALLOWED_COMMANDS = {
    # Package managers
    "npm", "npx", "yarn", "pnpm", "pip", "pip3", "poetry", "cargo",
    # Version control
    "git",
    # Build tools
    "make", "cmake", "gradle", "mvn",
    # Runtime
    "node", "python", "python3", "ruby", "go", "rustc",
    # Testing
    "jest", "pytest", "mocha", "vitest",
    # Utilities
    "echo", "cat", "ls", "pwd", "mkdir", "cp", "mv", "touch",
    # Development
    "tsc", "eslint", "prettier", "black", "ruff",
}
```

### Permission Model

```python
permissions = {
    "defaultMode": "acceptEdits",
    "allow": [
        "Read(./**)",      # Read any file in project
        "Write(./**)",     # Write any file in project
        "Edit(./**)",      # Edit any file in project
        "Glob(./**)",      # Glob patterns in project
        "Grep(./**)",      # Search in project
        "Bash(*)",         # Bash with allowlist validation
        # Serena MCP tools
        "mcp__serena__*",
        # Puppeteer for browser testing
        "mcp__puppeteer__*",
    ],
}
```

## MCP Configuration

### Serena MCP (Codebase Understanding)

Semantic code analysis for deep codebase understanding.

```python
mcp_servers = {
    "serena": {
        "command": "uvx",
        "args": ["serena"],
        "env": {
            "SERENA_PROJECT": str(project_path)
        }
    }
}
```

**Key Tools**:
- `get_symbols_overview` - Map top-level symbols in files
- `find_symbol` - Locate specific classes, methods, functions
- `find_referencing_symbols` - Trace dependencies and call graphs
- `search_for_pattern` - Find patterns across the codebase

### Sequential Thinking MCP (Complex Reasoning)

Step-by-step reasoning for complex planning and analysis tasks.

```python
mcp_servers = {
    "sequential-thinking": {
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-sequential-thinking"]
    }
}
```

**Key Tools**:
- `sequentialthinking` - Multi-step reasoning with revision support

### Context7 MCP (Library Documentation)

Up-to-date library documentation and context retrieval.

```python
mcp_servers = {
    "Context7": {
        "command": "npx",
        "args": ["-y", "@upstash/context7-mcp"]
    }
}
```

**Key Tools**:
- `resolve-library-id` - Find library identifiers
- `get-library-docs` - Fetch current documentation for any library

### Firecrawl MCP (Web Research)

Web scraping and content extraction for research tasks.

```python
mcp_servers = {
    "firecrawl-mcp": {
        "command": "npx",
        "args": ["-y", "firecrawl-mcp"],
        "env": {
            "FIRECRAWL_API_KEY": "${FIRECRAWL_API_KEY}"
        }
    }
}
```

**Key Tools**:
- `firecrawl_scrape` - Scrape single page content
- `firecrawl_search` - Search the web with content extraction
- `firecrawl_crawl` - Crawl multiple pages
- `firecrawl_map` - Map website structure

## Best Practices

### Writing Good Task Descriptions

1. **Be Specific**: "Add JWT auth" vs "Add authentication"
2. **Provide Context**: "Replace existing session auth with JWT"
3. **Define Scope**: "Only the /api/users endpoints"
4. **State Constraints**: "Must maintain backward compatibility"
5. **Include Acceptance Criteria**: "Should pass existing auth tests"

### Optimal Configuration

```python
config = {
    "max_sessions": 20,       # Limit context window resets
    "auto_commit": True,      # Git commit after each task
    "run_tests": True,        # Run tests after implementation
    "sandbox_enabled": True,  # Always use sandbox
    "model": "claude-sonnet-4-20250514",  # Balance speed/quality
}
```

### When to Use This Skill

**Good Fit:**
- Adding features to existing codebases
- Refactoring with clear requirements
- Integrating third-party services
- Creating new modules that follow existing patterns
- Bug fixes with known root cause

**Less Ideal:**
- Greenfield projects (use simpler agent)
- Highly ambiguous requirements
- Projects requiring extensive human design decisions
- Security-critical code without human review

## Limitations

- **Context Window**: Complex codebases may require multiple exploration sessions
- **Language Support**: Best with TypeScript, Python, JavaScript; varies for others
- **Testing**: Relies on existing test infrastructure
- **Architecture Decisions**: Makes reasonable choices but may not match team preferences
- **External Services**: Cannot configure cloud services, only generates code
- **Human Review**: Production code should always be reviewed

## Error Handling

### Common Issues

**"Serena MCP not available"**
- Ensure Serena is installed: `pip install serena`
- Check MCP configuration in client.py

**"Sandbox initialization failed"**
- Verify OS sandbox support
- Try with `sandbox_enabled=False` for debugging

**"Task exceeds max_sessions"**
- Break task into smaller pieces
- Increase `max_sessions` limit

**"Permission denied"**
- Check project_path permissions
- Verify file allowlist covers required paths

## Dependencies

- Python 3.11+
- `claude-agent-sdk` >= 0.1.49
- `serena` (via uvx or pip)
- Node.js 18+ (for npx commands)
- Git (for version control)

## Helpful Resources

- **Claude Agent SDK**: https://github.com/anthropics/claude-agent-sdk-python
- **Anthropic Quickstarts**: https://github.com/anthropics/anthropic-quickstarts
- **Serena MCP**: https://github.com/serea-ai/serena
- **Puppeteer MCP**: https://github.com/anthropics/puppeteer-mcp
- **Code Prompting Guidelines**: https://docs.anthropic.com/en/docs/build-with-claude/prompt-engineering
