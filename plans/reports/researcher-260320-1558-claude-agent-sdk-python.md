# Claude Agent SDK for Python — Comprehensive Documentation Research

**Date:** 2026-03-20 15:58 UTC
**Scope:** Official Claude Agent SDK for Python (claude-agent-sdk)
**Focus:** Package info, core API, streaming, authentication, and SDK differences

---

## 1. Package Information & Installation

### Official Package Name
- **PyPI Package:** `claude-agent-sdk`
- **Current Version:** 0.1.49 (released 2026-03-17)
- **Python Support:** 3.10–3.13
- **License:** MIT
- **Status:** Alpha development

### Installation Methods

**Standard pip:**
```bash
pip install claude-agent-sdk
```

**Using uv (recommended fast installer):**
```bash
uv init && uv add claude-agent-sdk
```

**Virtual environment setup:**
```bash
python3 -m venv .venv && source .venv/bin/activate
pip3 install claude-agent-sdk
```

### Key Dependencies
- Claude Code CLI is **automatically bundled** — no separate installation required
- Python >=3.10
- Async runtime (asyncio, anyio, or similar)

**Note:** This is fundamentally different from the `anthropic` package (Client SDK). The Agent SDK includes built-in tool execution; the Client SDK requires you to implement the agent loop manually.

---

## 2. Core API Surface

### Primary Entry Points

#### 1. `query()` Function — One-Off Tasks
Simplest interface for single interactions. Creates new session each call.

```python
async def query(
    prompt: str | AsyncIterable[dict],
    options: ClaudeAgentOptions | None = None,
    transport: Transport | None = None
) -> AsyncIterator[Message]
```

**Use cases:**
- Independent tasks, CI/CD pipelines, serverless functions
- No session persistence needed
- Stateless agents

**Example:**
```python
import asyncio
from claude_agent_sdk import query, ClaudeAgentOptions

async def main():
    async for message in query(
        prompt="Find and fix bugs in auth.py",
        options=ClaudeAgentOptions(allowed_tools=["Read", "Edit", "Bash"])
    ):
        print(message)

asyncio.run(main())
```

#### 2. `ClaudeSDKClient` Class — Interactive Sessions
Stateful client for multi-turn conversations. Maintains context across exchanges.

```python
async with ClaudeSDKClient(options=options) as client:
    await client.query(prompt_or_generator)
    async for message in client.receive_response():
        # Process message with full session context retained
        pass
```

**Use cases:**
- Interactive applications, chat interfaces
- Multi-turn conversations
- Following up on previous context
- Interrupts and model switching

**Key methods:**
- `query()` — Send prompt/message generator
- `receive_response()` — Iterate over messages
- `receive_messages()` — All messages including internal
- Context survives across multiple `query()` calls

### Message Types & Content Blocks

**Message Types:**
- `UserMessage` — User input/prompt
- `SystemMessage` — Session initialization
- `AssistantMessage` — Claude response with content
- `ResultMessage` — Final result (cost, tokens, subtype)
- `StreamEvent` — Raw API events (only with `include_partial_messages=True`)
- `CompactBoundaryMessage` — Conversation history compaction

**Content Block Types:**
- `TextBlock` — Text content
- `ToolUseBlock` — Tool invocation (name, input)
- `ToolResultBlock` — Tool execution results
- `ImageBlock` — Image content (streaming input mode)

---

## 3. Creating and Running Agents

### Method 1: Query with Options (Simple)
```python
async for message in query(
    prompt="Review utils.py for bugs",
    options=ClaudeAgentOptions(
        allowed_tools=["Read", "Edit", "Glob"],
        permission_mode="acceptEdits",
        system_prompt="You are a code expert"
    )
):
    pass
```

### Method 2: Programmatic Agent Definitions
Define custom subagents with specialized instructions:

