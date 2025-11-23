"""
Retry policies with exponential backoff for task-level failures.

Provides different retry strategies based on task types and failure modes,
avoiding overlap with DSPy's LLM-level retry mechanisms.
"""

import asyncio
import random
from typing import Optional, Dict, Any, Callable

from roma_dspy.types.task_type import TaskType
from roma_dspy.types.resilience_types import RetryStrategy
from roma_dspy.types.resilience_models import RetryConfig, FailureContext


class RetryPolicy:
    """
    Implements retry policies with various backoff strategies.

    Focuses on task orchestration failures, not LLM API failures
    which are handled by DSPy.
    """

    def __init__(self, config: Optional[RetryConfig] = None):
        """Initialize retry policy with configuration."""
        self.config = config or RetryConfig()
        self._task_specific_configs: Dict[TaskType, RetryConfig] = {}

    def configure_for_task_type(self, task_type: TaskType, config: RetryConfig) -> None:
        """Configure specific retry behavior for a task type."""
        self._task_specific_configs[task_type] = config

    def get_config_for_task(self, task_type: Optional[TaskType] = None) -> RetryConfig:
        """Get retry configuration for specific task type."""
        if task_type and task_type in self._task_specific_configs:
            return self._task_specific_configs[task_type]
        return self.config

    def calculate_delay(
        self,
        attempt: int,
        task_type: Optional[TaskType] = None,
        failure_context: Optional[FailureContext] = None,
    ) -> float:
        """
        Calculate delay for retry attempt.

        Args:
            attempt: Current retry attempt number (0-based)
            task_type: Type of task being retried
            failure_context: Context about the failure

        Returns:
            Delay in seconds before next retry
        """
        config = self.get_config_for_task(task_type)

        if config.strategy == RetryStrategy.NO_RETRY:
            return 0.0
        elif config.strategy == RetryStrategy.IMMEDIATE:
            return 0.0
        elif config.strategy == RetryStrategy.FIXED_DELAY:
            delay = config.base_delay
        elif config.strategy == RetryStrategy.LINEAR_BACKOFF:
            delay = config.base_delay * (attempt + 1)
        elif config.strategy == RetryStrategy.EXPONENTIAL_BACKOFF:
            delay = config.base_delay * (config.backoff_multiplier**attempt)
        else:
            delay = config.base_delay

        # Apply maximum delay constraint
        delay = min(delay, config.max_delay)

        # Add jitter to prevent thundering herd
        jitter = random.uniform(
            -delay * config.jitter_factor, delay * config.jitter_factor
        )
        delay = max(0.0, delay + jitter)

        return delay

    def should_retry(
        self,
        attempt: int,
        task_type: Optional[TaskType] = None,
        failure_context: Optional[FailureContext] = None,
    ) -> bool:
        """
        Determine if task should be retried.

        Args:
            attempt: Current retry attempt number (0-based)
            task_type: Type of task that failed
            failure_context: Context about the failure

        Returns:
            True if task should be retried
        """
        config = self.get_config_for_task(task_type)

        if config.strategy == RetryStrategy.NO_RETRY:
            return False

        return attempt < config.max_retries

    async def retry_with_backoff(
        self,
        func: Callable,
        task_type: Optional[TaskType] = None,
        failure_context: Optional[FailureContext] = None,
        *args,
        **kwargs,
    ) -> Any:
        """
        Execute function with retry and backoff.

        Args:
            func: Function to execute with retry
            task_type: Type of task being executed
            failure_context: Context about previous failures

        Returns:
            Result of successful function execution

        Raises:
            Exception: Last exception if all retries exhausted
        """
        last_exception = None

        for attempt in range(self.get_config_for_task(task_type).max_retries + 1):
            try:
                if asyncio.iscoroutinefunction(func):
                    return await func(*args, **kwargs)
                else:
                    return func(*args, **kwargs)
            except Exception as e:
                last_exception = e

                if not self.should_retry(attempt, task_type, failure_context):
                    break

                delay = self.calculate_delay(attempt, task_type, failure_context)
                if delay > 0:
                    await asyncio.sleep(delay)

        if last_exception:
            raise last_exception
        else:
            raise RuntimeError("Retry policy failed without capturing exception")


# Default retry policies for different task types
DEFAULT_RETRY_POLICIES = {
    TaskType.RETRIEVE: RetryConfig(
        strategy=RetryStrategy.EXPONENTIAL_BACKOFF,
        max_retries=3,
        base_delay=1.0,
        max_delay=30.0,
    ),
    TaskType.WRITE: RetryConfig(
        strategy=RetryStrategy.LINEAR_BACKOFF,
        max_retries=2,
        base_delay=2.0,
        max_delay=10.0,
    ),
    TaskType.THINK: RetryConfig(
        strategy=RetryStrategy.EXPONENTIAL_BACKOFF,
        max_retries=2,
        base_delay=0.5,
        max_delay=15.0,
    ),
    TaskType.CODE_INTERPRET: RetryConfig(
        strategy=RetryStrategy.FIXED_DELAY, max_retries=1, base_delay=3.0
    ),
    TaskType.IMAGE_GENERATION: RetryConfig(
        strategy=RetryStrategy.NO_RETRY, max_retries=0
    ),
}


def create_default_retry_policy() -> RetryPolicy:
    """Create retry policy with default task-specific configurations."""
    policy = RetryPolicy()

    for task_type, config in DEFAULT_RETRY_POLICIES.items():
        policy.configure_for_task_type(task_type, config)

    return policy
