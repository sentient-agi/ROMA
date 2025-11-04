"""
Recursive solver for hierarchical task decomposition with depth constraints.
"""

import asyncio
import threading
import warnings
from datetime import datetime, UTC
from typing import Callable, Optional, Union, Tuple, Dict, List, TYPE_CHECKING

import dspy
from loguru import logger

from roma_dspy.core.engine import TaskDAG
from roma_dspy.core.engine.event_loop import EventLoopController
from roma_dspy.core.engine.runtime import ModuleRuntime
from roma_dspy.core.registry import AgentRegistry
from roma_dspy.core.factory.agent_factory import AgentFactory
from roma_dspy.core.signatures import TaskNode
from roma_dspy.core.storage import FileStorage, PostgresStorage
from roma_dspy.core.context import ContextManager, ExecutionContext
from roma_dspy.types import TaskStatus, AgentType, ExecutionEventType
from roma_dspy.types.checkpoint_types import CheckpointTrigger
from roma_dspy.types.checkpoint_models import CheckpointConfig
from roma_dspy.resilience.checkpoint_manager import CheckpointManager
from roma_dspy.config.schemas.root import ROMAConfig
from roma_dspy.core.observability import MLflowManager, ObservabilityManager
from roma_dspy.tools.base.manager import ToolkitManager

if TYPE_CHECKING:
    pass

# Suppress DSPy warnings about forward() usage
warnings.filterwarnings("ignore", message="Calling module.forward.*is discouraged")


