"""Agent instance tracking state and budget."""
from dataclasses import dataclass, field
from enum import Enum
import time


class AgentStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class AgentInstance:
    """Tracks a single agent's lifecycle and cost."""

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
        if self.start_time == 0:
            return 0.0
        end = self.end_time if self.end_time > 0 else time.time()
        return end - self.start_time

    @property
    def budget_remaining(self) -> float:
        return max(0.0, self.budget_limit - self.cost)

    @property
    def budget_exceeded(self) -> bool:
        return self.cost >= self.budget_limit

    def add_cost(self, amount: float) -> None:
        self.cost += amount

    def start(self) -> None:
        self.status = AgentStatus.RUNNING
        self.start_time = time.time()

    def complete(self, error: str | None = None) -> None:
        self.end_time = time.time()
        if error:
            self.status = AgentStatus.FAILED
            self.error = error
        else:
            self.status = AgentStatus.COMPLETED

    def cancel(self) -> None:
        self.end_time = time.time()
        self.status = AgentStatus.CANCELLED
