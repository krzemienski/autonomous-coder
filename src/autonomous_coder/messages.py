"""Textual Message subclasses for inter-widget communication."""
from textual.message import Message


class AgentStarted(Message):
    """Fired when an agent begins execution."""

    def __init__(self, agent_name: str, phase: str) -> None:
        """Initialize AgentStarted message.

        Args:
            agent_name: Unique name of the agent.
            phase: Pipeline phase the agent belongs to.
        """
        super().__init__()
        self.agent_name = agent_name
        self.phase = phase


class AgentOutput(Message):
    """Fired when an agent produces output text."""

    def __init__(self, agent_name: str, text: str, block_type: str = "text") -> None:
        """Initialize AgentOutput message.

        Args:
            agent_name: Agent that produced the output.
            text: Raw output text.
            block_type: Kind of content -- "text", "tool", or "error".
        """
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
        """Initialize AgentCompleted message.

        Args:
            agent_name: Agent that finished.
            phase: Pipeline phase.
            cost: Total cost incurred by this agent in USD.
            duration: Wall-clock seconds the agent ran.
            success: True if the agent completed without error.
            error: Error message if the agent failed.
        """
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
        """Initialize AgentError message.

        Args:
            agent_name: Agent that encountered the error.
            error: Error description.
            phase: Pipeline phase where the error occurred.
        """
        super().__init__()
        self.agent_name = agent_name
        self.error = error
        self.phase = phase


class CostUpdate(Message):
    """Fired when agent cost changes."""

    def __init__(self, agent_name: str, cost: float, total_cost: float) -> None:
        """Initialize CostUpdate message.

        Args:
            agent_name: Agent that incurred the cost.
            cost: Incremental cost for this update in USD.
            total_cost: Running total cost across all agents.
        """
        super().__init__()
        self.agent_name = agent_name
        self.cost = cost
        self.total_cost = total_cost


class SecurityBlock(Message):
    """Fired when a tool call is blocked by security policy."""

    def __init__(self, agent_name: str, tool_name: str, reason: str) -> None:
        """Initialize SecurityBlock message.

        Args:
            agent_name: Agent whose tool call was blocked.
            tool_name: Name of the blocked tool.
            reason: Human-readable explanation.
        """
        super().__init__()
        self.agent_name = agent_name
        self.tool_name = tool_name
        self.reason = reason


class PhaseStarted(Message):
    """Fired when a pipeline phase begins."""

    def __init__(self, phase: str, phase_index: int, total_phases: int) -> None:
        """Initialize PhaseStarted message.

        Args:
            phase: Name of the phase starting.
            phase_index: Zero-based position in the pipeline.
            total_phases: Total number of phases.
        """
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
        """Initialize PhaseCompleted message.

        Args:
            phase: Name of the completed phase.
            phase_index: Zero-based position in the pipeline.
            cost: Cost incurred during this phase in USD.
            duration: Wall-clock seconds for the phase.
            success: True if the phase completed successfully.
        """
        super().__init__()
        self.phase = phase
        self.phase_index = phase_index
        self.cost = cost
        self.duration = duration
        self.success = success
