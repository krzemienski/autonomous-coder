# Claude Code SDK for Python — Comprehensive API Research (March 2026)

**Research Date:** March 19, 2026
**Knowledge Cutoff:** February 2025 (searches conducted for current info)
**Package:** `claude-agent-sdk` v0.1.49+ (Python >= 3.10)

---

## Executive Summary

The **Claude Code SDK has been renamed to the Claude Agent SDK** as of March 2026. The Python package is `claude-agent-sdk` (not `claude-code-sdk`, which is deprecated). Latest release: **v0.1.49** (March 17, 2026).

The SDK provides two primary interaction models:
1. **`query()`** — one-off interactions, returns `AsyncIterator[Message]`
2. **`ClaudeSDKClient`** — persistent multi-turn conversations with session management

Both support streaming, hooks, custom tools (MCP), subagents, and full file manipulation (Read/Write/Edit/Bash).

---

## 1. Installation & Authentication

### Package Installation
```bash
pip install claude-agent-sdk
```

### Python Version Requirement
Python >= 3.10

### API Key Setup
```bash
export ANTHROPIC_API_KEY=your-api-key
```

### Alternative Providers (with env flags)
- **Amazon Bedrock:** `CLAUDE_CODE_USE_BEDROCK=1` + AWS credentials
- **Google Vertex AI:** `CLAUDE_CODE_USE_VERTEX=1` + Google Cloud credentials
- **Microsoft Azure:** `CLAUDE_CODE_USE_FOUNDRY=1` + Azure credentials

---

## 2. Core API Surface

### 2.1 Primary Functions & Classes

| Component | Purpose | Returns |
|-----------|---------|---------|
| `query(prompt, options)` | One-off async queries | `AsyncIterator[Message]` |
| `ClaudeSDKClient()` | Multi-turn conversation client | Client instance (async context manager) |
| `@tool()` decorator | Define custom MCP tools | Tool definition |
| `create_sdk_mcp_server()` | Create in-process MCP server | MCP server instance |
| `list_sessions()` | Enumerate sessions on disk | `List[SessionInfo]` |
| `get_session_messages()` | Retrieve session history | `List[Message]` |

### 2.2 Query Function

```python
async for message in query(
    prompt="Create a Python web server",
    options=ClaudeAgentOptions(
        system_prompt="You are an expert Python developer",
        permission_mode="acceptEdits",
        allowed_tools=["Read", "Write", "Edit", "Bash"],
    )
):
    print(message)
```

**Parameters:**
- `prompt` (`str | AsyncIterable[SDKUserMessage]`): Input prompt or streaming input
- `options` (`ClaudeAgentOptions`): Optional configuration

**Returns:** `AsyncGenerator[Message, None]` — yields messages as they arrive

---

## 3. ClaudeAgentOptions — Configuration

Complete configuration object for all agent interactions.

### Key Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `system_prompt` | `str` | None | System prompt for agent behavior |
| `model` | `str` | `'sonnet'` | Model: `'haiku'`, `'sonnet'`, `'opus'` |
| `allowed_tools` | `List[str]` | All | Pre-approved tools (e.g., `["Read", "Bash"]`) |
| `disallowed_tools` | `List[str]` | None | Explicitly blocked tools |
| `permission_mode` | `str` | `'default'` | `'default'`, `'acceptEdits'`, `'plan'`, `'bypassPermissions'` |
| `mcp_servers` | `Dict[str, dict]` | None | MCP servers: `{"playwright": {"command": "npx", ...}}` |
| `tools` | `List[str]` | None | Base tool set (overrides defaults) |
| `agents` | `Dict[str, AgentDefinition]` | None | Subagent definitions |
| `hooks` | `Dict[str, List[HookMatcher]]` | None | Hook callbacks |
| `max_turns` | `int` | None | Max turns before auto-stop |
| `max_budget_usd` | `float` | None | Max cost budget |
| `sandbox` | `SandboxSettings` | None | Command isolation settings |
| `thinking` | `ThinkingConfig` | None | Extended thinking config |
| `include_partial_messages` | `bool` | `False` | Enable streaming deltas |
| `output_format` | `dict` | None | Structured output schema (JSON Schema) |
| `can_use_tool` | `Callable` | None | Custom permission function |
| `resume` | `str` | None | Session ID to resume |
| `fork_session` | `bool` | `False` | Fork instead of resume |
| `continue_conversation` | `bool` | `False` | Resume most recent session |
| `cwd` | `str` | Current dir | Working directory for agent |
| `setting_sources` | `List[str]` | None | Load settings: `["project"]` loads `.claude/CLAUDE.md`, `.claude/settings.json`, etc. |
| `enable_file_checkpointing` | `bool` | `False` | Enable file state rollback |
| `plugins` | `List[str]` | None | Plugin paths for custom commands |

