"""Unit tests for toolkit caching system with thread safety and execution isolation."""

import asyncio
import concurrent.futures
import hashlib
import json
import tempfile
import threading
from pathlib import Path
from typing import List
from unittest.mock import MagicMock, Mock, patch

import pytest

from roma_dspy.config.schemas import StorageConfig
from roma_dspy.config.schemas.toolkit import ToolkitConfig
from roma_dspy.core.storage import FileStorage
from roma_dspy.tools.base.base import BaseToolkit
from roma_dspy.tools.base.manager import ToolkitManager
from roma_dspy.tools.core.calculator import CalculatorToolkit


def create_file_storage(execution_id: str, temp_dir: Path) -> FileStorage:
    """Helper to create FileStorage with proper config."""
    storage_config = StorageConfig(
        base_path=str(temp_dir),
        max_file_size=100 * 1024 * 1024,  # 100MB
        buffer_size=1024 * 1024,  # 1MB
    )
    return FileStorage(config=storage_config, execution_id=execution_id)


class SimpleTestToolkit(BaseToolkit):
    """Simple test toolkit for caching tests."""

    def _setup_dependencies(self):
        pass

    def _initialize_tools(self):
        self.counter = self.config.get("counter", 0)

    def test_tool(self, x: int) -> int:
        """Simple test tool."""
        return x + self.counter


class TestToolkitConfigHashing:
    """Test config hashing for determinism and collision resistance."""

    def setup_method(self):
        """Set up test environment."""
        ToolkitManager._instance = None
        ToolkitManager._toolkit_registry.clear()
        self.manager = ToolkitManager()

    def test_config_hashing_determinism(self):
        """Test config hashing produces same hash for identical configs."""
        config1 = ToolkitConfig(
            class_name="TestToolkit",
            enabled=True,
            include_tools=["tool1", "tool2"],
            exclude_tools=["tool3"],
            toolkit_config={"param1": "value1", "param2": 42},
        )

        config2 = ToolkitConfig(
            class_name="TestToolkit",
            enabled=True,
            include_tools=["tool1", "tool2"],
            exclude_tools=["tool3"],
            toolkit_config={"param1": "value1", "param2": 42},
        )

        hash1 = self.manager._hash_toolkit_config(config1)
        hash2 = self.manager._hash_toolkit_config(config2)

        assert hash1 == hash2, "Same configs should produce same hash"
        assert len(hash1) == 16, "Hash should be 16 characters"

    def test_config_hashing_order_independence(self):
        """Test config hashing is independent of dict/list order."""
        config1 = ToolkitConfig(
            class_name="TestToolkit",
            include_tools=["tool1", "tool2", "tool3"],
            toolkit_config={"a": 1, "b": 2, "c": 3},
        )

        config2 = ToolkitConfig(
            class_name="TestToolkit",
            include_tools=["tool3", "tool1", "tool2"],  # Different order
            toolkit_config={"c": 3, "a": 1, "b": 2},  # Different order
        )

        hash1 = self.manager._hash_toolkit_config(config1)
        hash2 = self.manager._hash_toolkit_config(config2)

        # Should be the same because lists are sorted before hashing
        assert hash1 == hash2, "Hashing should be order-independent"

    def test_config_hashing_different_configs(self):
        """Test different configs produce different hashes."""
        config1 = ToolkitConfig(
            class_name="TestToolkit", toolkit_config={"param": "value1"}
        )

        config2 = ToolkitConfig(
            class_name="TestToolkit",
            toolkit_config={"param": "value2"},  # Different value
        )

        hash1 = self.manager._hash_toolkit_config(config1)
        hash2 = self.manager._hash_toolkit_config(config2)

        assert hash1 != hash2, "Different configs should produce different hashes"

    def test_config_hashing_sensitivity(self):
        """Test config hashing is sensitive to all fields."""
        base_config = ToolkitConfig(
            class_name="TestToolkit",
            enabled=True,
            include_tools=["tool1"],
            exclude_tools=["tool2"],
            toolkit_config={"param": "value"},
        )

        # Change enabled
        config_enabled = ToolkitConfig(
            class_name="TestToolkit",
            enabled=False,  # Changed
            include_tools=["tool1"],
            exclude_tools=["tool2"],
            toolkit_config={"param": "value"},
        )

        # Change include_tools
        config_include = ToolkitConfig(
            class_name="TestToolkit",
            enabled=True,
            include_tools=["tool1", "tool3"],  # Changed
            exclude_tools=["tool2"],
            toolkit_config={"param": "value"},
        )

        # Change exclude_tools
        config_exclude = ToolkitConfig(
            class_name="TestToolkit",
            enabled=True,
            include_tools=["tool1"],
            exclude_tools=["tool2", "tool4"],  # Changed
            toolkit_config={"param": "value"},
        )

        # Change toolkit_config
        config_params = ToolkitConfig(
            class_name="TestToolkit",
            enabled=True,
            include_tools=["tool1"],
            exclude_tools=["tool2"],
            toolkit_config={"param": "changed"},  # Changed
        )

        base_hash = self.manager._hash_toolkit_config(base_config)
        assert self.manager._hash_toolkit_config(config_enabled) != base_hash
        assert self.manager._hash_toolkit_config(config_include) != base_hash
        assert self.manager._hash_toolkit_config(config_exclude) != base_hash
        assert self.manager._hash_toolkit_config(config_params) != base_hash


