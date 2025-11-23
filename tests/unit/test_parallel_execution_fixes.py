"""
Tests for parallel execution fixes with DSPy's ParallelExecutor.

Validates that:
1. PostgresStorage shutdown works correctly in worker threads
2. Event loop cleanup doesn't cause RuntimeError
3. Multiple parallel executions complete successfully
4. Database connections are properly cleaned up
"""

import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock, patch

import pytest

from roma_dspy.core.storage.postgres_storage import PostgresStorage
from roma_dspy.config.schemas.storage import PostgresConfig


class TestParallelExecutionFixes:
    """Test fixes for parallel execution with DSPy's ParallelExecutor."""

    def test_postgres_shutdown_in_worker_thread(self):
        """Test that PostgresStorage.shutdown() works in worker threads."""

        async def worker_task():
            """Simulate a worker thread task that uses PostgresStorage."""
            # Create config with disabled storage (no actual DB needed for this test)
            config = PostgresConfig(
                enabled=False,  # Disable actual DB connection
                host="localhost",
                port=5432,
                database="test",
                user="test",
                password="test",
            )
            storage = PostgresStorage(config)

            # Simulate initialized state
            storage._local.initialized = True
            storage._local.engine = Mock()
            storage._local.session_factory = Mock()
            storage._local.event_loop_id = id(asyncio.get_running_loop())

            # Mock the dispose to raise RuntimeError (event loop closed)
            async def mock_dispose():
                raise RuntimeError("Event loop is closed")

            storage._local.engine.dispose = mock_dispose

            # This should not raise - it should handle the error gracefully
            await storage.shutdown()

            # Verify state was reset
            assert not storage._local.initialized
            assert storage._local.engine is None
            assert storage._local.session_factory is None
            assert storage._local.event_loop_id is None

        # Run the task in a new event loop (simulates worker thread)
        asyncio.run(worker_task())

    def test_postgres_shutdown_success_case(self):
        """Test that PostgresStorage.shutdown() works when dispose succeeds."""

        async def worker_task():
            """Simulate successful shutdown."""
            config = PostgresConfig(
                enabled=False,
                host="localhost",
                port=5432,
                database="test",
                user="test",
                password="test",
            )
            storage = PostgresStorage(config)

            # Simulate initialized state
            storage._local.initialized = True
            storage._local.engine = Mock()
            storage._local.session_factory = Mock()
            storage._local.event_loop_id = id(asyncio.get_running_loop())

            # Mock successful dispose
            async def mock_dispose():
                pass

            storage._local.engine.dispose = mock_dispose

            # This should work without errors
            await storage.shutdown()

            # Verify state was reset
            assert not storage._local.initialized
            assert storage._local.engine is None

        asyncio.run(worker_task())

    def test_parallel_execution_with_thread_pool(self):
        """Test that multiple parallel executions work correctly."""

        def worker(task_id: int) -> str:
            """Worker function that runs in a thread pool."""

            async def async_work():
                """Async work that simulates event_solve behavior."""
                # Simulate some async work
                await asyncio.sleep(0.01)

                # Create and cleanup storage (simulating event_solve cleanup)
                config = PostgresConfig(
                    enabled=False,
                    host="localhost",
                    port=5432,
                    database="test",
                    user="test",
                    password="test",
                )
                storage = PostgresStorage(config)

                # Simulate initialized state
                storage._local.initialized = True
                storage._local.engine = Mock()
                storage._local.session_factory = Mock()
                storage._local.event_loop_id = id(asyncio.get_running_loop())

                # Mock dispose that might fail
                call_count = [0]

                async def mock_dispose():
                    call_count[0] += 1
                    if call_count[0] == 1 and task_id % 2 == 0:
                        # Simulate event loop closed for some workers
                        raise RuntimeError("Event loop is closed")

                storage._local.engine.dispose = mock_dispose

                try:
                    return f"Task {task_id} completed"
                finally:
                    # This is what event_solve does
                    if storage._local.initialized:
                        await storage.shutdown()

            # Each worker gets its own event loop
            return asyncio.run(async_work())

        # Run multiple tasks in parallel (simulates DSPy's ParallelExecutor)
        with ThreadPoolExecutor(max_workers=4) as executor:
            results = list(executor.map(worker, range(8)))

        # All tasks should complete successfully
        assert len(results) == 8
        for i, result in enumerate(results):
            assert result == f"Task {i} completed"

    def test_event_loop_detection_in_shutdown(self):
        """Test that shutdown correctly detects different event loop error messages."""

        test_cases = [
            "Event loop is closed",
            "RuntimeError: Event loop is closed",
            "no running event loop",
            "Task got Future attached to a different loop",
        ]

        for error_msg in test_cases:

            async def test_error_handling():
                config = PostgresConfig(
                    enabled=False,
                    host="localhost",
                    port=5432,
                    database="test",
                    user="test",
                    password="test",
                )
                storage = PostgresStorage(config)

                storage._local.initialized = True
                storage._local.engine = Mock()
                storage._local.session_factory = Mock()
                storage._local.event_loop_id = id(asyncio.get_running_loop())

                async def mock_dispose():
                    raise RuntimeError(error_msg)

                storage._local.engine.dispose = mock_dispose

                # Should not raise
                await storage.shutdown()

                # Should be cleaned up
                assert not storage._local.initialized

            asyncio.run(test_error_handling())

    def test_thread_local_isolation(self):
        """Test that each thread gets isolated PostgresStorage state."""

        results = {}

        def worker(thread_id: int):
            """Worker that checks thread-local isolation."""

            async def check_isolation():
                config = PostgresConfig(
                    enabled=False,
                    host="localhost",
                    port=5432,
                    database="test",
                    user="test",
                    password="test",
                )
                storage = PostgresStorage(config)

                # Each thread should start uninitialized
                assert not storage._local.initialized

                # Simulate initialization
                storage._local.initialized = True
                storage._local.engine = Mock()
                storage._local.event_loop_id = (
                    thread_id  # Use thread_id as unique marker
                )

                # Store thread-specific data
                thread_ident = threading.get_ident()
                results[thread_ident] = storage._local.event_loop_id

                return thread_ident

            return asyncio.run(check_isolation())

        # Run workers in parallel
        with ThreadPoolExecutor(max_workers=3) as executor:
            thread_idents = list(executor.map(worker, range(3)))

        # Each thread should have unique results
        assert len(results) == 3
        assert len(set(results.values())) == 3  # All unique loop IDs
        assert len(set(thread_idents)) == 3  # All unique thread IDs


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
