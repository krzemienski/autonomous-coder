# Claude Agent SDK for Python -- Complete Primitives Reference

**Date:** 2026-03-21
**SDK Package:** `claude-agent-sdk` (PyPI)
**Python Requirement:** 3.10+
**Repository:** [anthropics/claude-agent-sdk-python](https://github.com/anthropics/claude-agent-sdk-python)

## Sources

| Source | URL |
|--------|-----|
| SDK Overview | https://platform.claude.com/docs/en/agent-sdk/overview |
| Python SDK Reference | https://platform.claude.com/docs/en/agent-sdk/python |
| Hooks Guide | https://platform.claude.com/docs/en/agent-sdk/hooks |
| MCP Integration | https://platform.claude.com/docs/en/agent-sdk/mcp |
| Custom Tools | https://platform.claude.com/docs/en/agent-sdk/custom-tools |
| Subagents | https://platform.claude.com/docs/en/agent-sdk/subagents |
| Sessions | https://platform.claude.com/docs/en/agent-sdk/sessions |
| Permissions | https://platform.claude.com/docs/en/agent-sdk/permissions |
| Agent Loop | https://platform.claude.com/docs/en/agent-sdk/agent-loop |
| User Input | https://platform.claude.com/docs/en/agent-sdk/user-input |
| System Prompts | https://platform.claude.com/docs/en/agent-sdk/modifying-system-prompts |
| Cost Tracking | https://platform.claude.com/docs/en/agent-sdk/cost-tracking |
| Streaming Output | https://platform.claude.com/docs/en/agent-sdk/streaming-output |
| Quickstart | https://platform.claude.com/docs/en/agent-sdk/quickstart |
| Cookbooks | https://github.com/anthropics/anthropic-cookbook (claude_agent_sdk/) |

---

## Table of Contents

1. [Installation & Authentication](#1-installation--authentication)
2. [Core Functions](#2-core-functions)
3. [ClaudeAgentOptions -- Full Parameter Reference](#3-claudeagentoptions----full-parameter-reference)
4. [ClaudeSDKClient -- Stateful Conversation Client](#4-claudesdkclient----stateful-conversation-client)
5. [Message Types & Content Blocks](#5-message-types--content-blocks)
6. [Streaming Events](#6-streaming-events)
7. [Hooks System](#7-hooks-system)
8. [Custom Tools & MCP Integration](#8-custom-tools--mcp-integration)
9. [Subagent / Agent Handoff](#9-subagent--agent-handoff)
10. [Sessions -- Resume, Fork, Continue](#10-sessions----resume-fork-continue)
11. [Permissions & User Input](#11-permissions--user-input)
12. [System Prompt Configuration](#12-system-prompt-configuration)
13. [Cost & Token Tracking](#13-cost--token-tracking)
14. [Error Handling](#14-error-handling)
15. [Transport Layer](#15-transport-layer)
16. [Model Selection](#16-model-selection)
17. [Built-in Tools Reference](#17-built-in-tools-reference)
18. [Structured Output](#18-structured-output)
19. [Complete Import Map](#19-complete-import-map)

---

## 1. Installation & Authentication

```bash
pip install claude-agent-sdk
```

The Claude Code CLI is **bundled** with the package. No separate installation needed.

**Authentication via env vars:**

| Variable | Purpose |
|----------|---------|
| `ANTHROPIC_API_KEY` | Direct Anthropic API key |
| `CLAUDE_CODE_USE_BEDROCK=1` | Use Amazon Bedrock (+ AWS credentials) |
| `CLAUDE_CODE_USE_VERTEX=1` | Use Google Vertex AI (+ GCP credentials) |
| `CLAUDE_CODE_USE_FOUNDRY=1` | Use Microsoft Azure AI Foundry (+ Azure credentials) |

---

## 2. Core Functions

### `query()`

The primary entry point. Creates a new session per call. Returns an async iterator yielding messages.

```python
async def query(
    *,
    prompt: str | AsyncIterable[dict[str, Any]],
    options: ClaudeAgentOptions | None = None,
    transport: Transport | None = None
) -> AsyncIterator[Message]
```

**Parameters:**
- `prompt` -- `str | AsyncIterable[dict]` -- Input prompt or async iterable for streaming input
- `options` -- `ClaudeAgentOptions | None` -- Configuration (defaults to `ClaudeAgentOptions()`)
- `transport` -- `Transport | None` -- Optional custom transport

**Returns:** `AsyncIterator[Message]`

**Additional methods on the returned iterator:**
- `await q.set_permission_mode("acceptEdits")` -- Change permission mode mid-session
- `await q.abort()` -- Abort the current query

```python
import asyncio
from claude_agent_sdk import query, ClaudeAgentOptions

async def main():
    async for message in query(
        prompt="Find and fix the bug in auth.py",
        options=ClaudeAgentOptions(allowed_tools=["Read", "Edit", "Bash"]),
    ):
        print(message)

asyncio.run(main())
```

### `tool()`

Decorator for defining MCP tools with type safety.

```python
def tool(
    name: str,
    description: str,
    input_schema: type | dict[str, Any],
    annotations: ToolAnnotations | None = None
) -> Callable[[Callable[[Any], Awaitable[dict[str, Any]]]], SdkMcpTool[Any]]
```

**Parameters:**
- `name` -- `str` -- Unique identifier
- `description` -- `str` -- Human-readable description
- `input_schema` -- `type | dict[str, Any]` -- Schema (simple type mapping or JSON Schema)
- `annotations` -- `ToolAnnotations | None` -- Optional MCP annotations (e.g., `readOnlyHint`)

**Input schema options:**

```python
# Option 1: Simple type mapping (recommended)
{"name": str, "count": int, "enabled": bool}

# Option 2: JSON Schema format
{
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "count": {"type": "integer", "minimum": 0},
    },
    "required": ["name"],
}
```

```python
from claude_agent_sdk import tool
from typing import Any

@tool("greet", "Greet a user", {"name": str})
async def greet(args: dict[str, Any]) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": f"Hello, {args['name']}!"}]}
```

### `create_sdk_mcp_server()`

Creates an in-process MCP server.

```python
def create_sdk_mcp_server(
    name: str,
    version: str = "1.0.0",
    tools: list[SdkMcpTool[Any]] | None = None
) -> McpSdkServerConfig
```

```python
from claude_agent_sdk import tool, create_sdk_mcp_server

@tool("add", "Add two numbers", {"a": float, "b": float})
async def add(args):
    return {"content": [{"type": "text", "text": f"Sum: {args['a'] + args['b']}"}]}

calculator = create_sdk_mcp_server(name="calculator", version="2.0.0", tools=[add])

options = ClaudeAgentOptions(
    mcp_servers={"calc": calculator},
    allowed_tools=["mcp__calc__add"],
)
```

### `list_sessions()`

Lists past sessions. **Synchronous.**

```python
def list_sessions(
    directory: str | None = None,
    limit: int | None = None,
    include_worktrees: bool = True
) -> list[SDKSessionInfo]
```

**SDKSessionInfo properties:** `session_id`, `summary`, `last_modified`, `file_size`, `custom_title`, `first_prompt`, `git_branch`, `cwd`

### `get_session_messages()`

Retrieves messages from a past session. **Synchronous.**

```python
def get_session_messages(
    session_id: str,
    directory: str | None = None,
    limit: int | None = None,
    offset: int = 0
) -> list[SessionMessage]
```

**SessionMessage properties:** `type` (`"user" | "assistant"`), `uuid`, `session_id`, `message`, `parent_tool_use_id`

---

## 3. ClaudeAgentOptions -- Full Parameter Reference

```python
@dataclass
class ClaudeAgentOptions:
    # Tool control
    tools: list[str] | ToolsPreset | None = None
    allowed_tools: list[str] = field(default_factory=list)
    disallowed_tools: list[str] = field(default_factory=list)

    # Prompting
    system_prompt: str | SystemPromptPreset | None = None

    # MCP
    mcp_servers: dict[str, McpServerConfig] | str | Path = field(default_factory=dict)

    # Permissions
    permission_mode: PermissionMode | None = None
    can_use_tool: CanUseTool | None = None
    permission_prompt_tool_name: str | None = None

    # Sessions
    continue_conversation: bool = False
    resume: str | None = None
    fork_session: bool = False

    # Limits
    max_turns: int | None = None
    max_budget_usd: float | None = None

    # Model
    model: str | None = None
    fallback_model: str | None = None

    # Thinking / Effort
    thinking: ThinkingConfig | None = None
    effort: Literal["low", "medium", "high", "max"] | None = None
    max_thinking_tokens: int | None = None  # Deprecated

    # Hooks
    hooks: dict[HookEvent, list[HookMatcher]] | None = None

    # Subagents
    agents: dict[str, AgentDefinition] | None = None

    # Settings & Environment
    cwd: str | Path | None = None
    cli_path: str | Path | None = None
    settings: str | None = None
    setting_sources: list[SettingSource] | None = None
    add_dirs: list[str | Path] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    extra_args: dict[str, str | None] = field(default_factory=dict)

    # Streaming
    include_partial_messages: bool = False

    # Output
    output_format: dict[str, Any] | None = None

    # Advanced
    betas: list[SdkBeta] = field(default_factory=list)
    plugins: list[SdkPluginConfig] = field(default_factory=list)
    sandbox: SandboxSettings | None = None
    user: str | None = None
    max_buffer_size: int | None = None
    stderr: Callable[[str], None] | None = None
    enable_file_checkpointing: bool = False
```

### Key Type Aliases

```python
PermissionMode = Literal["default", "acceptEdits", "bypassPermissions", "plan"]
# Note: "dontAsk" is TypeScript-only

SettingSource = Literal["user", "project", "local"]
# "user"    -> ~/.claude/CLAUDE.md, ~/.claude/settings.json
# "project" -> CLAUDE.md, .claude/settings.json, .claude/skills/, .claude/agents/
# "local"   -> .claude/settings.local.json

HookEvent = Literal[
    "PreToolUse", "PostToolUse", "PostToolUseFailure",
    "UserPromptSubmit", "Stop",
    "SubagentStart", "SubagentStop",
    "PreCompact", "PermissionRequest", "Notification"
]
# SessionStart, SessionEnd are TypeScript-only for SDK callbacks
# (Python supports them only via shell command hooks in settings files)
```

---

## 4. ClaudeSDKClient -- Stateful Conversation Client

Maintains a session across multiple exchanges. Handles session IDs internally.

```python
class ClaudeSDKClient:
    def __init__(
        self,
        options: ClaudeAgentOptions | None = None,
        transport: Transport | None = None
    )

    # Lifecycle
    async def connect(self, prompt: str | AsyncIterable[dict] | None = None) -> None
    async def disconnect(self) -> None

    # Querying
    async def query(self, prompt: str | AsyncIterable[dict], session_id: str = "default") -> None
    async def receive_messages(self) -> AsyncIterator[Message]
    async def receive_response(self) -> AsyncIterator[Message]
    async def interrupt(self) -> None

    # Runtime configuration
    async def set_permission_mode(self, mode: str) -> None
    async def set_model(self, model: str | None = None) -> None

    # File operations
    async def rewind_files(self, user_message_id: str) -> None

    # MCP management
    async def get_mcp_status(self) -> list[McpServerStatus]
    async def add_mcp_server(self, name: str, config: McpServerConfig) -> None
    async def remove_mcp_server(self, name: str) -> None

    # Info
    async def get_server_info(self) -> dict[str, Any] | None
```

**Context manager pattern (recommended):**

```python
async with ClaudeSDKClient(options=options) as client:
    await client.query("First message")
    async for msg in client.receive_response():
        print(msg)

    # Second query -- same session, full context preserved
    await client.query("Follow-up message")
    async for msg in client.receive_response():
        print(msg)
```

**Key differences from `query()`:**

| Feature | `query()` | `ClaudeSDKClient` |
|---------|-----------|-------------------|
| Session management | Manual (capture session_id) | Automatic |
| Multi-turn | Via `resume` option | Built-in (`query()` reuses session) |
| Interrupts | Not supported | `await client.interrupt()` |
| Runtime model change | Not supported | `await client.set_model("haiku")` |
| MCP hot-swap | Not supported | `add_mcp_server()` / `remove_mcp_server()` |
| Streaming input | Via async iterable prompt | Via async iterable prompt |

---

## 5. Message Types & Content Blocks

### Message Types

```python
from claude_agent_sdk import (
    SystemMessage,      # Session lifecycle events
    AssistantMessage,   # Claude's responses (text + tool calls)
    UserMessage,        # Tool results sent back to Claude
    ResultMessage,      # Final message -- always last
)
from claude_agent_sdk.types import StreamEvent  # Raw streaming events
```

| Type | `type` field | When emitted | Key fields |
|------|-------------|--------------|------------|
| `SystemMessage` | `"system"` | Session init, compaction | `subtype` ("init", "compact_boundary"), `data`, `session_id` (in data) |
| `AssistantMessage` | `"assistant"` | After each Claude response | `content` (list of blocks), `parent_tool_use_id` |
| `UserMessage` | `"user"` | After tool execution | `content` (tool results) |
| `ResultMessage` | `"result"` | Always last | `subtype`, `result`, `session_id`, `total_cost_usd`, `usage`, `num_turns`, `stop_reason` |
| `StreamEvent` | N/A (dataclass) | When `include_partial_messages=True` | `event` (raw API event dict), `uuid`, `session_id`, `parent_tool_use_id` |

### ResultMessage Subtypes

| Subtype | Meaning | `result` field? |
|---------|---------|:---------------:|
| `"success"` | Task completed normally | Yes |
| `"error_max_turns"` | Hit `max_turns` limit | No |
| `"error_max_budget_usd"` | Hit `max_budget_usd` limit | No |
| `"error_during_execution"` | API failure or cancelled | No |
| `"error_max_structured_output_retries"` | Structured output validation failed | No |

All result subtypes carry: `total_cost_usd`, `usage`, `num_turns`, `session_id`, `stop_reason`.

### Content Blocks

```python
from claude_agent_sdk import TextBlock, ToolUseBlock, ToolResultBlock

# In an AssistantMessage:
for block in message.content:
    if isinstance(block, TextBlock):
        print(block.text)
    elif isinstance(block, ToolUseBlock):
        print(f"Tool: {block.name}, ID: {block.id}, Input: {block.input}")
```

---

## 6. Streaming Events

Enable with `include_partial_messages=True`.

```python
from claude_agent_sdk import query, ClaudeAgentOptions
from claude_agent_sdk.types import StreamEvent

async for message in query(
    prompt="Explain databases",
    options=ClaudeAgentOptions(include_partial_messages=True),
):
    if isinstance(message, StreamEvent):
        event = message.event
        event_type = event.get("type")

        if event_type == "content_block_delta":
            delta = event.get("delta", {})
            if delta.get("type") == "text_delta":
                print(delta.get("text", ""), end="", flush=True)
            elif delta.get("type") == "input_json_delta":
                print(delta.get("partial_json", ""), end="")
```

### StreamEvent Structure

```python
@dataclass
class StreamEvent:
    uuid: str
    session_id: str
    event: dict[str, Any]  # Raw Claude API stream event
    parent_tool_use_id: str | None
```

### Event Flow

```
StreamEvent (message_start)
StreamEvent (content_block_start)  -- text or tool_use block
StreamEvent (content_block_delta)  -- text chunks or input_json chunks
StreamEvent (content_block_stop)
StreamEvent (message_delta)        -- stop_reason, usage
StreamEvent (message_stop)
AssistantMessage                   -- complete message with all content
... tool executes ...
... more streaming events for next turn ...
ResultMessage                      -- final result
```

### Event Types from Claude API

| Event Type | Description |
|:-----------|:------------|
| `message_start` | Start of a new message |
| `content_block_start` | Start of text or tool_use block |
| `content_block_delta` | Incremental text (`text_delta`) or tool input (`input_json_delta`) |
| `content_block_stop` | End of a content block |
| `message_delta` | Message-level updates (stop_reason, usage) |
| `message_stop` | End of the message |

**Limitation:** `StreamEvent` is NOT emitted when `max_thinking_tokens` / `thinking` is enabled.

---

## 7. Hooks System

Hooks are callback functions that fire at specific agent lifecycle points.

### Available Hook Events (Python)

| Hook Event | Trigger | Can block? | Key input fields |
|:-----------|:--------|:-----------|:-----------------|
| `PreToolUse` | Before tool executes | Yes (deny/allow/ask) | `tool_name`, `tool_input`, `agent_id`, `agent_type` |
| `PostToolUse` | After tool returns | No (add context only) | `tool_name`, `tool_input`, `tool_result`, `agent_id` |
| `PostToolUseFailure` | After tool fails | No | `tool_name`, `tool_input`, `error` |
| `UserPromptSubmit` | User prompt submitted | No (inject context) | `prompt` |
| `Stop` | Agent execution ends | No (save state) | `reason` |
| `SubagentStart` | Subagent spawns | No | `agent_id`, `agent_type` |
| `SubagentStop` | Subagent completes | No | `agent_id`, `agent_transcript_path`, `stop_hook_active` |
| `PreCompact` | Before context compaction | No | `trigger` ("manual" or "auto") |
| `PermissionRequest` | Permission dialog would show | No | Permission details |
| `Notification` | Agent status messages | No | `message`, `title` |

**Not available in Python SDK callbacks:** `SessionStart`, `SessionEnd`, `Setup`, `TeammateIdle`, `TaskCompleted`, `ConfigChange`, `WorktreeCreate`, `WorktreeRemove` (these are TypeScript-only).

### Hook Configuration

```python
from claude_agent_sdk import ClaudeAgentOptions, HookMatcher

options = ClaudeAgentOptions(
    hooks={
        "PreToolUse": [
            HookMatcher(matcher="Write|Edit", hooks=[protect_env_files]),
            HookMatcher(matcher="Bash", hooks=[validate_commands]),
            HookMatcher(hooks=[global_logger]),  # No matcher = all tools
        ],
        "PostToolUse": [
            HookMatcher(hooks=[audit_logger]),
        ],
        "SubagentStop": [
            HookMatcher(hooks=[subagent_tracker]),
        ],
    }
)
```

### HookMatcher

| Field | Type | Default | Description |
|:------|:-----|:--------|:------------|
| `matcher` | `str \| None` | `None` | Regex pattern matched against tool name (or event filter field) |
| `hooks` | `list[HookCallback]` | Required | Array of callback functions |
| `timeout` | `int` | `60` | Timeout in seconds |

### Hook Callback Signature

```python
async def my_hook(
    input_data: dict[str, Any],    # Event-specific data
    tool_use_id: str | None,       # Correlates PreToolUse/PostToolUse
    context: Any                    # Reserved for future use
) -> dict[str, Any]:
    ...
```

### All Hook Input Fields

**Shared across all hooks:** `session_id`, `cwd`, `hook_event_name`

**PreToolUse/PostToolUse/PostToolUseFailure additionally include:** `agent_id`, `agent_type` (populated when inside a subagent)

### Hook Output Format

```python
return {
    # Top-level: control the conversation
    "systemMessage": "Injected context visible to Claude",  # Optional
    "continue_": True,  # Whether agent keeps running (use continue_ in Python)

    # hookSpecificOutput: control the current operation
    "hookSpecificOutput": {
        "hookEventName": "PreToolUse",

        # For PreToolUse:
        "permissionDecision": "allow" | "deny" | "ask",
        "permissionDecisionReason": "Why this decision",
        "updatedInput": { ... },  # Modified tool input (requires allow)

        # For PostToolUse:
        "additionalContext": "Extra info appended to tool result",
    }
}

# Or return empty to allow without changes:
return {}
```

### Async (Non-blocking) Hook Output

```python
async def async_hook(input_data, tool_use_id, context):
    asyncio.create_task(send_to_logging_service(input_data))
    return {"async_": True, "asyncTimeout": 30000}
```

### Priority Rules

When multiple hooks apply: **deny > ask > allow**. If any hook returns `deny`, the tool is blocked.

### Complete PreToolUse Example

```python
async def protect_env_files(input_data, tool_use_id, context):
    file_path = input_data["tool_input"].get("file_path", "")
    if file_path.split("/")[-1] == ".env":
        return {
            "systemMessage": "Remember: .env files are protected.",
            "hookSpecificOutput": {
                "hookEventName": input_data["hook_event_name"],
                "permissionDecision": "deny",
                "permissionDecisionReason": "Cannot modify .env files",
            },
        }
    return {}

async def redirect_to_sandbox(input_data, tool_use_id, context):
    if input_data["tool_name"] == "Write":
        original_path = input_data["tool_input"].get("file_path", "")
        return {
            "hookSpecificOutput": {
                "hookEventName": input_data["hook_event_name"],
                "permissionDecision": "allow",
                "updatedInput": {
                    **input_data["tool_input"],
                    "file_path": f"/sandbox{original_path}",
                },
            }
        }
    return {}
```

---

## 8. Custom Tools & MCP Integration

### In-Process MCP Server (Custom Tools)

```python
from claude_agent_sdk import tool, create_sdk_mcp_server, ClaudeSDKClient, ClaudeAgentOptions
from typing import Any
import aiohttp

@tool(
    "get_weather",
    "Get current temperature for a location",
    {"latitude": float, "longitude": float},
)
async def get_weather(args: dict[str, Any]) -> dict[str, Any]:
    async with aiohttp.ClientSession() as session:
        async with session.get(
            f"https://api.open-meteo.com/v1/forecast?latitude={args['latitude']}&longitude={args['longitude']}&current=temperature_2m"
        ) as response:
            data = await response.json()
    return {
        "content": [{"type": "text", "text": f"Temp: {data['current']['temperature_2m']}"}]
    }

server = create_sdk_mcp_server(name="weather", version="1.0.0", tools=[get_weather])

options = ClaudeAgentOptions(
    mcp_servers={"weather": server},
    allowed_tools=["mcp__weather__get_weather"],
)
```

### Tool Return Format

All custom tools must return:

```python
{
    "content": [
        {"type": "text", "text": "Result string here"}
    ]
}
```

### SdkMcpTool Dataclass

```python
@dataclass
class SdkMcpTool(Generic[T]):
    name: str
    description: str
    input_schema: type[T] | dict[str, Any]
    handler: Callable[[T], Awaitable[dict[str, Any]]]
    annotations: ToolAnnotations | None = None
    # annotations.readOnlyHint = True enables parallel execution
```

### External MCP Servers

**stdio (local process):**

```python
options = ClaudeAgentOptions(
    mcp_servers={
        "github": {
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-github"],
            "env": {"GITHUB_TOKEN": os.environ["GITHUB_TOKEN"]},
        }
    },
    allowed_tools=["mcp__github__list_issues"],
)
```

**HTTP/SSE (remote):**

```python
options = ClaudeAgentOptions(
    mcp_servers={
        "remote-api": {
            "type": "sse",  # or "http" for non-streaming
            "url": "https://api.example.com/mcp/sse",
            "headers": {"Authorization": f"Bearer {os.environ['API_TOKEN']}"},
        }
    },
    allowed_tools=["mcp__remote-api__*"],
)
```

### MCP Tool Naming Convention

Pattern: `mcp__<server-name>__<tool-name>`

Wildcards supported: `mcp__github__*` allows all tools from github server.

### MCP Tool Search

Auto mode (default) activates when tool descriptions exceed 10% of context window.

```python
options = ClaudeAgentOptions(
    mcp_servers={...},
    env={"ENABLE_TOOL_SEARCH": "auto:5"},  # Enable at 5% threshold
)
```

Values: `"auto"` (default, 10%), `"auto:N"` (custom %), `"true"`, `"false"`

### Mixed Server Support

```python
options = ClaudeAgentOptions(
    mcp_servers={
        "internal": sdk_server,           # In-process
        "external": {                     # External subprocess
            "type": "stdio",
            "command": "external-server",
        },
        "remote": {                       # Remote HTTP
            "type": "http",
            "url": "https://api.example.com/mcp",
        },
    }
)
```

### .mcp.json File (Auto-loaded)

```json
{
  "mcpServers": {
    "filesystem": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/path"]
    }
  }
}
```

---

## 9. Subagent / Agent Handoff

### AgentDefinition

```python
from claude_agent_sdk import AgentDefinition

agents = {
    "code-reviewer": AgentDefinition(
        description="Expert code reviewer for quality and security reviews.",
        prompt="Analyze code quality and suggest improvements.",
        tools=["Read", "Glob", "Grep"],  # Read-only subset
        model="sonnet",                   # Per-agent model override
    ),
    "test-runner": AgentDefinition(
        description="Runs and analyzes test suites.",
        prompt="Run tests and provide clear analysis of results.",
        tools=["Bash", "Read", "Grep"],  # Has Bash access
    ),
}
```

| Field | Type | Required | Description |
|:------|:-----|:---------|:------------|
| `description` | `str` | Yes | Tells Claude when to use this agent |
| `prompt` | `str` | Yes | System prompt for the subagent |
| `tools` | `list[str]` | No | Allowed tools (omit = inherit all) |
| `model` | `"sonnet" \| "opus" \| "haiku" \| "inherit"` | No | Model override |

### Using Subagents

```python
options = ClaudeAgentOptions(
    allowed_tools=["Read", "Glob", "Grep", "Agent"],  # "Agent" tool required!
    agents=agents,
)
```

**Invocation:** Claude decides automatically based on `description`, or force via prompt: `"Use the code-reviewer agent to..."`

### What Subagents Inherit

| Receives | Does NOT receive |
|:---------|:----------------|
| Its own system prompt (`AgentDefinition.prompt`) | Parent's conversation history |
| Agent tool's prompt string | Parent's system prompt |
| Project CLAUDE.md (if settingSources enabled) | Skills (unless explicitly listed) |
| Tool definitions (from `tools` field or inherited) | Parent's tool results |

### Key Constraints

- Subagents **cannot** spawn their own subagents (no `Agent` in subagent `tools`)
- Parent receives subagent's final message as the Agent tool result
- Messages from within a subagent include `parent_tool_use_id`

### Detecting Subagent Invocation

```python
if hasattr(message, "content") and message.content:
    for block in message.content:
        if getattr(block, "type", None) == "tool_use" and block.name in ("Task", "Agent"):
            print(f"Subagent invoked: {block.input.get('subagent_type')}")

if hasattr(message, "parent_tool_use_id") and message.parent_tool_use_id:
    print("  (running inside subagent)")
```

Note: Tool name was renamed from `"Task"` to `"Agent"` in Claude Code v2.1.63. Check both for compatibility.

### Dynamic Agent Factory

```python
def create_security_agent(security_level: str) -> AgentDefinition:
    is_strict = security_level == "strict"
    return AgentDefinition(
        description="Security code reviewer",
        prompt=f"You are a {'strict' if is_strict else 'balanced'} security reviewer...",
        tools=["Read", "Grep", "Glob"],
        model="opus" if is_strict else "sonnet",
    )
```

### Resuming Subagents

Subagents can be resumed by capturing `session_id` and `agent_id` from the first run, then passing `resume=session_id` with the agent ID in the prompt.

---

## 10. Sessions -- Resume, Fork, Continue

### Session Approaches

| Approach | When to use | How |
|:---------|:-----------|:----|
| One-shot | Single prompt, no follow-up | Single `query()` call |
| `ClaudeSDKClient` | Multi-turn in one process | Client tracks session |
| `continue_conversation=True` | Resume most recent session | No ID needed |
| `resume=session_id` | Resume specific session | Track session ID |
| `fork_session=True` | Try alternative approach | Branch without losing original |

### Capturing Session ID

```python
from claude_agent_sdk import query, ClaudeAgentOptions, ResultMessage

session_id = None
async for message in query(prompt="Analyze the auth module", options=options):
    if isinstance(message, ResultMessage):
        session_id = message.session_id
        if message.subtype == "success":
            print(message.result)
```

### Resume by ID

```python
async for message in query(
    prompt="Now implement the refactoring you suggested",
    options=ClaudeAgentOptions(resume=session_id, allowed_tools=["Read", "Edit"]),
):
    ...
```

### Fork to Explore Alternatives

```python
async for message in query(
    prompt="Try OAuth2 instead",
    options=ClaudeAgentOptions(resume=session_id, fork_session=True),
):
    if isinstance(message, ResultMessage):
        forked_id = message.session_id  # New session ID
```

### Continue Most Recent

```python
options = ClaudeAgentOptions(continue_conversation=True)
```

### Session Storage

Sessions stored at: `~/.claude/projects/<encoded-cwd>/<session-id>.jsonl`

---

## 11. Permissions & User Input

### Permission Evaluation Order

1. **Hooks** -- can allow, deny, or continue
2. **Deny rules** (`disallowed_tools`) -- always blocks, even in bypassPermissions
3. **Permission mode** -- global policy
4. **Allow rules** (`allowed_tools`) -- auto-approve listed tools
5. **`can_use_tool` callback** -- runtime approval

### Permission Modes

| Mode | Behavior |
|:-----|:---------|
| `"default"` | Unmatched tools trigger `can_use_tool` callback |
| `"acceptEdits"` | Auto-approve file edits (`Edit`, `Write`, `mkdir`, `rm`, `mv`, `cp`) |
| `"bypassPermissions"` | All tools run without prompts (USE WITH CAUTION) |
| `"plan"` | No tool execution; Claude creates a plan only |

Note: `"dontAsk"` is TypeScript-only.

### can_use_tool Callback

```python
from claude_agent_sdk.types import (
    PermissionResultAllow,
    PermissionResultDeny,
    ToolPermissionContext,
)

async def can_use_tool(
    tool_name: str,
    input_data: dict,
    context: ToolPermissionContext,
) -> PermissionResultAllow | PermissionResultDeny:
    if tool_name == "AskUserQuestion":
        return await handle_clarifying_questions(input_data)

    if tool_name == "Bash" and "rm" in input_data.get("command", ""):
        return PermissionResultDeny(message="Delete not allowed")

    return PermissionResultAllow(updated_input=input_data)
```

**Important Python workaround:** `can_use_tool` requires streaming mode and a `PreToolUse` hook that returns `{"continue_": True}`:

```python
async def dummy_hook(input_data, tool_use_id, context):
    return {"continue_": True}

options = ClaudeAgentOptions(
    can_use_tool=can_use_tool,
    hooks={"PreToolUse": [HookMatcher(matcher=None, hooks=[dummy_hook])]},
)
```

### AskUserQuestion Tool

When Claude needs clarification, it calls `AskUserQuestion`. Input structure:

```python
{
    "questions": [
        {
            "question": "How should I format the output?",
            "header": "Format",
            "options": [
                {"label": "Summary", "description": "Brief overview"},
                {"label": "Detailed", "description": "Full explanation"},
            ],
            "multiSelect": False,
        }
    ]
}
```

Return format:

```python
return PermissionResultAllow(
    updated_input={
        "questions": input_data.get("questions", []),
        "answers": {
            "How should I format the output?": "Summary",
        },
    }
)
```

---

## 12. System Prompt Configuration

### Option 1: Custom String (Replaces Default)

```python
options = ClaudeAgentOptions(
    system_prompt="You are a Python coding specialist. Always use type hints."
)
```

### Option 2: Claude Code Preset

```python
options = ClaudeAgentOptions(
    system_prompt={"type": "preset", "preset": "claude_code"}
)
```

### Option 3: Preset + Append

```python
options = ClaudeAgentOptions(
    system_prompt={
        "type": "preset",
        "preset": "claude_code",
        "append": "Always include docstrings and type hints in Python code.",
    }
)
```

### Option 4: CLAUDE.md (Project-Level)

Requires `setting_sources=["project"]` to load. File at `CLAUDE.md` or `.claude/CLAUDE.md`.

```python
options = ClaudeAgentOptions(
    system_prompt={"type": "preset", "preset": "claude_code"},
    setting_sources=["project"],  # Required to load CLAUDE.md
)
```

### SystemPromptPreset Type

```python
class SystemPromptPreset(TypedDict):
    type: Literal["preset"]
    preset: Literal["claude_code"]
    append: NotRequired[str]
```

**Note:** The SDK uses a **minimal system prompt** by default. It contains only essential tool instructions but omits Claude Code's coding guidelines, response style, and project context. You must explicitly request `preset: "claude_code"` for the full prompt.

---

## 13. Cost & Token Tracking

### ResultMessage Cost Fields

```python
if isinstance(message, ResultMessage):
    print(f"Cost: ${message.total_cost_usd}")  # May be None on error paths
    print(f"Turns: {message.num_turns}")
    print(f"Session: {message.session_id}")
    print(f"Stop reason: {message.stop_reason}")

    # Usage dict
    usage = message.usage or {}
    print(f"Input tokens: {usage.get('input_tokens', 0)}")
    print(f"Output tokens: {usage.get('output_tokens', 0)}")
    print(f"Cache read: {usage.get('cache_read_input_tokens', 0)}")
    print(f"Cache creation: {usage.get('cache_creation_input_tokens', 0)}")
```

### Accumulate Across Calls

```python
total_spend = 0.0
for prompt in prompts:
    async for message in query(prompt=prompt):
        if isinstance(message, ResultMessage):
            total_spend += message.total_cost_usd or 0
print(f"Total: ${total_spend:.4f}")
```

### Python Limitations

- Per-step token breakdowns are NOT available on individual `AssistantMessage` objects
- Per-model breakdowns (`modelUsage`) are TypeScript-only
- `total_cost_usd` and `usage` may be `None` on some error paths

---

## 14. Error Handling

### Error Classes

```python
from claude_agent_sdk import (
    ClaudeSDKError,        # Base error class
    CLINotFoundError,      # Claude Code CLI not found
    CLIConnectionError,    # Connection issues
    ProcessError,          # Process failed (has .exit_code)
    CLIJSONDecodeError,    # JSON parsing failure
)
```

### Error Handling Pattern

```python
try:
    async for message in query(prompt="Hello"):
        if isinstance(message, ResultMessage):
            if message.subtype == "success":
                print(message.result)
            elif message.subtype == "error_max_turns":
                print(f"Hit turn limit. Resume: {message.session_id}")
            elif message.subtype == "error_max_budget_usd":
                print("Hit budget limit.")
            elif message.subtype == "error_during_execution":
                print("Execution error")
except CLINotFoundError:
    print("Install Claude Code CLI")
except ProcessError as e:
    print(f"Process failed: exit code {e.exit_code}")
except CLIJSONDecodeError:
    print("JSON parsing failed")
```

### MCP Server Connection Errors

```python
if isinstance(message, SystemMessage) and message.subtype == "init":
    failed = [
        s for s in message.data.get("mcp_servers", [])
        if s.get("status") != "connected"
    ]
    if failed:
        print(f"Failed MCP servers: {failed}")
```

---

## 15. Transport Layer

Custom transport for non-standard communication.

```python
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import Any

class Transport(ABC):
    @abstractmethod
    async def connect(self) -> None: ...

    @abstractmethod
    async def write(self, data: str) -> None: ...

    @abstractmethod
    def read_messages(self) -> AsyncIterator[dict[str, Any]]: ...

    @abstractmethod
    async def close(self) -> None: ...

    @abstractmethod
    def is_ready(self) -> bool: ...

    @abstractmethod
    async def end_input(self) -> None: ...
```

---

## 16. Model Selection

### At Options Level

```python
options = ClaudeAgentOptions(
    model="claude-sonnet-4-6",       # Pin a specific model
    fallback_model="claude-haiku-3-5",  # Fallback if primary fails
)
```

### Per-Subagent

```python
AgentDefinition(
    description="...",
    prompt="...",
    model="sonnet",  # "sonnet" | "opus" | "haiku" | "inherit"
)
```

### Runtime Change (ClaudeSDKClient only)

```python
await client.set_model("claude-haiku-3-5")  # Change mid-session
await client.set_model(None)                  # Reset to default
```

### Effort Level

```python
options = ClaudeAgentOptions(
    effort="high",  # "low" | "medium" | "high" | "max"
)
```

| Level | Behavior | Use for |
|:------|:---------|:--------|
| `"low"` | Minimal reasoning | File lookups, listing |
| `"medium"` | Balanced | Routine edits |
| `"high"` | Thorough | Refactors, debugging |
| `"max"` | Maximum depth | Multi-step analysis |

### Extended Thinking

```python
options = ClaudeAgentOptions(
    thinking={"type": "enabled", "budget_tokens": 10000}
)
# Note: disables StreamEvent emission
```

---

## 17. Built-in Tools Reference

| Tool | Category | What it does |
|:-----|:---------|:-------------|
| `Read` | File ops | Read any file in working directory |
| `Write` | File ops | Create new files |
| `Edit` | File ops | Make precise edits to existing files |
| `Bash` | Execution | Run shell commands, scripts, git |
| `Glob` | Search | Find files by pattern |
| `Grep` | Search | Search file contents with regex |
| `WebSearch` | Web | Search the web |
| `WebFetch` | Web | Fetch and parse web pages |
| `Agent` | Orchestration | Spawn subagents |
| `Skill` | Orchestration | Invoke skills |
| `AskUserQuestion` | Orchestration | Ask user clarifying questions |
| `TodoWrite` | Orchestration | Track tasks |
| `ToolSearch` | Discovery | Dynamically find/load tools on-demand |

### Tool Scoping

```python
allowed_tools=[
    "Read",
    "Bash(npm:*)",          # Only npm commands
    "mcp__github__*",       # All GitHub MCP tools
    "mcp__db__query",       # Only query from db server
]
```

---

## 18. Structured Output

```python
options = ClaudeAgentOptions(
    output_format={
        "type": "json_schema",
        "schema": {
            "type": "object",
            "properties": {
                "summary": {"type": "string"},
                "score": {"type": "integer"},
            },
            "required": ["summary", "score"],
        },
    }
)
```

Result appears in `ResultMessage.structured_output` (not streamed as deltas).

---

## 19. Complete Import Map

```python
# Core functions
from claude_agent_sdk import query
from claude_agent_sdk import ClaudeSDKClient
from claude_agent_sdk import ClaudeAgentOptions

# Tool creation
from claude_agent_sdk import tool
from claude_agent_sdk import create_sdk_mcp_server

# Session management
from claude_agent_sdk import list_sessions
from claude_agent_sdk import get_session_messages

# Subagent definition
from claude_agent_sdk import AgentDefinition

# Hook configuration
from claude_agent_sdk import HookMatcher

# Message types
from claude_agent_sdk import AssistantMessage
from claude_agent_sdk import UserMessage
from claude_agent_sdk import SystemMessage
from claude_agent_sdk import ResultMessage

# Content blocks
from claude_agent_sdk import TextBlock
from claude_agent_sdk import ToolUseBlock
from claude_agent_sdk import ToolResultBlock

# Streaming
from claude_agent_sdk.types import StreamEvent

# Permission types
from claude_agent_sdk.types import PermissionResultAllow
from claude_agent_sdk.types import PermissionResultDeny
from claude_agent_sdk.types import ToolPermissionContext

# Error classes
from claude_agent_sdk import ClaudeSDKError
from claude_agent_sdk import CLINotFoundError
from claude_agent_sdk import CLIConnectionError
from claude_agent_sdk import ProcessError
from claude_agent_sdk import CLIJSONDecodeError
```

---

## Appendix A: Cookbook Examples Summary

From [anthropic-cookbook/claude_agent_sdk](https://github.com/anthropics/anthropic-cookbook):

| Notebook | Agent Type | Key SDK Features |
|:---------|:-----------|:-----------------|
| 00 | One-Liner Research Agent | `query()`, WebSearch, Read, `ClaudeSDKClient`, system prompts |
| 01 | Chief of Staff Agent | CLAUDE.md, plan mode, slash commands, hooks, subagent orchestration, Bash |
| 02 | Observability Agent | Git MCP, GitHub MCP (100+ tools), CI/CD analysis |
| 03 | Site Reliability Agent | Custom MCP tool server (12+ tools), PreToolUse safety hooks, read-write remediation |
| 04 | Migration from OpenAI Agents SDK | Side-by-side comparison |

---

## Appendix B: Architecture Notes for Redesign

### Key Patterns

1. **`query()` is the fundamental primitive** -- everything flows through async iteration
2. **Hooks are the control plane** -- PreToolUse for guardrails, PostToolUse for observability
3. **MCP is the extension mechanism** -- both in-process (`create_sdk_mcp_server`) and external (stdio/HTTP)
4. **Subagents provide context isolation** -- fresh context window, only final result returns to parent
5. **Sessions are persistent** -- stored as JSONL, resume/fork/continue supported
6. **ClaudeSDKClient wraps query() for statefulness** -- tracks session, supports interrupts

### Parallelism Model

- Read-only tools run concurrently within a turn
- State-mutating tools run sequentially
- Custom tools default to sequential; set `readOnlyHint` in annotations for parallel
- Multiple subagents can run concurrently

### Context Window Management

- System prompt + tool definitions + CLAUDE.md + conversation history all accumulate
- Automatic compaction when approaching limit (emits `compact_boundary`)
- Subagents start fresh (key strategy for long-running agents)
- `PreCompact` hook for archiving before summarization

### Permission Flow (Python-specific)

```
Hook PreToolUse → disallowed_tools → permission_mode → allowed_tools → can_use_tool callback
```

`bypassPermissions` still respects `disallowed_tools` and hooks.
