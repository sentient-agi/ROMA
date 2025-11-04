"""ExecutionService for managing solver lifecycle and background tasks."""

import asyncio
from datetime import datetime, timezone
from typing import Dict, Optional, Any
from uuid import uuid4

from loguru import logger

from roma_dspy.core.engine.solve import RecursiveSolver
from roma_dspy.core.storage.postgres_storage import PostgresStorage
from roma_dspy.core.engine.dag import TaskDAG
from roma_dspy.config.manager import ConfigManager
from roma_dspy.types import ExecutionStatus


class ExecutionCache:
    """
    In-memory cache for execution status with TTL.

    Reduces database load for frequent polling.
    """

    def __init__(self, ttl_seconds: int = 5):
        """
        Initialize cache with TTL.

        Args:
            ttl_seconds: Time-to-live for cached entries
        """
        self.ttl_seconds = ttl_seconds
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._timestamps: Dict[str, datetime] = {}

    def get(self, execution_id: str) -> Optional[Dict[str, Any]]:
        """Get cached execution data if not expired."""
        if execution_id not in self._cache:
            return None

        timestamp = self._timestamps[execution_id]
        age = (datetime.now(timezone.utc) - timestamp).total_seconds()

        if age > self.ttl_seconds:
            # Expired
            del self._cache[execution_id]
            del self._timestamps[execution_id]
            return None

        return self._cache[execution_id]

    def set(self, execution_id: str, data: Dict[str, Any]) -> None:
        """Cache execution data with current timestamp."""
        self._cache[execution_id] = data
        self._timestamps[execution_id] = datetime.now(timezone.utc)

    def invalidate(self, execution_id: str) -> None:
        """Invalidate cached entry."""
        self._cache.pop(execution_id, None)
        self._timestamps.pop(execution_id, None)

    def clear(self) -> None:
        """Clear all cached entries."""
        self._cache.clear()
        self._timestamps.clear()

    def size(self) -> int:
        """Get current cache size."""
        return len(self._cache)