```python
from claude_agent_sdk import ClaudeAgentOptions, AgentDefinition

agents = {
    "code_reviewer": AgentDefinition(
        description="Reviews Python code for quality",
        prompt="You are a code review expert...",
        tools=["Read", "Grep"],
        model="sonnet"  # Optional: sonnet, opus, haiku, or inherit
    ),
    "test_writer": AgentDefinition(
        description="Writes comprehensive test suites",
        prompt="You are a testing expert...",
        tools=["Read", "Write", "Bash"]
    )
}

options = ClaudeAgentOptions(
    allowed_tools=["Read", "Write", "Agent"],  # Must include "Agent" to invoke
    agents=agents
)

async for message in query(
    prompt="Use the code_reviewer agent to review the codebase",
    options=options
):
    pass
```

### Method 3: Subagent Tool Invocation
Claude automatically spawns subagents when needed. Tool use object:
```json
{
    "type": "use_tool",
    "name": "Agent",
    "input": {
        "description": "Task description (3-5 words)",
        "prompt": "The detailed task for the subagent",
        "subagent_type": "Agent type"
    }
}
```

### Continuous Session with Context
```python
async with ClaudeSDKClient(options=options) as client:
    # First query - reads authentication module
    await client.query("Read the authentication module")
    async for message in client.receive_response():
        if isinstance(message, AssistantMessage):
            print(f"Context: {message}")

    # Follow-up - "it" refers to auth module, context retained
    await client.query("Now find all places that call it")
    async for message in client.receive_response():
        pass
```

---

## 4. Built-In Tools

| Tool | Description | Read-Only |
|------|-------------|-----------|
| **Read** | Read files in working directory | Yes |
| **Write** | Create new files | No |
| **Edit** | Precise edits to existing files | No |
| **Bash** | Run terminal commands, scripts, git | No |
| **Glob** | Find files by pattern (`**/*.ts`, `src/**/*.py`) | Yes |
| **Grep** | Search file contents with regex | Yes |
| **WebSearch** | Search the web for current information | Yes |
| **WebFetch** | Fetch and parse web page content | Yes |
| **AskUserQuestion** | Ask user for input/approval (interactive) | Yes |
| **Agent** | Spawn subagents for specialized work | Yes (orchestration) |
| **NotebookEdit** | Edit Jupyter notebooks | No |
| **MCP tools** | Custom tools via Model Context Protocol | Variable |

---

## 5. Handling Tool Use

### Allowed Tools & Permissions

**Pre-approval (auto-allow):**
```python
options = ClaudeAgentOptions(
    allowed_tools=["Read", "Write", "Edit"],  # These run automatically
    permission_mode="acceptEdits"  # Auto-approve file changes
)
```

**Permission modes:**
- `"acceptEdits"` — Auto-approve file edits, ask for other actions. Best for trusted workflows.
- `"default"` — Requires custom `can_use_tool` callback for approval logic.
- `"bypassPermissions"` — Run every tool without prompts. Sandboxed/CI only.
- `"plan"` — Requires user approval before execution.

**Denying tools:**
```python
options = ClaudeAgentOptions(
    allowed_tools=["Read", "Write"],
    disallowed_tools=["Bash", "WebSearch"]  # Always deny these
)
```

### Custom Tool Permissions Handler
```python
async def can_use_tool(
    tool_name: str,
    input_data: dict,
    context: ToolPermissionContext
) -> PermissionResult:
    if tool_name == "Write" and "/system/" in input_data.get("file_path", ""):
        return PermissionResultDeny(message="System directory protected")
    return PermissionResultAllow(updated_input=input_data)

options = ClaudeAgentOptions(can_use_tool=can_use_tool)
```

### Custom Tools with MCP (In-Process)
Define Python functions as tools without separate processes:

