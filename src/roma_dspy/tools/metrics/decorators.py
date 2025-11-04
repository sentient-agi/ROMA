"""Decorators for toolkit and tool invocation tracking.

Provides comprehensive metrics collection for toolkit lifecycle and tool usage:
- Toolkit creation/caching/cleanup timing and success rates
- Individual tool invocation tracking with input/output sizes
- Integration with MLflow, PostgreSQL, and structured logging
"""

from __future__ import annotations

import asyncio
import functools
import time
from datetime import datetime, timezone
from typing import Any, Callable, Optional, TypeVar

from loguru import logger

from roma_dspy.core.context import ExecutionContext
from roma_dspy.tools.metrics.models import ToolkitLifecycleEvent, ToolInvocationEvent
from roma_dspy.tools.metrics.artifact_detector import (
    extract_file_paths_from_result,
    auto_register_artifacts,
)

F = TypeVar('F', bound=Callable[..., Any])


async def _detect_and_register_artifacts(
    result: Any,
    toolkit_class: str,
    tool_name: str,
    execution_id: Optional[str],
    tool_kwargs: Optional[dict] = None
) -> None:
    """
    Helper function to detect and register artifacts from tool output.

    Works for any toolkit type (builtin, MCP, etc.) and any return format.
    DRY: Single implementation used by both sync and async decorators.

    Args:
        result: Tool return value (any format)
        toolkit_class: Name of toolkit (e.g., "CoinGeckoToolkit", "MCPToolkit")
        tool_name: Name of tool that was invoked
        execution_id: Execution ID for context
        tool_kwargs: Optional tool arguments for rich description
    """
    try:
        ctx = ExecutionContext.get()
        if not ctx or not ctx.file_storage:
            return  # No context or storage, skip detection

        from pathlib import Path
        execution_dir = Path(ctx.file_storage.root)

        # Extract file paths from result (any format: JSON, string, dict, etc.)
        file_paths = extract_file_paths_from_result(result, execution_dir)

        # Auto-register as artifacts (with deduplication)
        if file_paths:
            await auto_register_artifacts(
                file_paths=file_paths,
                toolkit_class=toolkit_class,
                tool_name=tool_name,
                execution_id=execution_id,
                tool_kwargs=tool_kwargs
            )
    except Exception as e:
        # Silent failure - artifact detection is optional
        logger.debug(f"Artifact detection failed for {toolkit_class}.{tool_name}: {e}")


