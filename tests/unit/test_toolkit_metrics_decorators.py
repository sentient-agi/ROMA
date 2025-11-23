"""Unit tests for toolkit metrics decorators."""

import asyncio
import time
from datetime import datetime, timezone
from unittest.mock import Mock, patch

import pytest

from roma_dspy.tools.metrics.decorators import (
    track_toolkit_lifecycle,
    track_tool_invocation,
    measure_toolkit_operation,
)
from roma_dspy.tools.metrics.models import ToolkitLifecycleEvent, ToolInvocationEvent
from roma_dspy.core.context import ExecutionContext


@pytest.fixture
def mock_execution_context():
    """Create a mock ExecutionContext with event collection."""
    ctx = Mock()
    ctx.execution_id = "test_exec_123"
    ctx.toolkit_events = []
    ctx.tool_invocations = []
    return ctx


@pytest.fixture
def mock_file_storage():
    """Create a mock FileStorage instance."""
    storage = Mock()
    storage.execution_id = "test_exec_123"
    return storage


class TestTrackToolkitLifecycle:
    """Tests for @track_toolkit_lifecycle decorator."""

    def test_sync_function_success(self, mock_execution_context, mock_file_storage):
        """Test lifecycle tracking on successful sync function."""

        @track_toolkit_lifecycle("create")
        def create_toolkit():
            time.sleep(0.01)  # Simulate work
            return "created"

        with patch.object(ExecutionContext, "get", return_value=mock_execution_context):
            result = create_toolkit()

        assert result == "created"
        assert len(mock_execution_context.toolkit_events) == 1

        event = mock_execution_context.toolkit_events[0]
        assert isinstance(event, ToolkitLifecycleEvent)
        assert event.execution_id == "test_exec_123"
        assert event.operation == "create"
        assert event.success is True
        assert event.error is None
        assert event.duration_ms > 0

    def test_sync_function_failure(self, mock_execution_context):
        """Test lifecycle tracking on failed sync function."""

        @track_toolkit_lifecycle("cleanup")
        def cleanup_toolkit():
            raise ValueError("Cleanup failed")

        with patch.object(ExecutionContext, "get", return_value=mock_execution_context):
            with pytest.raises(ValueError, match="Cleanup failed"):
                cleanup_toolkit()

        assert len(mock_execution_context.toolkit_events) == 1

        event = mock_execution_context.toolkit_events[0]
        assert event.success is False
        assert event.error == "Cleanup failed"
        assert event.metadata["error_type"] == "ValueError"

    @pytest.mark.asyncio
    async def test_async_function_success(self, mock_execution_context):
        """Test lifecycle tracking on successful async function."""

        @track_toolkit_lifecycle("cache_hit")
        async def get_from_cache():
            await asyncio.sleep(0.01)
            return "cached_data"

        with patch.object(ExecutionContext, "get", return_value=mock_execution_context):
            result = await get_from_cache()

        assert result == "cached_data"
        assert len(mock_execution_context.toolkit_events) == 1

        event = mock_execution_context.toolkit_events[0]
        assert event.operation == "cache_hit"
        assert event.success is True
        assert event.duration_ms > 0

    @pytest.mark.asyncio
    async def test_async_function_failure(self, mock_execution_context):
        """Test lifecycle tracking on failed async function."""

        @track_toolkit_lifecycle("cache_miss")
        async def cache_lookup():
            await asyncio.sleep(0.01)
            raise KeyError("Not found in cache")

        with patch.object(ExecutionContext, "get", return_value=mock_execution_context):
            with pytest.raises(KeyError, match="Not found in cache"):
                await cache_lookup()

        assert len(mock_execution_context.toolkit_events) == 1

        event = mock_execution_context.toolkit_events[0]
        assert event.success is False
        assert event.error == "Not found in cache"
        assert event.metadata["error_type"] == "KeyError"

    def test_no_execution_context(self):
        """Test behavior when ExecutionContext is not set."""

        @track_toolkit_lifecycle("create")
        def create_toolkit():
            return "created"

        with patch.object(ExecutionContext, "get", return_value=None):
            # Should not raise, just log without context
            result = create_toolkit()
            assert result == "created"

    def test_timing_accuracy(self, mock_execution_context):
        """Test that duration measurement is reasonably accurate."""
        sleep_duration = 0.05  # 50ms

        @track_toolkit_lifecycle("test")
        def timed_function():
            time.sleep(sleep_duration)
            return "done"

        with patch.object(ExecutionContext, "get", return_value=mock_execution_context):
            timed_function()

        event = mock_execution_context.toolkit_events[0]
        # Allow 20ms tolerance for timing variations
        assert (
            sleep_duration * 1000 - 20 < event.duration_ms < sleep_duration * 1000 + 20
        )


