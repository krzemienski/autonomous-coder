# How to Use Autonomous Coder

This guide provides detailed usage examples for the Autonomous Coder skill.

## Table of Contents

1. [Basic Usage](#basic-usage)
2. [Slash Command Usage](#slash-command-usage)
3. [Python API Usage](#python-api-usage)
4. [CLI Usage](#cli-usage)
5. [Advanced Scenarios](#advanced-scenarios)
6. [Understanding the Four Phases](#understanding-the-four-phases)
7. [Working with Progress](#working-with-progress)
8. [Customization](#customization)

---

## Basic Usage

### Simple Task Request

The simplest way to use the Autonomous Coder is through the slash command:

```
/autonomous-code Add a dark mode toggle to the settings page
```

The skill will:
1. Research relevant MCP servers and resources via web search
2. Explore your codebase to understand its structure
3. Create a detailed implementation plan
4. Implement each task with verification

### Complex Feature Request

For multi-part features, provide comprehensive descriptions:

```
/autonomous-code Implement a complete user notification system with:
- Email notifications for account events
- In-app notification center
- User preferences for notification types
- Unsubscribe functionality
```

---

## Slash Command Usage

### Basic Syntax

```
/autonomous-code <task description>
```

### Examples

#### Adding a New Feature

```
/autonomous-code Add pagination to the products API endpoint with:
- Page size parameter (default 20, max 100)
- Cursor-based pagination for performance
- Total count in response headers
- Update existing tests
```

#### Bug Fix

```
/autonomous-code Fix the race condition in the checkout process where
concurrent requests can double-charge customers. The issue is in the
payment processing module.
```

#### Refactoring

```
/autonomous-code Refactor the authentication module to use the
repository pattern. Keep all existing functionality but improve
testability and separation of concerns.
```

#### Adding Tests

```
/autonomous-code Add comprehensive unit tests for the OrderService
class. Cover all public methods including edge cases for invalid
inputs, empty orders, and failed payments.
```

---

## Python API Usage

### Basic Example

```python
import asyncio
from autonomous_coder import run_autonomous_coder

async def main():
    result = await run_autonomous_coder(
        task="Add user authentication with JWT tokens",
        project_path="/path/to/my/project"
    )

    if result["success"]:
        print(f"✓ Task completed successfully!")
        print(f"  Completed: {result['completed_tasks']}/{result['total_tasks']} tasks")
        print(f"  Files modified: {len(result['files_modified'])}")
    else:
        print(f"✗ Task failed: {result['error']}")
        print(f"  Phase: {result['failed_phase']}")
        print(f"  Details: {result['error_details']}")

asyncio.run(main())
```

### With Progress Callback

```python
from autonomous_coder import run_autonomous_coder, ProgressTracker

def on_progress(phase: str, status: str, details: dict):
    """Callback for progress updates."""
    print(f"[{phase}] {status}")
    if "current_task" in details:
        print(f"  Task {details['current_task']}/{details['total_tasks']}")

async def main():
    result = await run_autonomous_coder(
        task="Implement caching layer",
        project_path="/path/to/project",
        progress_callback=on_progress
    )

asyncio.run(main())
```

### Resuming Interrupted Work

```python
from autonomous_coder import run_autonomous_coder, ProgressTracker

async def main():
    # Check for existing progress
    tracker = ProgressTracker("/path/to/project")

    if tracker.has_existing_progress():
        print(f"Found existing progress: {tracker.get_status()}")
        print(f"Resuming from task {tracker.current_task}...")

        result = await run_autonomous_coder(
            task=tracker.original_task,
            project_path="/path/to/project",
            resume=True  # Resume from saved state
        )
    else:
        result = await run_autonomous_coder(
            task="New task here",
            project_path="/path/to/project"
        )

asyncio.run(main())
```

### Using Specific Client Options

```python
from autonomous_coder import AutonomousCoderAgent, AutonomousCoderClient

async def main():
    # Create custom client with all MCP servers
    client = AutonomousCoderClient(
        model="claude-sonnet-4-20250514",
        max_tokens=32000,
        mcp_servers={
            "serena": {
                "command": "uvx",
                "args": ["serena"],
                "env": {
                    "SERENA_PROJECT": "/path/to/project"
                }
            },
            "sequential-thinking": {
                "command": "npx",
                "args": ["-y", "@modelcontextprotocol/server-sequential-thinking"]
            },
            "Context7": {
                "command": "npx",
                "args": ["-y", "@upstash/context7-mcp"]
            },
            "firecrawl-mcp": {
                "command": "npx",
                "args": ["-y", "firecrawl-mcp"],
                "env": {
                    "FIRECRAWL_API_KEY": "${FIRECRAWL_API_KEY}"
                }
            }
        }
    )

    # Create agent with custom client
    agent = AutonomousCoderAgent(
        client=client,
        project_path="/path/to/project"
    )

    # Run the task
    result = await agent.run("Implement feature X")

asyncio.run(main())
```

---

## CLI Usage

### Basic Command

```bash
python -m autonomous_coder \
    --task "Add rate limiting to all API endpoints" \
    --project /path/to/your/project
```

### With Verbose Output

```bash
python -m autonomous_coder \
    --task "Implement caching" \
    --project /path/to/project \
    --verbose
```

### Resume Interrupted Work

```bash
python -m autonomous_coder \
    --project /path/to/project \
    --resume
```

### Dry Run (Plan Only)

```bash
python -m autonomous_coder \
    --task "Add new feature" \
    --project /path/to/project \
    --plan-only
```

### Export Plan to File

```bash
python -m autonomous_coder \
    --task "Add authentication" \
    --project /path/to/project \
    --plan-only \
    --output plan.json
```

---

## Advanced Scenarios

### Working with Monorepos

For monorepo projects, specify the target package:

```
/autonomous-code In the @myorg/auth package, add OAuth2 support for
Google and GitHub providers. Update the shared types in @myorg/types.
```

### Multi-Language Projects

The skill handles polyglot codebases:

```
/autonomous-code Add a Python data processing service that:
- Reads from the existing PostgreSQL database
- Processes data using pandas
- Exposes results via FastAPI
- Integrates with the existing Node.js frontend
```

### Database Migrations

```
/autonomous-code Add a user_preferences table with:
- user_id (foreign key to users)
- notification_email (boolean, default true)
- notification_push (boolean, default true)
- theme (enum: light, dark, system)
- language (varchar, default 'en')

Include migration files and update the User model.
```

### API Versioning

```
/autonomous-code Implement API versioning (v1, v2) for all endpoints.
- v1 keeps current behavior
- v2 adds pagination, filtering, and new response format
- Version via URL prefix (/api/v1/, /api/v2/)
- Add version negotiation middleware
```

---

## Understanding the Four Phases

### Phase 1: Research

The Research phase performs web research to discover relevant tools and resources:

```
┌─────────────────────────────────────────────────┐
│                   RESEARCH                      │
├─────────────────────────────────────────────────┤
│  1. Task Type Detection                         │
│     └─ Identify domains (iOS, web, API, etc.)  │
│                                                 │
│  2. MCP Server Discovery                        │
│     └─ Search for relevant MCP servers         │
│     └─ Example: xc-mcp for iOS development     │
│                                                 │
│  3. Skills & Examples Search                    │
│     └─ Find Claude Code skills on GitHub       │
│     └─ Discover Anthropic quickstarts          │
│                                                 │
│  4. Library Documentation Fetch                 │
│     └─ Use Context7 for up-to-date docs        │
│     └─ Get best practices and patterns         │
│                                                 │
│  5. Recommendations                             │
│     └─ MCPs to install with commands           │
│     └─ Implementation approach suggestions      │
└─────────────────────────────────────────────────┘
```

**Output**: Research report with MCP recommendations, skills to adapt, library documentation, and implementation approach suggestions.

**Example for iOS Task**:
```json
{
  "task_analysis": {
    "domains": ["ios", "mobile"],
    "languages": ["Swift"],
    "frameworks": ["SwiftUI"]
  },
  "mcp_servers": [
    {
      "name": "xc-mcp",
      "relevance": "high",
      "installation": {
        "command": "npx",
        "args": ["-y", "@headwayio/xc-mcp"]
      }
    }
  ],
  "recommendations": {
    "must_install": ["xc-mcp for iOS simulator control"],
    "approach": "Use SwiftUI with Combine for reactive UI"
  }
}
```

### Phase 2: Explorer

The Explorer phase uses Serena MCP to analyze your codebase:

```
┌─────────────────────────────────────────────────┐
│                    EXPLORER                      │
├─────────────────────────────────────────────────┤
│  1. Project Structure Discovery                  │
│     └─ list_dir(recursive=true)                 │
│                                                  │
│  2. Architecture Analysis                        │
│     └─ get_symbols_overview() on key files      │
│                                                  │
│  3. Pattern Recognition                          │
│     └─ search_for_pattern() for conventions     │
│                                                  │
│  4. Dependency Mapping                           │
│     └─ find_symbol() + find_referencing_symbols │
│                                                  │
│  5. Relevant File Identification                 │
│     └─ Files to create/modify for the task      │
└─────────────────────────────────────────────────┘
```

**Output**: Structured JSON with project overview, architecture patterns, coding conventions, relevant files, and risks.

### Phase 3: Planner

The Planner creates atomic, testable tasks:

```
┌─────────────────────────────────────────────────┐
│                    PLANNER                       │
├─────────────────────────────────────────────────┤
│  1. Task Decomposition                           │
│     └─ Break into atomic, focused tasks         │
│                                                  │
│  2. Dependency Analysis                          │
│     └─ Identify task order and parallel groups  │
│                                                  │
│  3. Risk Mitigation                              │
│     └─ Rollback strategies and checkpoints      │
│                                                  │
│  4. Testing Strategy                             │
│     └─ Unit, integration, and manual tests      │
└─────────────────────────────────────────────────┘
```

**Output**: Detailed plan with tasks, dependencies, parallel groups, and validation checkpoints.

### Phase 4: Coder

The Coder implements tasks iteratively:

```
┌─────────────────────────────────────────────────┐
│                     CODER                        │
├─────────────────────────────────────────────────┤
│  For each task:                                  │
│                                                  │
│  1. Understand Context                           │
│     └─ Read related files via Serena            │
│                                                  │
│  2. Implement Changes                            │
│     └─ Follow existing patterns exactly         │
│                                                  │
│  3. Add Tests                                    │
│     └─ Write and run specified tests            │
│                                                  │
│  4. Verify                                       │
│     └─ Run test suite, check success criteria   │
│                                                  │
│  5. Report                                       │
│     └─ Document changes and any issues          │
└─────────────────────────────────────────────────┘
```

**Output**: Per-task completion reports with files modified, tests added, and verification status.

---

## Working with Progress

### Progress File Location

Progress is stored in `.autonomous-coder/progress.json` in your project:

```json
{
  "task": "Add user authentication",
  "started_at": "2024-01-15T10:30:00Z",
  "phase": "coding",
  "status": "in_progress",
  "research": {
    "task_analysis": {...},
    "mcp_servers": [...],
    "skills": [...],
    "recommendations": {...}
  },
  "exploration_results": {
    "project_overview": {...},
    "architecture": {...},
    "relevant_files": [...]
  },
  "plan": {
    "tasks": [...],
    "parallel_groups": [...]
  },
  "completed_tasks": [1, 2, 3],
  "current_task": 4,
  "total_tasks": 7,
  "task_results": [
    {
      "task_id": 1,
      "status": "completed",
      "files_modified": [...],
      "tests_added": [...]
    }
  ]
}
```

### Checking Progress Programmatically

```python
from autonomous_coder import ProgressTracker

tracker = ProgressTracker("/path/to/project")

# Check status
print(f"Phase: {tracker.phase}")
print(f"Progress: {tracker.completed_tasks}/{tracker.total_tasks}")
print(f"Current task: {tracker.current_task}")

# Get completion percentage
print(f"Complete: {tracker.completion_percentage}%")
```

### Clearing Progress

```bash
# Via CLI
python -m autonomous_coder --project /path/to/project --clear-progress

# Or manually
rm -rf /path/to/project/.autonomous-coder/
```

---

## Customization

### Custom Prompt Templates

Override default prompts by creating files in your project:

```
.autonomous-coder/
├── prompts/
│   ├── explorer_prompt.md  # Custom explorer prompt
│   ├── planner_prompt.md   # Custom planner prompt
│   └── coder_prompt.md     # Custom coder prompt
```

The skill will use these instead of the defaults.

### Custom Security Rules

Extend the allowed commands list:

```python
from autonomous_coder.security import ALLOWED_COMMANDS

# Add custom commands
ALLOWED_COMMANDS.extend([
    "docker",
    "docker-compose",
    "kubectl"
])
```

### Custom MCP Servers

Add project-specific MCP servers:

```python
from autonomous_coder import AutonomousCoderClient

client = AutonomousCoderClient(
    mcp_servers={
        "serena": {...},
        "custom-server": {
            "command": "node",
            "args": ["./my-mcp-server.js"],
            "env": {"CONFIG": "production"}
        }
    }
)
```

---

## Best Practices

1. **Be Specific** - Detailed task descriptions lead to better results
2. **Review Plans** - Check the generated plan before implementation
3. **Use Resume** - Don't restart from scratch on interruptions
4. **Check Progress** - Monitor `.autonomous-coder/progress.json`
5. **Test Thoroughly** - The skill writes tests, but verify them
6. **Commit Often** - Commit after each successful task

## Common Pitfalls

1. **Vague Tasks** - "Make it better" won't work well
2. **Ignoring Exploration** - The skill needs to understand your codebase
3. **Skipping Tests** - Don't disable test verification
4. **Large Tasks** - Break huge features into smaller requests
5. **Missing Dependencies** - Ensure Serena MCP is properly installed
