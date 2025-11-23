"""
Decorators for task and module resilience patterns.

Provides clean integration of retry policies and circuit breakers
without modifying existing method signatures.
"""

import asyncio
import functools
import time
from typing import Callable, Optional, Any, TypeVar, Union
from datetime import datetime

from loguru import logger

from roma_dspy.types.task_type import TaskType
from roma_dspy.types.task_status import TaskStatus
from roma_dspy.types.resilience_types import CircuitOpenError, CircuitState
from roma_dspy.types.resilience_models import (
    RetryConfig,
    CircuitBreakerConfig,
    FailureContext,
)
from roma_dspy.resilience.retry_policy import RetryPolicy, create_default_retry_policy
from roma_dspy.resilience.circuit_breaker import module_circuit_breaker

F = TypeVar("F", bound=Callable[..., Any])


def with_retry(
    retry_config: Optional[RetryConfig] = None, task_type: Optional[TaskType] = None
) -> Callable[[F], F]:
    """
    Decorator to add retry logic with exponential backoff to functions.

    Args:
        retry_config: Custom retry configuration
        task_type: Task type for task-specific retry policies

    Returns:
        Decorated function with retry capability
    """

    def decorator(func: F) -> F:
        retry_policy = (
            RetryPolicy(retry_config) if retry_config else create_default_retry_policy()
        )

        if asyncio.iscoroutinefunction(func):

            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs):
                last_exception = None

                for attempt in range(
                    retry_policy.get_config_for_task(task_type).max_retries + 1
                ):
                    try:
                        return await func(*args, **kwargs)
                    except Exception as e:
                        # Don't retry circuit open errors or cancellation
                        if isinstance(e, (CircuitOpenError, asyncio.CancelledError)):
                            raise

                        last_exception = e

                        if not retry_policy.should_retry(attempt, task_type):
                            break

                        failure_context = FailureContext(
                            error_type=type(e).__name__,
                            error_message=str(e),
                            task_type=task_type,
                            metadata={
                                "function": func.__name__,
                                "attempt": attempt,
                                "args_count": len(args),
                                "kwargs_keys": list(kwargs.keys()),
                            },
                        )

                        delay = retry_policy.calculate_delay(
                            attempt, task_type, failure_context
                        )
                        if delay > 0:
                            await asyncio.sleep(delay)

                if last_exception:
                    raise last_exception

            return async_wrapper
        else:

            @functools.wraps(func)
            def sync_wrapper(*args, **kwargs):
                last_exception = None

                for attempt in range(
                    retry_policy.get_config_for_task(task_type).max_retries + 1
                ):
                    try:
                        return func(*args, **kwargs)
                    except Exception as e:
                        # Don't retry circuit open errors
                        if isinstance(e, CircuitOpenError):
                            raise

                        last_exception = e

                        if not retry_policy.should_retry(attempt, task_type):
                            break

                        failure_context = FailureContext(
                            error_type=type(e).__name__,
                            error_message=str(e),
                            task_type=task_type,
                            metadata={
                                "function": func.__name__,
                                "attempt": attempt,
                                "args_count": len(args),
                                "kwargs_keys": list(kwargs.keys()),
                            },
                        )

                        delay = retry_policy.calculate_delay(
                            attempt, task_type, failure_context
                        )
                        if delay > 0:
                            time.sleep(delay)

                if last_exception:
                    raise last_exception

            return sync_wrapper

    return decorator


def with_circuit_breaker(
    module_name: Optional[str] = None, config: Optional[CircuitBreakerConfig] = None
) -> Callable[[F], F]:
    """
    Decorator to add circuit breaker protection to functions.

    Args:
        module_name: Name for circuit breaker identification
        config: Custom circuit breaker configuration

    Returns:
        Decorated function with circuit breaker protection
    """

    def decorator(func: F) -> F:
        breaker_name = module_name or func.__name__

        if asyncio.iscoroutinefunction(func):

            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs):
                failure_context = FailureContext(
                    error_type="CircuitBreakerExecution",
                    error_message=f"Circuit breaker execution for {breaker_name}",
                    module_name=breaker_name,
                    metadata={
                        "function": func.__name__,
                        "args_count": len(args),
                        "kwargs_keys": list(kwargs.keys()),
                    },
                )

                async def execute():
                    return await func(*args, **kwargs)

                return await module_circuit_breaker.call_with_breaker(
                    breaker_name,
                    execute,
                    config=config,
                    failure_context=failure_context,
                )

            return async_wrapper
        else:

            @functools.wraps(func)
            def sync_wrapper(*args, **kwargs):
                failure_context = FailureContext(
                    error_type="CircuitBreakerExecution",
                    error_message=f"Circuit breaker execution for {breaker_name}",
                    module_name=breaker_name,
                    metadata={
                        "function": func.__name__,
                        "args_count": len(args),
                        "kwargs_keys": list(kwargs.keys()),
                    },
                )

                breaker = module_circuit_breaker.get_breaker(breaker_name, config)

                # Manual circuit breaker logic for sync functions
                if breaker._should_attempt_reset():
                    breaker._transition_to(CircuitState.HALF_OPEN)

                if breaker.state.value == "open":
                    raise CircuitOpenError(
                        f"Circuit breaker is open for: {breaker_name}"
                    )

                try:
                    result = func(*args, **kwargs)
                    breaker._record_success()
                    return result
                except Exception as e:
                    breaker._record_failure(e, failure_context)
                    raise

            return sync_wrapper

    return decorator


