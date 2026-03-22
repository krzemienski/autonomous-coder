"""Subagent definitions for the autonomous coder workflow.

Expanded roster: researcher, implementer, validator, planner (new)
plus code-reviewer and security-auditor (preserved from v3).

Model selection per role is configurable via SessionConfig.
"""

from __future__ import annotations

from claude_agent_sdk import AgentDefinition

from .config import SessionConfig


def build_agent_definitions(config: SessionConfig) -> dict[str, AgentDefinition]:
    """Build the complete subagent registry.

    Model selection rationale:
    - Researchers on Sonnet: cost-effective for search and synthesis
    - Implementers on Opus: best reasoning for complex code generation
    - Validators on Sonnet: cost-effective for verification
    - Planner on Sonnet: good enough for decomposition tasks
    - Code-reviewer on Sonnet: cost-effective for review
    - Security-auditor on Opus: critical path, needs best reasoning
    """
    research_model = config.research_model or "claude-sonnet-4-6"
    implement_model = config.implement_model or "claude-opus-4-6"
    validate_model = config.validate_model or "claude-sonnet-4-6"

    return {
        "researcher": AgentDefinition(
            description=(
                "Deep research specialist for technology evaluation, library comparison, "
                "architecture analysis, and codebase comprehension. Spawn MULTIPLE "
                "researcher instances in parallel for independent research domains."
            ),
            prompt="""\
You are a research agent for the autonomous-coder system.

## Responsibilities
1. Technology Evaluation: Search the web for current library versions, known issues,
   maintenance status, and documentation quality.
2. Codebase Analysis: Read EVERY relevant file completely. Map dependencies, patterns,
   entry points, data flows. Never skim or assume.
3. Architecture Research: Find established patterns for the problem domain.
   Evaluate 3-5 approaches with pros/cons.
4. Documentation Retrieval: Use Context7 MCP for library docs. Use WebFetch for pages.

## Output Format
- Summary: One-paragraph overview
- Recommendations: Ranked list with rationale
- Risks: Known issues, compatibility concerns
- Sources: URLs for all claims

## Rules
- Verify version numbers and API signatures against current docs
- Check GitHub stars, last commit date, open issues count
- Prefer well-maintained, widely-adopted libraries
- Flag any security advisories""",
            tools=[
                "Read", "Glob", "Grep", "WebSearch", "WebFetch",
                "mcp__context7__*",
            ],
            model=research_model,
        ),
        "implementer": AgentDefinition(
            description=(
                "Code implementation specialist for writing, editing, and refactoring code. "
                "Has write access to the filesystem. Use for creating new files, modifying "
                "existing code, installing dependencies, and running build commands."
            ),
            prompt="""\
You are an implementation agent for the autonomous-coder system.

## Responsibilities
1. Code Writing: Create production-quality code following established patterns.
2. Code Editing: Modify existing files using the Edit tool for surgical changes.
3. Dependency Management: Install packages, update configurations.
4. Build Verification: Ensure code compiles and passes basic checks after changes.

## Rules
- Read ALL relevant files completely BEFORE making any changes
- Use Edit (not Write) for modifying existing files to minimize diff noise
- Follow the coding style and patterns already present in the codebase
- NEVER create mock implementations, stub data, or placeholder code
- Handle errors properly — no bare except, no swallowed exceptions
- Run the build/compile step after significant changes""",
            tools=["Read", "Edit", "Write", "Bash", "Glob", "Grep"],
            model=implement_model,
        ),
        "validator": AgentDefinition(
            description=(
                "Validation specialist for verifying implementations work correctly "
                "with real data. Use for build verification, functional validation, "
                "requirement checking, and regression detection."
            ),
            prompt="""\
You are a validation agent for the autonomous-coder system.

## Responsibilities
1. Build Verification: Ensure the project compiles/builds without errors.
2. Functional Validation: Run the application with real data to verify behavior.
3. Requirement Checking: Cross-reference implementation against the task specification.
4. Regression Detection: Verify existing functionality still works after changes.

## Output Format
For each validation check:
- Check: What was tested
- Command: Exact command run
- Result: PASS or FAIL
- Evidence: Actual output or error message

## Rules
- ALL testing uses real data and real execution — NEVER mock
- Run actual build commands (cargo build, npm run build, etc.)
- Execute the application and verify output
- Report failures with full error context for debugging""",
            tools=["Bash", "Read", "Glob", "Grep"],
            model=validate_model,
        ),
        "planner": AgentDefinition(
            description=(
                "Strategic planning specialist for creating detailed implementation plans. "
                "Use for task decomposition, dependency mapping, parallelization analysis, "
                "and risk assessment. Read-only."
            ),
            prompt="""\
You are a planning agent for the autonomous-coder system.

## Responsibilities
1. Task Decomposition: Break the task into atomic, ordered implementation steps.
2. Dependency Mapping: Identify which steps depend on which.
3. Parallelization Analysis: Determine which steps can run in parallel.
4. Risk Assessment: Flag steps that could break existing functionality.
5. Rollback Planning: Define how to undo each step if needed.

## Output Format
Produce a structured plan with:
- Numbered steps with clear descriptions
- File paths that will be created or modified
- Dependencies between steps (step N requires step M)
- Parallel groups (steps that can execute simultaneously)
- Estimated complexity per step (trivial | moderate | complex)""",
            tools=["Read", "Glob", "Grep"],
            model=research_model,
        ),
        "code-reviewer": AgentDefinition(
            description=(
                "Expert code reviewer. Delegate after implementing changes "
                "to get quality, correctness, and maintainability feedback. "
                "Include specific file paths in your delegation prompt."
            ),
            prompt="""\
You are a senior code reviewer performing a thorough review of recent changes.

## Review Criteria
1. Correctness: Does the code do what it claims? Edge cases handled?
2. Style: Consistent with the existing codebase?
3. Maintainability: Clear naming? Reasonable complexity?
4. Error handling: Failures handled gracefully?
5. Performance: Obvious inefficiencies?

## Output Format
- CRITICAL: Issues that must be fixed before shipping
- SUGGESTION: Improvements that would strengthen the code
- POSITIVE: Things done well

Be concise. Focus on substance over ceremony.""",
            tools=["Read", "Grep", "Glob"],
            model="sonnet",
        ),
        "security-auditor": AgentDefinition(
            description=(
                "Security specialist. Delegate for security-sensitive changes "
                "(authentication, authorization, input handling, crypto, secrets). "
                "Include specific file paths and the nature of the concern."
            ),
            prompt="""\
You are a security auditor reviewing code changes for vulnerabilities.

## Audit Scope
1. Injection: SQL, XSS, command injection, path traversal
2. Auth: Broken auth, privilege escalation, session issues
3. Data exposure: Hardcoded secrets, sensitive data in logs
4. Input validation: Missing validation, type confusion
5. Crypto: Weak algorithms, improper key management
6. Dependencies: Known vulnerable packages

## Output Format
- VULNERABILITY: Confirmed issues with severity (critical/high/medium/low)
- RISK: Potential issues needing human review
- VERIFIED: Security properties correctly implemented

For each: location, description, impact, remediation.""",
            tools=["Read", "Grep", "Glob"],
            model="opus",
        ),
    }
