"""
Execution observability manager for ROMA-DSPy.

Handles all observability concerns for task execution:
- PostgreSQL initialization and lifecycle
- Execution record creation and updates
- DSPy settings configuration for tracing
- MLflow coordination
- Execution context setup for LM trace persistence

This manager follows SRP by centralizing all observability setup/teardown logic,
previously scattered across RecursiveSolver.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional, Any

import dspy
from loguru import logger

try:
    import mlflow
    MLFLOW_AVAILABLE = True
except ImportError:
    MLFLOW_AVAILABLE = False

from roma_dspy.core.observability.span_manager import ROMASpanManager, set_span_manager

if TYPE_CHECKING:
    from roma_dspy.core.engine.dag import TaskDAG
    from roma_dspy.core.signatures import TaskNode
    from roma_dspy.core.storage import PostgresStorage
    from roma_dspy.core.observability import MLflowManager
    from roma_dspy.config.schemas.root import ROMAConfig
    from roma_dspy.core.engine.runtime import ModuleRuntime
    from roma_dspy.types import TaskStatus, ExecutionStatus


class ObservabilityManager:
    """
    Manages all observability setup and teardown for task execution.

    Responsibilities:
    - Initialize and manage PostgreSQL storage lifecycle
    - Create and update execution records
    - Configure DSPy settings for distributed tracing
    - Coordinate MLflow tracing
    - Setup execution context for LM trace persistence

    This class enables clean separation of observability concerns from
    execution orchestration, making both easier to test and maintain.
    """

    def __init__(
        self,
        postgres_storage: Optional["PostgresStorage"] = None,
        mlflow_manager: Optional["MLflowManager"] = None,
        runtime: Optional["ModuleRuntime"] = None
    ):
        """
        Initialize observability manager.

        Args:
            postgres_storage: PostgreSQL storage for execution persistence
            mlflow_manager: MLflow manager for experiment tracking
            runtime: Module runtime for context store access
        """
        self.postgres_storage = postgres_storage
        self.mlflow_manager = mlflow_manager
        self.runtime = runtime

        tracking_uri = None
        span_enabled = False
        if mlflow_manager and getattr(mlflow_manager, "config", None):
            tracking_uri = getattr(mlflow_manager.config, "tracking_uri", None)
            span_enabled = bool(getattr(mlflow_manager.config, "enabled", False))

        set_span_manager(ROMASpanManager(enabled=span_enabled, tracking_uri=tracking_uri))

    async def setup_execution(
        self,
        task: "TaskNode",
        dag: "TaskDAG",
        config: "ROMAConfig",
        depth: int = 0,
        execution_mode: str = "recursive"
    ) -> None:
        """
        Setup all observability systems for execution.

        Performs comprehensive initialization:
        1. Initialize PostgreSQL storage if not already initialized
        2. Configure DSPy settings for distributed tracing
        3. Create execution record in PostgreSQL
        4. Setup execution context for LM trace persistence

        Args:
            task: Task being executed (TaskNode or string goal)
            dag: TaskDAG with execution_id
            config: ROMA configuration
            depth: Current recursion depth
            execution_mode: "recursive" or "event_driven"
        """
        # Initialize Postgres storage if available
        if self.postgres_storage and not self.postgres_storage._local.initialized:
            await self._initialize_postgres()

        # Configure DSPy settings with execution_id for trace correlation
        self._configure_dspy_tracing(dag.execution_id)

        # Create execution record in Postgres
        await self._create_execution_record(task, dag, config, depth, execution_mode)

        # Set execution context for LM trace persistence
        self._setup_trace_context(dag.execution_id)

    async def finalize_execution(
        self,
        dag: "TaskDAG",
        result: "TaskNode"
    ) -> None:
        """
        Finalize all observability data for completed execution.

        Updates execution status in PostgreSQL with:
        - Final status (completed/failed)
        - Task statistics (total, completed, failed)
        - DAG snapshot for replay/analysis

        Args:
            dag: TaskDAG with execution data
            result: Final task result with status
        """
        if not self.postgres_storage:
            return

        try:
            # Import types here to avoid circular dependency
            from roma_dspy.types import TaskStatus, ExecutionStatus

            # DAG snapshot now saved via checkpoints (see checkpoint_manager)
            await self.postgres_storage.update_execution(
                execution_id=dag.execution_id,
                status=ExecutionStatus.COMPLETED.value if result.status == TaskStatus.COMPLETED else ExecutionStatus.FAILED.value,
                total_tasks=len(dag.get_all_tasks()),
                completed_tasks=len(dag.completed_tasks),
                failed_tasks=len(dag.failed_tasks)
            )

            logger.debug(f"Updated execution status for {dag.execution_id}")

        except Exception as e:
            logger.warning(f"Failed to update execution in Postgres: {e}")

    async def _initialize_postgres(self) -> None:
        """Initialize PostgreSQL storage with fail-fast behavior.

        Raises:
            Exception: If PostgreSQL initialization fails (database unreachable,
                      connection error, schema creation failure, etc.)
        """
        if not self.postgres_storage:
            return

        try:
            await self.postgres_storage.initialize()
            logger.info(f"✓ PostgreSQL storage initialized successfully")
        except Exception as e:
            logger.error(
                f"Failed to initialize PostgreSQL storage: {e}\n"
                f"Database connection URL: {self.postgres_storage.config.connection_url}\n"
                "This is a critical error. Execution cannot proceed without database connectivity."
            )
            # Re-raise: If Postgres is enabled but can't be initialized, fail immediately
            # This prevents FK violations from traces trying to insert with non-existent execution_id
            raise RuntimeError(
                f"PostgreSQL initialization failed: {e}. "
                "Check database connectivity and configuration."
            ) from e

    def _configure_dspy_tracing(self, execution_id: str) -> None:
        """
        Configure DSPy settings for distributed tracing.

        Sets execution_id on DSPy settings to enable trace correlation
        across distributed components. Thread-safe for DSPy parallelizer.

        Args:
            execution_id: Unique execution identifier
        """
        import threading

        # Get current thread ID for thread-safe configuration
        current_thread_id = threading.get_ident()

        # Check if we need to configure (skip if already configured in this thread)
        if (hasattr(dspy.settings, '_roma_execution_id') and
            dspy.settings._roma_execution_id == execution_id and
            hasattr(dspy.settings, '_roma_thread_id') and
            dspy.settings._roma_thread_id == current_thread_id):
            logger.debug(f"DSPy already configured for execution {execution_id[:8]} in thread {current_thread_id}")
            return

        try:
            # Configure DSPy with tracing and token usage tracking enabled
            # BUG FIX: trace must be a list, not a boolean (DSPy calls len(trace))
            # See: https://github.com/stanfordnlp/dspy/issues/377
            # Enable track_usage to capture token metrics via get_lm_usage()
            if hasattr(dspy.settings, 'configure'):
                try:
                    dspy.settings.configure(trace=[], track_usage=True)
                except RuntimeError as e:
                    # Thread-local configuration error - this is expected in worker threads
                    # DSPy parallelizer creates worker threads that can't reconfigure
                    error_msg = str(e).lower()
                    if 'thread' in error_msg and 'configured' in error_msg:
                        logger.debug(
                            f"Skipping DSPy reconfiguration in worker thread {current_thread_id} "
                            f"(already configured by main thread). This is expected."
                        )
                        # Still try to set custom attributes (these are thread-local)
                        try:
                            dspy.settings.execution_id = execution_id
                            dspy.settings._roma_execution_id = execution_id
                            dspy.settings._roma_thread_id = current_thread_id
                        except Exception:
                            pass
                        return
                    else:
                        raise

            # Set execution_id as custom attribute
            dspy.settings.execution_id = execution_id
            dspy.settings._roma_execution_id = execution_id
            dspy.settings._roma_thread_id = current_thread_id

            logger.debug(f"Configured DSPy settings with execution_id: {execution_id[:8]} in thread {current_thread_id}")

            # PHASE 1: Set session metadata for trace grouping
            # This groups ALL traces (including DSPy autolog) by execution_id
            if MLFLOW_AVAILABLE:
                try:
                    # Check if there's an active trace before trying to update
                    if hasattr(mlflow, 'get_current_active_span') and mlflow.get_current_active_span():
                        mlflow.update_current_trace(metadata={
                            "mlflow.trace.session": execution_id,
                            "mlflow.trace.user": "roma-dspy",
                        })
                        logger.info(f"✓ Set MLflow session metadata for execution: {execution_id[:8]}")
                    else:
                        # No active trace yet - will be set when first span is created
                        logger.debug(f"No active MLflow trace yet for {execution_id[:8]}, metadata will be set later")
                except AttributeError as e:
                    # MLflow version too old (< 3.0) - missing update_current_trace
                    logger.debug(f"MLflow session metadata not available (requires MLflow 3.0+): {e}")
                except Exception as e:
                    # Non-fatal: session grouping is optional enhancement
                    logger.debug(f"Could not set MLflow session metadata: {e}")

        except (AttributeError, TypeError) as e:
            # DSPy API may not support custom kwargs - log warning but continue
            logger.debug(f"DSPy settings configuration partial: {e}. Continuing without full DSPy integration.")

            # Still set execution_id as attribute if possible
            try:
                dspy.settings.execution_id = execution_id
                dspy.settings._roma_execution_id = execution_id
                dspy.settings._roma_thread_id = current_thread_id
            except Exception:
                logger.debug("Could not set execution_id on dspy.settings")

        except Exception as e:
            # Unexpected error - log but don't fail execution
            logger.debug(f"Unexpected error configuring DSPy settings: {e}. Continuing without DSPy integration.")

    async def _create_execution_record(
        self,
        task: Any,
        dag: "TaskDAG",
        config: "ROMAConfig",
        depth: int,
        execution_mode: str
    ) -> None:
        """
        Create execution record in PostgreSQL.

        Args:
            task: Task being executed
            dag: TaskDAG with execution_id
            config: ROMA configuration
            depth: Current recursion depth
            execution_mode: "recursive" or "event_driven"

        Raises:
            RuntimeError: If postgres_storage exists but is not initialized
        """
        if not self.postgres_storage:
            return

        # Defense in depth: Verify postgres_storage is initialized in current thread
        # This should never trigger if _initialize_postgres() is working correctly,
        # but provides a clear error message if initialization was somehow skipped
        if not self.postgres_storage._local.initialized:
            raise RuntimeError(
                f"PostgresStorage exists but is not initialized in current thread. "
                "This indicates a bug in initialization flow. "
                f"Database URL: {self.postgres_storage.config.connection_url}"
            )

        try:
            # Extract goal from task
            from roma_dspy.core.signatures import TaskNode

            initial_goal = task.goal if isinstance(task, TaskNode) else str(task)

            # Serialize config using ROMAConfig.to_dict() method
            config_dict = config.to_dict() if config else {}

            # Extract experiment_name from config (defensive: handle missing/None observability fields)
            experiment_name = "unknown"
            if config and config.observability and config.observability.mlflow:
                experiment_name = getattr(config.observability.mlflow, 'experiment_name', 'unknown')

            # Extract profile name from config metadata if available, otherwise use "unknown"
            # Profile name should be set in metadata by the caller (ExecutionService or CLI)
            profile_name = config_dict.get("metadata", {}).get("profile_name", "unknown")

            await self.postgres_storage.create_execution(
                execution_id=dag.execution_id,
                initial_goal=initial_goal,
                max_depth=getattr(task, 'max_depth', 2) if isinstance(task, TaskNode) else 2,
                profile=profile_name,
                experiment_name=experiment_name,
                config=config_dict,
                metadata={
                    "solver_version": "0.1.0",
                    "depth": depth,
                    "execution_mode": execution_mode,
                    "profile_name": profile_name,
                    "experiment_name": experiment_name
                }
            )

            # Verify execution record was committed and is readable
            # This prevents FK violations in LM traces
            execution = await self.postgres_storage.get_execution(dag.execution_id)
            if not execution:
                raise RuntimeError(
                    f"Execution record {dag.execution_id} was created but cannot be retrieved. "
                    "This may indicate a transaction isolation issue."
                )

            logger.debug(f"Created and verified execution record: {dag.execution_id}")

        except Exception as e:
            # Check if this is an event loop error from worker thread
            error_str = str(e).lower()
            if "event loop" in error_str or "different loop" in error_str:
                logger.warning(
                    f"Failed to create execution record in Postgres (event loop issue in worker thread): {e}\n"
                    "This is expected when running in DSPy's ParallelExecutor. "
                    "Worker threads cannot share database connections across event loops."
                )
                # Non-fatal in worker threads: The task can still complete, just without persistence
                return
            else:
                # Other errors are critical
                logger.error(f"Failed to create execution record in Postgres: {e}")
                # Re-raise: execution record is critical for FK constraints
                # LM traces, task traces depend on this record existing
                raise

    def _setup_trace_context(self, execution_id: str) -> None:
        """
        Setup execution context for LM trace persistence.

        Args:
            execution_id: Unique execution identifier
        """
        if not self.postgres_storage or not self.runtime:
            return

        try:
            self.runtime.context_store.set_execution_context(
                execution_id=execution_id,
                postgres_storage=self.postgres_storage
            )
            logger.debug(f"Setup LM trace context for {execution_id}")
        except Exception as e:
            logger.warning(f"Failed to setup trace context: {e}")