class RecursiveSolver:
    """
    Implements recursive hierarchical task decomposition algorithm.

    Key features:
    - Maximum recursion depth constraint with forced execution
    - Comprehensive execution tracking for all modules
    - State-based execution flow
    - Nested DAG management for hierarchical decomposition
    - Async and sync execution support
    - Integrated visualization support
    """

    def __init__(
        self,
        config: Optional["ROMAConfig"] = None,
        registry: Optional[AgentRegistry] = None,
        max_depth: Optional[int] = None,
        enable_logging: bool = False,
        enable_checkpoints: bool = True,
        checkpoint_config: Optional[CheckpointConfig] = None
    ):
        """
        Initialize the recursive solver.

        Args:
            config: ROMAConfig instance with complete configuration
            registry: Pre-configured AgentRegistry (overrides config)
            max_depth: Maximum recursion depth (overrides config)
            enable_logging: Whether to enable debug logging
            enable_checkpoints: Whether to enable checkpointing
            checkpoint_config: Checkpoint configuration (overrides config)
        """
        # Store config for later use (needed for FileStorage creation)
        self.config = config

        # Initialize registry from config or use provided
        if registry is not None:
            self.registry = registry
            self.max_depth = max_depth or 2
        elif config is not None:
            factory = AgentFactory()
            self.registry = AgentRegistry()
            self.registry.initialize_from_config(config, factory)
            self.max_depth = max_depth or config.runtime.max_depth
        else:
            raise ValueError("Either 'config' or 'registry' must be provided")

        # Initialize Postgres storage if enabled
        self.postgres_storage = None
        if config and config.storage and config.storage.postgres and config.storage.postgres.enabled:
            self.postgres_storage = PostgresStorage(config.storage.postgres)

        # Initialize checkpoint system
        self.checkpoint_enabled = enable_checkpoints
        checkpoint_cfg = checkpoint_config or (config.resilience.checkpoint if config else CheckpointConfig())
        self.checkpoint_manager = (
            CheckpointManager(checkpoint_cfg, postgres_storage=self.postgres_storage)
            if enable_checkpoints else None
        )

        # Initialize MLflow tracing
        self.mlflow_manager = None
        if config and config.observability and config.observability.mlflow and config.observability.mlflow.enabled:
            self.mlflow_manager = MLflowManager(config.observability.mlflow)
            self.mlflow_manager.initialize()

        # Initialize runtime with registry and config
        self.runtime = ModuleRuntime(registry=self.registry, config=config)

        # Initialize observability manager
        from roma_dspy.core.observability import ObservabilityManager
        self.observability = ObservabilityManager(
            postgres_storage=self.postgres_storage,
            mlflow_manager=self.mlflow_manager,
            runtime=self.runtime
        )

        # Initialize toolkit manager
        self.toolkit_manager = ToolkitManager.get_instance()

        # Configure logging (managed by loguru now)
        # enable_logging controls whether debug logs are shown
        self.enable_logging = enable_logging

        # Note: Loguru configuration is handled in logging_config.py
        # The enable_logging flag is used for checkpoint metadata

        # Configure DSPy cache system
        if config and config.runtime.cache.enabled:
            self._configure_dspy_cache(config.runtime.cache)
        elif not config:
            # Registry mode: use default cache config
            from roma_dspy.config.schemas.base import CacheConfig
            self._configure_dspy_cache(CacheConfig())

        # Thread-safe storage for last_dag (fixes GEPA parallel execution race condition)
        self._local = threading.local()

    @property
    def last_dag(self) -> Optional[TaskDAG]:
        """Get last DAG for current thread (thread-safe)."""
        return getattr(self._local, 'last_dag', None)

    @last_dag.setter
    def last_dag(self, value: Optional[TaskDAG]) -> None:
        """Set last DAG for current thread (thread-safe)."""
        self._local.last_dag = value

    def __getstate__(self):
        """
        Custom pickle serialization to handle unpicklable objects.

        GEPA (and other DSPy optimizers) use multiprocessing which requires
        pickling the solver. We exclude unpicklable objects like threading.local,
        database connections, locks, and singleton managers.

        The config and registry are preserved since they're needed to recreate
        the solver in the new process.
        """
        state = self.__dict__.copy()

        # Remove ALL unpicklable objects
        state.pop('_local', None)  # threading.local
        state.pop('postgres_storage', None)  # Has _ThreadLocalState
        state.pop('checkpoint_manager', None)  # Has _ThreadLocalState
        state.pop('mlflow_manager', None)  # Has module object
        state.pop('observability', None)  # Has _ThreadLocalState
        state.pop('runtime', None)  # Has _thread.lock
        state.pop('toolkit_manager', None)  # Has _thread.lock
        state.pop('registry', None)  # Has _thread.lock

        return state

    def __setstate__(self, state):
        """
        Custom pickle deserialization to restore unpicklable objects.

        After unpickling, we recreate the excluded objects. Since GEPA runs
        in separate processes, each process will have its own instances of
        these objects. This matches the initialization logic in __init__.
        """
        self.__dict__.update(state)

        # Recreate threading.local
        self._local = threading.local()

        # Recreate registry from config
        self.registry = AgentRegistry()
        if self.config:
            factory = AgentFactory()
            self.registry.initialize_from_config(self.config, factory)

        # Recreate PostgresStorage if it was enabled
        if self.config and self.config.storage and self.config.storage.postgres and self.config.storage.postgres.enabled:
            self.postgres_storage = PostgresStorage(self.config.storage.postgres)
        else:
            self.postgres_storage = None

        # Recreate checkpoint system
        checkpoint_cfg = self.config.resilience.checkpoint if self.config else CheckpointConfig()
        self.checkpoint_manager = (
            CheckpointManager(checkpoint_cfg, postgres_storage=self.postgres_storage)
            if self.checkpoint_enabled else None
        )

        # Recreate MLflow tracing
        if self.config and self.config.observability and self.config.observability.mlflow and self.config.observability.mlflow.enabled:
            self.mlflow_manager = MLflowManager(self.config.observability.mlflow)
            self.mlflow_manager.initialize()
        else:
            self.mlflow_manager = None

        # Recreate runtime with registry and config
        self.runtime = ModuleRuntime(registry=self.registry, config=self.config)

        # Recreate observability manager
        self.observability = ObservabilityManager(
            postgres_storage=self.postgres_storage,
            mlflow_manager=self.mlflow_manager,
            runtime=self.runtime
        )

        # Recreate ToolkitManager (singleton pattern will return same instance in this process)
        self.toolkit_manager = ToolkitManager.get_instance()

    def _configure_dspy_cache(self, cache_config: "CacheConfig") -> None:
        """
        Configure DSPy cache system from ROMA config.

        Args:
            cache_config: CacheConfig instance with cache settings
        """
        import os

        # Expand cache directory (handle ~, env vars)
        cache_dir = os.path.expanduser(cache_config.disk_cache_dir)

        # Ensure directory exists
        os.makedirs(cache_dir, exist_ok=True)

        try:
            dspy.configure_cache(
                enable_disk_cache=cache_config.enable_disk_cache,
                enable_memory_cache=cache_config.enable_memory_cache,
                disk_cache_dir=cache_dir,
                disk_size_limit_bytes=cache_config.disk_size_limit_bytes,
                memory_max_entries=cache_config.memory_max_entries
            )
            logger.info(
                f"DSPy cache configured: disk={cache_config.enable_disk_cache}, "
                f"memory={cache_config.enable_memory_cache}, dir={cache_dir}"
            )
        except Exception as e:
            logger.warning(f"Failed to configure DSPy cache: {e}")
            # Non-fatal: cache will use defaults

    def _emit_execution_event(
        self,
        event_type: Union[str, ExecutionEventType],
        task_id: Optional[str] = None,
        dag_id: Optional[str] = None,
        event_data: Optional[Dict] = None
    ) -> None:
        """
        Emit an execution event if event traces are enabled.

        This method checks EventTracesConfig settings before emitting events.
        Events are buffered in ExecutionContext and persisted at execution end.

        Args:
            event_type: Event type (ExecutionEventType enum or string)
            task_id: Optional task identifier
            dag_id: Optional DAG/execution identifier
            event_data: Optional event payload
        """
        # Check if event traces are enabled
        if not self.config or not self.config.observability or not self.config.observability.event_traces:
            return

        event_config = self.config.observability.event_traces

        if not event_config.enabled:
            return

        # Convert enum to string for filtering
        event_type_str = event_type.value if isinstance(event_type, ExecutionEventType) else event_type

        # Apply event type filtering
        if event_type_str in (ExecutionEventType.EXECUTION_START.value, ExecutionEventType.EXECUTION_COMPLETE.value) and not event_config.track_execution_events:
            return
        if event_type_str in (
            ExecutionEventType.ATOMIZE_COMPLETE.value,
            ExecutionEventType.PLAN_COMPLETE.value,
            ExecutionEventType.EXECUTE_COMPLETE.value,
            ExecutionEventType.AGGREGATE_COMPLETE.value
        ) and not event_config.track_module_events:
            return
        if event_type_str == ExecutionEventType.EXECUTION_FAILED.value and not event_config.track_failures:
            return

        # Apply sampling
        import random
        if event_config.sample_rate < 1.0 and random.random() > event_config.sample_rate:
            return

        # Get execution context
        ctx = ExecutionContext.get()
        if not ctx:
            return

        # Emit event to context buffer
        ctx.emit_execution_event(
            event_type=event_type_str,
            task_id=task_id,
            dag_id=dag_id,
            event_data=event_data or {},
            priority=0
        )

    # ==================== Main Entry Points ====================

    def solve(
        self,
        task: Union[str, TaskNode],
        dag: Optional[TaskDAG] = None,
        depth: int = 0
    ) -> TaskNode:
        """
        Synchronously solve a task using recursive decomposition.

        This is a thin synchronous wrapper around async_solve().
        If you're already in an async context, use async_solve() directly.

        Args:
            task: Task goal string or TaskNode
            dag: Optional DAG to track execution
            depth: Current recursion depth

        Returns:
            Completed TaskNode with results
        """
        return asyncio.run(self.async_solve(task, dag, depth))

    async def async_solve(
        self,
        task: Union[str, TaskNode],
        dag: Optional[TaskDAG] = None,
        depth: int = 0
    ) -> TaskNode:
        """
        Asynchronously solve a task using recursive decomposition.

        Args:
            task: Task goal string or TaskNode
            dag: Optional DAG to track execution
            depth: Current recursion depth

        Returns:
            Completed TaskNode with results
        """
        logger.debug(f"Starting async_solve for task: {task if isinstance(task, str) else task.goal}")

        # Initialize task and DAG
        task, dag = self._initialize_task_and_dag(task, dag, depth)

        # Setup observability using ObservabilityManager
        await self.observability.setup_execution(task, dag, self.config, depth, execution_mode="recursive")

        # Setup toolkits using ToolkitManager
        await self.toolkit_manager.setup_for_execution(dag, self.config, self.registry)

        try:
            # Wrap execution with MLflow tracing
            if self.mlflow_manager and self.mlflow_manager.config.enabled:
                with self.mlflow_manager.trace_execution(
                    execution_id=dag.execution_id,
                    metadata={
                        "max_depth": self.max_depth,
                        "initial_goal": str(task.goal) if isinstance(task, TaskNode) else str(task),
                        "depth": depth
                    }
                ):
                    result = await self._async_solve_internal(task, dag, depth)

                    # Log final metrics
                    self.mlflow_manager.log_metrics({
                        "total_tasks": len(dag.get_all_tasks()) if dag else 1,
                        "max_depth_reached": result.depth,
                        "success": 1.0 if result.status == TaskStatus.COMPLETED else 0.0
                    })

                    # Create final checkpoint before finalization (ensures visualization of completed runs)
                    if self.checkpoint_manager:
                        try:
                            await self.checkpoint_manager.create_checkpoint(
                                checkpoint_id=None,
                                dag=dag,
                                trigger=CheckpointTrigger.EXECUTION_COMPLETE,
                                current_depth=result.depth,
                                max_depth=self.max_depth
                            )
                            logger.debug("Created final EXECUTION_COMPLETE checkpoint")
                        except Exception as e:
                            logger.warning(f"Failed to create final checkpoint: {e}")

                    # Finalize execution using ObservabilityManager
                    await self.observability.finalize_execution(dag, result)

                    return result
            else:
                result = await self._async_solve_internal(task, dag, depth)

                # Create final checkpoint before finalization (ensures visualization of completed runs)
                if self.checkpoint_manager:
                    try:
                        await self.checkpoint_manager.create_checkpoint(
                            checkpoint_id=None,
                            dag=dag,
                            trigger=CheckpointTrigger.EXECUTION_COMPLETE,
                            current_depth=result.depth,
                            max_depth=self.max_depth
                        )
                        logger.debug("Created final EXECUTION_COMPLETE checkpoint")
                    except Exception as e:
                        logger.warning(f"Failed to create final checkpoint: {e}")

                # Finalize execution using ObservabilityManager
                await self.observability.finalize_execution(dag, result)

                return result
        finally:
            # Stop periodic checkpoints if running
            if self.checkpoint_manager:
                await self.checkpoint_manager.stop_periodic_checkpoints()

            # Cleanup toolkits BEFORE persisting metrics
            # (cleanup generates toolkit lifecycle events that need to be persisted)
            await self.toolkit_manager.cleanup_execution(dag.execution_id)

            # Auto-persist metrics (including cleanup events) and reset context
            if hasattr(dag, '_exec_context_token'):
                await ExecutionContext.reset_async(dag._exec_context_token, self.postgres_storage)

            logger.debug(f"Cleaned up execution for {dag.execution_id}")

    async def _async_solve_internal(
        self,
        task: TaskNode,
        dag: TaskDAG,
        depth: int
    ) -> TaskNode:
        """Internal async solve implementation (separated for MLflow wrapping)."""
        # Emit execution_start event
        start_time = datetime.now(UTC)
        self._emit_execution_event(
            event_type=ExecutionEventType.EXECUTION_START,
            task_id=task.task_id,
            dag_id=dag.execution_id,
            event_data={
                "goal": task.goal[:200] if len(task.goal) > 200 else task.goal,
                "depth": depth,
                "max_depth": self.max_depth,
            }
        )

        # Create initial checkpoint at execution start (ensures visualization even if interrupted)
        checkpoint_id = None
        if self.checkpoint_manager:
            try:
                checkpoint_id = await self.checkpoint_manager.create_checkpoint(
                    checkpoint_id=None,
                    dag=dag,
                    trigger=CheckpointTrigger.EXECUTION_START,
                    current_depth=depth,
                    max_depth=self.max_depth,
                    solver_config={
                        'max_depth': self.max_depth,
                        'enable_logging': self.enable_logging
                    }
                )
                logger.debug(f"Created initial checkpoint: {checkpoint_id}")

                # Start periodic checkpoints for long-running executions
                await self.checkpoint_manager.start_periodic_checkpoints(dag, self.max_depth)
            except Exception as e:
                logger.warning(f"Failed to create initial checkpoint: {e}")

        try:
            # Execute based on current state
            task = await self._async_execute_state_machine(task, dag, checkpoint_id)

            # Emit execution_complete event
            end_time = datetime.now(UTC)
            duration_ms = (end_time - start_time).total_seconds() * 1000
            self._emit_execution_event(
                event_type=ExecutionEventType.EXECUTION_COMPLETE,
                task_id=task.task_id,
                dag_id=dag.execution_id,
                event_data={
                    "status": task.status.value,
                    "duration_ms": duration_ms,
                    "result_preview": task.result[:200] if task.result and len(task.result) > 200 else task.result,
                }
            )

            # Logging is now handled by TreeVisualizer when called by user
            logger.debug(f"Completed async_solve with status: {task.status}")
            return task
        except Exception as e:
            # Emit execution_failed event
            end_time = datetime.now(UTC)
            duration_ms = (end_time - start_time).total_seconds() * 1000
            self._emit_execution_event(
                event_type=ExecutionEventType.EXECUTION_FAILED,
                task_id=task.task_id,
                dag_id=dag.execution_id,
                event_data={
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "duration_ms": duration_ms,
                    "depth": task.depth,
                }
            )

            # Enhance error with task hierarchy context
            error_msg = f"Task '{task.task_id}' failed at depth {task.depth}: {str(e)}"
            if task.goal:
                error_msg += f"\nTask goal: {task.goal[:100]}..."

            # Add checkpoint recovery info
            if checkpoint_id and self.checkpoint_manager:
                error_msg += f"\nCheckpoint {checkpoint_id} available for recovery"

            logger.error(error_msg)

            # Re-raise with enhanced context
            # Use RuntimeError instead of trying to reconstruct original exception type
            # (some exception types have custom constructors that don't accept simple string messages)
            enhanced_error = RuntimeError(error_msg)
            enhanced_error.__cause__ = e
            raise enhanced_error from e

    async def async_event_solve(
        self,
        task: Union[str, TaskNode],
        dag: Optional[TaskDAG] = None,
        depth: int = 0,
        priority_fn: Optional[Callable[[TaskNode], int]] = None,
        concurrency: int = 1,
    ) -> TaskNode:
        """Run the event-driven scheduler to solve the task graph."""

        logger.debug(
            "Starting async_event_solve for task: %s",
            task if isinstance(task, str) else task.goal,
        )

        # Initialize task and DAG
        task, dag = self._initialize_task_and_dag(task, dag, depth)

        # Setup observability using ObservabilityManager
        await self.observability.setup_execution(task, dag, self.config, depth, execution_mode="event_driven")

        # Setup toolkits using ToolkitManager
        await self.toolkit_manager.setup_for_execution(dag, self.config, self.registry)

        try:
            # Pass checkpoint manager and postgres_storage to event controller if available
            controller = EventLoopController(
                dag,
                self.runtime,
                priority_fn=priority_fn,
                checkpoint_manager=self.checkpoint_manager,
                postgres_storage=self.postgres_storage
            )

            # Apply any pending state restorations from previous recovery operations
            if self.checkpoint_manager:
                await controller.apply_pending_restorations()

            # Wrap execution with MLflow tracing
            if self.mlflow_manager and self.mlflow_manager.config.enabled:
                with self.mlflow_manager.trace_execution(
                    execution_id=dag.execution_id,
                    metadata={
                        "max_depth": self.max_depth,
                        "initial_goal": str(task.goal) if isinstance(task, TaskNode) else str(task),
                        "depth": depth,
                        "execution_mode": "event_driven",
                        "concurrency": concurrency
                    }
                ):
                    await controller.run(max_concurrency=concurrency)

                    updated_task = dag.get_node(task.task_id)

                    # Log final metrics
                    self.mlflow_manager.log_metrics({
                        "total_tasks": len(dag.get_all_tasks()),
                        "max_depth_reached": updated_task.depth,
                        "success": 1.0 if updated_task.status == TaskStatus.COMPLETED else 0.0,
                        "concurrency": concurrency
                    })

                    # Create final checkpoint before finalization (ensures visualization of completed runs)
                    if self.checkpoint_manager:
                        try:
                            await self.checkpoint_manager.create_checkpoint(
                                checkpoint_id=None,
                                dag=dag,
                                trigger=CheckpointTrigger.EXECUTION_COMPLETE,
                                current_depth=updated_task.depth,
                                max_depth=self.max_depth
                            )
                            logger.debug("Created final EXECUTION_COMPLETE checkpoint")
                        except Exception as e:
                            logger.warning(f"Failed to create final checkpoint: {e}")

                    # Finalize execution using ObservabilityManager
                    await self.observability.finalize_execution(dag, updated_task)

                    logger.debug("Completed async_event_solve with status: %s", updated_task.status)
                    return updated_task
            else:
                await controller.run(max_concurrency=concurrency)

                updated_task = dag.get_node(task.task_id)

                # Create final checkpoint before finalization (ensures visualization of completed runs)
                if self.checkpoint_manager:
                    try:
                        await self.checkpoint_manager.create_checkpoint(
                            checkpoint_id=None,
                            dag=dag,
                            trigger=CheckpointTrigger.EXECUTION_COMPLETE,
                            current_depth=updated_task.depth,
                            max_depth=self.max_depth
                        )
                        logger.debug("Created final EXECUTION_COMPLETE checkpoint")
                    except Exception as e:
                        logger.warning(f"Failed to create final checkpoint: {e}")

                # Finalize execution using ObservabilityManager
                await self.observability.finalize_execution(dag, updated_task)

                logger.debug("Completed async_event_solve with status: %s", updated_task.status)
                return updated_task
        finally:
            # Stop periodic checkpoints if running
            if self.checkpoint_manager:
                await self.checkpoint_manager.stop_periodic_checkpoints()

            # Critical cleanup: prevents memory leaks and stale context
            # Cleanup toolkits BEFORE persisting metrics (cleanup generates events)
            await self.toolkit_manager.cleanup_execution(dag.execution_id)

            # Auto-persist metrics and reset execution context
            if hasattr(dag, '_exec_context_token'):
                await ExecutionContext.reset_async(dag._exec_context_token, self.postgres_storage)

            logger.debug(f"Cleaned up execution for {dag.execution_id}")

    def event_solve(
        self,
        task: Union[str, TaskNode],
        dag: Optional[TaskDAG] = None,
        depth: int = 0,
        priority_fn: Optional[Callable[[TaskNode], int]] = None,
        concurrency: int = 1,
    ) -> TaskNode:
        """Synchronous wrapper around the event-driven scheduler.

        Thread-safe: Works correctly when called from DSPy's ParallelExecutor worker threads.
        Ensures proper cleanup of database connections before event loop closes.
        """

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            raise RuntimeError("event_solve() cannot be called from a running event loop")

        # Wrap execution with proper cleanup for worker threads
        async def _run_with_cleanup():
            try:
                result = await self.async_event_solve(
                    task=task,
                    dag=dag,
                    depth=depth,
                    priority_fn=priority_fn,
                    concurrency=concurrency,
                )
                return result
            finally:
                # Critical: Shutdown PostgresStorage before event loop closes
                # This prevents "RuntimeError: Event loop is closed" when cleaning up
                # database connections in DSPy's worker threads
                if self.postgres_storage and self.postgres_storage._local.initialized:
                    try:
                        await self.postgres_storage.shutdown()
                        logger.debug("PostgresStorage shutdown complete before event loop closure")
                    except Exception as e:
                        # Non-fatal: log but don't fail the task
                        logger.debug(f"PostgresStorage shutdown error (non-fatal): {e}")

        return asyncio.run(_run_with_cleanup())

    # ==================== Initialization ====================

    def _initialize_task_and_dag(
        self,
        task: Union[str, TaskNode],
        dag: Optional[TaskDAG],
        depth: int
    ) -> Tuple[TaskNode, TaskDAG]:
        """Initialize task node and DAG for execution."""
        # Track whether we're creating a new DAG
        newly_created_dag = dag is None

        # Create DAG if not provided
        if dag is None:
            dag = TaskDAG()
            self.last_dag = dag  # Store for visualization

        # Create new ContextManager for each new DAG to ensure execution isolation
        # Each DAG has unique execution_id and needs isolated FileStorage
        if newly_created_dag or self.runtime.context_manager is None:
            # Validate config availability
            if self.config is None:
                raise ValueError(
                    "Config is required for FileStorage creation. "
                    "Provide config when creating RecursiveSolver."
                )

            # Create FileStorage for this execution
            file_storage = FileStorage(
                config=self.config.storage,
                execution_id=dag.execution_id
            )

            # Set ExecutionContext for toolkit lifecycle management
            # Store token in DAG for later cleanup
            dag._exec_context_token = ExecutionContext.set(
                execution_id=dag.execution_id,
                file_storage=file_storage
            )

            # Extract overall objective from task
            overall_objective = task if isinstance(task, str) else task.goal

            # Create and inject ContextManager into runtime
            context_manager = ContextManager(file_storage, overall_objective)
            self.runtime.context_manager = context_manager

            logger.debug(f"Initialized context system with execution_id: {dag.execution_id}")

        # Convert string to TaskNode if needed
        if isinstance(task, str):
            task = TaskNode(goal=task, depth=depth, max_depth=self.max_depth, execution_id=dag.execution_id)

        # Add to DAG if not already present
        if task.task_id not in dag.graph:
            dag.add_node(task)

        return task, dag

    # ==================== State Machine Execution ====================

    async def _async_execute_state_machine(self, task: TaskNode, dag: TaskDAG, checkpoint_id: Optional[str] = None) -> TaskNode:
        """Execute asynchronous state machine for task processing."""
        # Check for forced execution at max depth
        if task.should_force_execute():
            logger.debug(f"Force executing task at max depth: {task.depth}")
            return await self.runtime.force_execute_async(task, dag)

        # Process based on current state
        if task.status == TaskStatus.PENDING:
            logger.debug(f"Async atomizing task: {task.goal[:50]}...")
            task = await self.runtime.atomize_async(task, dag)

        if task.status == TaskStatus.ATOMIZING:
            task = self.runtime.transition_from_atomizing(task, dag)

        if task.status == TaskStatus.PLANNING:
            logger.debug(f"Async planning task: {task.goal[:50]}...")
            task = await self.runtime.plan_async(task, dag)

            # Create checkpoint after planning (expensive operation completed)
            if self.checkpoint_manager and task.status == TaskStatus.PLAN_DONE:
                try:
                    await self.checkpoint_manager.create_checkpoint(
                        checkpoint_id=f"{checkpoint_id}_after_plan" if checkpoint_id else None,
                        dag=dag,
                        trigger=CheckpointTrigger.AFTER_PLANNING,
                        current_depth=task.depth,
                        max_depth=self.max_depth
                    )
                except Exception as e:
                    logger.warning(f"Failed to create post-planning checkpoint: {e}")

        if task.status == TaskStatus.EXECUTING:
            logger.debug(f"Async executing task: {task.goal[:50]}...")
            task = await self.runtime.execute_async(task, dag)
        elif task.status == TaskStatus.PLAN_DONE:
            # Create checkpoint before aggregation (preserve completed subtasks)
            if self.checkpoint_manager:
                try:
                    await self.checkpoint_manager.create_checkpoint(
                        checkpoint_id=f"{checkpoint_id}_before_agg" if checkpoint_id else None,
                        dag=dag,
                        trigger=CheckpointTrigger.BEFORE_AGGREGATION,
                        current_depth=task.depth,
                        max_depth=self.max_depth
                    )
                except Exception as e:
                    logger.warning(f"Failed to create pre-aggregation checkpoint: {e}")

            # Pass _async_solve_internal to avoid nested observability setup
            # (observability is already set up at the top level)
            task = await self.runtime.process_subgraph_async(task, dag, self._async_solve_internal)

        return task

    # ==================== Unified Checkpoint Coordination ====================

    async def create_unified_checkpoint(
        self,
        trigger: CheckpointTrigger,
        dag: Optional[TaskDAG] = None,
        task_context: Optional[TaskNode] = None
    ) -> Optional[str]:
        """Create a unified checkpoint capturing all system components."""
        if not self.checkpoint_manager:
            logger.debug("Checkpoint manager not available, skipping unified checkpoint")
            return None

        try:
            logger.info(f"Creating unified system checkpoint for trigger: {trigger}")

            # Use provided DAG or create a minimal one
            target_dag = dag or TaskDAG("unified_checkpoint")
            if task_context and dag is None:
                target_dag.add_node(task_context)

            # Collect comprehensive system state
            solver_config = {
                "max_depth": self.max_depth,
                "enable_logging": self.enable_logging,
                "registry_stats": self.registry.get_stats()
            }

            # Collect runtime state if available
            module_states = {}
            if hasattr(self, 'runtime') and self.runtime:
                module_states["runtime"] = {
                    "total_operations": getattr(self.runtime, '_operation_count', 0),
                    "last_activity": "unified_checkpoint_creation"
                }

            # Create the unified checkpoint
            checkpoint_id = await self.checkpoint_manager.create_checkpoint(
                checkpoint_id=None,  # Let manager generate ID
                dag=target_dag,
                trigger=trigger,
                current_depth=task_context.depth if task_context else 0,
                max_depth=self.max_depth,
                solver_config=solver_config,
                module_states=module_states
            )

            logger.info(f"Created unified checkpoint: {checkpoint_id}")
            return checkpoint_id

        except Exception as e:
            logger.error(f"Failed to create unified checkpoint: {e}")
            return None

    async def restore_from_unified_checkpoint(
        self,
        checkpoint_id: str,
        strategy: Optional[str] = None
    ) -> bool:
        """Restore system state from a unified checkpoint."""
        if not self.checkpoint_manager:
            logger.error("Checkpoint manager not available for restoration")
            return False

        try:
            logger.info(f"Restoring system from unified checkpoint: {checkpoint_id}")

            # Load checkpoint
            checkpoint_data = await self.checkpoint_manager.load_checkpoint(checkpoint_id)

            # Create recovery plan
            from roma_dspy.types.checkpoint_types import RecoveryStrategy
            recovery_strategy = RecoveryStrategy.PARTIAL
            if strategy == "full":
                recovery_strategy = RecoveryStrategy.FULL
            elif strategy == "selective":
                recovery_strategy = RecoveryStrategy.SELECTIVE

            recovery_plan = await self.checkpoint_manager.create_recovery_plan(
                checkpoint_data,
                strategy=recovery_strategy
            )

            # Enable module state restoration
            recovery_plan.restore_module_states = True

            # Create a temporary DAG for restoration
            temp_dag = TaskDAG("restoration_target")

            # Apply recovery plan
            restored_dag = await self.checkpoint_manager.apply_recovery_plan(recovery_plan, temp_dag)

            # Wire restored DAG back into solver for subsequent operations
            self.last_dag = restored_dag

            # Restore solver configuration if available
            if checkpoint_data.solver_config:
                solver_config = checkpoint_data.solver_config
                self.max_depth = solver_config.get("max_depth", self.max_depth)

            logger.info(f"Successfully restored from unified checkpoint: {checkpoint_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to restore from unified checkpoint {checkpoint_id}: {e}")
            return False

    async def list_unified_checkpoints_async(self) -> list:
        """List all available unified checkpoints (async version)."""
        if not self.checkpoint_manager:
            return []

        try:
            return await self.checkpoint_manager.list_checkpoints()
        except Exception as e:
            logger.error(f"Failed to list checkpoints: {e}")
            return []

    def list_unified_checkpoints(self) -> list:
        """List all available unified checkpoints (sync version)."""
        try:
            import asyncio
            # Try to use existing event loop or create new one
            try:
                loop = asyncio.get_running_loop()
                # We're in an async context, can't use run_until_complete
                logger.warning("list_unified_checkpoints called from async context. Use list_unified_checkpoints_async instead.")
                return []
            except RuntimeError:
                # No running loop, safe to create one
                return asyncio.run(self.list_unified_checkpoints_async())
        except Exception as e:
            logger.error(f"Failed to list checkpoints: {e}")
            return []

    async def auto_recover(self, max_attempts: int = 3) -> bool:
        """Simple recovery mechanism that attempts to restore from the latest checkpoint."""
        if not self.checkpoint_manager:
            logger.error("Cannot auto-recover: checkpoint manager not available")
            return False

        try:
            logger.info("Starting auto-recovery process...")

            # Get list of available checkpoints
            checkpoints = await self.checkpoint_manager.list_checkpoints()
            if not checkpoints:
                logger.warning("No checkpoints available for recovery")
                return False

            # Sort by creation time (most recent first)
            checkpoints.sort(key=lambda x: x["created_at"], reverse=True)

            # Try to recover from checkpoints, starting with the most recent
            for attempt, checkpoint in enumerate(checkpoints[:max_attempts], 1):
                checkpoint_id = checkpoint["checkpoint_id"]
                logger.info(f"Recovery attempt {attempt}/{max_attempts}: trying checkpoint {checkpoint_id}")

                try:
                    # Validate checkpoint first
                    is_valid = await self.checkpoint_manager.validate_checkpoint(checkpoint_id)
                    if not is_valid:
                        logger.warning(f"Checkpoint {checkpoint_id} is invalid, skipping")
                        continue

                    # Attempt restoration
                    success = await self.restore_from_unified_checkpoint(checkpoint_id, strategy="partial")

                    if success:
                        logger.info(f"Successfully recovered from checkpoint {checkpoint_id}")
                        return True
                    else:
                        logger.warning(f"Failed to restore from checkpoint {checkpoint_id}")

                except Exception as e:
                    logger.warning(f"Error during recovery attempt {attempt}: {e}")
                    continue

            logger.error(f"Auto-recovery failed after {max_attempts} attempts")
            return False

        except Exception as e:
            logger.error(f"Auto-recovery process failed: {e}")
            return False

    def get_system_health(self) -> dict:
        """Get overall system health status for recovery decisions."""
        health_status = {
            "checkpoint_system": {
                "enabled": self.checkpoint_manager is not None,
                "available": self.checkpoint_manager.config.enabled if self.checkpoint_manager else False
            },
            "registry": self.registry.get_stats(),
            "configuration": {
                "max_depth": self.max_depth,
                "logging_enabled": self.enable_logging
            }
        }

        # Add checkpoint storage stats if available (without async issues)
        if self.checkpoint_manager:
            try:
                import asyncio
                # Try to use existing event loop or create new one
                try:
                    loop = asyncio.get_running_loop()
                    # We're in an async context, skip storage stats to avoid issues
                    health_status["checkpoint_storage"] = {"note": "Stats unavailable from async context. Use get_system_health_async()"}
                except RuntimeError:
                    # No running loop, safe to create one
                    storage_stats = asyncio.run(self.checkpoint_manager.get_storage_stats())
                    health_status["checkpoint_storage"] = storage_stats
            except Exception as e:
                health_status["checkpoint_storage"] = {"error": str(e)}

        return health_status

    async def get_system_health_async(self) -> dict:
        """Get overall system health status for recovery decisions (async version)."""
        health_status = {
            "checkpoint_system": {
                "enabled": self.checkpoint_manager is not None,
                "available": self.checkpoint_manager.config.enabled if self.checkpoint_manager else False
            },
            "registry": self.registry.get_stats(),
            "configuration": {
                "max_depth": self.max_depth,
                "logging_enabled": self.enable_logging
            }
        }

        # Add checkpoint storage stats if available
        if self.checkpoint_manager:
            try:
                storage_stats = await self.checkpoint_manager.get_storage_stats()
                health_status["checkpoint_storage"] = storage_stats
            except Exception as e:
                health_status["checkpoint_storage"] = {"error": str(e)}

        return health_status