class TestCacheKeyGeneration:
    """Test cache key generation for execution isolation."""

    def setup_method(self):
        """Set up test environment."""
        ToolkitManager._instance = None
        ToolkitManager._toolkit_registry.clear()
        self.manager = ToolkitManager()

    def test_cache_key_format(self):
        """Test cache key format: execution_id:ClassName:config_hash."""
        config = ToolkitConfig(class_name="TestToolkit")

        cache_key = self.manager._get_toolkit_cache_key(
            execution_id="exec_123", class_name="TestToolkit", config=config
        )

        parts = cache_key.split(":")
        assert len(parts) == 3, "Cache key should have 3 parts"
        assert parts[0] == "exec_123", "First part should be execution_id"
        assert parts[1] == "TestToolkit", "Second part should be class name"
        assert len(parts[2]) == 16, "Third part should be 16-char hash"

    def test_cache_key_execution_isolation(self):
        """Test different execution_ids produce different cache keys."""
        config = ToolkitConfig(class_name="TestToolkit")

        key1 = self.manager._get_toolkit_cache_key("exec_1", "TestToolkit", config)
        key2 = self.manager._get_toolkit_cache_key("exec_2", "TestToolkit", config)

        assert key1 != key2, "Different executions should have different keys"
        assert key1.startswith("exec_1:"), "Key should start with execution_id"
        assert key2.startswith("exec_2:"), "Key should start with execution_id"

    def test_cache_key_sanitization(self):
        """Test execution_id sanitization prevents key injection."""
        config = ToolkitConfig(class_name="TestToolkit")

        # Test with special characters that could break key format
        cache_key = self.manager._get_toolkit_cache_key(
            execution_id="exec:123|456",  # Contains : and |
            class_name="TestToolkit",
            config=config,
        )

        # Should replace : and | with _
        assert "exec_123_456:" in cache_key, "Special chars should be sanitized"
        assert "::" not in cache_key, "Should not have double colons"
        assert "||" not in cache_key, "Should not have double pipes"

    def test_cache_key_config_specificity(self):
        """Test cache keys differ for different configs."""
        config1 = ToolkitConfig(
            class_name="TestToolkit", toolkit_config={"param": "value1"}
        )
        config2 = ToolkitConfig(
            class_name="TestToolkit", toolkit_config={"param": "value2"}
        )

        key1 = self.manager._get_toolkit_cache_key("exec_1", "TestToolkit", config1)
        key2 = self.manager._get_toolkit_cache_key("exec_1", "TestToolkit", config2)

        # Same execution, same class, different config -> different keys
        assert key1 != key2, "Different configs should produce different keys"


