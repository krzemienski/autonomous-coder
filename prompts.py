"""
Prompt template loading and formatting utilities.

Provides functions to load and format prompt templates
for the four-phase agent architecture: Research → Explorer → Planner → Coder.
"""

from pathlib import Path
from typing import Any


# Base path for prompt templates
PROMPTS_DIR = Path(__file__).parent / "prompts"


def load_prompt_template(template_name: str) -> str:
    """
    Load a prompt template from the prompts directory.

    Args:
        template_name: Name of the template file (with or without .md extension)

    Returns:
        The template content as a string

    Raises:
        FileNotFoundError: If the template file doesn't exist
    """
    if not template_name.endswith(".md"):
        template_name = f"{template_name}.md"

    template_path = PROMPTS_DIR / template_name

    if not template_path.exists():
        raise FileNotFoundError(f"Template not found: {template_path}")

    return template_path.read_text(encoding="utf-8")


def format_prompt(template: str, **kwargs: Any) -> str:
    """
    Format a prompt template with the given variables.

    Uses simple string formatting with {variable} placeholders.

    Args:
        template: The template string
        **kwargs: Variables to substitute in the template

    Returns:
        The formatted prompt string
    """
    try:
        return template.format(**kwargs)
    except KeyError as e:
        raise ValueError(f"Missing required template variable: {e}")


def get_researcher_prompt(
    task: str,
    project_path: str,
    additional_context: str = "",
) -> str:
    """
    Get the formatted researcher prompt for web research and MCP discovery.

    Args:
        task: The user's task description
        project_path: Path to the project directory
        additional_context: Any additional context to include

    Returns:
        Formatted researcher prompt
    """
    template = load_prompt_template("researcher_prompt")
    return format_prompt(
        template,
        task=task,
        project_path=project_path,
        additional_context=additional_context,
    )


def get_explorer_prompt(
    task: str,
    project_path: str,
    additional_context: str = "",
) -> str:
    """
    Get the formatted explorer prompt for codebase analysis.

    Args:
        task: The user's task description
        project_path: Path to the project directory
        additional_context: Any additional context to include

    Returns:
        Formatted explorer prompt
    """
    template = load_prompt_template("explorer_prompt")
    return format_prompt(
        template,
        task=task,
        project_path=project_path,
        additional_context=additional_context,
    )


def get_planner_prompt(
    task: str,
    exploration_results: str,
    project_path: str,
) -> str:
    """
    Get the formatted planner prompt for implementation planning.

    Args:
        task: The user's task description
        exploration_results: Results from the exploration phase
        project_path: Path to the project directory

    Returns:
        Formatted planner prompt
    """
    template = load_prompt_template("planner_prompt")
    return format_prompt(
        template,
        task=task,
        exploration_results=exploration_results,
        project_path=project_path,
    )


def get_coder_prompt(
    task: dict[str, Any],
    plan: dict[str, Any],
    completed_tasks: list[int],
    project_path: str,
) -> str:
    """
    Get the formatted coder prompt for a specific implementation task.

    Args:
        task: The current task to implement
        plan: The full implementation plan
        completed_tasks: List of completed task IDs
        project_path: Path to the project directory

    Returns:
        Formatted coder prompt
    """
    template = load_prompt_template("coder_prompt")

    # Format the task details
    task_details = f"""
Task ID: {task.get('id', 'N/A')}
Title: {task.get('title', 'N/A')}
Description: {task.get('description', 'N/A')}
Files to modify: {', '.join(task.get('files', []))}
Dependencies: {', '.join(map(str, task.get('dependencies', [])))}
Test criteria: {task.get('test_criteria', 'N/A')}
Complexity: {task.get('estimated_complexity', 'N/A')}
"""

    # Format plan context
    plan_context = f"""
Overall Goal: {plan.get('goal', 'N/A')}
Context Summary: {plan.get('context_summary', 'N/A')}
Total Tasks: {plan.get('total_tasks', 0)}
Completed: {len(completed_tasks)} ({', '.join(map(str, completed_tasks)) if completed_tasks else 'none'})
Risks: {', '.join(plan.get('risks', []))}
"""

    return format_prompt(
        template,
        task_details=task_details,
        plan_context=plan_context,
        project_path=project_path,
    )