### Example: Comprehensive Options

```python
options = ClaudeAgentOptions(
    system_prompt="You are a security-focused code reviewer.",
    model="opus",
    allowed_tools=["Read", "Grep", "Glob"],  # Read-only
    permission_mode="acceptEdits",
    max_turns=10,
    max_budget_usd=1.50,
    include_partial_messages=True,
    mcp_servers={
        "playwright": {
            "command": "npx",
            "args": ["@playwright/mcp@latest"]
        }
    },
    cwd="/home/user/project",
    setting_sources=["project"],  # Load CLAUDE.md + settings
)
```

---

## 4. ClaudeSDKClient — Multi-Turn Conversations

For persistent conversations that maintain session state across multiple exchanges.

### Basic Pattern

```python
from claude_agent_sdk import ClaudeSDKClient, ClaudeAgentOptions

async with ClaudeSDKClient(options=ClaudeAgentOptions(...)) as client:
    # First query
    await client.query("Analyze the auth module")
    async for message in client.receive_response():
        print(message)

    # Second query — context from first is retained
    await client.query("Now refactor it to use OAuth2")
    async for message in client.receive_response():
        print(message)
```

### Methods

| Method | Signature | Description |
|--------|-----------|-------------|
| `query(prompt)` | `async` | Submit prompt to agent |
| `receive_response()` | `AsyncIterator[Message]` | Iterate over response messages |
| `interrupt()` | `async` | Stop current execution |
| `get_session_id()` | `str` | Get internal session ID |

### Context Retention

- Each `await client.query(...)` automatically continues the same session
- Full conversation history is retained
- No manual session ID tracking needed
- Must use as async context manager: `async with ClaudeSDKClient(...) as client:`

---

## 5. Message Types

All messages are dataclasses yielded by `query()` or `client.receive_response()`.

### Message Hierarchy

```
Message (union type)
├── SystemMessage          # Session init, metadata
├── UserMessage            # User prompts
├── AssistantMessage       # Claude response
├── ToolUseBlock          # Tool invocation request
├── ToolResultBlock       # Tool result
├── TextBlock             # Text content
├── ThinkingBlock         # Extended thinking output
├── ResultMessage         # Final result, cost, exit status
├── StreamEvent           # Partial streaming event (if include_partial_messages=True)
└── CompactBoundaryMessage  # Conversation compaction marker
```

### Key Message Types

#### AssistantMessage
```python
@dataclass
class AssistantMessage:
    content: List[ContentBlock]  # Text, tool use, thinking, etc.
    model: str
    stop_reason: str  # "end_turn", "tool_use", "stop_sequence"
    usage: Usage
    parent_tool_use_id: str | None  # Populated if from subagent
```

#### ResultMessage
```python
@dataclass
class ResultMessage:
    subtype: str  # "success", "error", "error_max_turns", "error_max_budget_usd"
    result: str | None  # Human-readable summary
    session_id: str  # Session ID (always populated)
    total_cost_usd: float | None  # Cumulative cost
    exit_code: int | None  # Exit status
    permission_denials: List[PermissionDenial]  # Blocked operations
```

#### StreamEvent (when `include_partial_messages=True`)
```python
@dataclass
class StreamEvent:
    uuid: str
    session_id: str
    event: dict[str, Any]  # Raw Claude API streaming event
    parent_tool_use_id: str | None
```