def track_toolkit_lifecycle(operation: str) -> Callable[[F], F]:
    """
    Decorator to track toolkit manager lifecycle operations.

    Tracks creation, caching, cleanup operations with timing and success/failure.
    Integrates with ExecutionContext for per-execution tracking.

    Args:
        operation: Operation name (create, cache_hit, cache_miss, cleanup)

    Returns:
        Decorated function with lifecycle tracking

    Example:
        @track_toolkit_lifecycle("create")
        async def _create_execution_toolkits(...):
            ...
    """
    def decorator(func: F) -> F:
        if asyncio.iscoroutinefunction(func):
            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs):
                start_time = time.time()

                # Try to get execution context (may not be set in all cases)
                execution_id = None
                try:
                    ctx = ExecutionContext.get()
                    execution_id = ctx.execution_id if ctx else None
                except Exception:
                    pass  # Context not available, continue without it

                # Extract toolkit class name if available from args
                toolkit_class = None
                if args and len(args) > 0:
                    # For methods, first arg is self
                    if hasattr(args[0], '__class__'):
                        # Try to get toolkit class from method arguments
                        for arg in args:
                            if hasattr(arg, 'class_name'):
                                toolkit_class = arg.class_name
                                break

                try:
                    result = await func(*args, **kwargs)
                    duration_ms = (time.time() - start_time) * 1000

                    # Create lifecycle event
                    event = ToolkitLifecycleEvent(
                        execution_id=execution_id or "unknown",
                        timestamp=datetime.now(timezone.utc),
                        operation=operation,
                        toolkit_class=toolkit_class,
                        duration_ms=duration_ms,
                        success=True,
                        error=None,
                        metadata={}
                    )

                    # Store event in context for batch persistence
                    if execution_id:
                        try:
                            ctx = ExecutionContext.get()
                            if ctx and hasattr(ctx, 'toolkit_events'):
                                ctx.toolkit_events.append(event)
                        except Exception:
                            pass

                    # Log to MLflow if available
                    try:
                        from roma_dspy.core.observability import MLflowManager
                        # MLflow logging would be added here if manager is accessible
                    except Exception:
                        pass

                    # Structured logging
                    logger.info(
                        f"Toolkit {operation} completed",
                        duration_ms=duration_ms,
                        operation=operation,
                        toolkit_class=toolkit_class,
                        execution_id=execution_id,
                        success=True
                    )

                    return result

                except Exception as e:
                    duration_ms = (time.time() - start_time) * 1000

                    # Create failure event
                    event = ToolkitLifecycleEvent(
                        execution_id=execution_id or "unknown",
                        timestamp=datetime.now(timezone.utc),
                        operation=operation,
                        toolkit_class=toolkit_class,
                        duration_ms=duration_ms,
                        success=False,
                        error=str(e),
                        metadata={"error_type": type(e).__name__}
                    )

                    # Store event
                    if execution_id:
                        try:
                            ctx = ExecutionContext.get()
                            if ctx and hasattr(ctx, 'toolkit_events'):
                                ctx.toolkit_events.append(event)
                        except Exception:
                            pass

                    # Error logging
                    logger.error(
                        f"Toolkit {operation} failed",
                        error=str(e),
                        error_type=type(e).__name__,
                        duration_ms=duration_ms,
                        operation=operation,
                        toolkit_class=toolkit_class,
                        execution_id=execution_id
                    )

                    raise

            return async_wrapper  # type: ignore
        else:
            # Sync version
            @functools.wraps(func)
            def sync_wrapper(*args, **kwargs):
                start_time = time.time()

                execution_id = None
                try:
                    ctx = ExecutionContext.get()
                    execution_id = ctx.execution_id if ctx else None
                except Exception:
                    pass

                toolkit_class = None
                if args and len(args) > 0:
                    if hasattr(args[0], '__class__'):
                        for arg in args:
                            if hasattr(arg, 'class_name'):
                                toolkit_class = arg.class_name
                                break

                try:
                    result = func(*args, **kwargs)
                    duration_ms = (time.time() - start_time) * 1000

                    event = ToolkitLifecycleEvent(
                        execution_id=execution_id or "unknown",
                        timestamp=datetime.now(timezone.utc),
                        operation=operation,
                        toolkit_class=toolkit_class,
                        duration_ms=duration_ms,
                        success=True,
                        error=None,
                        metadata={}
                    )

                    # Store event in context
                    if execution_id:
                        try:
                            ctx = ExecutionContext.get()
                            if ctx and hasattr(ctx, 'toolkit_events'):
                                ctx.toolkit_events.append(event)
                        except Exception:
                            pass

                    logger.info(
                        f"Toolkit {operation} completed",
                        duration_ms=duration_ms,
                        operation=operation,
                        toolkit_class=toolkit_class,
                        execution_id=execution_id,
                        success=True
                    )

                    return result

                except Exception as e:
                    duration_ms = (time.time() - start_time) * 1000

                    logger.error(
                        f"Toolkit {operation} failed",
                        error=str(e),
                        error_type=type(e).__name__,
                        duration_ms=duration_ms,
                        operation=operation,
                        toolkit_class=toolkit_class,
                        execution_id=execution_id
                    )

                    # Store failure event
                    event = ToolkitLifecycleEvent(
                        execution_id=execution_id or "unknown",
                        timestamp=datetime.now(timezone.utc),
                        operation=operation,
                        toolkit_class=toolkit_class,
                        duration_ms=duration_ms,
                        success=False,
                        error=str(e),
                        metadata={"error_type": type(e).__name__}
                    )

                    if execution_id:
                        try:
                            ctx = ExecutionContext.get()
                            if ctx and hasattr(ctx, 'toolkit_events'):
                                ctx.toolkit_events.append(event)
                        except Exception:
                            pass

                    raise

            return sync_wrapper  # type: ignore

    return decorator


