"""
Execution context for toolkit lifecycle management.

This module provides execution-scoped context propagation using Python's contextvars.
It enables toolkits to access execution-specific FileStorage without explicit parameter passing
through the call stack.

The ExecutionContext is set once at the beginning of each solve() execution and automatically
propagates to all modules and toolkits within that execution, ensuring thread-safety and
async-safety.
"""

from contextvars import ContextVar
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from roma_dspy.core.storage import FileStorage
    from roma_dspy.tools.metrics.models import (
        ExecutionEventData,
        ToolkitLifecycleEvent,
        ToolInvocationEvent,
    )

from roma_dspy.core.artifacts import ArtifactRegistry


class ExecutionContext:
    """
    Execution-scoped context for toolkit file storage management.

    This class serves two purposes:
    1. Data container: Holds execution_id and file_storage reference
    2. Context propagation: Uses contextvars for thread-safe, async-safe propagation

    Usage:
        # Set context at execution start (in RecursiveSolver.solve)
        token = ExecutionContext.set(execution_id="exec_123", file_storage=storage)
        try:
            # ... execution happens, context automatically available ...
        finally:
            ExecutionContext.reset(token)

        # Get context anywhere in the execution
        ctx = ExecutionContext.get()
        if ctx:
            file_storage = ctx.file_storage
            execution_id = ctx.execution_id

    Thread Safety:
        contextvars are thread-local and async-task-local, ensuring isolation
        between concurrent executions even in multi-threaded or async environments.

    Performance:
        contextvars have O(1) read access, negligible overhead compared to
        thread-local storage or explicit parameter passing.
    """

    # Class-level contextvar for thread-safe storage
    _context: ContextVar[Optional["ExecutionContext"]] = ContextVar(
        "execution_context", default=None
    )

    def __init__(self, execution_id: str, file_storage: "FileStorage"):
        """
        Initialize execution context.

        Args:
            execution_id: Unique identifier for this execution
            file_storage: FileStorage instance for this execution
        """
        self.execution_id = execution_id
        self.file_storage = file_storage

        # Artifact registry for this execution
        self.artifact_registry = ArtifactRegistry()

        # Metrics collection buffers for observability
        # These accumulate events during execution and are persisted at the end
        self.toolkit_events: List["ToolkitLifecycleEvent"] = []
        self.tool_invocations: List["ToolInvocationEvent"] = []
        self.execution_events: List["ExecutionEventData"] = []

    @classmethod
    def set(cls, execution_id: str, file_storage: "FileStorage") -> "ContextVar.Token":
        """
        Set execution context for current execution scope.

        This should be called once at the beginning of solve() execution.
        Returns a token that can be used to reset the context.

        Args:
            execution_id: Unique identifier for this execution
            file_storage: FileStorage instance for this execution

        Returns:
            Token for resetting context (use with reset())

        Example:
            token = ExecutionContext.set("exec_123", storage)
            try:
                # ... execution ...
            finally:
                ExecutionContext.reset(token)
        """
        ctx = cls(execution_id=execution_id, file_storage=file_storage)
        return cls._context.set(ctx)

    @classmethod
    def get(cls) -> Optional["ExecutionContext"]:
        """
        Get current execution context.

        Returns:
            ExecutionContext if set, None otherwise

        Example:
            ctx = ExecutionContext.get()
            if ctx:
                storage = ctx.file_storage
        """
        return cls._context.get()

    @classmethod
    def reset(cls, token: "ContextVar.Token") -> None:
        """
        Reset execution context to previous state (sync version).

        Note: This method cannot auto-persist metrics as it's synchronous.
        For async code, use reset_async() instead to enable auto-persistence.

        Args:
            token: Token returned by set()

        Example:
            token = ExecutionContext.set("exec_123", storage)
            try:
                # ... execution ...
            finally:
                ExecutionContext.reset(token)
        """
        cls._context.reset(token)

    @classmethod
    async def reset_async(
        cls,
        token: "ContextVar.Token",
        postgres_storage: Optional[Any] = None,
        auto_persist: bool = True
    ) -> None:
        """
        Reset execution context to previous state (async version with auto-persist).

        This method automatically persists accumulated metrics before resetting
        the context, eliminating the need for manual persistence in finally blocks.

        Args:
            token: Token returned by set()
            postgres_storage: Optional PostgreSQL storage for metrics persistence
            auto_persist: Whether to automatically persist metrics (default: True)

        Example:
            token = ExecutionContext.set("exec_123", storage)
            try:
                # ... execution ...
            finally:
                await ExecutionContext.reset_async(token, postgres_storage)
        """
        # Auto-persist metrics before resetting if enabled
        if auto_persist and postgres_storage:
            ctx = cls.get()
            if ctx:
                try:
                    await ctx.persist_metrics(postgres_storage)
                except Exception as e:
                    from loguru import logger
                    logger.error(f"Failed to auto-persist metrics during reset: {e}")

        # Reset context
        cls._context.reset(token)

    @classmethod
    def get_file_storage(cls) -> Optional["FileStorage"]:
        """
        Convenience method to get FileStorage from current context.

        Returns:
            FileStorage if context is set, None otherwise

        Example:
            storage = ExecutionContext.get_file_storage()
            if storage:
                artifacts_path = storage.get_artifacts_path()
        """
        ctx = cls.get()
        return ctx.file_storage if ctx else None

    @classmethod
    def get_execution_id(cls) -> Optional[str]:
        """
        Convenience method to get execution_id from current context.

        Returns:
            execution_id if context is set, None otherwise

        Example:
            exec_id = ExecutionContext.get_execution_id()
            if exec_id:
                logger.info(f"Running in execution {exec_id}")
        """
        ctx = cls.get()
        return ctx.execution_id if ctx else None

    @classmethod
    def get_artifact_registry(cls) -> Optional[ArtifactRegistry]:
        """
        Convenience method to get artifact_registry from current context.

        Returns:
            ArtifactRegistry if context is set, None otherwise

        Example:
            registry = ExecutionContext.get_artifact_registry()
            if registry:
                await registry.register(artifact)
        """
        ctx = cls.get()
        return ctx.artifact_registry if ctx else None

    def emit_execution_event(
        self,
        event_type: str,
        task_id: Optional[str] = None,
        dag_id: Optional[str] = None,
        event_data: Optional[Dict[str, Any]] = None,
        priority: int = 0,
    ) -> None:
        """
        Emit an execution event to be persisted later.

        This method buffers execution events during RecursiveSolver execution.
        Events are automatically persisted when reset_async() is called.

        Args:
            event_type: Event type (execution_start, atomize_complete, plan_complete, etc.)
            task_id: Optional task identifier
            dag_id: Optional DAG identifier
            event_data: Optional event payload (module results, timing, error info, etc.)
            priority: Event priority (default 0)

        Example:
            ctx = ExecutionContext.get()
            if ctx:
                ctx.emit_execution_event(
                    event_type="plan_complete",
                    task_id="task_123",
                    event_data={"subtasks": 5, "duration_ms": 100}
                )
        """
        from roma_dspy.tools.metrics.models import ExecutionEventData

        event = ExecutionEventData(
            execution_id=self.execution_id,
            timestamp=datetime.now(timezone.utc),
            event_type=event_type,
            priority=priority,
            task_id=task_id,
            dag_id=dag_id,
            event_data=event_data or {},
            dropped=False,
        )
        self.execution_events.append(event)

    async def persist_metrics(self, postgres_storage) -> None:
        """
        Persist accumulated observability data to PostgreSQL.

        This method is called before reset() to ensure all collected metrics
        and events are saved to the database.

        Args:
            postgres_storage: PostgresStorage instance for database operations

        Note:
            Errors during persistence are logged but don't raise exceptions,
            ensuring that execution cleanup proceeds even if metrics fail to save.
        """
        if not postgres_storage:
            return

        try:
            from loguru import logger

            toolkit_events_count = len(self.toolkit_events)
            tool_invocations_count = len(self.tool_invocations)
            execution_events_count = len(self.execution_events)

            # Persist toolkit lifecycle events
            for event in self.toolkit_events:
                try:
                    await postgres_storage.save_toolkit_trace(
                        execution_id=event.execution_id,
                        operation=event.operation,
                        toolkit_class=event.toolkit_class,
                        duration_ms=event.duration_ms,
                        success=event.success,
                        error=event.error,
                        metadata=event.metadata
                    )
                except Exception as e:
                    logger.error(f"Failed to persist toolkit lifecycle event: {e}")

            # Persist tool invocation events
            for event in self.tool_invocations:
                try:
                    await postgres_storage.save_tool_invocation_trace(
                        execution_id=event.execution_id,
                        toolkit_class=event.toolkit_class,
                        tool_name=event.tool_name,
                        duration_ms=event.duration_ms,
                        input_size_bytes=event.input_size_bytes,
                        output_size_bytes=event.output_size_bytes,
                        success=event.success,
                        error=event.error,
                        metadata=event.metadata
                    )
                except Exception as e:
                    logger.error(f"Failed to persist tool invocation event: {e}")

            # Persist execution events
            for event in self.execution_events:
                try:
                    await postgres_storage.save_event_trace(
                        execution_id=event.execution_id,
                        event_type=event.event_type,
                        priority=event.priority,
                        task_id=event.task_id,
                        dag_id=event.dag_id,
                        event_data=event.event_data,
                        dropped=event.dropped
                    )
                except Exception as e:
                    logger.error(f"Failed to persist execution event: {e}")

            # Log summary
            if toolkit_events_count > 0 or tool_invocations_count > 0 or execution_events_count > 0:
                logger.info(
                    f"Persisted observability data for {self.execution_id}",
                    toolkit_events=toolkit_events_count,
                    tool_invocations=tool_invocations_count,
                    execution_events=execution_events_count,
                    execution_id=self.execution_id
                )

        except Exception as e:
            from loguru import logger
            logger.error(f"Failed to persist observability data for {self.execution_id}: {e}")