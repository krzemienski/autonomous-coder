"""Agent instance tracking state and budget."""
from dataclasses import dataclass
from enum import Enum
import time


class AgentStatus(Enum):
    """Lifecycle states for a single agent instance."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class AgentInstance:
    """Tracks a single agent's lifecycle and cost.

    Attributes:
        name: Unique display name (typically ``{phase}-{role}``).
        role: Role key matching an ``OrchestratorConfig.roles`` entry.
        phase: Pipeline phase this agent belongs to.
        status: Current lifecycle state.
        cost: Cumulative cost incurred in USD.
        budget_limit: Maximum allowed spend in USD.
        start_time: Unix epoch when the agent started.
        end_time: Unix epoch when the agent finished.
        turns_used: Number of conversational turns consumed.
        max_turns: Hard cap on conversational turns.
        session_id: Optional external session identifier.
        error: Error message if the agent failed.
    """

    name: str
    role: str
    phase: str
    status: AgentStatus = AgentStatus.PENDING
    cost: float = 0.0
    budget_limit: float = 1.0
    start_time: float = 0.0
    end_time: float = 0.0
    turns_used: int = 0
    max_turns: int = 30
    session_id: str | None = None
    error: str | None = None

    @property
    def duration(self) -> float:
        """Elapsed wall-clock seconds since start (or total if finished)."""
        if self.start_time == 0:
            return 0.0
        end = self.end_time if self.end_time > 0 else time.time()
        return end - self.start_time

    @property
    def budget_remaining(self) -> float:
        """USD remaining before the budget cap is reached."""
        return max(0.0, self.budget_limit - self.cost)

    @property
    def budget_exceeded(self) -> bool:
        """True when cumulative cost meets or exceeds the budget limit."""
        return self.cost >= self.budget_limit

    def add_cost(self, amount: float) -> None:
        """Add an incremental cost (USD) to this agent's running total."""
        self.cost += amount

    def start(self) -> None:
        """Transition to RUNNING and record the start timestamp."""
        self.status = AgentStatus.RUNNING
        self.start_time = time.time()

    def complete(self, error: str | None = None) -> None:
        """Mark the agent as finished.

        Args:
            error: If provided, sets status to FAILED with this message.
        """
        self.end_time = time.time()
        if error:
            self.status = AgentStatus.FAILED
            self.error = error
        else:
            self.status = AgentStatus.COMPLETED

    def cancel(self) -> None:
        """Mark the agent as cancelled and record the end timestamp."""
        self.end_time = time.time()
        self.status = AgentStatus.CANCELLED
