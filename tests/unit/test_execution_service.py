"""Unit tests for ExecutionService."""

import asyncio
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

from roma_dspy.api.execution_service import ExecutionService, ExecutionCache


class TestExecutionCache:
    """Tests for ExecutionCache."""

    def test_cache_miss(self):
        """Test cache miss returns None."""
        cache = ExecutionCache(ttl_seconds=5)
        assert cache.get("missing-id") is None

    def test_cache_hit(self):
        """Test cache hit returns data."""
        cache = ExecutionCache(ttl_seconds=5)
        data = {"status": "running"}
        cache.set("exec-1", data)
        assert cache.get("exec-1") == data

    def test_cache_expiration(self):
        """Test cache expires after TTL."""
        cache = ExecutionCache(ttl_seconds=0)  # Immediate expiration
        cache.set("exec-1", {"status": "running"})

        # Should be expired immediately
        import time

        time.sleep(0.01)
        assert cache.get("exec-1") is None

    def test_cache_invalidate(self):
        """Test manual cache invalidation."""
        cache = ExecutionCache(ttl_seconds=5)
        cache.set("exec-1", {"status": "running"})
        cache.invalidate("exec-1")
        assert cache.get("exec-1") is None

    def test_cache_clear(self):
        """Test clearing all cache entries."""
        cache = ExecutionCache(ttl_seconds=5)
        cache.set("exec-1", {"status": "running"})
        cache.set("exec-2", {"status": "completed"})
        cache.clear()
        assert cache.size() == 0

    def test_cache_size(self):
        """Test cache size tracking."""
        cache = ExecutionCache(ttl_seconds=5)
        assert cache.size() == 0
        cache.set("exec-1", {"status": "running"})
        assert cache.size() == 1
        cache.set("exec-2", {"status": "completed"})
        assert cache.size() == 2