class ExecutionService:
    """
    Manages execution lifecycle for RecursiveSolver.

    Responsibilities:
    - Background task management
    - In-memory status caching
    - Error propagation
    - Execution cleanup

    NOT responsible for:
    - Checkpoint management (use RecursiveSolver directly)
    - Visualization (use visualizer classes directly)
    """

    def __init__(
        self,
        storage: PostgresStorage,
        config_manager: ConfigManager,
        cache_ttl_seconds: int = 5
    ):
        """
        Initialize ExecutionService.

        Args:
            storage: PostgresStorage instance
            config_manager: ConfigManager instance
            cache_ttl_seconds: Cache TTL in seconds (default: 5)
        """
        self.storage = storage
        self.config_manager = config_manager
        self.cache = ExecutionCache(ttl_seconds=cache_ttl_seconds)

        # Track background tasks
        self._background_tasks: Dict[str, asyncio.Task] = {}

        logger.info("ExecutionService initialized")

    async def start_execution(
        self,
        goal: str,
        max_depth: int = 2,
        config_profile: str = "default",
        config_overrides: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Start a new execution in the background.

        Args:
            goal: Task goal to decompose and execute
            max_depth: Maximum recursion depth
            config_profile: Configuration profile name (required)
            config_overrides: Configuration overrides
            metadata: Additional metadata

        Returns:
            Execution ID
        """
        execution_id = str(uuid4())

        # Load configuration
        config = self.config_manager.load_config(
            profile=config_profile,
            overrides=config_overrides or {}
        )

        # Extract experiment name from config (defensive: handle missing/None observability fields)
        experiment_name = "unknown"
        if config.observability and config.observability.mlflow:
            experiment_name = getattr(config.observability.mlflow, 'experiment_name', 'unknown')

        # Enhance metadata with profile and experiment info
        enhanced_metadata = metadata or {}
        enhanced_metadata.update({
            "profile_name": config_profile,
            "experiment_name": experiment_name,
        })

        # Create execution record
        await self.storage.create_execution(
            execution_id=execution_id,
            initial_goal=goal,
            max_depth=max_depth,
            profile=config_profile,
            experiment_name=experiment_name,
            config=config.model_dump() if hasattr(config, 'model_dump') else dict(config),
            metadata=enhanced_metadata
        )

        # Start background task
        task = asyncio.create_task(
            self._run_execution(execution_id, goal, max_depth, config)
        )
        self._background_tasks[execution_id] = task

        logger.info(f"Started execution {execution_id} (profile={config_profile}, experiment={experiment_name}) for goal: {goal[:100]}")
        return execution_id

    async def _run_execution(
        self,
        execution_id: str,
        goal: str,
        max_depth: int,
        config: Any
    ) -> None:
        """
        Run execution in background with error handling.

        Args:
            execution_id: Execution ID
            goal: Task goal
            max_depth: Maximum recursion depth
            config: Configuration object
        """
        try:
            # Update status to running
            await self.storage.update_execution(
                execution_id=execution_id,
                status=ExecutionStatus.RUNNING.value
            )
            self.cache.invalidate(execution_id)

            # Create solver
            solver = RecursiveSolver(
                config=config,
                storage=self.storage,
                execution_id=execution_id
            )

            # Execute
            logger.info(f"Executing {execution_id}")
            result = await solver.async_solve(goal, depth=0)

            # DAG snapshot now saved via checkpoints (see checkpoint_manager)
            # Update status to completed with final result
            await self.storage.update_execution(
                execution_id=execution_id,
                status=ExecutionStatus.COMPLETED.value,
                final_result={"result": result.result, "status": result.status.value} if result else None
            )
            self.cache.invalidate(execution_id)

            logger.info(f"Execution {execution_id} completed successfully")

        except Exception as e:
            logger.error(f"Execution {execution_id} failed: {e}")

            # Update status to failed - merge error info with existing metadata
            try:
                execution = await self.storage.get_execution(execution_id)

                # Safely merge metadata
                existing_metadata = {}
                if execution and hasattr(execution, 'execution_metadata') and execution.execution_metadata:
                    existing_metadata = execution.execution_metadata if isinstance(execution.execution_metadata, dict) else {}

                merged_metadata = {
                    **existing_metadata,
                    "error": str(e),
                    "error_type": type(e).__name__
                }

                await self.storage.update_execution(
                    execution_id=execution_id,
                    status=ExecutionStatus.FAILED.value,
                    execution_metadata=merged_metadata
                )
                self.cache.invalidate(execution_id)
            except Exception as storage_error:
                logger.error(
                    f"Failed to update execution {execution_id} status: {storage_error}"
                )

        finally:
            # Cleanup background task reference
            self._background_tasks.pop(execution_id, None)

            # Periodic cleanup if too many completed tasks
            if len(self._background_tasks) > 100:
                await self.cleanup_completed_tasks()

    async def get_execution_status(self, execution_id: str) -> Optional[Dict[str, Any]]:
        """
        Get execution status with caching.

        Args:
            execution_id: Execution ID

        Returns:
            Execution status dictionary or None if not found
        """
        # Check cache first
        cached = self.cache.get(execution_id)
        if cached:
            return cached

        # Fetch from storage
        execution = await self.storage.get_execution(execution_id)
        if not execution:
            return None

        status_data = {
            "execution_id": execution.execution_id,
            "status": execution.status,
            "initial_goal": execution.initial_goal,
            "total_tasks": execution.total_tasks,
            "completed_tasks": execution.completed_tasks,
            "failed_tasks": execution.failed_tasks,
            "created_at": execution.created_at.isoformat(),
            "updated_at": execution.updated_at.isoformat(),
        }

        # Cache it
        self.cache.set(execution_id, status_data)

        return status_data

    async def cancel_execution(self, execution_id: str) -> bool:
        """
        Cancel a running execution.

        Args:
            execution_id: Execution ID to cancel

        Returns:
            True if cancelled, False if not running
        """
        task = self._background_tasks.get(execution_id)
        if not task:
            logger.warning(f"No running task found for execution {execution_id}")
            return False

        # Cancel the task
        task.cancel()

        try:
            await task
        except asyncio.CancelledError:
            logger.info(f"Execution {execution_id} cancelled")

        # Update status
        await self.storage.update_execution(
            execution_id=execution_id,
            status=ExecutionStatus.CANCELLED.value
        )
        self.cache.invalidate(execution_id)

        # Cleanup
        self._background_tasks.pop(execution_id, None)

        return True

    def is_running(self, execution_id: str) -> bool:
        """Check if execution is currently running in background."""
        task = self._background_tasks.get(execution_id)
        return task is not None and not task.done()

    def get_active_executions(self) -> list[str]:
        """Get list of active execution IDs."""
        return [
            exec_id
            for exec_id, task in self._background_tasks.items()
            if not task.done()
        ]

    async def cleanup_completed_tasks(self) -> int:
        """
        Clean up completed background tasks.

        Returns:
            Number of tasks cleaned up
        """
        completed = [
            exec_id
            for exec_id, task in self._background_tasks.items()
            if task.done()
        ]

        for exec_id in completed:
            self._background_tasks.pop(exec_id)

        return len(completed)

    async def shutdown(self) -> None:
        """Shutdown service and cancel all running tasks."""
        logger.info("Shutting down ExecutionService")

        # Cancel all running tasks
        for exec_id, task in list(self._background_tasks.items()):
            if not task.done():
                logger.info(f"Cancelling execution {exec_id}")
                task.cancel()

                try:
                    await task
                except asyncio.CancelledError:
                    pass

        # Clear cache
        self.cache.clear()

        logger.info("ExecutionService shutdown complete")