#### SystemMessage (init)
```python
@dataclass
class SystemMessage:
    subtype: str  # "init"
    data: dict  # Contains session_id, cwd, etc.
    session_id: str  # Shortcut access
```

### Content Block Types

```python
class TextBlock:
    type: str = "text"
    text: str

class ToolUseBlock:
    type: str = "tool_use"
    id: str  # Unique tool call ID
    name: str  # Tool name (e.g., "Read", "Bash")
    input: dict  # Tool arguments

class ToolResultBlock:
    type: str = "tool_result"
    tool_use_id: str  # Correlates to ToolUseBlock.id
    content: str | List[dict]  # Result content

class ThinkingBlock:
    type: str = "thinking"
    thinking: str  # Model's reasoning

class TextBlock / ToolResultBlock / etc. are accessed via message.content list.
```

---

## 6. Streaming Output

Enable `include_partial_messages=True` to receive text and tool calls in real-time.

### Enable Streaming

```python
options = ClaudeAgentOptions(include_partial_messages=True)

async for message in query(prompt="...", options=options):
    if isinstance(message, StreamEvent):
        event = message.event
        if event.get("type") == "content_block_delta":
            delta = event.get("delta", {})
            if delta.get("type") == "text_delta":
                print(delta.get("text", ""), end="", flush=True)
```

### StreamEvent Structure

```python
event: dict[str, Any] = {
    "type": "content_block_delta",  # or message_start, message_stop, etc.
    "delta": {
        "type": "text_delta",       # or input_json_delta
        "text": "Partial text...",
        "partial_json": "{\"key\": \"val...",  # for tool input
    }
}
```

### Common Event Types

| Event Type | Description |
|------------|-------------|
| `message_start` | New message starting |
| `content_block_start` | New content block (text or tool) |
| `content_block_delta` | Incremental update (text or tool input JSON) |
| `content_block_stop` | Content block complete |
| `message_delta` | Message-level updates |
| `message_stop` | Message complete |

### Streaming Tool Calls

Track tool calls as they stream:

```python
current_tool = None
tool_input = ""

async for message in query(prompt="...", options=ClaudeAgentOptions(include_partial_messages=True)):
    if isinstance(message, StreamEvent):
        event = message.event

        if event.get("type") == "content_block_start":
            content_block = event.get("content_block", {})
            if content_block.get("type") == "tool_use":
                current_tool = content_block.get("name")
                tool_input = ""
                print(f"Tool: {current_tool}")

        elif event.get("type") == "content_block_delta":
            delta = event.get("delta", {})
            if delta.get("type") == "input_json_delta":
                chunk = delta.get("partial_json", "")
                tool_input += chunk

        elif event.get("type") == "content_block_stop":
            if current_tool:
                print(f"  Input: {tool_input}")
                current_tool = None
```

### Known Limitations
- Extended thinking: when `max_thinking_tokens` is explicitly set, `StreamEvent` is not emitted
- Structured output: JSON result appears only in final `ResultMessage.structured_output`

---

## 7. Session Management

Sessions persist conversation history to disk, enabling resumption later.

### Session Location

```
~/.claude/projects/<encoded-cwd>/<session-id>.jsonl
```

Where `<encoded-cwd>` = absolute path with non-alphanumeric chars → `-`

### 7.1 Automatic (ClaudeSDKClient)

```python
async with ClaudeSDKClient(options=options) as client:
    await client.query("First prompt")
    async for msg in client.receive_response():
        pass  # Session ID tracked internally

    await client.query("Follow-up")  # Automatically continues same session
    async for msg in client.receive_response():
        pass
```

**No session ID tracking required.**

### 7.2 Manual: Resume

Capture session ID from `ResultMessage`, then resume:

```python
session_id = None

# First query
async for message in query(prompt="Analyze auth.py", options=ClaudeAgentOptions()):
    if isinstance(message, ResultMessage):
        session_id = message.session_id
        print(message.result)

# Resume with full context
async for message in query(
    prompt="Now implement the refactoring",
    options=ClaudeAgentOptions(resume=session_id)
):
    if isinstance(message, ResultMessage):
        print(message.result)
```