class TestTrackToolInvocation:
    """Tests for @track_tool_invocation decorator."""

    def test_sync_tool_success(self, mock_execution_context):
        """Test tool invocation tracking on successful sync tool."""

        @track_tool_invocation("search_web", "SerperToolkit")
        def search_web(query: str) -> dict:
            time.sleep(0.01)
            return {"results": [f"Result for {query}"]}

        with patch.object(ExecutionContext, "get", return_value=mock_execution_context):
            result = search_web("test query")

        assert result == {"results": ["Result for test query"]}
        assert len(mock_execution_context.tool_invocations) == 1

        event = mock_execution_context.tool_invocations[0]
        assert isinstance(event, ToolInvocationEvent)
        assert event.execution_id == "test_exec_123"
        assert event.toolkit_class == "SerperToolkit"
        assert event.tool_name == "search_web"
        assert event.success is True
        assert event.error is None
        assert event.duration_ms > 0
        assert event.input_size_bytes > 0  # Args encoded
        assert event.output_size_bytes > 0  # Result encoded

    def test_sync_tool_failure(self, mock_execution_context):
        """Test tool invocation tracking on failed sync tool."""

        @track_tool_invocation("get_price", "CoinGeckoToolkit")
        def get_price(coin_id: str) -> float:
            raise ConnectionError("API unavailable")

        with patch.object(ExecutionContext, "get", return_value=mock_execution_context):
            with pytest.raises(ConnectionError, match="API unavailable"):
                get_price("bitcoin")

        assert len(mock_execution_context.tool_invocations) == 1

        event = mock_execution_context.tool_invocations[0]
        assert event.success is False
        assert event.error == "API unavailable"
        assert event.metadata["error_type"] == "ConnectionError"
        assert event.output_size_bytes == 0  # No output on failure

    @pytest.mark.asyncio
    async def test_async_tool_success(self, mock_execution_context):
        """Test tool invocation tracking on successful async tool."""

        @track_tool_invocation("fetch_data", "HTTPToolkit")
        async def fetch_data(url: str) -> dict:
            await asyncio.sleep(0.01)
            return {"data": f"Content from {url}"}

        with patch.object(ExecutionContext, "get", return_value=mock_execution_context):
            result = await fetch_data("https://example.com")

        assert result == {"data": "Content from https://example.com"}
        assert len(mock_execution_context.tool_invocations) == 1

        event = mock_execution_context.tool_invocations[0]
        assert event.toolkit_class == "HTTPToolkit"
        assert event.tool_name == "fetch_data"
        assert event.success is True

    @pytest.mark.asyncio
    async def test_async_tool_failure(self, mock_execution_context):
        """Test tool invocation tracking on failed async tool."""

        @track_tool_invocation("execute_code", "E2BToolkit")
        async def execute_code(code: str) -> str:
            await asyncio.sleep(0.01)
            raise RuntimeError("Execution timeout")

        with patch.object(ExecutionContext, "get", return_value=mock_execution_context):
            with pytest.raises(RuntimeError, match="Execution timeout"):
                await execute_code("print('hello')")

        assert len(mock_execution_context.tool_invocations) == 1

        event = mock_execution_context.tool_invocations[0]
        assert event.success is False
        assert event.metadata["error_type"] == "RuntimeError"

    def test_input_output_size_calculation(self, mock_execution_context):
        """Test input/output size calculation."""

        @track_tool_invocation("process_data", "TestToolkit")
        def process_data(data: list) -> dict:
            return {"processed": len(data), "items": data}

        large_input = list(range(1000))

        with patch.object(ExecutionContext, "get", return_value=mock_execution_context):
            result = process_data(large_input)

        event = mock_execution_context.tool_invocations[0]
        # Input should be larger due to encoding list with 1000 items
        assert event.input_size_bytes > 100
        # Output should include the dict with processed items
        assert event.output_size_bytes > 100

    def test_no_execution_context(self):
        """Test behavior when ExecutionContext is not set."""

        @track_tool_invocation("test_tool", "TestToolkit")
        def test_tool():
            return "result"

        with patch.object(ExecutionContext, "get", return_value=None):
            # Should not raise, just execute without tracking
            result = test_tool()
            assert result == "result"


class TestMeasureToolkitOperation:
    """Tests for @measure_toolkit_operation alias."""

    def test_alias_works_same_as_lifecycle(self, mock_execution_context):
        """Test that alias decorator works identically to track_toolkit_lifecycle."""

        @measure_toolkit_operation("create")
        def create_toolkit():
            return "created"

        with patch.object(ExecutionContext, "get", return_value=mock_execution_context):
            result = create_toolkit()

        assert result == "created"
        assert len(mock_execution_context.toolkit_events) == 1

        event = mock_execution_context.toolkit_events[0]
        assert event.operation == "create"
        assert event.success is True


class TestDecoratorIntegration:
    """Integration tests for decorator combinations."""

    def test_multiple_decorators_same_execution(self, mock_execution_context):
        """Test multiple decorated functions in same execution."""

        @track_toolkit_lifecycle("create")
        def create():
            return "toolkit"

        @track_tool_invocation("tool1", "TestToolkit")
        def tool1():
            return "result1"

        @track_tool_invocation("tool2", "TestToolkit")
        def tool2():
            return "result2"

        with patch.object(ExecutionContext, "get", return_value=mock_execution_context):
            create()
            tool1()
            tool2()

        # Should have 1 lifecycle event and 2 invocation events
        assert len(mock_execution_context.toolkit_events) == 1
        assert len(mock_execution_context.tool_invocations) == 2

        assert mock_execution_context.toolkit_events[0].operation == "create"
        assert mock_execution_context.tool_invocations[0].tool_name == "tool1"
        assert mock_execution_context.tool_invocations[1].tool_name == "tool2"

    @pytest.mark.asyncio
    async def test_mixed_sync_async(self, mock_execution_context):
        """Test mix of sync and async decorated functions."""

        @track_toolkit_lifecycle("create")
        def sync_create():
            return "sync"

        @track_tool_invocation("async_tool", "TestToolkit")
        async def async_tool():
            await asyncio.sleep(0.01)
            return "async"

        with patch.object(ExecutionContext, "get", return_value=mock_execution_context):
            sync_create()
            await async_tool()

        assert len(mock_execution_context.toolkit_events) == 1
        assert len(mock_execution_context.tool_invocations) == 1