```python
from claude_agent_sdk import tool, create_sdk_mcp_server

@tool("greet", "Greet a user", {"name": str})
async def greet_user(args: dict[str, Any]) -> dict[str, Any]:
    return {
        "content": [
            {"type": "text", "text": f"Hello, {args['name']}!"}
        ]
    }

@tool("calculate", "Do math", {"expression": str})
async def calculate(args):
    result = eval(args["expression"])
    return {"content": [{"type": "text", "text": f"Result: {result}"}]}

# Create MCP server
my_server = create_sdk_mcp_server(
    name="utilities",
    version="1.0.0",
    tools=[greet_user, calculate]
)

# Use with agent
options = ClaudeAgentOptions(
    mcp_servers={"utils": my_server},
    allowed_tools=["mcp__utils__greet", "mcp__utils__calculate"]
)
```

### External MCP Servers
Connect to external systems via stdio, HTTP, or built-in MCP servers:

```python
options = ClaudeAgentOptions(
    mcp_servers={
        "playwright": {  # External subprocess
            "command": "npx",
            "args": ["@playwright/mcp@latest"]
        },
        "sqlite": {      # Hypothetical local MCP
            "command": "sqlite-mcp"
        }
    }
)
```

---

## 6. Streaming Patterns

### Output Streaming (Receiving Tokens in Real-Time)

By default, `query()` returns complete `AssistantMessage` objects. To enable streaming:

**Enable streaming output:**
```python
options = ClaudeAgentOptions(include_partial_messages=True)

async for message in query(prompt="Your task", options=options):
    # Yields StreamEvent messages with raw API events
    pass
```

#### Stream Text in Real-Time
```python
from claude_agent_sdk import query, ClaudeAgentOptions
from claude_agent_sdk.types import StreamEvent
import asyncio

async def stream_text():
    options = ClaudeAgentOptions(include_partial_messages=True)

    async for message in query(prompt="Explain databases", options=options):
        if isinstance(message, StreamEvent):
            event = message.event
            if event.get("type") == "content_block_delta":
                delta = event.get("delta", {})
                if delta.get("type") == "text_delta":
                    # Print text chunks as they arrive
                    print(delta.get("text", ""), end="", flush=True)

asyncio.run(stream_text())
```

#### Stream Tool Calls
```python
async def stream_tool_calls():
    options = ClaudeAgentOptions(
        include_partial_messages=True,
        allowed_tools=["Read", "Bash"]
    )

    current_tool = None
    tool_input = ""

    async for message in query(prompt="Read README.md", options=options):
        if isinstance(message, StreamEvent):
            event = message.event
            event_type = event.get("type")

            if event_type == "content_block_start":
                # Tool starting
                content_block = event.get("content_block", {})
                if content_block.get("type") == "tool_use":
                    current_tool = content_block.get("name")
                    print(f"Starting tool: {current_tool}")

            elif event_type == "content_block_delta":
                delta = event.get("delta", {})
                if delta.get("type") == "input_json_delta":
                    # Accumulate JSON input as it streams
                    chunk = delta.get("partial_json", "")
                    tool_input += chunk
                    print(f"  Input chunk: {chunk}")

            elif event_type == "content_block_stop":
                if current_tool:
                    print(f"Tool {current_tool} called with: {tool_input}")
                    current_tool = None
```

#### Build a Streaming UI
```python
from claude_agent_sdk import query, ResultMessage
from claude_agent_sdk.types import StreamEvent

async def streaming_ui():
    options = ClaudeAgentOptions(
        include_partial_messages=True,
        allowed_tools=["Read", "Bash", "Grep"]
    )

    in_tool = False

    async for message in query(
        prompt="Find all TODO comments", options=options
    ):
        if isinstance(message, StreamEvent):
            event = message.event
            event_type = event.get("type")

            if event_type == "content_block_start":
                content_block = event.get("content_block", {})
                if content_block.get("type") == "tool_use":
                    print(f"\n[Using {content_block.get('name')}...]", end="")
                    in_tool = True

            elif event_type == "content_block_delta":
                delta = event.get("delta", {})
                # Stream text only when not in tool
                if delta.get("type") == "text_delta" and not in_tool:
                    print(delta.get("text", ""), end="", flush=True)

            elif event_type == "content_block_stop":
                if in_tool:
                    print(" done", flush=True)
                    in_tool = False

        elif isinstance(message, ResultMessage):
            print("\n\n--- Complete ---")
```