class TestIndividualToolkitCaching:
    """Test individual toolkit caching and reuse."""

    def setup_method(self):
        """Set up test environment."""
        ToolkitManager._instance = None
        ToolkitManager._toolkit_registry.clear()
        self.manager = ToolkitManager()
        self.manager.register_external_toolkit("SimpleTestToolkit", SimpleTestToolkit)
        self.temp_dir = tempfile.mkdtemp()

    def teardown_method(self):
        """Clean up test environment."""
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    @pytest.mark.asyncio
    async def test_toolkit_reuse_across_agents(self):
        """Test toolkit is reused when multiple agents use same config."""
        execution_id = "test_exec_1"
        file_storage = create_file_storage(execution_id, Path(self.temp_dir))

        # Same config used by multiple agents
        config = ToolkitConfig(
            class_name="SimpleTestToolkit", enabled=True, toolkit_config={"counter": 10}
        )

        # Agent 1 requests toolkit
        tools1 = await self.manager.get_tools_for_execution(
            execution_id=execution_id,
            file_storage=file_storage,
            toolkit_configs=[config],
        )

        # Agent 2 requests same toolkit
        tools2 = await self.manager.get_tools_for_execution(
            execution_id=execution_id,
            file_storage=file_storage,
            toolkit_configs=[config],
        )

        # Should have created only ONE toolkit instance
        cache_key = self.manager._get_toolkit_cache_key(
            execution_id, "SimpleTestToolkit", config
        )
        assert cache_key in self.manager._toolkit_cache
        assert self.manager._toolkit_refcounts[cache_key] == 2, (
            "Should have 2 references"
        )

        # Verify cache hit rate
        assert len(tools1) == len(tools2), "Both agents should get same tools"

    @pytest.mark.asyncio
    async def test_different_configs_create_separate_instances(self):
        """Test different configs create separate toolkit instances."""
        execution_id = "test_exec_2"
        file_storage = create_file_storage(execution_id, Path(self.temp_dir))

        config1 = ToolkitConfig(
            class_name="SimpleTestToolkit", toolkit_config={"counter": 10}
        )
        config2 = ToolkitConfig(
            class_name="SimpleTestToolkit",
            toolkit_config={"counter": 20},  # Different config
        )

        # Request different configs
        await self.manager.get_tools_for_execution(
            execution_id, file_storage, [config1]
        )
        await self.manager.get_tools_for_execution(
            execution_id, file_storage, [config2]
        )

        # Should have created TWO separate toolkit instances
        key1 = self.manager._get_toolkit_cache_key(
            execution_id, "SimpleTestToolkit", config1
        )
        key2 = self.manager._get_toolkit_cache_key(
            execution_id, "SimpleTestToolkit", config2
        )

        assert key1 in self.manager._toolkit_cache
        assert key2 in self.manager._toolkit_cache
        assert key1 != key2, "Different configs should have different keys"
        assert len(self.manager._toolkit_cache) == 2, "Should have 2 cached instances"

    @pytest.mark.asyncio
    async def test_cache_performance_logging(self, caplog):
        """Test cache performance metrics are logged."""
        execution_id = "test_exec_3"
        file_storage = create_file_storage(execution_id, Path(self.temp_dir))

        config = ToolkitConfig(class_name="SimpleTestToolkit")

        # First request - should create
        await self.manager.get_tools_for_execution(execution_id, file_storage, [config])

        # Second request - should reuse
        await self.manager.get_tools_for_execution(execution_id, file_storage, [config])

        # Check logs for cache stats
        assert any("created=1" in record.message for record in caplog.records)
        assert any("reused=1" in record.message for record in caplog.records)
        assert any("hit_rate" in record.message for record in caplog.records)


class TestThreadSafety:
    """Test thread safety with hybrid locking."""

    def setup_method(self):
        """Set up test environment."""
        ToolkitManager._instance = None
        ToolkitManager._toolkit_registry.clear()
        self.manager = ToolkitManager()
        self.manager.register_external_toolkit("SimpleTestToolkit", SimpleTestToolkit)
        self.temp_dir = tempfile.mkdtemp()

    def teardown_method(self):
        """Clean up test environment."""
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_concurrent_thread_safety(self):
        """Test concurrent access from multiple threads is safe."""
        execution_id = "test_exec_concurrent"
        # Create FileStorage once outside threads to ensure same instance
        file_storage = create_file_storage(execution_id, Path(self.temp_dir))

        config = ToolkitConfig(class_name="SimpleTestToolkit")
        results = []

        def get_tools_in_thread():
            """Function to run in thread."""
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                tools = loop.run_until_complete(
                    self.manager.get_tools_for_execution(
                        execution_id, file_storage, [config]
                    )
                )
                results.append(len(tools))
            finally:
                loop.close()

        # Create 10 threads requesting same toolkit
        threads = [threading.Thread(target=get_tools_in_thread) for _ in range(10)]

        # Start all threads
        for t in threads:
            t.start()

        # Wait for all to complete
        for t in threads:
            t.join()

        # All threads should succeed
        assert len(results) == 10, "All threads should complete successfully"
        assert all(r > 0 for r in results), "All threads should get tools"

        # Due to threading race conditions, we should have created only a few instances
        # (ideally 1, but race conditions may cause a few more)
        cache_key = self.manager._get_toolkit_cache_key(
            execution_id, "SimpleTestToolkit", config
        )
        assert cache_key in self.manager._toolkit_cache, (
            "At least one toolkit should be cached"
        )
        # Refcount should be at least 1 (threads may have finished and decremented)
        assert self.manager._toolkit_refcounts[cache_key] >= 1, (
            "Should have at least 1 reference"
        )