def get_system_prompt() -> str:
    """
    Get the base system prompt for all agents.

    Returns:
        The system prompt string
    """
    return """You are an expert software engineer working on a codebase.

You have access to powerful tools for code exploration, analysis, and modification:

## Serena MCP Tools (Codebase Understanding)
- `get_symbols_overview` - Get high-level view of symbols in a file
- `find_symbol` - Find specific classes, methods, functions by name
- `find_referencing_symbols` - Find where symbols are used
- `search_for_pattern` - Regex search across the codebase
- `list_dir` - List directory contents
- `read_file` - Read file contents

## Serena MCP Tools (Code Modification)
- `replace_content` - Replace content in files using regex
- `replace_symbol_body` - Replace entire symbol definitions
- `insert_after_symbol` - Insert code after a symbol
- `insert_before_symbol` - Insert code before a symbol
- `create_text_file` - Create new files
- `execute_shell_command` - Run shell commands

## Guidelines
1. ALWAYS explore before modifying - understand the codebase first
2. Use semantic tools (find_symbol, get_symbols_overview) over raw file reading
3. Make minimal, focused changes - don't over-engineer
4. Follow existing code patterns and conventions
5. Write tests when appropriate
6. Commit changes with clear messages
7. Handle errors gracefully

## Security
- Only use allowed bash commands
- Stay within the project directory
- Don't expose secrets or credentials
- Follow security best practices in code
"""


# Fallback prompts in case template files don't exist
FALLBACK_RESEARCHER_PROMPT = """# Research/Onboarding Phase

## Task
{task}

## Project Path
{project_path}

## Instructions

Your goal is to perform web research BEFORE any codebase exploration to discover:
1. Relevant MCP servers for the task domain
2. Existing skills and examples that could be adapted
3. Library documentation and best practices
4. GitHub repositories with relevant implementations

Use available MCP tools to:

### 1. Search for MCP Servers
Use Firecrawl MCP to search for relevant MCP servers:
- Search github.com/modelcontextprotocol
- Search npmjs.com/search?q=mcp-server
- Search github.com/topics/mcp-server

### 2. Find Skills and Examples
Search for Claude Code skills and automation examples:
- Anthropic quickstarts
- Community skills repositories
- Similar implementations on GitHub

### 3. Fetch Library Documentation
Use Context7 MCP to get up-to-date library docs:
- resolve-library-id for finding library IDs
- get-library-docs for fetching documentation

### 4. Synthesize Recommendations
Based on research, provide:
- MCP servers to install (with commands)
- Skills to adapt or reference
- Key documentation links
- Implementation approach suggestions

## Output Format

Provide a structured JSON report with:
```json
{{
  "task_analysis": {{
    "domains": ["technology domains"],
    "languages": ["programming languages"],
    "frameworks": ["frameworks/libraries"],
    "platforms": ["target platforms"]
  }},
  "mcp_servers": [
    {{
      "name": "MCP server name",
      "description": "What it does",
      "relevance": "high|medium|low",
      "installation": {{"command": "npx or uvx", "args": []}},
      "source_url": "URL"
    }}
  ],
  "skills": [
    {{
      "name": "Skill name",
      "description": "What it demonstrates",
      "source_url": "URL"
    }}
  ],
  "libraries": [
    {{
      "name": "Library name",
      "context7_id": "ID if found",
      "documentation_summary": "Key points"
    }}
  ],
  "recommendations": {{
    "must_install": [],
    "suggested": [],
    "approach": "Recommended implementation approach"
  }}
}}
```

{additional_context}
"""

