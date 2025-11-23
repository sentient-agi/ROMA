"""
Type definitions for resilience patterns.
"""

from enum import Enum
from typing import Dict, Any, Optional
from collections import deque

from roma_dspy.types.task_type import TaskType


class RetryStrategy(str, Enum):
    """Retry strategy types for different failure scenarios."""

    EXPONENTIAL_BACKOFF = "exponential_backoff"
    LINEAR_BACKOFF = "linear_backoff"
    FIXED_DELAY = "fixed_delay"
    IMMEDIATE = "immediate"
    NO_RETRY = "no_retry"


class CircuitState(str, Enum):
    """Circuit breaker states."""

    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Failing, rejecting calls
    HALF_OPEN = "half_open"  # Testing recovery


class CircuitOpenError(Exception):
    """Raised when circuit breaker is open."""

    def __init__(self, message: str = "Circuit breaker is open"):
        super().__init__(message)
        self.message = message