### Input Streaming (Sending Messages)

Two modes for sending input:

#### 1. Streaming Input Mode (Recommended) — ClaudeSDKClient
Persistent session with queued messages and interrupts:

```python
async def message_generator():
    # First message
    yield {
        "type": "user",
        "message": {
            "role": "user",
            "content": "Analyze this codebase"
        }
    }

    # Wait or collect user input
    await asyncio.sleep(2)

    # Follow-up message
    yield {
        "type": "user",
        "message": {
            "role": "user",
            "content": "Now focus on security"
        }
    }

options = ClaudeAgentOptions(max_turns=10, allowed_tools=["Read", "Grep"])

async with ClaudeSDKClient(options) as client:
    await client.query(message_generator())

    async for message in client.receive_response():
        # Full session context maintained
        pass
```

**Benefits:**
- Full tool integration
- Hook support
- Image attachments
- Real-time interruption
- Natural multi-turn conversations

#### 2. Single Message Input — query()
One-shot queries with session management:

```python
# First query
async for message in query(
    prompt="Explain authentication",
    options=ClaudeAgentOptions(max_turns=1, allowed_tools=["Read"])
):
    pass

# Continue conversation (session state resumed)
async for message in query(
    prompt="Now explain authorization",
    options=ClaudeAgentOptions(continue_conversation=True, max_turns=1)
):
    pass
```

**Limitations:**
- No direct image attachments
- No dynamic message queueing
- No interruption/cancellation
- No hooks
- Limited multi-turn support

---

## 7. Authentication Patterns

### Primary Authentication (Anthropic API Key)
Set your API key via environment variable:

```bash
export ANTHROPIC_API_KEY=your-api-key
```

Or in `.env` file:
```
ANTHROPIC_API_KEY=your-api-key
```

The SDK automatically reads from environment.

### Third-Party Provider Authentication

**Amazon Bedrock:**
```bash
export CLAUDE_CODE_USE_BEDROCK=1
# Configure AWS credentials (aws configure or environment variables)
```

**Google Vertex AI:**
```bash
export CLAUDE_CODE_USE_VERTEX=1
# Configure Google Cloud credentials
```

**Microsoft Azure AI Foundry:**
```bash
export CLAUDE_CODE_USE_FOUNDRY=1
# Configure Azure credentials
```

### Important Restrictions
**Anthropic Policy:** Unless previously approved, Anthropic does NOT allow third-party developers to offer `claude.ai` login or rate limits for products using the Claude Agent SDK. All authentication must use:
- Direct Anthropic API key
- Amazon Bedrock
- Google Vertex AI
- Microsoft Azure AI Foundry

**Implication:** Cannot use Claude.ai accounts directly in SDK-based products.

---

## 8. Key Configuration Options (ClaudeAgentOptions)

```python
from claude_agent_sdk import ClaudeAgentOptions, AgentDefinition

options = ClaudeAgentOptions(
    # === Tools & Permissions ===
    tools={"type": "preset", "preset": "claude_code"},  # Preset or custom
    allowed_tools=["Read", "Write", "Bash"],            # Pre-approve
    disallowed_tools=["WebSearch"],                     # Always deny
    permission_mode="acceptEdits",                      # default, plan, acceptEdits, bypassPermissions
    can_use_tool=custom_permission_handler,             # Custom logic

    # === Model & Behavior ===
    model="claude-3-5-sonnet-20241022",                 # Model variant
    max_turns=10,                                        # Max tool-use loops
    max_budget_usd=5.0,                                 # Cost limit

    # === System Configuration ===
    system_prompt="You are an expert...",               # Custom system prompt
    cwd="/project",                                      # Working directory
    env={"DEBUG": "1"},                                 # Environment variables

    # === Extensibility ===
    mcp_servers={                                        # MCP server configs
        "internal": sdk_server,                          # In-process
        "external": {"command": "server-name"}           # Subprocess
    },
    hooks={                                              # Lifecycle hooks
        "PreToolUse": [HookMatcher(hooks=[my_hook])],
        "PostToolUse": [...]
    },
    agents={"reviewer": agent_def},                     # Subagent definitions

    # === Advanced ===
    thinking={"type": "enabled", "budget_tokens": 8000},
    output_format={"type": "json_schema", "schema": {...}},
    enable_file_checkpointing=True,
    include_partial_messages=True,                      # Enable streaming
    resume="session_id",                                # Resume prior session
    continue_conversation=True,                         # Resume single-turn
)
```