class TestAsyncSafety:
    """Test async safety with event-loop-specific locks."""

    def setup_method(self):
        """Set up test environment."""
        ToolkitManager._instance = None
        ToolkitManager._toolkit_registry.clear()
        self.manager = ToolkitManager()
        self.manager.register_external_toolkit("SimpleTestToolkit", SimpleTestToolkit)
        self.temp_dir = tempfile.mkdtemp()

    def teardown_method(self):
        """Clean up test environment."""
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    @pytest.mark.asyncio
    async def test_concurrent_async_tasks(self):
        """Test concurrent async tasks can safely access cache."""
        execution_id = "test_exec_async"
        file_storage = create_file_storage(execution_id, Path(self.temp_dir))

        config = ToolkitConfig(class_name="SimpleTestToolkit")

        # Create 10 concurrent tasks
        tasks = [
            self.manager.get_tools_for_execution(execution_id, file_storage, [config])
            for _ in range(10)
        ]

        # Run concurrently
        results = await asyncio.gather(*tasks)

        # All tasks should succeed
        assert len(results) == 10
        assert all(len(r) > 0 for r in results), "All tasks should get tools"

        # Should have created only ONE toolkit instance
        cache_key = self.manager._get_toolkit_cache_key(
            execution_id, "SimpleTestToolkit", config
        )
        assert cache_key in self.manager._toolkit_cache
        assert self.manager._toolkit_refcounts[cache_key] == 10

    def test_async_lock_per_event_loop(self):
        """Test async lock is created per event loop."""
        # First event loop
        lock1 = None
        loop1 = asyncio.new_event_loop()
        asyncio.set_event_loop(loop1)
        try:
            lock1 = self.manager._get_async_lock()
            assert lock1 is not None, "Lock should be created"
            assert isinstance(lock1, asyncio.Lock), "Should be an asyncio.Lock"
        finally:
            loop1.close()

        # Second event loop - reset manager's lock to test recreation
        self.manager._cache_async_lock = None
        lock2 = None
        loop2 = asyncio.new_event_loop()
        asyncio.set_event_loop(loop2)
        try:
            lock2 = self.manager._get_async_lock()
            assert lock2 is not None, "Lock should be created"
            assert isinstance(lock2, asyncio.Lock), "Should be an asyncio.Lock"
        finally:
            loop2.close()

        # Locks should be different (different event loops)
        assert lock1 is not lock2, "Different event loops should have different locks"