### 7.3 Manual: Fork

Create a new session branching from prior history:

```python
forked_id = None

# Fork: branch from session_id
async for message in query(
    prompt="Try OAuth2 instead",
    options=ClaudeAgentOptions(resume=session_id, fork_session=True)
):
    if isinstance(message, ResultMessage):
        forked_id = message.session_id  # New ID, independent session

# Original session is untouched
async for message in query(
    prompt="Continue with JWT",
    options=ClaudeAgentOptions(resume=session_id)
):
    pass  # This path preserves original conversation
```

**Key difference:** Fork creates a new session; original is unaffected.

### 7.4 Continue Most Recent

Resume the most recent session without tracking ID:

```python
async for message in query(
    prompt="Continue work",
    options=ClaudeAgentOptions(continue_conversation=True)
):
    pass
```

### 7.5 List & Retrieve Sessions

```python
from claude_agent_sdk import list_sessions, get_session_messages

# List all sessions
for session in list_sessions(directory="/path/to/project", limit=10):
    print(f"{session.summary}: {session.session_id}")

# Get messages from a session
messages = get_session_messages(session_id, limit=50)
for msg in messages:
    print(msg)
```

### 7.6 Cross-Host Resume

Session files are local. To resume on a different host:

**Option 1:** Copy the session file
```bash
# On original host
cp ~/.claude/projects/<encoded-cwd>/<session-id>.jsonl /tmp/

# On new host
cp /tmp/<session-id>.jsonl ~/.claude/projects/<encoded-cwd>/
```

**Option 2:** Don't rely on session resume
- Capture results as application state
- Pass them in prompt to fresh session

---

## 8. Subagents

Spawn specialized agents to handle focused subtasks.

### 8.1 Define Subagents

```python
from claude_agent_sdk import AgentDefinition

agents = {
    "code-reviewer": AgentDefinition(
        description="Expert code review specialist. Use for quality, security reviews.",
        prompt="""You are a code review specialist with expertise in security and performance.
Identify vulnerabilities, performance issues, and suggest improvements.""",
        tools=["Read", "Grep", "Glob"],  # Read-only
        model="sonnet",  # Optional model override
    ),
    "test-runner": AgentDefinition(
        description="Runs and analyzes test suites.",
        prompt="""You are a test execution specialist. Run tests and analyze results.""",
        tools=["Bash", "Read", "Grep"],
    ),
}
```

### 8.2 Invoke Subagents

```python
async for message in query(
    prompt="Use the code-reviewer agent to review this codebase",
    options=ClaudeAgentOptions(
        allowed_tools=["Read", "Glob", "Grep", "Agent"],  # Must include "Agent"
        agents=agents,
    ),
):
    if hasattr(message, "result"):
        print(message.result)
```

**Important:** Include `"Agent"` in `allowed_tools` to enable subagent spawning.

### 8.3 AgentDefinition Structure

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `description` | `str` | Yes | When to use this agent (Claude reads this to decide) |
| `prompt` | `str` | Yes | System prompt defining agent's role & behavior |
| `tools` | `List[str]` | No | Allowed tools (inherit all if omitted) |
| `model` | `str` | No | Model override: `'haiku'`, `'sonnet'`, `'opus'`, `'inherit'` |
| `skills` | `List[str]` | No | (TypeScript only) |

### 8.4 Explicit Subagent Invocation

Mention subagent by name to guarantee use:

```python
await client.query("Use the code-reviewer agent to check auth.py for security issues")
```

### 8.5 Detect Subagent Invocation

```python
if hasattr(message, "content") and message.content:
    for block in message.content:
        # Match both "Task" (old) and "Agent" (new)
        if getattr(block, "type", None) == "tool_use" and block.name in ("Task", "Agent"):
            print(f"Subagent invoked: {block.input.get('subagent_type')}")

if hasattr(message, "parent_tool_use_id") and message.parent_tool_use_id:
    print("Running inside subagent")
```

### 8.6 Context Inheritance