# ==================== Convenience Functions ====================

def solve(task: Union[str, TaskNode], max_depth: int = 2, config: Optional[ROMAConfig] = None, **kwargs) -> TaskNode:
    """
    Solve a task using recursive decomposition.

    Args:
        task: Task goal string or TaskNode
        max_depth: Maximum recursion depth
        config: Optional ROMAConfig (creates default if None)
        **kwargs: Additional arguments for RecursiveSolver

    Returns:
        Completed TaskNode with results
    """
    if config is None:
        config = ROMAConfig()  # Uses Pydantic defaults
    solver = RecursiveSolver(config=config, max_depth=max_depth, **kwargs)
    return solver.solve(task)


async def async_solve(task: Union[str, TaskNode], max_depth: int = 2, config: Optional[ROMAConfig] = None, **kwargs) -> TaskNode:
    """
    Asynchronously solve a task using recursive decomposition.

    Args:
        task: Task goal string or TaskNode
        max_depth: Maximum recursion depth
        config: Optional ROMAConfig (creates default if None)
        **kwargs: Additional arguments for RecursiveSolver

    Returns:
        Completed TaskNode with results
    """
    if config is None:
        config = ROMAConfig()  # Uses Pydantic defaults
    solver = RecursiveSolver(config=config, max_depth=max_depth, **kwargs)
    return await solver.async_solve(task)


def event_solve(
    task: Union[str, TaskNode],
    max_depth: int = 2,
    config: Optional[ROMAConfig] = None,
    priority_fn: Optional[Callable[[TaskNode], int]] = None,
    concurrency: int = 1,
    **kwargs,
) -> TaskNode:
    """Synchronously solve using the event-driven scheduler."""

    if config is None:
        config = ROMAConfig()  # Uses Pydantic defaults
    solver = RecursiveSolver(config=config, max_depth=max_depth, **kwargs)
    return solver.event_solve(task, priority_fn=priority_fn, concurrency=concurrency)


async def async_event_solve(
    task: Union[str, TaskNode],
    max_depth: int = 2,
    config: Optional[ROMAConfig] = None,
    priority_fn: Optional[Callable[[TaskNode], int]] = None,
    concurrency: int = 1,
    **kwargs,
) -> TaskNode:
    """Asynchronously solve using the event-driven scheduler."""

    if config is None:
        config = ROMAConfig()  # Uses Pydantic defaults
    solver = RecursiveSolver(config=config, max_depth=max_depth, **kwargs)
    return await solver.async_event_solve(
        task,
        priority_fn=priority_fn,
        concurrency=concurrency,
    )
