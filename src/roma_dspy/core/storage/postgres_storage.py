"""PostgreSQL async storage for execution traces and checkpoints."""

import asyncio
import threading
import warnings
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from loguru import logger
from sqlalchemy import select, update, delete
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.exc import SQLAlchemyError

from roma_dspy.config.schemas.storage import PostgresConfig
from roma_dspy.types.checkpoint_models import CheckpointData, CheckpointState, CheckpointTrigger
from roma_dspy.types import ExecutionStatus
from roma_dspy.core.storage.models import Base, Execution, Checkpoint, TaskTrace, LMTrace, CircuitBreaker, EventTrace, ToolkitTrace, ToolInvocationTrace


class _ThreadLocalState(threading.local):
    """Thread-local state for PostgresStorage.

    Each thread gets its own engine and session factory bound to its own event loop.
    This enables safe multi-threaded usage with DSPy's parallelizer.
    """
    def __init__(self):
        self.engine: Optional[AsyncEngine] = None
        self.session_factory: Optional[async_sessionmaker[AsyncSession]] = None
        self.initialized: bool = False
        self.event_loop_id: Optional[int] = None  # Track which event loop the engine is bound to


class PostgresStorage:
    """
    Async Postgres storage for execution traces and checkpoints.

    Provides durable, queryable persistence for all execution data including
    checkpoints, task traces, LM traces, and circuit breaker states.

    Thread-safe: Each thread gets its own database engine bound to its own event loop,
    enabling safe concurrent usage with DSPy's parallelizer.

    Example:
        ```python
        storage = PostgresStorage(postgres_config)
        await storage.initialize()

        # Create execution
        await storage.create_execution(
            execution_id="exec_123",
            initial_goal="Build a web scraper",
            max_depth=5
        )

        # Save checkpoint
        await storage.save_checkpoint(checkpoint_data)

        # Query traces
        traces = await storage.get_task_traces(
            execution_id="exec_123",
            status="completed"
        )
        ```
    """

    def __init__(self, config: PostgresConfig):
        """Initialize Postgres storage.

        Args:
            config: PostgresConfig with connection settings
        """
        self.config = config
        self._local = _ThreadLocalState()  # Thread-local storage for engine/sessions

    async def initialize(self) -> None:
        """Initialize database engine and session factory for current thread.

        Must be called before using any storage operations.
        Safe to call multiple times - idempotent per thread.

        Detects and handles event loop changes within the same thread:
        - If event loop has changed (closed and recreated), disposes old engine and reinitializes
        - If same event loop, returns immediately (already initialized)

        Each thread gets its own engine bound to its own event loop, enabling
        safe concurrent usage with DSPy's parallelizer.
        """
        if not self.config.enabled:
            logger.info("PostgreSQL storage disabled in config")
            return

        # Get current event loop and its ID
        try:
            current_loop = asyncio.get_running_loop()
            current_loop_id = id(current_loop)
        except RuntimeError:
            raise RuntimeError("PostgresStorage.initialize() must be called from an async context")

        # Check if we need to reinitialize due to event loop change
        if self._local.initialized:
            if self._local.event_loop_id == current_loop_id:
                logger.debug(
                    f"PostgresStorage already initialized in thread {threading.get_ident()} "
                    f"with event loop {current_loop_id}"
                )
                return
            else:
                # Event loop changed - dispose old engine and reinitialize
                logger.info(
                    f"Event loop changed in thread {threading.get_ident()} "
                    f"(old={self._local.event_loop_id}, new={current_loop_id}), "
                    "disposing old engine and reinitializing PostgresStorage"
                )
                if self._local.engine:
                    try:
                        await self._local.engine.dispose()
                    except Exception as e:
                        logger.warning(f"Error disposing old engine: {e}")

                # Reset state
                self._local.initialized = False
                self._local.engine = None
                self._local.session_factory = None
                self._local.event_loop_id = None

        try:
            # Create async engine with connection pooling for this thread
            self._local.engine = create_async_engine(
                self.config.connection_url,
                pool_size=self.config.pool_size,
                max_overflow=self.config.max_overflow,
                pool_timeout=self.config.pool_timeout,
                echo=self.config.echo_sql,
                pool_pre_ping=True,  # Verify connections before using
            )

            # Create session factory for this thread
            self._local.session_factory = async_sessionmaker(
                self._local.engine,
                class_=AsyncSession,
                expire_on_commit=False,  # Avoid lazy loading issues
            )

            # Create tables if needed (safe to call multiple times)
            async with self._local.engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)

            # Store the event loop ID this engine is bound to
            self._local.event_loop_id = current_loop_id
            self._local.initialized = True

            logger.info(
                f"PostgresStorage initialized in thread {threading.get_ident()} "
                f"with event loop {current_loop_id}"
            )

        except Exception as e:
            logger.error(f"Failed to initialize PostgresStorage in thread {threading.get_ident()}: {e}")
            self.config.enabled = False
            raise

    @asynccontextmanager
    async def session(self) -> AsyncSession:
        """Get database session context manager for current thread.

        Yields:
            AsyncSession for database operations

        Raises:
            RuntimeError: If storage not initialized in current thread
        """
        if not self._local.initialized or not self._local.session_factory:
            raise RuntimeError(
                f"PostgresStorage not initialized in thread {threading.get_ident()}. "
                "Call initialize() first."
            )

        async with self._local.session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    # ==================== Execution Operations ====================

    async def create_execution(
        self,
        execution_id: str,
        initial_goal: str,
        max_depth: int,
        profile: str,
        experiment_name: str,
        config: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Execution:
        """Create new execution record.

        Args:
            execution_id: Unique execution identifier
            initial_goal: Initial task goal
            max_depth: Maximum recursion depth
            profile: Configuration profile name (e.g., 'crypto_agent')
            experiment_name: Experiment name from profile config (e.g., 'ROMA-Crypto-Agent-Mapped')
            config: Optional runtime configuration snapshot
            metadata: Optional execution metadata

        Returns:
            Created Execution model

        Raises:
            SQLAlchemyError: On database error
        """
        async with self.session() as session:
            execution = Execution(
                execution_id=execution_id,
                status=ExecutionStatus.RUNNING.value,
                initial_goal=initial_goal,
                max_depth=max_depth,
                profile=profile,
                experiment_name=experiment_name,
                config=config or {},
                execution_metadata=metadata or {}
            )
            session.add(execution)
            await session.flush()
            logger.debug(f"Created execution: {execution_id} (profile={profile}, experiment={experiment_name})")
            return execution

    async def update_execution(
        self,
        execution_id: str,
        **kwargs: Any
    ) -> None:
        """Update execution record.

        Args:
            execution_id: Execution to update
            **kwargs: Fields to update (status, total_tasks, etc.)

        Raises:
            SQLAlchemyError: On database error
        """
        async with self.session() as session:
            stmt = (
                update(Execution)
                .where(Execution.execution_id == execution_id)
                .values(updated_at=datetime.now(timezone.utc), **kwargs)
            )
            await session.execute(stmt)
            logger.debug(f"Updated execution {execution_id}: {kwargs}")

    async def get_execution(self, execution_id: str) -> Optional[Execution]:
        """Get execution by ID.

        Args:
            execution_id: Execution identifier

        Returns:
            Execution model or None if not found
        """
        async with self.session() as session:
            stmt = select(Execution).where(Execution.execution_id == execution_id)
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def list_executions(
        self,
        status: Optional[str] = None,
        experiment_name: Optional[str] = None,
        profile: Optional[str] = None,
        offset: int = 0,
        limit: int = 100
    ) -> List[Execution]:
        """List executions with optional filtering and pagination.

        Args:
            status: Filter by status (running, completed, failed)
            experiment_name: Filter by experiment name
            profile: Filter by profile name
            offset: Number of records to skip
            limit: Maximum number of results

        Returns:
            List of Execution models, ordered by experiment_name then created_at descending
        """
        async with self.session() as session:
            stmt = (
                select(Execution)
                .order_by(Execution.experiment_name, Execution.created_at.desc())
                .offset(offset)
                .limit(limit)
            )
            if status:
                stmt = stmt.where(Execution.status == status)
            if experiment_name:
                stmt = stmt.where(Execution.experiment_name == experiment_name)
            if profile:
                stmt = stmt.where(Execution.profile == profile)
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def count_executions(
        self,
        status: Optional[str] = None,
        experiment_name: Optional[str] = None,
        profile: Optional[str] = None
    ) -> int:
        """Count total executions with optional filters.

        Args:
            status: Filter by status (running, completed, failed)
            experiment_name: Filter by experiment name
            profile: Filter by profile name

        Returns:
            Total count of matching executions
        """
        from sqlalchemy import func
        async with self.session() as session:
            stmt = select(func.count(Execution.execution_id))
            if status:
                stmt = stmt.where(Execution.status == status)
            if experiment_name:
                stmt = stmt.where(Execution.experiment_name == experiment_name)
            if profile:
                stmt = stmt.where(Execution.profile == profile)
            result = await session.execute(stmt)
            return result.scalar() or 0

    async def list_experiments(self) -> List[tuple[str, int, int, int, int]]:
        """List all experiments with execution counts and status breakdown.

        Returns:
            List of tuples: (experiment_name, total_count, running_count, completed_count, failed_count)
            Ordered by experiment_name
        """
        from sqlalchemy import func, case
        async with self.session() as session:
            stmt = (
                select(
                    Execution.experiment_name,
                    func.count(Execution.execution_id).label('total'),
                    func.sum(case((Execution.status == 'running', 1), else_=0)).label('running'),
                    func.sum(case((Execution.status == 'completed', 1), else_=0)).label('completed'),
                    func.sum(case((Execution.status == 'failed', 1), else_=0)).label('failed')
                )
                .group_by(Execution.experiment_name)
                .order_by(Execution.experiment_name)
            )
            result = await session.execute(stmt)
            return [(row.experiment_name, row.total, row.running or 0, row.completed or 0, row.failed or 0)
                    for row in result]

    # ==================== Checkpoint Operations ====================

    async def save_checkpoint(self, checkpoint_data: CheckpointData) -> None:
        """Save checkpoint to database.

        Args:
            checkpoint_data: Checkpoint data to persist

        Raises:
            SQLAlchemyError: On database error
        """
        async with self.session() as session:
            checkpoint = Checkpoint(
                checkpoint_id=checkpoint_data.checkpoint_id,
                execution_id=checkpoint_data.execution_id,
                created_at=checkpoint_data.created_at,
                trigger=checkpoint_data.trigger.value,
                state=checkpoint_data.state.value,
                dag_snapshot=checkpoint_data.root_dag.model_dump(mode="json"),
                preserved_results=checkpoint_data.preserved_results,
                module_states=checkpoint_data.module_states,
                failed_task_ids=list(checkpoint_data.failed_task_ids),
                file_path=checkpoint_data.file_path,
                compressed=True
            )
            session.add(checkpoint)
            await session.flush()
            logger.debug(f"Saved checkpoint: {checkpoint_data.checkpoint_id}")

    async def load_checkpoint(self, checkpoint_id: str) -> Optional[CheckpointData]:
        """Load checkpoint from database.

        Args:
            checkpoint_id: Checkpoint identifier

        Returns:
            CheckpointData or None if not found
        """
        async with self.session() as session:
            stmt = select(Checkpoint).where(Checkpoint.checkpoint_id == checkpoint_id)
            result = await session.execute(stmt)
            checkpoint = result.scalar_one_or_none()

            if not checkpoint:
                return None

            # Convert DB model back to CheckpointData
            return CheckpointData(
                checkpoint_id=checkpoint.checkpoint_id,
                execution_id=checkpoint.execution_id,
                created_at=checkpoint.created_at,
                trigger=CheckpointTrigger(checkpoint.trigger),
                state=CheckpointState(checkpoint.state),
                root_dag=checkpoint.dag_snapshot,
                preserved_results=checkpoint.preserved_results,
                module_states=checkpoint.module_states,
                failed_task_ids=set(checkpoint.failed_task_ids),
                file_path=checkpoint.file_path
            )

    async def list_checkpoints(
        self,
        execution_id: str,
        limit: int = 50
    ) -> List[Checkpoint]:
        """List checkpoints for an execution.

        Args:
            execution_id: Execution identifier
            limit: Maximum number of results

        Returns:
            List of Checkpoint models ordered by creation time (newest first)
        """
        async with self.session() as session:
            stmt = (
                select(Checkpoint)
                .where(Checkpoint.execution_id == execution_id)
                .order_by(Checkpoint.created_at.desc())
                .limit(limit)
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def get_latest_checkpoint(
        self,
        execution_id: str,
        valid_only: bool = True
    ) -> Optional[CheckpointData]:
        """Get the most recent checkpoint for an execution.

        This is the primary method for visualization endpoints to retrieve
        DAG snapshots, replacing the deprecated Execution.dag_snapshot field.

        Args:
            execution_id: Execution identifier
            valid_only: If True, only return checkpoints with state='valid'

        Returns:
            CheckpointData for the latest checkpoint, or None if no checkpoints exist

        Example:
            ```python
            checkpoint = await storage.get_latest_checkpoint(execution_id)
            if checkpoint:
                dag = TaskDAG.from_dict(checkpoint.root_dag)
                # ... visualize DAG
            ```
        """
        async with self.session() as session:
            stmt = (
                select(Checkpoint)
                .where(Checkpoint.execution_id == execution_id)
                .order_by(Checkpoint.created_at.desc())
                .limit(1)
            )

            if valid_only:
                stmt = stmt.where(Checkpoint.state == CheckpointState.VALID.value)

            result = await session.execute(stmt)
            checkpoint = result.scalar_one_or_none()

            if not checkpoint:
                logger.debug(f"No {'valid ' if valid_only else ''}checkpoint found for execution {execution_id}")
                return None

            # Convert DB model back to CheckpointData
            checkpoint_data = CheckpointData(
                checkpoint_id=checkpoint.checkpoint_id,
                execution_id=checkpoint.execution_id,
                created_at=checkpoint.created_at,
                trigger=CheckpointTrigger(checkpoint.trigger),
                state=CheckpointState(checkpoint.state),
                root_dag=checkpoint.dag_snapshot,
                preserved_results=checkpoint.preserved_results,
                module_states=checkpoint.module_states,
                failed_task_ids=set(checkpoint.failed_task_ids),
                file_path=checkpoint.file_path
            )

            logger.debug(f"Retrieved latest checkpoint {checkpoint.checkpoint_id} for execution {execution_id}")
            return checkpoint_data

    async def delete_checkpoint(self, checkpoint_id: str) -> bool:
        """Delete checkpoint by ID.

        Args:
            checkpoint_id: Checkpoint identifier

        Returns:
            True if deleted, False if not found
        """
        async with self.session() as session:
            stmt = delete(Checkpoint).where(Checkpoint.checkpoint_id == checkpoint_id)
            result = await session.execute(stmt)
            deleted = result.rowcount > 0
            if deleted:
                logger.debug(f"Deleted checkpoint: {checkpoint_id}")
            return deleted

    # ==================== Task Trace Operations ====================

    async def save_task_trace(
        self,
        execution_id: str,
        task_id: str,
        task_type: str,
        status: str,
        depth: int,
        goal: Optional[str] = None,
        result: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
        **kwargs: Any
    ) -> TaskTrace:
        """Save task execution trace.

        Args:
            execution_id: Execution identifier
            task_id: Task identifier
            task_type: Task type (RETRIEVE, WRITE, etc.)
            status: Task status
            depth: Task depth in hierarchy
            goal: Optional task goal
            result: Optional task result
            error: Optional error message
            **kwargs: Additional fields (parent_task_id, dependencies, metadata, etc.)

        Returns:
            Created TaskTrace model

        Raises:
            SQLAlchemyError: On database error
        """
        async with self.session() as session:
            trace = TaskTrace(
                execution_id=execution_id,
                task_id=task_id,
                task_type=task_type,
                status=status,
                depth=depth,
                goal=goal,
                result=result,
                error=error,
                **kwargs
            )
            session.add(trace)
            await session.flush()
            logger.debug(f"Saved task trace: {task_id}")
            return trace

    async def get_task_traces(
        self,
        execution_id: str,
        status: Optional[str] = None,
        task_id: Optional[str] = None,
        limit: int = 1000
    ) -> List[TaskTrace]:
        """Get task traces with optional filtering.

        Args:
            execution_id: Execution identifier
            status: Optional status filter
            task_id: Optional task ID filter
            limit: Maximum number of results

        Returns:
            List of TaskTrace models
        """
        async with self.session() as session:
            stmt = (
                select(TaskTrace)
                .where(TaskTrace.execution_id == execution_id)
                .order_by(TaskTrace.created_at.desc())
                .limit(limit)
            )
            if status:
                stmt = stmt.where(TaskTrace.status == status)
            if task_id:
                stmt = stmt.where(TaskTrace.task_id == task_id)

            result = await session.execute(stmt)
            return list(result.scalars().all())

    # ==================== LM Trace Operations ====================

    async def save_lm_trace(
        self,
        execution_id: str,
        module_name: str,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        total_tokens: int,
        task_id: Optional[str] = None,
        cost_usd: Optional[float] = None,
        **kwargs: Any
    ) -> LMTrace:
        """Save LM call trace.

        Args:
            execution_id: Execution identifier
            module_name: Module name (planner, executor, etc.)
            model: Model identifier
            prompt_tokens: Prompt token count
            completion_tokens: Completion token count
            total_tokens: Total token count
            task_id: Optional task identifier
            cost_usd: Optional cost in USD
            **kwargs: Additional fields (prompt, response, latency_ms, etc.)

        Returns:
            Created LMTrace model

        Raises:
            SQLAlchemyError: On database error
        """
        async with self.session() as session:
            trace = LMTrace(
                execution_id=execution_id,
                task_id=task_id,
                module_name=module_name,
                model=model,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
                cost_usd=cost_usd,
                **kwargs
            )
            session.add(trace)
            await session.flush()
            logger.debug(f"Saved LM trace for module {module_name}")
            return trace

    async def get_lm_traces(
        self,
        execution_id: str,
        module_name: Optional[str] = None,
        model: Optional[str] = None,
        limit: int = 1000
    ) -> List[LMTrace]:
        """Get LM traces with optional filtering.

        Args:
            execution_id: Execution identifier
            module_name: Optional module filter
            model: Optional model filter
            limit: Maximum number of results

        Returns:
            List of LMTrace models
        """
        async with self.session() as session:
            stmt = (
                select(LMTrace)
                .where(LMTrace.execution_id == execution_id)
                .order_by(LMTrace.created_at.desc())
                .limit(limit)
            )
            if module_name:
                stmt = stmt.where(LMTrace.module_name == module_name)
            if model:
                stmt = stmt.where(LMTrace.model == model)

            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def get_lm_trace(self, trace_id: int) -> Optional[LMTrace]:
        """Get single LM trace by ID.

        Args:
            trace_id: LM trace identifier

        Returns:
            LMTrace model or None if not found
        """
        async with self.session() as session:
            stmt = select(LMTrace).where(LMTrace.trace_id == trace_id)
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def get_execution_costs(self, execution_id: str) -> Dict[str, Any]:
        """Calculate total costs for an execution.

        Args:
            execution_id: Execution identifier

        Returns:
            Dict with total_cost_usd, total_tokens, traces_count
        """
        traces = await self.get_lm_traces(execution_id)

        total_cost = sum(trace.cost_usd for trace in traces if trace.cost_usd) or 0.0
        total_tokens = sum(trace.total_tokens for trace in traces)

        return {
            "total_cost_usd": float(total_cost),
            "total_tokens": total_tokens,
            "traces_count": len(traces)
        }

    # ==================== Circuit Breaker Operations ====================

    async def update_circuit_breaker(
        self,
        circuit_id: str,
        state: str,
        config: Dict[str, Any],
        execution_id: Optional[str] = None,
        **kwargs: Any
    ) -> CircuitBreaker:
        """Update or create circuit breaker state.

        Args:
            circuit_id: Circuit identifier
            state: Circuit state (closed, open, half_open)
            config: Circuit configuration
            execution_id: Optional execution identifier
            **kwargs: Additional fields (failure_count, success_count, etc.)

        Returns:
            Updated/created CircuitBreaker model

        Raises:
            SQLAlchemyError: On database error
        """
        async with self.session() as session:
            # Try to find existing
            stmt = select(CircuitBreaker).where(CircuitBreaker.circuit_id == circuit_id)
            result = await session.execute(stmt)
            circuit = result.scalar_one_or_none()

            if circuit:
                # Update existing
                circuit.state = state
                circuit.config = config
                circuit.execution_id = execution_id or circuit.execution_id
                circuit.updated_at = datetime.now(timezone.utc)
                for key, value in kwargs.items():
                    setattr(circuit, key, value)
            else:
                # Create new
                circuit = CircuitBreaker(
                    circuit_id=circuit_id,
                    execution_id=execution_id,
                    state=state,
                    config=config,
                    **kwargs
                )
                session.add(circuit)

            await session.flush()
            logger.debug(f"Updated circuit breaker: {circuit_id}")
            return circuit

    async def get_circuit_breaker(self, circuit_id: str) -> Optional[CircuitBreaker]:
        """Get circuit breaker by ID.

        Args:
            circuit_id: Circuit identifier

        Returns:
            CircuitBreaker model or None if not found
        """
        async with self.session() as session:
            stmt = select(CircuitBreaker).where(CircuitBreaker.circuit_id == circuit_id)
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    # ==================== Event Trace Operations ====================

    async def save_event_trace(
        self,
        execution_id: str,
        event_type: str,
        priority: int,
        task_id: Optional[str] = None,
        dag_id: Optional[str] = None,
        event_data: Optional[Dict[str, Any]] = None,
        dropped: bool = False
    ) -> EventTrace:
        """Save event trace to database.

        Args:
            execution_id: Execution identifier
            event_type: Event type (READY, COMPLETED, FAILED, etc.)
            priority: Event priority
            task_id: Optional task identifier
            dag_id: Optional DAG identifier
            event_data: Optional event payload
            dropped: Whether event was dropped due to queue overflow

        Returns:
            Created EventTrace model

        Raises:
            SQLAlchemyError: On database error
        """
        async with self.session() as session:
            trace = EventTrace(
                execution_id=execution_id,
                task_id=task_id,
                dag_id=dag_id,
                event_type=event_type,
                priority=priority,
                event_data=event_data,
                dropped=dropped
            )
            session.add(trace)
            await session.flush()
            logger.debug(f"Saved event trace: {event_type} for task {task_id}")
            return trace

    async def update_event_processed(
        self,
        event_id: int,
        handler_name: str,
        latency_ms: int,
        error: Optional[str] = None
    ) -> None:
        """Update event with processing results.

        Args:
            event_id: Event trace identifier
            handler_name: Name of handler that processed event
            latency_ms: Processing latency in milliseconds
            error: Optional error message if processing failed

        Raises:
            SQLAlchemyError: On database error
        """
        async with self.session() as session:
            stmt = (
                update(EventTrace)
                .where(EventTrace.event_id == event_id)
                .values(
                    processed_at=datetime.now(timezone.utc),
                    handler_name=handler_name,
                    latency_ms=latency_ms,
                    processing_error=error
                )
            )
            await session.execute(stmt)
            logger.debug(f"Updated event {event_id} processing status")

    async def get_event_traces(
        self,
        execution_id: str,
        event_type: Optional[str] = None,
        task_id: Optional[str] = None,
        limit: int = 1000
    ) -> List[EventTrace]:
        """Get event traces with optional filtering.

        Args:
            execution_id: Execution identifier
            event_type: Optional event type filter
            task_id: Optional task ID filter
            limit: Maximum number of results

        Returns:
            List of EventTrace models ordered by creation time
        """
        async with self.session() as session:
            stmt = (
                select(EventTrace)
                .where(EventTrace.execution_id == execution_id)
                .order_by(EventTrace.created_at.asc())
                .limit(limit)
            )
            if event_type:
                stmt = stmt.where(EventTrace.event_type == event_type)
            if task_id:
                stmt = stmt.where(EventTrace.task_id == task_id)

            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def get_event_summary(self, execution_id: str) -> Dict[str, Any]:
        """Get event statistics summary for an execution.

        Args:
            execution_id: Execution identifier

        Returns:
            Dict with event counts by type, dropped events, avg latency
        """
        traces = await self.get_event_traces(execution_id, limit=10000)

        by_type: Dict[str, int] = {}
        processed_count = 0
        total_latency = 0
        dropped_count = 0
        error_count = 0

        for trace in traces:
            by_type[trace.event_type] = by_type.get(trace.event_type, 0) + 1
            if trace.processed_at:
                processed_count += 1
                if trace.latency_ms:
                    total_latency += trace.latency_ms
            if trace.dropped:
                dropped_count += 1
            if trace.processing_error:
                error_count += 1

        return {
            "total_events": len(traces),
            "by_type": by_type,
            "processed_count": processed_count,
            "dropped_count": dropped_count,
            "error_count": error_count,
            "avg_latency_ms": total_latency / processed_count if processed_count > 0 else 0
        }

    # ==================== Toolkit Metrics Operations ====================

    async def save_toolkit_trace(
        self,
        execution_id: str,
        operation: str,
        toolkit_class: Optional[str],
        duration_ms: float,
        success: bool,
        error: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> ToolkitTrace:
        """Save toolkit lifecycle trace.

        Args:
            execution_id: Execution identifier
            operation: Operation type (create, cache_hit, cache_miss, cleanup)
            toolkit_class: Name of toolkit class
            duration_ms: Operation duration in milliseconds
            success: Whether operation succeeded
            error: Optional error message
            metadata: Optional metadata (error_type, config, etc.)

        Returns:
            Created ToolkitTrace model

        Raises:
            SQLAlchemyError: On database error
        """
        async with self.session() as session:
            trace = ToolkitTrace(
                execution_id=execution_id,
                operation=operation,
                toolkit_class=toolkit_class,
                duration_ms=duration_ms,
                success=success,
                error=error,
                metadata=metadata or {}
            )
            session.add(trace)
            await session.flush()
            logger.debug(f"Saved toolkit trace: {toolkit_class} {operation}")
            return trace

    async def save_tool_invocation_trace(
        self,
        execution_id: str,
        toolkit_class: str,
        tool_name: str,
        duration_ms: float,
        input_size_bytes: int,
        output_size_bytes: int,
        success: bool,
        error: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> ToolInvocationTrace:
        """Save tool invocation trace.

        Args:
            execution_id: Execution identifier
            toolkit_class: Name of toolkit class
            tool_name: Name of tool invoked
            duration_ms: Invocation duration in milliseconds
            input_size_bytes: Size of input data in bytes
            output_size_bytes: Size of output data in bytes
            success: Whether invocation succeeded
            error: Optional error message
            metadata: Optional metadata (error_type, params, etc.)

        Returns:
            Created ToolInvocationTrace model

        Raises:
            SQLAlchemyError: On database error
        """
        async with self.session() as session:
            trace = ToolInvocationTrace(
                execution_id=execution_id,
                toolkit_class=toolkit_class,
                tool_name=tool_name,
                duration_ms=duration_ms,
                input_size_bytes=input_size_bytes,
                output_size_bytes=output_size_bytes,
                success=success,
                error=error,
                metadata=metadata or {}
            )
            session.add(trace)
            await session.flush()
            logger.debug(f"Saved tool invocation trace: {toolkit_class}.{tool_name}")
            return trace

    async def get_toolkit_traces(
        self,
        execution_id: str,
        operation: Optional[str] = None,
        toolkit_class: Optional[str] = None,
        limit: int = 1000
    ) -> List[ToolkitTrace]:
        """Get toolkit traces with optional filtering.

        Args:
            execution_id: Execution identifier
            operation: Optional operation filter (create, cache_hit, etc.)
            toolkit_class: Optional toolkit class filter
            limit: Maximum number of results

        Returns:
            List of ToolkitTrace models
        """
        async with self.session() as session:
            stmt = (
                select(ToolkitTrace)
                .where(ToolkitTrace.execution_id == execution_id)
                .order_by(ToolkitTrace.timestamp.asc())
                .limit(limit)
            )
            if operation:
                stmt = stmt.where(ToolkitTrace.operation == operation)
            if toolkit_class:
                stmt = stmt.where(ToolkitTrace.toolkit_class == toolkit_class)

            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def get_tool_invocation_traces(
        self,
        execution_id: str,
        toolkit_class: Optional[str] = None,
        tool_name: Optional[str] = None,
        limit: int = 1000
    ) -> List[ToolInvocationTrace]:
        """Get tool invocation traces with optional filtering.

        Args:
            execution_id: Execution identifier
            toolkit_class: Optional toolkit class filter
            tool_name: Optional tool name filter
            limit: Maximum number of results

        Returns:
            List of ToolInvocationTrace models
        """
        async with self.session() as session:
            stmt = (
                select(ToolInvocationTrace)
                .where(ToolInvocationTrace.execution_id == execution_id)
                .order_by(ToolInvocationTrace.invoked_at.asc())
                .limit(limit)
            )
            if toolkit_class:
                stmt = stmt.where(ToolInvocationTrace.toolkit_class == toolkit_class)
            if tool_name:
                stmt = stmt.where(ToolInvocationTrace.tool_name == tool_name)

            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def get_toolkit_metrics_summary(self, execution_id: str) -> Dict[str, Any]:
        """Calculate toolkit metrics summary for an execution.

        Args:
            execution_id: Execution identifier

        Returns:
            Dict with toolkit lifecycle and tool invocation metrics
        """
        from roma_dspy.tools.metrics.models import (
            ToolkitLifecycleEvent,
            ToolInvocationEvent,
            aggregate_toolkit_metrics
        )

        # Get traces from database
        lifecycle_traces = await self.get_toolkit_traces(execution_id)
        invocation_traces = await self.get_tool_invocation_traces(execution_id)

        # Convert to event models
        lifecycle_events = [
            ToolkitLifecycleEvent(
                execution_id=trace.execution_id,
                timestamp=trace.timestamp,
                operation=trace.operation,
                toolkit_class=trace.toolkit_class,
                duration_ms=trace.duration_ms,
                success=trace.success,
                error=trace.error,
                metadata=trace.metadata
            )
            for trace in lifecycle_traces
        ]

        invocation_events = [
            ToolInvocationEvent(
                execution_id=trace.execution_id,
                toolkit_class=trace.toolkit_class,
                tool_name=trace.tool_name,
                invoked_at=trace.invoked_at,
                duration_ms=trace.duration_ms,
                input_size_bytes=trace.input_size_bytes,
                output_size_bytes=trace.output_size_bytes,
                success=trace.success,
                error=trace.error,
                metadata=trace.metadata
            )
            for trace in invocation_traces
        ]

        # Aggregate metrics
        if not invocation_events:
            # Return empty summary if no data
            return {
                "execution_id": execution_id,
                "toolkit_lifecycle": {
                    "total_created": 0,
                    "cache_hit_rate": 0.0,
                },
                "tool_invocations": {
                    "total_calls": 0,
                    "successful_calls": 0,
                    "failed_calls": 0,
                    "success_rate": 0.0,
                    "avg_duration_ms": 0.0,
                    "total_duration_ms": 0.0,
                },
                "by_toolkit": {},
                "by_tool": {}
            }

        summary = aggregate_toolkit_metrics(lifecycle_events, invocation_events)
        return summary.to_response_dict()

    # ==================== Cleanup Operations ====================

    async def cleanup_old_executions(self, days: int = 30) -> int:
        """Delete executions older than specified days.

        Args:
            days: Delete executions older than this many days

        Returns:
            Number of executions deleted
        """
        from datetime import timedelta

        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        async with self.session() as session:
            stmt = delete(Execution).where(Execution.created_at < cutoff)
            result = await session.execute(stmt)
            deleted = result.rowcount
            if deleted > 0:
                logger.info(f"Cleaned up {deleted} old executions")
            return deleted

    async def close(self) -> None:
        """Close database connections for current thread (alias for shutdown)."""
        await self.shutdown()

    async def shutdown(self) -> None:
        """Cleanup database connections for current thread.

        Each thread manages its own engine lifecycle. This only affects
        the calling thread's engine.

        Thread-safe: Works correctly when called from DSPy's ParallelExecutor
        worker threads, even when event loop is about to close.
        """
        if self._local.engine:
            try:
                # Use sync disposal to avoid event loop dependency
                # This is critical for worker threads where asyncio.run() is about to close the loop
                # Reference: https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html#using-asyncio-scoped-session
                await self._local.engine.dispose()
                logger.debug(f"PostgresStorage disposed engine for thread {threading.get_ident()}")
            except RuntimeError as e:
                # Event loop already closed - this is expected in worker threads
                # The connections will be cleaned up by the engine's finalizer
                if "Event loop is closed" in str(e) or "no running event loop" in str(e).lower():
                    logger.debug(
                        f"PostgresStorage: Event loop closed before engine disposal in thread {threading.get_ident()}. "
                        "Connection cleanup will be handled by finalizer (expected in worker threads)."
                    )
                else:
                    # Unexpected RuntimeError - log but don't fail
                    logger.warning(f"PostgresStorage shutdown error in thread {threading.get_ident()}: {e}")
            except Exception as e:
                # Other errors - log but don't fail
                logger.warning(f"PostgresStorage shutdown error in thread {threading.get_ident()}: {e}")
            finally:
                # Always reset state, even if disposal failed
                logger.info(f"PostgresStorage shutdown complete for thread {threading.get_ident()}")
                self._local.initialized = False
                self._local.engine = None
                self._local.session_factory = None
                self._local.event_loop_id = None
