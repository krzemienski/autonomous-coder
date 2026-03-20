# Security Pipeline — Defense in Depth

**Type:** Feature Diagram
**Last Updated:** 2026-03-19
**Related Files:**
- `security.py` — `is_command_allowed()`, `ALLOWED_COMMANDS`, `DANGEROUS_PATTERNS`
- `orchestrator.py` — `security_callback()` using `can_use_tool`
- `agent_factory.py` — Wires `can_use_tool` into `ClaudeAgentOptions`

## Purpose

Shows how the security layer protects users from dangerous commands being executed by autonomous agents, using the SDK's `can_use_tool` callback to block commands BEFORE execution — fixing the legacy pattern that checked AFTER execution.

## Diagram

```mermaid
flowchart TB
    subgraph "Front-Stage — User Protection"
        USER[👤 User watches agent work]
        NOTIFY[🔔 TUI notification:<br/>"Command blocked: rm -rf /"]
        SAFE[✅ Safe commands execute normally]
    end

    subgraph "Back-Stage — Security Enforcement"
        AGENT[Agent calls Tool: Bash]
        AGENT --> CUT{can_use_tool callback<br/>🛡️ Called BEFORE execution}

        CUT -->|"tool_name == 'Bash'"| CHECK[is_command_allowed<br/>⚡ Checks allowlist + dangerous patterns]
        CUT -->|"tool_name != 'Bash'"| ALLOW[PermissionResultAllow<br/>✅ Non-bash tools pass through]

        CHECK -->|"command in ALLOWED_COMMANDS<br/>AND no DANGEROUS_PATTERNS"| ALLOW
        CHECK -->|"command blocked"| DENY[PermissionResultDeny<br/>❌ behavior='deny', interrupt=False]

        DENY --> MSG[SecurityBlock message<br/>📢 Posted to TUI]
        DENY --> RECOVER[Agent tries alternative<br/>🔄 interrupt=False keeps agent alive]

        ALLOW --> EXEC[Tool executes<br/>⚡ SDK runs the command]
        EXEC --> HOOKS[PostToolUse hook<br/>📊 Logs to TUI for observability]
    end

    MSG --> NOTIFY
    EXEC --> SAFE
    HOOKS --> USER

    style CUT fill:#c8e6c9
    style DENY fill:#ffcdd2
    style ALLOW fill:#c8e6c9
```

## Key Insights

- **Pre-execution blocking**: `can_use_tool` is called BEFORE the SDK executes the tool — unlike the legacy `client.py` which checked AFTER
- **Non-destructive denial**: `interrupt=False` means a blocked command doesn't kill the agent — it can try an alternative approach
- **142 allowed commands**: Curated allowlist covers package managers, build tools, runtimes, linters, safe shell utilities
- **20 dangerous patterns**: Catches `rm -rf /`, fork bombs, `curl | sh`, `sudo rm`, etc. regardless of allowlist
- **Separation of concerns**: `can_use_tool` for security enforcement, `hooks` for observability only

## Change History

- **2026-03-19:** Initial security pipeline diagram