| Subagent Receives | Subagent Does NOT Receive |
|------------------|---------------------------|
| Its own system prompt | Parent conversation history |
| Project CLAUDE.md (if `settingSources` enabled) | Parent system prompt |
| Tool definitions (inherited or restricted) | Parent tool results |

**Key:** Only channel parent → subagent is the Agent tool's prompt string.

### 8.7 Resume Subagents

```python
import json
import re

def extract_agent_id(text: str) -> str | None:
    match = re.search(r"agentId:\s*([a-f0-9-]+)", text)
    return match.group(1) if match else None

agent_id = None
session_id = None

# First invocation
async for message in query(
    prompt="Use the Explore agent to find API endpoints",
    options=ClaudeAgentOptions(allowed_tools=["Read", "Grep", "Glob", "Agent"])
):
    if hasattr(message, "session_id"):
        session_id = message.session_id
    if hasattr(message, "content"):
        content_str = json.dumps(message.content, default=str)
        agent_id = extract_agent_id(content_str)
    if hasattr(message, "result"):
        print(message.result)

# Resume subagent
if agent_id and session_id:
    async for message in query(
        prompt=f"Resume agent {agent_id} and list the top 3 complex endpoints",
        options=ClaudeAgentOptions(resume=session_id, allowed_tools=["Read", "Grep", "Glob", "Agent"])
    ):
        if hasattr(message, "result"):
            print(message.result)
```

### 8.8 Constraints

- **Subagents cannot spawn other subagents** (no nesting)
- Subagent context window starts fresh
- Subagent transcript persists independently
- Cannot be deep in complex workflows (context window isolation)

---

## 9. Hooks — Intercept & Control Behavior

Hooks are callbacks that run at key execution points.

### 9.1 Available Hooks

| Hook | When it fires | Python | TypeScript | Example |
|------|---------------|--------|------------|---------|
| `PreToolUse` | Before tool execution | Yes | Yes | Validate/block/modify tool calls |
| `PostToolUse` | After tool completes | Yes | Yes | Log, audit, append context |
| `PostToolUseFailure` | Tool fails | Yes | Yes | Handle or retry |
| `UserPromptSubmit` | User submits prompt | Yes | Yes | Inject context into prompts |
| `Stop` | Agent execution stops | Yes | Yes | Save state, clean up |
| `SubagentStart` | Subagent initializes | Yes | Yes | Track spawning |
| `SubagentStop` | Subagent completes | Yes | Yes | Aggregate results |
| `PreCompact` | Before conversation compaction | Yes | Yes | Archive transcript |
| `PermissionRequest` | Permission dialog shown | Yes | Yes | Custom permission logic |
| `Notification` | Status messages | Yes | Yes | Forward to Slack/Discord |
| `SessionStart` | Session starts | No | Yes | Initialize logging |
| `SessionEnd` | Session ends | No | Yes | Clean up resources |

### 9.2 Register Hooks

```python
from claude_agent_sdk import HookMatcher, ClaudeAgentOptions

async def my_hook(input_data, tool_use_id, context):
    # Your logic here
    return {}

options = ClaudeAgentOptions(
    hooks={
        "PreToolUse": [
            HookMatcher(matcher="Write|Edit", hooks=[my_hook])
        ]
    }
)
```

### 9.3 Hook Callback Signature

```python
async def hook_callback(
    input_data: dict,           # Hook-specific input
    tool_use_id: str | None,    # Correlates Pre/Post tool use
    context: Any                # Reserved for future use
) -> dict:
    # Return dict with hookSpecificOutput and optional top-level fields
    return {}
```

### 9.4 Hook Output

```python
return {
    # Top-level: modify conversation
    "systemMessage": "Additional context for model",
    "continue_": True,  # Continue execution (Python: continue_)

    # Hook-specific output
    "hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",  # "allow", "deny", "ask"
        "permissionDecisionReason": "Security policy",
        "updatedInput": {...},  # Modify tool input
    },

    # Async operation (non-blocking)
    "async_": True,  # Python: async_
    "asyncTimeout": 30000,  # ms
}
```