def with_module_resilience(
    module_name: Optional[str] = None,
    retry_config: Optional[RetryConfig] = None,
    circuit_config: Optional[CircuitBreakerConfig] = None,
    task_type: Optional[TaskType] = None,
) -> Callable[[F], F]:
    """
    Decorator combining retry policy and circuit breaker for module functions.

    Args:
        module_name: Module name for identification
        retry_config: Custom retry configuration
        circuit_config: Custom circuit breaker configuration
        task_type: Task type for task-specific policies

    Returns:
        Decorated function with full resilience protection
    """

    def decorator(func: F) -> F:
        # Apply retry first (inner), then circuit breaker (outer)
        # This ensures circuit breaker sees aggregate retry behavior, not individual attempts
        retry_protected = with_retry(retry_config=retry_config, task_type=task_type)(
            func
        )

        circuit_protected = with_circuit_breaker(
            module_name=module_name, config=circuit_config
        )(retry_protected)

        return circuit_protected

    return decorator


def measure_execution_time(func: F) -> F:
    """
    Decorator to measure and log execution time with integrated logging.

    Extracts token_metrics and messages from the result object and returns them
    along with the result and duration. Automatically logs start, completion, and errors.

    Args:
        func: Function to measure

    Returns:
        Decorated function with timing measurement, metrics extraction, and logging
    """

    if asyncio.iscoroutinefunction(func):

        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            # Extract context for logging (module name from first arg if available)
            context_name = func.__name__
            if args and hasattr(args[0], "__class__"):
                context_name = f"{args[0].__class__.__name__}.{func.__name__}"

            # Log execution start
            logger.debug(
                f"{context_name} async starting | args_count={len(args)} | kwargs={list(kwargs.keys())}"
            )

            start_time = datetime.now()
            try:
                result = await func(*args, **kwargs)
                duration = (datetime.now() - start_time).total_seconds()

                # Extract metrics from result object
                token_metrics = getattr(result, "token_metrics", None) or getattr(
                    result, "token_usage", None
                )
                messages = getattr(result, "messages", None)

                # Log successful completion with metrics
                log_msg = f"{context_name} async completed | duration={duration:.2f}s"
                if token_metrics:
                    log_msg += f" | tokens={getattr(token_metrics, 'total', 'N/A')}"
                logger.info(log_msg)

                return result, duration, token_metrics, messages
            except Exception as e:
                duration = (datetime.now() - start_time).total_seconds()
                # Attach duration to exception for logging
                e.__dict__["execution_duration"] = duration

                # Log failure with duration and full traceback
                import traceback

                tb_str = "".join(
                    traceback.format_exception(type(e), e, e.__traceback__)
                )
                logger.error(
                    f"{context_name} async failed | duration={duration:.2f}s | error={str(e)}\nFull traceback:\n{tb_str}"
                )
                raise

        return async_wrapper
    else:

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            # Extract context for logging (module name from first arg if available)
            context_name = func.__name__
            if args and hasattr(args[0], "__class__"):
                context_name = f"{args[0].__class__.__name__}.{func.__name__}"

            # Log execution start
            logger.debug(
                f"{context_name} starting | args_count={len(args)} | kwargs={list(kwargs.keys())}"
            )

            start_time = datetime.now()
            try:
                result = func(*args, **kwargs)
                duration = (datetime.now() - start_time).total_seconds()

                # Extract metrics from result object
                token_metrics = getattr(result, "token_metrics", None) or getattr(
                    result, "token_usage", None
                )
                messages = getattr(result, "messages", None)

                # Log successful completion with metrics
                log_msg = f"{context_name} completed | duration={duration:.2f}s"
                if token_metrics:
                    log_msg += f" | tokens={getattr(token_metrics, 'total', 'N/A')}"
                logger.info(log_msg)

                return result, duration, token_metrics, messages
            except Exception as e:
                duration = (datetime.now() - start_time).total_seconds()
                # Attach duration to exception for logging
                e.__dict__["execution_duration"] = duration

                # Log failure with duration
                logger.error(
                    f"{context_name} failed | duration={duration:.2f}s | error={str(e)}",
                    exc_info=True,
                )
                raise

        return sync_wrapper