---

## 9. Hooks — Intercept Agent Behavior

Run custom code at key lifecycle points:

```python
async def check_bash_command(input_data, tool_use_id, context):
    """Validate or deny Bash commands"""
    tool_name = input_data["tool_name"]
    tool_input = input_data["tool_input"]

    if tool_name == "Bash":
        command = tool_input.get("command", "")
        if "rm -rf" in command:
            return {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": "Destructive commands not allowed"
                }
            }
    return {}

async def log_file_change(input_data, tool_use_id, context):
    """Log all file modifications"""
    if input_data["tool_name"] in ["Write", "Edit"]:
        file_path = input_data["tool_input"].get("file_path")
        with open("audit.log", "a") as f:
            f.write(f"{datetime.now()}: modified {file_path}\n")
    return {}

options = ClaudeAgentOptions(
    allowed_tools=["Bash", "Read", "Write"],
    hooks={
        "PreToolUse": [
            HookMatcher(matcher="Bash", hooks=[check_bash_command])
        ],
        "PostToolUse": [
            HookMatcher(matcher="Write|Edit", hooks=[log_file_change])
        ]
    }
)
```

**Available Hooks:**
- `PreToolUse` — Before tool execution (validate/deny)
- `PostToolUse` — After tool execution (log, transform)
- `Stop` — Agent stopping
- `SessionStart` — Session initialization
- `SessionEnd` — Session cleanup
- `UserPromptSubmit` — User input submitted

---

## 10. Differences from Anthropic Python SDK (anthropic package)

| Aspect | Claude Agent SDK | Anthropic SDK (Client) |
|--------|------------------|----------------------|
| **Installation** | `pip install claude-agent-sdk` | `pip install anthropic` |
| **Tool Execution** | Built-in, autonomous | Manual, you implement loop |
| **Async** | `AsyncIterator[Message]` | Streaming or blocking |
| **Use Case** | Autonomous agents, CI/CD, apps | Low-level API access, prompts |
| **Agent Loop** | Handled by SDK | You implement it |
| **Built-in Tools** | Read, Write, Bash, Glob, Grep, WebSearch, WebFetch, AskUserQuestion | None (you define them) |
| **MCP Support** | Native (in-process & stdio) | Not built-in |
| **Sessions** | Yes (resume, fork) | Not available |
| **Hooks** | PreToolUse, PostToolUse, SessionStart, etc. | Not available |
| **Streaming** | Partial messages + StreamEvent | Token streaming only |
| **Permission Control** | Allowlist + custom handler | Not applicable |
| **Learning Curve** | High (agent-specific) | Low (API-focused) |
| **Code Complexity** | Less (SDK handles orchestration) | More (you orchestrate) |

**When to use each:**
- **Client SDK (anthropic):** Direct API access, custom tool implementation, low-level control, prompts
- **Agent SDK:** Autonomous agents, file operations, terminal execution, CI/CD automation, custom tools via MCP

---

## 11. Error Handling

```python
from claude_agent_sdk import (
    ClaudeSDKError,          # Base error
    CLINotFoundError,        # Claude Code CLI not found
    CLIConnectionError,      # Connection issues
    ProcessError,            # Process failed (includes exit_code)
    CLIJSONDecodeError       # JSON parsing issues
)

try:
    async for message in query(prompt="Your task"):
        pass
except CLINotFoundError:
    print("Install Claude Code: https://claude.com")
except ProcessError as e:
    print(f"Agent failed with exit code {e.exit_code}")
except CLIConnectionError:
    print("Cannot connect to Claude Code CLI")
except CLIJSONDecodeError as e:
    print(f"Parsing error: {e}")
except ClaudeSDKError as e:
    print(f"Unexpected error: {e}")
```