def track_tool_invocation(tool_name: str, toolkit_class: str) -> Callable[[F], F]:
    """
    Decorator to track individual tool invocations.

    Captures timing, success/failure, input/output sizes, and errors for each tool call.
    Supports both sync and async tools.

    Args:
        tool_name: Name of the tool being invoked
        toolkit_class: Class name of the parent toolkit

    Returns:
        Decorated function with invocation tracking

    Example:
        @track_tool_invocation("search_web", "SerperToolkit")
        async def search_web(query: str) -> dict:
            ...
    """
    def decorator(func: F) -> F:
        if asyncio.iscoroutinefunction(func):
            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs):
                start_time = time.time()

                # Get execution context
                execution_id = None
                try:
                    ctx = ExecutionContext.get()
                    execution_id = ctx.execution_id if ctx else None
                except Exception:
                    pass

                # Calculate input size (rough estimate)
                try:
                    input_str = str(args) + str(kwargs)
                    input_size = len(input_str.encode('utf-8'))
                except Exception:
                    input_size = 0

                try:
                    result = await func(*args, **kwargs)
                    duration_ms = (time.time() - start_time) * 1000

                    # Calculate output size
                    try:
                        output_size = len(str(result).encode('utf-8'))
                    except Exception:
                        output_size = 0

                    # Create invocation event
                    event = ToolInvocationEvent(
                        execution_id=execution_id or "unknown",
                        toolkit_class=toolkit_class,
                        tool_name=tool_name,
                        invoked_at=datetime.now(timezone.utc),
                        duration_ms=duration_ms,
                        input_size_bytes=input_size,
                        output_size_bytes=output_size,
                        success=True,
                        error=None,
                        metadata={}
                    )

                    # Store in context
                    if execution_id:
                        try:
                            ctx = ExecutionContext.get()
                            if ctx and hasattr(ctx, 'tool_invocations'):
                                ctx.tool_invocations.append(event)
                        except Exception:
                            pass

                    # Debug logging (use debug to avoid spam)
                    logger.debug(
                        f"Tool invoked: {toolkit_class}.{tool_name}",
                        duration_ms=duration_ms,
                        input_size_bytes=input_size,
                        output_size_bytes=output_size,
                        success=True,
                        execution_id=execution_id
                    )

                    # Automatic artifact detection from tool output
                    await _detect_and_register_artifacts(
                        result=result,
                        toolkit_class=toolkit_class,
                        tool_name=tool_name,
                        execution_id=execution_id,
                        tool_kwargs=kwargs
                    )

                    return result

                except Exception as e:
                    duration_ms = (time.time() - start_time) * 1000

                    # Create failure event
                    event = ToolInvocationEvent(
                        execution_id=execution_id or "unknown",
                        toolkit_class=toolkit_class,
                        tool_name=tool_name,
                        invoked_at=datetime.now(timezone.utc),
                        duration_ms=duration_ms,
                        input_size_bytes=input_size,
                        output_size_bytes=0,
                        success=False,
                        error=str(e),
                        metadata={"error_type": type(e).__name__}
                    )

                    # Store in context
                    if execution_id:
                        try:
                            ctx = ExecutionContext.get()
                            if ctx and hasattr(ctx, 'tool_invocations'):
                                ctx.tool_invocations.append(event)
                        except Exception:
                            pass

                    # Error logging
                    logger.error(
                        f"Tool failed: {toolkit_class}.{tool_name}",
                        error=str(e),
                        error_type=type(e).__name__,
                        duration_ms=duration_ms,
                        execution_id=execution_id
                    )

                    raise

            return async_wrapper  # type: ignore
        else:
            # Sync version
            @functools.wraps(func)
            def sync_wrapper(*args, **kwargs):
                start_time = time.time()

                execution_id = None
                try:
                    ctx = ExecutionContext.get()
                    execution_id = ctx.execution_id if ctx else None
                except Exception:
                    pass

                try:
                    input_str = str(args) + str(kwargs)
                    input_size = len(input_str.encode('utf-8'))
                except Exception:
                    input_size = 0

                try:
                    result = func(*args, **kwargs)
                    duration_ms = (time.time() - start_time) * 1000

                    try:
                        output_size = len(str(result).encode('utf-8'))
                    except Exception:
                        output_size = 0

                    event = ToolInvocationEvent(
                        execution_id=execution_id or "unknown",
                        toolkit_class=toolkit_class,
                        tool_name=tool_name,
                        invoked_at=datetime.now(timezone.utc),
                        duration_ms=duration_ms,
                        input_size_bytes=input_size,
                        output_size_bytes=output_size,
                        success=True,
                        error=None,
                        metadata={}
                    )

                    # Store in context
                    if execution_id:
                        try:
                            ctx = ExecutionContext.get()
                            if ctx and hasattr(ctx, 'tool_invocations'):
                                ctx.tool_invocations.append(event)
                        except Exception:
                            pass

                    logger.debug(
                        f"Tool invoked: {toolkit_class}.{tool_name}",
                        duration_ms=duration_ms,
                        success=True,
                        execution_id=execution_id
                    )

                    # Automatic artifact detection from tool output (sync version)
                    # Run async detection in event loop
                    try:
                        loop = asyncio.get_event_loop()
                        if loop.is_running():
                            # Create task (fire and forget - don't block sync tool)
                            asyncio.create_task(_detect_and_register_artifacts(
                                result=result,
                                toolkit_class=toolkit_class,
                                tool_name=tool_name,
                                execution_id=execution_id,
                                tool_kwargs=kwargs
                            ))
                        else:
                            # Run in existing event loop
                            loop.run_until_complete(_detect_and_register_artifacts(
                                result=result,
                                toolkit_class=toolkit_class,
                                tool_name=tool_name,
                                execution_id=execution_id,
                                tool_kwargs=kwargs
                            ))
                    except RuntimeError:
                        # No event loop, create new one
                        asyncio.run(_detect_and_register_artifacts(
                            result=result,
                            toolkit_class=toolkit_class,
                            tool_name=tool_name,
                            execution_id=execution_id,
                            tool_kwargs=kwargs
                        ))
                    except Exception as e:
                        # Silent failure
                        logger.debug(f"Artifact detection failed: {e}")

                    return result

                except Exception as e:
                    duration_ms = (time.time() - start_time) * 1000

                    logger.error(
                        f"Tool failed: {toolkit_class}.{tool_name}",
                        error=str(e),
                        error_type=type(e).__name__,
                        duration_ms=duration_ms,
                        execution_id=execution_id
                    )

                    # Store failure event
                    event = ToolInvocationEvent(
                        execution_id=execution_id or "unknown",
                        toolkit_class=toolkit_class,
                        tool_name=tool_name,
                        invoked_at=datetime.now(timezone.utc),
                        duration_ms=duration_ms,
                        input_size_bytes=input_size,
                        output_size_bytes=0,
                        success=False,
                        error=str(e),
                        metadata={"error_type": type(e).__name__}
                    )

                    if execution_id:
                        try:
                            ctx = ExecutionContext.get()
                            if ctx and hasattr(ctx, 'tool_invocations'):
                                ctx.tool_invocations.append(event)
                        except Exception:
                            pass

                    raise

            return sync_wrapper  # type: ignore

    return decorator


# Alias for backward compatibility with measure_execution_time pattern
def measure_toolkit_operation(operation: str) -> Callable[[F], F]:
    """
    Alias for track_toolkit_lifecycle following naming convention.

    Args:
        operation: Operation name to track

    Returns:
        Decorated function with lifecycle tracking
    """
    return track_toolkit_lifecycle(operation)