class TestExecutionService:
    """Tests for ExecutionService."""

    @pytest.fixture
    def mock_storage(self):
        """Create mock storage."""
        storage = AsyncMock()
        storage.create_execution = AsyncMock(return_value=None)
        storage.update_execution = AsyncMock(return_value=None)
        storage.get_execution = AsyncMock()
        return storage

    @pytest.fixture
    def mock_config_manager(self):
        """Create mock config manager."""
        from unittest.mock import MagicMock
        from omegaconf import OmegaConf

        manager = MagicMock()
        # Use OmegaConf directly so config_to_dict can serialize it
        mock_config = OmegaConf.create({"test": "config", "observability": None})
        manager.load_config.return_value = mock_config
        return manager

    @pytest.fixture
    def service(self, mock_storage, mock_config_manager):
        """Create ExecutionService instance."""
        return ExecutionService(
            storage=mock_storage,
            config_manager=mock_config_manager,
            cache_ttl_seconds=5,
        )

    @pytest.mark.asyncio
    async def test_start_execution(self, service, mock_storage):
        """Test starting a new execution."""
        with patch(
            "roma_dspy.api.execution_service.RecursiveSolver"
        ) as mock_solver_class:
            # Mock the solver instance with a long-running task
            mock_solver = AsyncMock()

            async def long_running_solve(*args, **kwargs):
                await asyncio.sleep(1.0)  # Keep running
                return AsyncMock(status="completed")

            mock_solver.async_solve = long_running_solve
            mock_solver_class.return_value = mock_solver

            exec_id = await service.start_execution(goal="Test task", max_depth=2)

            assert exec_id is not None
            mock_storage.create_execution.assert_called_once()

            # Wait a bit for background task to start
            await asyncio.sleep(0.05)

            # Verify execution is tracked
            assert service.is_running(exec_id)

    @pytest.mark.asyncio
    async def test_get_execution_status_cached(self, service, mock_storage):
        """Test getting execution status with caching."""
        mock_execution = AsyncMock()
        mock_execution.execution_id = "exec-123"
        mock_execution.status = "running"
        mock_execution.initial_goal = "Test"
        mock_execution.total_tasks = 10
        mock_execution.completed_tasks = 5
        mock_execution.failed_tasks = 0
        mock_execution.created_at = datetime.now(timezone.utc)
        mock_execution.updated_at = datetime.now(timezone.utc)

        mock_storage.get_execution.return_value = mock_execution

        # First call - should query storage
        status1 = await service.get_execution_status("exec-123")
        assert status1 is not None
        assert mock_storage.get_execution.call_count == 1

        # Second call - should use cache
        status2 = await service.get_execution_status("exec-123")
        assert status2 is not None
        assert mock_storage.get_execution.call_count == 1  # Still only 1 call

    @pytest.mark.asyncio
    async def test_get_execution_status_not_found(self, service, mock_storage):
        """Test getting status for non-existent execution."""
        mock_storage.get_execution.return_value = None

        status = await service.get_execution_status("missing-id")
        assert status is None

    @pytest.mark.asyncio
    async def test_cancel_execution(self, service, mock_storage):
        """Test canceling a running execution."""
        with patch(
            "roma_dspy.api.execution_service.RecursiveSolver"
        ) as mock_solver_class:
            mock_solver = AsyncMock()

            async def long_running_solve(*args, **kwargs):
                await asyncio.sleep(1.0)  # Keep running
                return AsyncMock(status="completed")

            mock_solver.async_solve = long_running_solve
            mock_solver_class.return_value = mock_solver

            # Start an execution
            exec_id = await service.start_execution(goal="Test", max_depth=2)

            # Wait for it to start
            await asyncio.sleep(0.05)

            # Cancel it
            cancelled = await service.cancel_execution(exec_id)
            assert cancelled is True

            # Verify storage was updated
            mock_storage.update_execution.assert_called()

    @pytest.mark.asyncio
    async def test_cancel_non_running_execution(self, service):
        """Test canceling a non-running execution."""
        cancelled = await service.cancel_execution("non-existent")
        assert cancelled is False

    def test_is_running(self, service):
        """Test checking if execution is running."""
        assert not service.is_running("non-existent")

    def test_get_active_executions(self, service):
        """Test getting list of active executions."""
        active = service.get_active_executions()
        assert isinstance(active, list)
        assert len(active) == 0

    @pytest.mark.asyncio
    async def test_cleanup_completed_tasks(self, service, mock_storage):
        """Test cleanup of completed background tasks."""
        with patch(
            "roma_dspy.api.execution_service.RecursiveSolver"
        ) as mock_solver_class:
            mock_solver = AsyncMock()
            mock_solver.async_solve = AsyncMock(
                return_value=AsyncMock(status="completed")
            )
            mock_solver_class.return_value = mock_solver

            # Start an execution
            exec_id = await service.start_execution(goal="Test", max_depth=2)

            # Wait for it to process
            await asyncio.sleep(0.2)

            # Cleanup
            cleaned = await service.cleanup_completed_tasks()
            assert isinstance(cleaned, int)

    @pytest.mark.asyncio
    async def test_shutdown(self, service, mock_storage):
        """Test service shutdown."""
        with patch(
            "roma_dspy.api.execution_service.RecursiveSolver"
        ) as mock_solver_class:
            mock_solver = AsyncMock()
            mock_solver.async_solve = AsyncMock(
                return_value=AsyncMock(status="completed")
            )
            mock_solver_class.return_value = mock_solver

            # Start an execution
            exec_id = await service.start_execution(goal="Test", max_depth=2)

            # Wait for it to start
            await asyncio.sleep(0.1)

            # Shutdown
            await service.shutdown()

            # Verify cache is cleared
            assert service.cache.size() == 0

    @pytest.mark.asyncio
    async def test_execution_error_handling(self, service, mock_storage):
        """Test error handling in background execution."""
        # Mock RecursiveSolver to raise error
        with patch("roma_dspy.api.execution_service.RecursiveSolver") as mock_solver:
            mock_solver.return_value.async_solve = AsyncMock(
                side_effect=Exception("Test error")
            )

            exec_id = await service.start_execution(goal="Test", max_depth=2)

            # Wait for execution to fail
            await asyncio.sleep(0.2)

            # Verify storage was updated with failure
            calls = [
                call
                for call in mock_storage.update_execution.call_args_list
                if "status" in call.kwargs and call.kwargs["status"] == "failed"
            ]
            assert len(calls) > 0