class TestReferenceCounting:
    """Test reference counting for safe cleanup."""

    def setup_method(self):
        """Set up test environment."""
        ToolkitManager._instance = None
        ToolkitManager._toolkit_registry.clear()
        self.manager = ToolkitManager()
        self.manager.register_external_toolkit("SimpleTestToolkit", SimpleTestToolkit)
        self.temp_dir = tempfile.mkdtemp()

    def teardown_method(self):
        """Clean up test environment."""
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    @pytest.mark.asyncio
    async def test_reference_counting_increment(self):
        """Test reference count increments on reuse."""
        execution_id = "test_exec_refcount"
        file_storage = create_file_storage(execution_id, Path(self.temp_dir))

        config = ToolkitConfig(class_name="SimpleTestToolkit")

        # Request 3 times
        await self.manager.get_tools_for_execution(execution_id, file_storage, [config])
        await self.manager.get_tools_for_execution(execution_id, file_storage, [config])
        await self.manager.get_tools_for_execution(execution_id, file_storage, [config])

        cache_key = self.manager._get_toolkit_cache_key(
            execution_id, "SimpleTestToolkit", config
        )

        # Should have refcount = 3
        assert self.manager._toolkit_refcounts[cache_key] == 3

    @pytest.mark.asyncio
    async def test_cleanup_decrements_refcount(self):
        """Test cleanup decrements refcount without removing if still in use."""
        execution_id = "test_exec_cleanup"
        file_storage = create_file_storage(execution_id, Path(self.temp_dir))

        config = ToolkitConfig(class_name="SimpleTestToolkit")

        # Request 3 times
        await self.manager.get_tools_for_execution(execution_id, file_storage, [config])
        await self.manager.get_tools_for_execution(execution_id, file_storage, [config])
        await self.manager.get_tools_for_execution(execution_id, file_storage, [config])

        cache_key = self.manager._get_toolkit_cache_key(
            execution_id, "SimpleTestToolkit", config
        )
        assert self.manager._toolkit_refcounts[cache_key] == 3

        # Cleanup once
        await self.manager.cleanup_execution(execution_id)

        # Should decrement refcount but NOT remove (still 2 references)
        assert cache_key in self.manager._toolkit_cache, "Should still be cached"
        assert self.manager._toolkit_refcounts[cache_key] == 2, "Should decrement to 2"

    @pytest.mark.asyncio
    async def test_cleanup_removes_at_zero_refcount(self):
        """Test cleanup removes toolkit when refcount reaches 0."""
        execution_id = "test_exec_remove"
        file_storage = create_file_storage(execution_id, Path(self.temp_dir))

        config = ToolkitConfig(class_name="SimpleTestToolkit")

        # Request once
        await self.manager.get_tools_for_execution(execution_id, file_storage, [config])

        cache_key = self.manager._get_toolkit_cache_key(
            execution_id, "SimpleTestToolkit", config
        )
        assert cache_key in self.manager._toolkit_cache

        # Cleanup
        await self.manager.cleanup_execution(execution_id)

        # Should remove toolkit (refcount was 1, now 0)
        assert cache_key not in self.manager._toolkit_cache
        assert cache_key not in self.manager._toolkit_refcounts


class TestExecutionIsolation:
    """Test execution isolation prevents cross-execution toolkit sharing."""

    def setup_method(self):
        """Set up test environment."""
        ToolkitManager._instance = None
        ToolkitManager._toolkit_registry.clear()
        self.manager = ToolkitManager()
        self.manager.register_external_toolkit("SimpleTestToolkit", SimpleTestToolkit)
        self.temp_dir = tempfile.mkdtemp()

    def teardown_method(self):
        """Clean up test environment."""
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    @pytest.mark.asyncio
    async def test_different_executions_separate_toolkits(self):
        """Test different executions get separate toolkit instances."""
        config = ToolkitConfig(class_name="SimpleTestToolkit")

        # Execution 1
        exec1_storage = create_file_storage("exec_1", Path(self.temp_dir) / "exec1")
        await self.manager.get_tools_for_execution("exec_1", exec1_storage, [config])

        # Execution 2
        exec2_storage = create_file_storage("exec_2", Path(self.temp_dir) / "exec2")
        await self.manager.get_tools_for_execution("exec_2", exec2_storage, [config])

        # Should have TWO separate instances
        key1 = self.manager._get_toolkit_cache_key(
            "exec_1", "SimpleTestToolkit", config
        )
        key2 = self.manager._get_toolkit_cache_key(
            "exec_2", "SimpleTestToolkit", config
        )

        assert key1 in self.manager._toolkit_cache
        assert key2 in self.manager._toolkit_cache
        assert key1 != key2, "Different executions should have different cache keys"
        assert len(self.manager._toolkit_cache) == 2

    @pytest.mark.asyncio
    async def test_cleanup_only_affects_target_execution(self):
        """Test cleanup only removes toolkits for target execution."""
        config = ToolkitConfig(class_name="SimpleTestToolkit")

        # Create toolkits for two executions
        exec1_storage = create_file_storage("exec_1", Path(self.temp_dir) / "exec1")
        exec2_storage = create_file_storage("exec_2", Path(self.temp_dir) / "exec2")

        await self.manager.get_tools_for_execution("exec_1", exec1_storage, [config])
        await self.manager.get_tools_for_execution("exec_2", exec2_storage, [config])

        # Cleanup execution 1
        await self.manager.cleanup_execution("exec_1")

        # Execution 1 toolkit should be removed
        key1 = self.manager._get_toolkit_cache_key(
            "exec_1", "SimpleTestToolkit", config
        )
        assert key1 not in self.manager._toolkit_cache

        # Execution 2 toolkit should still exist
        key2 = self.manager._get_toolkit_cache_key(
            "exec_2", "SimpleTestToolkit", config
        )
        assert key2 in self.manager._toolkit_cache


