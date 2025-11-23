"""
TaskStatus enumeration for ROMA v2.0

Manages the lifecycle states of task nodes in the execution graph.
"""

from enum import Enum
from typing import Literal, Set


class TaskStatus(str, Enum):
    """
    Status of a task node in the execution graph.

    State transition flow:
    PENDING → ATOMIZING → (PLANNING | EXECUTING) → (PLAN_DONE | AGGREGATING) → COMPLETED

    Special states:
    - ATOMIZING: Determining if task is atomic or needs decomposition
    - PLANNING: Decomposing task into subtasks
    - PLAN_DONE: Planning complete, subtasks ready for execution
    - AGGREGATING: Parent collecting results from completed children
    - NEEDS_REPLAN: Triggers replanning when children fail
    """

    PENDING = "PENDING"  # Task created, waiting to be processed
    ATOMIZING = "ATOMIZING"  # Determining if task is atomic
    PLANNING = "PLANNING"  # Decomposing into subtasks
    PLAN_DONE = "PLAN_DONE"  # Planning complete, subtasks created
    READY = "READY"  # Dependencies satisfied, ready to execute
    EXECUTING = "EXECUTING"  # Currently being processed
    AGGREGATING = "AGGREGATING"  # Parent collecting child results
    COMPLETED = "COMPLETED"  # Successfully finished
    FAILED = "FAILED"  # Execution failed
    NEEDS_REPLAN = "NEEDS_REPLAN"  # Requires replanning due to failure

    def __str__(self) -> str:
        return self.value

    @classmethod
    def from_string(cls, value: str) -> "TaskStatus":
        """
        Convert string to TaskStatus.

        Args:
            value: String representation of task status

        Returns:
            TaskStatus enum value

        Raises:
            ValueError: If value is not a valid task status
        """
        try:
            return cls(value.upper())
        except ValueError:
            valid_statuses = [s.value for s in cls]
            raise ValueError(
                f"Invalid task status '{value}'. Valid statuses: {valid_statuses}"
            )

    @property
    def is_terminal(self) -> bool:
        """Check if this is a terminal state (execution finished)."""
        return self in {TaskStatus.COMPLETED, TaskStatus.FAILED}

    @property
    def is_active(self) -> bool:
        """Check if this task is currently active."""
        return self in {
            TaskStatus.ATOMIZING,
            TaskStatus.PLANNING,
            TaskStatus.EXECUTING,
            TaskStatus.AGGREGATING,
        }

    @property
    def can_transition_to(self) -> Set["TaskStatus"]:
        """
        Get valid transition states from current status.

        Returns:
            Set of valid target statuses for transitions
        """
        transitions = {
            TaskStatus.PENDING: {
                TaskStatus.ATOMIZING,
                TaskStatus.EXECUTING,
                TaskStatus.READY,
                TaskStatus.FAILED,
            },
            TaskStatus.ATOMIZING: {
                TaskStatus.PLANNING,
                TaskStatus.EXECUTING,
                TaskStatus.FAILED,
            },
            TaskStatus.PLANNING: {TaskStatus.PLAN_DONE, TaskStatus.FAILED},
            TaskStatus.PLAN_DONE: {TaskStatus.AGGREGATING, TaskStatus.READY},
            TaskStatus.READY: {TaskStatus.EXECUTING, TaskStatus.FAILED},
            TaskStatus.EXECUTING: {
                TaskStatus.COMPLETED,
                TaskStatus.FAILED,
                TaskStatus.AGGREGATING,
                TaskStatus.NEEDS_REPLAN,
            },
            TaskStatus.AGGREGATING: {TaskStatus.COMPLETED, TaskStatus.FAILED},
            TaskStatus.NEEDS_REPLAN: {
                TaskStatus.PLANNING,
                TaskStatus.READY,
                TaskStatus.FAILED,
            },
            TaskStatus.COMPLETED: set(),  # Terminal state
            TaskStatus.FAILED: {TaskStatus.NEEDS_REPLAN, TaskStatus.READY},  # Recovery
        }

        return transitions.get(self, set())

    def can_transition_to_status(self, target: "TaskStatus") -> bool:
        """
        Check if transition to target status is valid.

        Args:
            target: Target status to transition to

        Returns:
            True if transition is valid, False otherwise
        """
        return target in self.can_transition_to


# Type hints for use in other modules
TaskStatusLiteral = Literal[
    "PENDING",
    "ATOMIZING",
    "PLANNING",
    "PLAN_DONE",
    "READY",
    "EXECUTING",
    "AGGREGATING",
    "COMPLETED",
    "FAILED",
    "NEEDS_REPLAN",
]
