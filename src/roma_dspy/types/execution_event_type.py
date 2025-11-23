"""Execution event type enumeration for observability tracking."""

from enum import Enum


class ExecutionEventType(str, Enum):
    """
    Event types for execution flow tracking in RecursiveSolver.

    These events capture the hierarchical task decomposition lifecycle,
    enabling debugging, monitoring, and execution trace reconstruction.
    """

    # Top-level execution lifecycle
    EXECUTION_START = "execution_start"
    EXECUTION_COMPLETE = "execution_complete"
    EXECUTION_FAILED = "execution_failed"

    # Module execution events
    ATOMIZE_COMPLETE = "atomize_complete"
    PLAN_COMPLETE = "plan_complete"
    EXECUTE_COMPLETE = "execute_complete"
    AGGREGATE_COMPLETE = "aggregate_complete"
    VERIFY_COMPLETE = "verify_complete"

    # Task lifecycle events
    TASK_TRANSITION = "task_transition"
    SUBTASK_CREATED = "subtask_created"