---

## 12. Example: Complete Bug-Fixing Agent

```python
import asyncio
from claude_agent_sdk import query, ClaudeAgentOptions, AssistantMessage, ResultMessage

async def bug_fixing_agent():
    """Autonomously find and fix bugs in Python code."""

    options = ClaudeAgentOptions(
        allowed_tools=["Read", "Edit", "Glob", "Bash"],
        permission_mode="acceptEdits",  # Auto-approve file changes
        system_prompt="You are a Python expert. Fix bugs, improve error handling.",
        cwd="/Users/nick/project",
        max_turns=10,
        max_budget_usd=2.0
    )

    async for message in query(
        prompt="Review utils.py for bugs that would cause crashes. Fix any issues you find.",
        options=options
    ):
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if hasattr(block, "text"):
                    print(f"Assistant: {block.text}")
                elif hasattr(block, "name"):
                    print(f"[Tool: {block.name}]")
        elif isinstance(message, ResultMessage):
            print(f"\nAgent finished: {message.subtype}")
            print(f"Cost: ${message.total_cost_usd}")
            print(f"Tokens: input={message.usage.input_tokens}, output={message.usage.output_tokens}")

asyncio.run(bug_fixing_agent())
```

---

## 13. Key Limitations & Known Issues

### Streaming Incompatibilities
- **Extended Thinking:** When `max_thinking_tokens` is set, `StreamEvent` messages are NOT emitted. Only complete messages after each turn.
- **Structured Output:** JSON result appears only in final `ResultMessage.structured_output`, not as streaming deltas.

### Input Mode Limitations (Single-Turn query())
- No direct image attachments
- No dynamic message queueing
- No real-time interruption
- No hook integration
- Limited multi-turn support

### Permission Modes
- `bypassPermissions` only safe in sandboxed/CI environments
- `plan` mode requires user approval before execution
- Custom `can_use_tool` handler must be async

---

## 14. Resources

**Official Documentation:**
- [Agent SDK Overview](https://platform.claude.com/docs/en/agent-sdk/overview)
- [Quickstart](https://platform.claude.com/docs/en/agent-sdk/quickstart)
- [Python API Reference](https://platform.claude.com/docs/en/agent-sdk/python)
- [Streaming Output](https://platform.claude.com/docs/en/agent-sdk/streaming-output)
- [Input Streaming & Session Management](https://platform.claude.com/docs/en/agent-sdk/streaming-vs-single-mode)

**Examples:**
- [Example Agents Repository](https://github.com/anthropics/claude-agent-sdk-demos)
- [Main SDK Repository](https://github.com/anthropics/claude-agent-sdk-python)

**Related:**
- [PyPI Package](https://pypi.org/project/claude-agent-sdk/)
- [Migration from Claude Code SDK](https://platform.claude.com/docs/en/agent-sdk/migration-guide)
- [Changelog](https://github.com/anthropics/claude-agent-sdk-python/blob/main/CHANGELOG.md)

---

## Unresolved Questions

1. **Exact token costs:** Are Agent SDK tool invocations more expensive than Client SDK API calls? (Not documented in official sources)
2. **Performance metrics:** What's the latency for streaming text vs. non-streaming mode? (No benchmarks provided)
3. **Thinking budget interaction:** When extended thinking is enabled with streaming, are partial thinking tokens streamed? (Documentation unclear)
4. **Session storage:** Are resumed sessions stored on Anthropic servers or client-side? (Not specified)
5. **MCP server lifecycle:** What happens if an external MCP server crashes during execution? (Error handling docs incomplete)
6. **Rate limits:** Does third-party rate limiting apply to Agent SDK usage? (Policy mentions but no technical details)