### 9.5 Common Hook Patterns

#### Block dangerous operations
```python
async def protect_env_files(input_data, tool_use_id, context):
    file_path = input_data.get("tool_input", {}).get("file_path", "")
    if file_path.endswith(".env"):
        return {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": "Cannot modify .env files"
            }
        }
    return {}
```

#### Auto-approve read-only tools
```python
async def auto_approve_read_only(input_data, tool_use_id, context):
    if input_data.get("hook_event_name") != "PreToolUse":
        return {}

    read_only = ["Read", "Glob", "Grep"]
    if input_data.get("tool_name") in read_only:
        return {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "allow"
            }
        }
    return {}
```

#### Log file changes
```python
async def log_writes(input_data, tool_use_id, context):
    if input_data.get("hook_event_name") != "PostToolUse":
        return {}

    if input_data.get("tool_name") in ["Write", "Edit"]:
        file_path = input_data.get("tool_input", {}).get("file_path", "unknown")
        with open("audit.log", "a") as f:
            f.write(f"{datetime.now()}: {file_path}\n")

    return {}
```

#### Forward notifications to Slack
```python
async def slack_notifier(input_data, tool_use_id, context):
    message = input_data.get("message", "")
    try:
        await asyncio.to_thread(
            lambda: requests.post(
                "https://hooks.slack.com/services/YOUR/WEBHOOK/URL",
                json={"text": f"Agent: {message}"}
            )
        )
    except Exception as e:
        print(f"Failed to send notification: {e}")

    return {}
```

### 9.6 Matchers

Filter hooks by tool name or event type:

```python
HookMatcher(
    matcher="Write|Edit",  # Regex: matches tool names
    hooks=[my_hook],
    timeout=60  # seconds
)
```

**Matcher examples:**
- `"Bash"` — only Bash tool
- `"Write|Edit"` — Write OR Edit
- `"^mcp__"` — all MCP tools
- `None` (omit) — all tools

---

## 10. Custom Tools & MCP

Define custom tools as Python functions and expose them to Claude.

### 10.1 Define Custom Tool with @tool Decorator

```python
from claude_agent_sdk import tool

@tool("greet", "Greet a user", {"name": str})
async def greet(args):
    name = args.get("name", "World")
    return {
        "content": [
            {"type": "text", "text": f"Hello, {name}!"}
        ]
    }

@tool("add", "Add two numbers", {"a": float, "b": float})
async def add(args):
    result = args["a"] + args["b"]
    return {
        "content": [
            {"type": "text", "text": f"Result: {result}"}
        ]
    }
```

### 10.2 Create SDK MCP Server

```python
from claude_agent_sdk import create_sdk_mcp_server

server = create_sdk_mcp_server(
    name="math_tools",
    tools=[add, greet]  # List of @tool functions
)
```

### 10.3 Register with Agent

```python
options = ClaudeAgentOptions(
    mcp_servers={"math": server},
    allowed_tools=["mcp__math__add", "mcp__math__greet"]
)

async for message in query(
    prompt="Add 5 and 3, then greet the user",
    options=options
):
    print(message)
```

### 10.4 Tool Output Format

Tools return a dict with `content` key containing tool result blocks:

```python
return {
    "content": [
        {"type": "text", "text": "Result text"},
        {"type": "error", "error": "Error message"},  # Optional error
    ]
}
```

### 10.5 External MCP Servers

Connect to external MCP servers (e.g., Playwright for browser automation):

```python
options = ClaudeAgentOptions(
    mcp_servers={
        "playwright": {
            "command": "npx",
            "args": ["@playwright/mcp@latest"]
        }
    }
)
```

---

## 11. Permissions & Security

Control which tools agents can use.

### 11.1 Allow/Disallow Lists

```python
options = ClaudeAgentOptions(
    allowed_tools=["Read", "Bash", "Glob"],      # Pre-approve
    disallowed_tools=["Write", "Edit", "Delete"]  # Block
)
```

### 11.2 Permission Modes

