"""
Circuit breaker implementation for module-level failure protection.

Prevents cascading failures by temporarily disabling failing modules
and providing graceful degradation.
"""

import time
import asyncio
from typing import Callable, Dict, Any, Optional

from roma_dspy.types.resilience_types import CircuitState, CircuitOpenError
from roma_dspy.types.resilience_models import (
    CircuitBreakerConfig,
    CircuitMetrics,
    FailureContext,
)


class CircuitBreaker:
    """
    Circuit breaker for protecting against cascading module failures.

    Implements three states:
    - CLOSED: Normal operation, tracking failures
    - OPEN: Rejecting calls, waiting for recovery timeout
    - HALF_OPEN: Testing recovery with limited calls
    """

    def __init__(self, config: Optional[CircuitBreakerConfig] = None):
        """Initialize circuit breaker with configuration."""
        self.config = config or CircuitBreakerConfig()
        self.state = CircuitState.CLOSED
        self.metrics = CircuitMetrics()
        self._state_change_time = time.time()
        self._half_open_success_count = 0

    def _should_trip(self) -> bool:
        """Determine if circuit should trip to OPEN state."""
        if self.state != CircuitState.CLOSED:
            return False

        failure_rate = self.metrics.get_failure_rate(self.config.evaluation_window)
        return self.metrics.failure_count >= self.config.failure_threshold

    def _should_attempt_reset(self) -> bool:
        """Determine if circuit should attempt reset to HALF_OPEN."""
        if self.state != CircuitState.OPEN:
            return False

        time_since_open = time.time() - self._state_change_time
        return time_since_open >= self.config.recovery_timeout

    def _transition_to(self, new_state: CircuitState) -> None:
        """Transition circuit to new state."""
        self.state = new_state
        self._state_change_time = time.time()

        if new_state == CircuitState.HALF_OPEN:
            self._half_open_success_count = 0

    async def call(
        self,
        func: Callable,
        *args,
        failure_context: Optional[FailureContext] = None,
        **kwargs,
    ) -> Any:
        """
        Execute function with circuit breaker protection.

        Args:
            func: Function to execute
            failure_context: Context for failure tracking

        Returns:
            Result of function execution

        Raises:
            CircuitOpenError: If circuit is open
            Exception: Original exception if function fails
        """
        # Check if we should attempt reset
        if self._should_attempt_reset():
            self._transition_to(CircuitState.HALF_OPEN)

        # Reject calls if circuit is open
        if self.state == CircuitState.OPEN:
            raise CircuitOpenError(
                f"Circuit breaker is open. "
                f"Last failure: {self.metrics.last_failure_time}"
            )

        # Execute function
        try:
            if asyncio.iscoroutinefunction(func):
                result = await func(*args, **kwargs)
            else:
                result = func(*args, **kwargs)

            # Record success
            self._record_success()
            return result

        except Exception as e:
            # Record failure
            self._record_failure(e, failure_context)
            raise

    def _record_success(self) -> None:
        """Record successful execution and update state."""
        self.metrics.record_success()

        if self.state == CircuitState.HALF_OPEN:
            self._half_open_success_count += 1

            # Reset to CLOSED if enough successes
            if self._half_open_success_count >= self.config.success_threshold:
                self._transition_to(CircuitState.CLOSED)
                self.metrics = CircuitMetrics()  # Reset metrics

    def _record_failure(
        self, exception: Exception, failure_context: Optional[FailureContext] = None
    ) -> None:
        """Record failed execution and update state."""
        self.metrics.record_failure()

        # Trip circuit if failure threshold reached
        if self._should_trip():
            self._transition_to(CircuitState.OPEN)

        # Half-open state goes back to open on failure
        elif self.state == CircuitState.HALF_OPEN:
            self._transition_to(CircuitState.OPEN)

    def get_status(self) -> Dict[str, Any]:
        """Get current circuit breaker status."""
        return {
            "state": self.state.value,
            "failure_count": self.metrics.failure_count,
            "success_count": self.metrics.success_count,
            "total_calls": self.metrics.total_calls,
            "failure_rate": self.metrics.get_failure_rate(
                self.config.evaluation_window
            ),
            "time_since_state_change": time.time() - self._state_change_time,
            "last_failure_time": self.metrics.last_failure_time,
        }

    def reset(self) -> None:
        """Manually reset circuit breaker to CLOSED state."""
        self._transition_to(CircuitState.CLOSED)
        self.metrics = CircuitMetrics()


class ModuleCircuitBreaker:
    """Circuit breaker manager for different module types."""

    def __init__(self):
        """Initialize module circuit breaker manager."""
        self._breakers: Dict[str, CircuitBreaker] = {}
        self._default_config = CircuitBreakerConfig()

    def get_breaker(
        self, module_name: str, config: Optional[CircuitBreakerConfig] = None
    ) -> CircuitBreaker:
        """Get or create circuit breaker for module."""
        if module_name not in self._breakers:
            breaker_config = config or self._default_config
            self._breakers[module_name] = CircuitBreaker(breaker_config)

        return self._breakers[module_name]

    async def call_with_breaker(
        self,
        module_name: str,
        func: Callable,
        *args,
        config: Optional[CircuitBreakerConfig] = None,
        failure_context: Optional[FailureContext] = None,
        **kwargs,
    ) -> Any:
        """Execute function with module-specific circuit breaker."""
        breaker = self.get_breaker(module_name, config)
        return await breaker.call(
            func, *args, failure_context=failure_context, **kwargs
        )

    def get_all_status(self) -> Dict[str, Dict[str, Any]]:
        """Get status of all circuit breakers."""
        return {
            module: breaker.get_status() for module, breaker in self._breakers.items()
        }

    def reset_all(self) -> None:
        """Reset all circuit breakers."""
        for breaker in self._breakers.values():
            breaker.reset()


# Global module circuit breaker instance
module_circuit_breaker = ModuleCircuitBreaker()