FALLBACK_EXPLORER_PROMPT = """# Codebase Exploration

## Task
{task}

## Project Path
{project_path}

## Instructions

Your goal is to explore and understand the existing codebase to gather context for implementing the task.

Use the Serena MCP tools to:

1. **Understand the project structure**
   - Use `list_dir` to explore the directory layout
   - Identify key directories (src, lib, tests, etc.)

2. **Detect the technology stack**
   - Check package.json, requirements.txt, Cargo.toml, etc.
   - Identify the framework, language version, key dependencies

3. **Map relevant symbols**
   - Use `get_symbols_overview` on key files
   - Use `find_symbol` to locate relevant classes/functions
   - Use `find_referencing_symbols` to understand dependencies

4. **Find patterns**
   - Use `search_for_pattern` to find similar implementations
   - Identify coding conventions and patterns

5. **Identify impact areas**
   - Which files need modification?
   - What tests might need updates?
   - What could break?

## Output Format

Provide a structured JSON report with:
```json
{{
  "stack": {{
    "language": "string",
    "framework": "string",
    "database": "string (if any)",
    "testing": "string"
  }},
  "architecture": "string describing the architecture",
  "entry_points": ["list of main entry files"],
  "relevant_files": [
    {{"path": "relative/path", "relevance": "high|medium|low", "reason": "why relevant"}}
  ],
  "patterns_detected": ["list of patterns found"],
  "impact_areas": ["areas that might be affected"],
  "key_symbols": [
    {{"name": "SymbolName", "type": "class|function|method", "file": "path"}}
  ],
  "recommendations": ["recommendations for implementation"]
}}
```

{additional_context}
"""

FALLBACK_PLANNER_PROMPT = """# Implementation Planning

## Task
{task}

## Exploration Results
{exploration_results}

## Project Path
{project_path}

## Instructions

Based on the exploration results, create a detailed implementation plan.

Your plan should:

1. **Break down the work into atomic tasks**
   - Each task should be small and testable
   - Each task should have clear completion criteria
   - Tasks should be ordered by dependencies

2. **Consider dependencies**
   - Which tasks must complete before others can start?
   - Are there any parallelizable tasks?

3. **Identify risks**
   - What could go wrong?
   - What needs extra attention?
   - Are there any breaking changes?

4. **Define test strategy**
   - How will each task be verified?
   - What tests need to be written or updated?

## Output Format

Provide the plan as JSON:
```json
{{
  "goal": "The original task description",
  "context_summary": "Key findings from exploration",
  "tasks": [
    {{
      "id": 1,
      "title": "Brief task title",
      "description": "Detailed description of what to do",
      "files": ["list of files to modify"],
      "dependencies": [],
      "test_criteria": "How to verify this task is complete",
      "estimated_complexity": "low|medium|high"
    }}
  ],
  "risks": ["List of identified risks"],
  "total_tasks": 5
}}
```

## Guidelines
- Keep tasks atomic and focused
- Order tasks so dependencies are satisfied
- Include setup/cleanup tasks if needed
- Consider rollback points for risky changes
"""

FALLBACK_CODER_PROMPT = """# Implementation Task

## Current Task
{task_details}

## Plan Context
{plan_context}

## Project Path
{project_path}

## Instructions

Implement the current task following these guidelines:

1. **Focus on this task only**
   - Don't implement other tasks
   - Stay within the scope of this task
   - Make minimal changes

2. **Follow the codebase patterns**
   - Match existing code style
   - Use established patterns
   - Be consistent with conventions

3. **Verify your changes**
   - Run existing tests if applicable
   - Test the changes manually if possible
   - Check for obvious errors

4. **Handle errors gracefully**
   - If something doesn't work, report it
   - Don't force changes that break things
   - Ask for help if stuck

5. **Document if needed**
   - Add comments for complex logic
   - Update documentation if changing APIs
   - Note any assumptions

## Completion

When done, provide:
1. Summary of changes made
2. Files modified
3. Test results (if any)
4. Any issues or concerns

If you cannot complete the task, explain why and what's needed.
"""


def ensure_prompt_templates_exist() -> None:
    """
    Ensure prompt template files exist, creating them from fallbacks if needed.
    """
    PROMPTS_DIR.mkdir(parents=True, exist_ok=True)

    templates = {
        "researcher_prompt.md": FALLBACK_RESEARCHER_PROMPT,
        "explorer_prompt.md": FALLBACK_EXPLORER_PROMPT,
        "planner_prompt.md": FALLBACK_PLANNER_PROMPT,
        "coder_prompt.md": FALLBACK_CODER_PROMPT,
    }

    for name, content in templates.items():
        path = PROMPTS_DIR / name
        if not path.exists():
            path.write_text(content, encoding="utf-8")


# Export
__all__ = [
    "load_prompt_template",
    "format_prompt",
    "get_researcher_prompt",
    "get_explorer_prompt",
    "get_planner_prompt",
    "get_coder_prompt",
    "get_system_prompt",
    "ensure_prompt_templates_exist",
]