| Mode | Behavior |
|------|----------|
| `'default'` | Prompt for permission on restricted tools |
| `'acceptEdits'` | Auto-approve file edits |
| `'plan'` | Agent describes plan, waits for approval |
| `'bypassPermissions'` | No prompts (use with caution) |

```python
options = ClaudeAgentOptions(permission_mode="acceptEdits")
```

### 11.3 Custom Permission Function

```python
async def can_use_tool(tool_name, tool_input, context):
    if tool_name == "Bash" and "rm -rf" in tool_input.get("command", ""):
        return PermissionResultDeny(message="Destructive commands blocked")
    return PermissionResultAllow()

options = ClaudeAgentOptions(can_use_tool=can_use_tool)
```

---

## 12. File Checkpointing

Snapshot and revert file changes across sessions.

### Enable & Use

```python
options = ClaudeAgentOptions(
    enable_file_checkpointing=True
)

async for message in query(prompt="...", options=options):
    if hasattr(message, "result"):
        print(message.result)
```

**Files modified during the session can be reverted to prior states without re-running the agent.**

---

## 13. Built-in Tools Reference

All agents have access to these tools by default (unless restricted).

| Tool | Purpose | Example |
|------|---------|---------|
| **Read** | Read file contents | `Read(file_path="/path/to/file.py")` |
| **Write** | Create new file | `Write(file_path="...", content="...")` |
| **Edit** | Modify existing file | `Edit(file_path="...", old_string="...", new_string="...")` |
| **Bash** | Run shell commands | `Bash(command="ls -la")` |
| **Glob** | Find files by pattern | `Glob(pattern="**/*.py")` |
| **Grep** | Search file contents | `Grep(pattern="TODO", glob="**/*.py")` |
| **WebSearch** | Search the web | `WebSearch(query="...")` |
| **WebFetch** | Fetch web page | `WebFetch(url="...", prompt="...")` |
| **Agent** | Invoke subagent | (Invoked via Agent tool, not directly) |
| **AskUserQuestion** | Prompt user | Multiple choice or free-form |
| **Delete** | Remove file/directory | `Delete(path="...")` |

---

## 14. Recent Changes (2026)

### Version History: v0.1.x (March 2026)

- **v0.1.49** (Mar 17, 2026) — Latest
  - Typed hook input structures (TypedDict for IDE autocomplete)
  - `tools` option in `ClaudeAgentOptions` to control base tool set
  - `CLAUDE_AGENT_SDK_SKIP_VERSION_CHECK` env var to disable version check

- **Earlier v0.1.x** (Sep-Oct 2025)
  - Initial SDK release with `query()` and basic tool support
  - `ClaudeSDKClient` for multi-turn conversations
  - Streaming with `include_partial_messages`
  - Session management (resume, fork)
  - Hooks infrastructure
  - Subagent support

### Migration from claude-code-sdk

If updating from deprecated `claude-code-sdk`:

1. Change import: `from claude_agent_sdk import query`
2. Some internal APIs changed; check CHANGELOG.md on GitHub
3. Tool names and options largely compatible

---

## 15. Complete Example: Multi-Turn Research Agent

```python
import asyncio
from claude_agent_sdk import (
    ClaudeSDKClient,
    ClaudeAgentOptions,
    AgentDefinition,
    HookMatcher,
)


async def audit_hook(input_data, tool_use_id, context):
    """Log all tool calls for compliance."""
    if input_data.get("hook_event_name") == "PostToolUse":
        tool = input_data.get("tool_name")
        print(f"[AUDIT] {tool} executed")
    return {}


async def main():
    # Define a security reviewer subagent
    agents = {
        "security-reviewer": AgentDefinition(
            description="Security code reviewer",
            prompt="""Analyze code for vulnerabilities.
Check for SQL injection, XSS, auth flaws.""",
            tools=["Read", "Grep", "Glob"],
            model="opus",
        )
    }

    options = ClaudeAgentOptions(
        system_prompt="You are a code research assistant.",
        model="sonnet",
        allowed_tools=["Read", "Bash", "Glob", "Grep", "WebSearch", "Agent"],
        agents=agents,
        permission_mode="acceptEdits",
        include_partial_messages=True,
        hooks={
            "PostToolUse": [HookMatcher(hooks=[audit_hook])]
        },
        cwd="/home/user/project",
    )

    async with ClaudeSDKClient(options=options) as client:
        # First query: explore codebase
        await client.query("Find all authentication-related files in this project")
        print("=== First Response ===")
        async for message in client.receive_response():
            if hasattr(message, "content"):
                for block in message.content:
                    if hasattr(block, "text"):
                        print(block.text)

        # Second query: leverage prior analysis
        await client.query("Use the security-reviewer agent to audit auth.py")
        print("\n=== Security Review ===")
        async for message in client.receive_response():
            if hasattr(message, "result"):
                print(message.result)

        # Third query: implementation
        await client.query("Fix the vulnerabilities found and commit changes")
        print("\n=== Implementation ===")
        async for message in client.receive_response():
            if hasattr(message, "result"):
                print(message.result)


asyncio.run(main())
```