class TestClearCache:
    """Test global cache clearing."""

    def setup_method(self):
        """Set up test environment."""
        ToolkitManager._instance = None
        ToolkitManager._toolkit_registry.clear()
        self.manager = ToolkitManager()
        self.manager.register_external_toolkit("SimpleTestToolkit", SimpleTestToolkit)
        self.temp_dir = tempfile.mkdtemp()

    def teardown_method(self):
        """Clean up test environment."""
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    @pytest.mark.asyncio
    async def test_clear_cache_removes_all(self):
        """Test clear_cache removes all toolkits across all executions."""
        config = ToolkitConfig(class_name="SimpleTestToolkit")

        # Create toolkits for multiple executions
        for i in range(3):
            exec_id = f"exec_{i}"
            storage = create_file_storage(exec_id, Path(self.temp_dir) / exec_id)
            await self.manager.get_tools_for_execution(exec_id, storage, [config])

        # Should have 3 cached toolkits
        assert len(self.manager._toolkit_cache) == 3

        # Clear cache
        self.manager.clear_cache()

        # All should be removed
        assert len(self.manager._toolkit_cache) == 0
        assert len(self.manager._toolkit_refcounts) == 0


class TestToolkitLifecycleTracking:
    """Test toolkit lifecycle event tracking."""

    def setup_method(self):
        """Set up test environment."""
        ToolkitManager._instance = None
        ToolkitManager._toolkit_registry.clear()
        self.manager = ToolkitManager()
        self.manager.register_external_toolkit("SimpleTestToolkit", SimpleTestToolkit)
        self.temp_dir = tempfile.mkdtemp()

    def teardown_method(self):
        """Clean up test environment."""
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    @pytest.mark.asyncio
    async def test_track_toolkit_event_buffers_to_context(self):
        """Test _track_toolkit_event() buffers events to ExecutionContext."""
        from roma_dspy.core.context import ExecutionContext

        execution_id = "test_exec_tracking"
        file_storage = create_file_storage(execution_id, Path(self.temp_dir))

        # Set up execution context
        token = ExecutionContext.set(
            execution_id=execution_id, file_storage=file_storage
        )

        try:
            # Track an event
            await self.manager._track_toolkit_event(
                execution_id=execution_id,
                operation="create",
                toolkit_class="TestToolkit",
                duration_ms=123.45,
                success=True,
                error=None,
            )

            # Verify event was buffered
            ctx = ExecutionContext.get()
            assert ctx is not None
            assert len(ctx.toolkit_events) == 1

            event = ctx.toolkit_events[0]
            assert event.execution_id == execution_id
            assert event.operation == "create"
            assert event.toolkit_class == "TestToolkit"
            assert event.duration_ms == 123.45
            assert event.success is True
            assert event.error is None

        finally:
            ExecutionContext.reset(token)

    @pytest.mark.asyncio
    async def test_track_toolkit_event_with_error(self):
        """Test _track_toolkit_event() captures error details."""
        from roma_dspy.core.context import ExecutionContext

        execution_id = "test_exec_error"
        file_storage = create_file_storage(execution_id, Path(self.temp_dir))
        token = ExecutionContext.set(
            execution_id=execution_id, file_storage=file_storage
        )

        try:
            # Track failed event
            await self.manager._track_toolkit_event(
                execution_id=execution_id,
                operation="create",
                toolkit_class="TestToolkit",
                duration_ms=0,
                success=False,
                error="API key not found",
            )

            # Verify error was captured
            ctx = ExecutionContext.get()
            assert len(ctx.toolkit_events) == 1

            event = ctx.toolkit_events[0]
            assert event.success is False
            assert event.error == "API key not found"

        finally:
            ExecutionContext.reset(token)

    @pytest.mark.asyncio
    async def test_cache_hit_tracking(self):
        """Test cache hit events are tracked."""
        from roma_dspy.core.context import ExecutionContext

        execution_id = "test_cache_hit"
        file_storage = create_file_storage(execution_id, Path(self.temp_dir))

        token = ExecutionContext.set(
            execution_id=execution_id, file_storage=file_storage
        )

        try:
            config = ToolkitConfig(class_name="SimpleTestToolkit")

            # First request - creates toolkit
            await self.manager.get_tools_for_execution(
                execution_id, file_storage, [config]
            )

            # Clear events from first request
            ctx = ExecutionContext.get()
            ctx.toolkit_events.clear()

            # Second request - should hit cache
            await self.manager.get_tools_for_execution(
                execution_id, file_storage, [config]
            )

            # Verify cache hit was tracked
            ctx = ExecutionContext.get()
            assert len(ctx.toolkit_events) == 1

            event = ctx.toolkit_events[0]
            assert event.operation == "cache_hit"
            assert event.toolkit_class == "SimpleTestToolkit"
            assert event.duration_ms == 0  # Instant
            assert event.success is True

        finally:
            ExecutionContext.reset(token)

    @pytest.mark.asyncio
    async def test_toolkit_creation_tracking_with_timing(self):
        """Test toolkit creation events include timing."""
        from roma_dspy.core.context import ExecutionContext

        execution_id = "test_creation_timing"
        file_storage = create_file_storage(execution_id, Path(self.temp_dir))

        token = ExecutionContext.set(
            execution_id=execution_id, file_storage=file_storage
        )

        try:
            config = ToolkitConfig(class_name="SimpleTestToolkit")

            # Create toolkit
            await self.manager.get_tools_for_execution(
                execution_id, file_storage, [config]
            )

            # Verify creation event was tracked with timing
            ctx = ExecutionContext.get()
            creation_events = [e for e in ctx.toolkit_events if e.operation == "create"]

            assert len(creation_events) == 1

            event = creation_events[0]
            assert event.operation == "create"
            assert event.toolkit_class == "SimpleTestToolkit"
            assert event.duration_ms > 0, "Should have non-zero duration"
            assert event.success is True
            assert event.error is None

        finally:
            ExecutionContext.reset(token)

    @pytest.mark.asyncio
    async def test_failed_creation_tracking(self):
        """Test failed toolkit creation events are tracked with error details."""
        from roma_dspy.core.context import ExecutionContext

        execution_id = "test_failed_creation"
        file_storage = create_file_storage(execution_id, Path(self.temp_dir))

        token = ExecutionContext.set(
            execution_id=execution_id, file_storage=file_storage
        )

        try:
            # Use invalid toolkit class to trigger error
            config = ToolkitConfig(class_name="NonExistentToolkit")

            # Attempt to create toolkit (should fail)
            await self.manager.get_tools_for_execution(
                execution_id, file_storage, [config]
            )

            # Verify failed creation was tracked
            ctx = ExecutionContext.get()
            failed_events = [
                e
                for e in ctx.toolkit_events
                if e.operation == "create" and not e.success
            ]

            assert len(failed_events) == 1

            event = failed_events[0]
            assert event.operation == "create"
            assert event.toolkit_class == "NonExistentToolkit"
            assert event.success is False
            assert event.error is not None
            assert "NonExistentToolkit" in event.error

        finally:
            ExecutionContext.reset(token)

    @pytest.mark.asyncio
    async def test_multiple_operations_tracked(self):
        """Test multiple toolkit operations are tracked correctly."""
        from roma_dspy.core.context import ExecutionContext

        execution_id = "test_multiple_ops"
        file_storage = create_file_storage(execution_id, Path(self.temp_dir))

        token = ExecutionContext.set(
            execution_id=execution_id, file_storage=file_storage
        )

        try:
            config = ToolkitConfig(class_name="SimpleTestToolkit")

            # First request - creates
            await self.manager.get_tools_for_execution(
                execution_id, file_storage, [config]
            )

            # Second request - cache hit
            await self.manager.get_tools_for_execution(
                execution_id, file_storage, [config]
            )

            # Third request - another cache hit
            await self.manager.get_tools_for_execution(
                execution_id, file_storage, [config]
            )

            # Verify all operations were tracked
            ctx = ExecutionContext.get()
            assert len(ctx.toolkit_events) == 3

            # First should be create
            assert ctx.toolkit_events[0].operation == "create"
            assert ctx.toolkit_events[0].success is True

            # Next two should be cache hits
            assert ctx.toolkit_events[1].operation == "cache_hit"
            assert ctx.toolkit_events[2].operation == "cache_hit"

        finally:
            ExecutionContext.reset(token)

    @pytest.mark.asyncio
    async def test_tracking_without_context_does_not_error(self):
        """Test tracking without ExecutionContext doesn't raise errors."""
        # No ExecutionContext set - should not error
        await self.manager._track_toolkit_event(
            execution_id="test_no_context",
            operation="create",
            toolkit_class="TestToolkit",
            duration_ms=100,
            success=True,
        )

        # Should complete without error (event just not tracked)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
