"""Execution status enumeration."""

from enum import Enum
from typing import Literal


class ExecutionStatus(str, Enum):
    """Status of an execution.

    Lifecycle:
        PENDING -> RUNNING -> (COMPLETED | FAILED | CANCELLED)

    States:
        PENDING: Execution created but not yet started
        RUNNING: Execution is currently in progress
        COMPLETED: Execution finished successfully
        FAILED: Execution failed due to errors
        CANCELLED: Execution was cancelled by user
    """

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

    def __str__(self) -> str:
        """Return the value for string conversion."""
        return self.value

    def is_terminal(self) -> bool:
        """Check if this is a terminal state (cannot transition further)."""
        return self in {self.COMPLETED, self.FAILED, self.CANCELLED}

    def is_active(self) -> bool:
        """Check if this is an active state (can still make progress)."""
        return self in {self.PENDING, self.RUNNING}


# Type alias for literal type checking
ExecutionStatusLiteral = Literal[
    "pending", "running", "completed", "failed", "cancelled"
]