---

## 16. Error Handling

```python
from claude_agent_sdk import (
    CLINotFoundError,
    ProcessError,
    CLIJSONDecodeError,
)

try:
    async for msg in query(prompt="..."):
        pass
except CLINotFoundError:
    print("Claude Code CLI not installed")
except ProcessError as e:
    print(f"CLI process failed: exit code {e.exit_code}")
except CLIJSONDecodeError:
    print("Failed to parse CLI response")
except Exception as e:
    print(f"Unexpected error: {e}")
```

---

## 17. Performance & Cost Control

### Limit Execution

```python
options = ClaudeAgentOptions(
    max_turns=15,           # Stop after N turns
    max_budget_usd=2.50,    # Stop if cost exceeds $2.50
)
```

### Monitor Cost

```python
if isinstance(message, ResultMessage):
    print(f"Session cost: ${message.total_cost_usd:.4f}")
```

### Streaming for Token Efficiency

```python
options = ClaudeAgentOptions(include_partial_messages=True)
# Yields StreamEvent for incremental progress, reduces token waste
```

---

## 18. Unresolved Questions

1. **Extended thinking limitations:** Documentation states `StreamEvent` is not emitted when `max_thinking_tokens` is set. Has this been addressed in v0.1.49+?

2. **MCP tool typing:** Are there TypedDict definitions for `@tool` decorator arguments in recent versions? The docs mention Zod schemas (TypeScript), but Python's typing story is unclear.

3. **Cross-session file synchronization:** When using multiple sessions in parallel (via multiprocessing), is there built-in file locking/conflict detection, or is it user's responsibility?

4. **Subagent prompt injection risk:** When passing unsanitized user input to subagent via Agent tool prompt, are there guardrails against prompt injection attacks?

5. **Custom permission logic async:** Can `can_use_tool` callable make async API calls (HTTP), or is it synchronous-only?

6. **Session file format stability:** Is `.jsonl` format stable/versioned, or could it break between minor versions?

7. **Hooks timeout behavior:** When a hook times out (PreToolUse returning after timeout), does the tool execute anyway, or is it automatically denied?

8. **Third-party MCP server subprocess management:** When using external MCP servers via `mcp_servers` dict (e.g., Playwright), who manages process lifecycle (start/stop/restart)?

---

## Sources

- [Claude Agent SDK Overview](https://platform.claude.com/docs/en/agent-sdk/overview)
- [Claude Agent SDK Python Reference](https://platform.claude.com/docs/en/agent-sdk/python)
- [Subagents Documentation](https://platform.claude.com/docs/en/agent-sdk/subagents)
- [Hooks Guide](https://platform.claude.com/docs/en/agent-sdk/hooks)
- [Streaming Output](https://platform.claude.com/docs/en/agent-sdk/streaming-output)
- [Session Management](https://platform.claude.com/docs/en/agent-sdk/sessions)
- [GitHub: claude-agent-sdk-python](https://github.com/anthropics/claude-agent-sdk-python)
- [PyPI: claude-agent-sdk](https://pypi.org/project/claude-agent-sdk/)
