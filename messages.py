"""Textual Message subclasses for inter-widget communication."""
from textual.message import Message


class AgentStarted(Message):
    """Fired when an agent begins execution."""

    def __init__(self, agent_name: str, phase: str) -> None:
        super().__init__()
        self.agent_name = agent_name
        self.phase = phase


class AgentOutput(Message):
    """Fired when an agent produces output text."""

    def __init__(self, agent_name: str, text: str, block_type: str = "text") -> None:
        super().__init__()
        self.agent_name = agent_name
        self.text = text
        self.block_type = block_type


class AgentCompleted(Message):
    """Fired when an agent finishes execution."""

    def __init__(
        self,
        agent_name: str,
        phase: str,
        cost: float,
        duration: float,
        success: bool,
        error: str | None = None,
    ) -> None:
        super().__init__()
        self.agent_name = agent_name
        self.phase = phase
        self.cost = cost
        self.duration = duration
        self.success = success
        self.error = error


class AgentError(Message):
    """Fired when an agent encounters a fatal error."""

    def __init__(self, agent_name: str, error: str, phase: str) -> None:
        super().__init__()
        self.agent_name = agent_name
        self.error = error
        self.phase = phase


class CostUpdate(Message):
    """Fired when agent cost changes."""

    def __init__(self, agent_name: str, cost: float, total_cost: float) -> None:
        super().__init__()
        self.agent_name = agent_name
        self.cost = cost
        self.total_cost = total_cost


class SecurityBlock(Message):
    """Fired when a tool call is blocked by security policy."""

    def __init__(self, agent_name: str, tool_name: str, reason: str) -> None:
        super().__init__()
        self.agent_name = agent_name
        self.tool_name = tool_name
        self.reason = reason


class PhaseStarted(Message):
    """Fired when a pipeline phase begins."""

    def __init__(self, phase: str, phase_index: int, total_phases: int) -> None:
        super().__init__()
        self.phase = phase
        self.phase_index = phase_index
        self.total_phases = total_phases


class PhaseCompleted(Message):
    """Fired when a pipeline phase finishes."""

    def __init__(
        self,
        phase: str,
        phase_index: int,
        cost: float,
        duration: float,
        success: bool,
    ) -> None:
        super().__init__()
        self.phase = phase
        self.phase_index = phase_index
        self.cost = cost
        self.duration = duration
        self.success = success
