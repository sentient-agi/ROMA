"""
Pydantic models for resilience patterns.
"""

from typing import Dict, Any, Optional
from pydantic import BaseModel, Field
from collections import deque

from roma_dspy.types.task_type import TaskType
from roma_dspy.types.resilience_types import RetryStrategy


class RetryConfig(BaseModel):
    """Configuration for retry behavior."""

    strategy: RetryStrategy = Field(default=RetryStrategy.EXPONENTIAL_BACKOFF)
    max_retries: int = Field(default=3, ge=0, le=10)
    base_delay: float = Field(default=1.0, gt=0.0)
    max_delay: float = Field(default=60.0, gt=0.0)
    jitter_factor: float = Field(default=0.1, ge=0.0, le=1.0)
    backoff_multiplier: float = Field(default=2.0, gt=1.0)


class CircuitBreakerConfig(BaseModel):
    """Configuration for circuit breaker behavior."""

    failure_threshold: int = Field(default=5, ge=1)
    recovery_timeout: float = Field(default=60.0, gt=0.0)
    success_threshold: int = Field(default=2, ge=1)
    evaluation_window: float = Field(default=300.0, gt=0.0)


class FailureContext(BaseModel):
    """Context information about a failure."""

    error_type: str
    error_message: str
    module_name: Optional[str] = None
    task_type: Optional[TaskType] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class CircuitMetrics(BaseModel):
    """Metrics for circuit breaker evaluation."""

    failure_count: int = Field(default=0)
    success_count: int = Field(default=0)
    total_calls: int = Field(default=0)
    last_failure_time: Optional[float] = None
    failure_times: deque = Field(default_factory=lambda: deque(maxlen=100))

    class Config:
        arbitrary_types_allowed = True

    def record_success(self) -> None:
        """Record successful execution."""
        self.success_count += 1
        self.total_calls += 1

    def record_failure(self) -> None:
        """Record failed execution."""
        import time

        self.failure_count += 1
        self.total_calls += 1
        current_time = time.time()
        self.last_failure_time = current_time
        self.failure_times.append(current_time)

    def get_failure_rate(self, window_seconds: float) -> float:
        """Get failure rate within time window."""
        import time

        if not self.failure_times:
            return 0.0

        current_time = time.time()
        recent_failures = [
            t for t in self.failure_times if current_time - t <= window_seconds
        ]

        if not recent_failures:
            return 0.0

        # Calculate rate as failures per second
        time_span = max(1.0, current_time - recent_failures[0])
        return len(recent_failures) / time_span
