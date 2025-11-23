"""End-to-end integration tests for toolkit metrics system."""

import asyncio
from datetime import datetime, timezone

import pytest
import pytest_asyncio

from roma_dspy.core.context import ExecutionContext
from roma_dspy.core.storage import FileStorage
from roma_dspy.core.storage.postgres_storage import PostgresStorage
from roma_dspy.config.schemas.storage import PostgresConfig
from roma_dspy.tools.metrics.decorators import (
    track_toolkit_lifecycle,
    track_tool_invocation,
)
from roma_dspy.tools.metrics.models import aggregate_toolkit_metrics


@pytest_asyncio.fixture
async def temp_postgres_storage(tmp_path):
    """Create temporary PostgreSQL storage for testing."""
    config = PostgresConfig(
        enabled=True,
        connection_url="sqlite+aiosqlite:///:memory:",  # Use SQLite for testing
        echo_sql=False,
    )

    storage = PostgresStorage(config)
    await storage.initialize()

    # Create test execution
    await storage.create_execution(
        execution_id="test_exec_e2e", initial_goal="Test toolkit metrics", max_depth=3
    )

    yield storage

    await storage.shutdown()


@pytest.fixture
def mock_file_storage(tmp_path):
    """Create mock FileStorage for testing."""
    from roma_dspy.config.schemas import StorageConfig

    config = StorageConfig(
        base_path=str(tmp_path),
        max_file_size=100 * 1024 * 1024,  # 100MB
        buffer_size=8192,
    )
    storage = FileStorage(config=config, execution_id="test_exec_e2e")
    return storage


class TestToolkitMetricsE2E:
    """End-to-end tests for complete metrics flow."""

    @pytest.mark.asyncio
    async def test_complete_metrics_flow(
        self, temp_postgres_storage, mock_file_storage
    ):
        """Test complete flow: tracking -> context -> storage -> query."""

        # Set up execution context
        token = ExecutionContext.set(
            execution_id="test_exec_e2e", file_storage=mock_file_storage
        )

        try:
            ctx = ExecutionContext.get()
            assert ctx is not None

            # Simulate toolkit lifecycle
            @track_toolkit_lifecycle("create")
            async def create_toolkit():
                await asyncio.sleep(0.01)
                return "toolkit_instance"

            # Simulate tool invocations
            @track_tool_invocation("search_web", "SerperToolkit")
            async def search_web(query: str):
                await asyncio.sleep(0.02)
                return {"results": [f"Result for {query}"]}

            @track_tool_invocation("get_price", "CoinGeckoToolkit")
            async def get_price(coin_id: str):
                await asyncio.sleep(0.015)
                return 42000.0

            # Execute operations
            await create_toolkit()
            await search_web("test query")
            await get_price("bitcoin")

            # Verify events collected in context
            assert len(ctx.toolkit_events) == 1
            assert len(ctx.tool_invocations) == 2

            # Persist events to storage
            for event in ctx.toolkit_events:
                await temp_postgres_storage.save_toolkit_trace(
                    execution_id=event.execution_id,
                    operation=event.operation,
                    toolkit_class=event.toolkit_class,
                    duration_ms=event.duration_ms,
                    success=event.success,
                    error=event.error,
                    metadata=event.metadata,
                )

            for event in ctx.tool_invocations:
                await temp_postgres_storage.save_tool_invocation_trace(
                    execution_id=event.execution_id,
                    toolkit_class=event.toolkit_class,
                    tool_name=event.tool_name,
                    duration_ms=event.duration_ms,
                    input_size_bytes=event.input_size_bytes,
                    output_size_bytes=event.output_size_bytes,
                    success=event.success,
                    error=event.error,
                    metadata=event.metadata,
                )

            # Query traces from storage
            lifecycle_traces = await temp_postgres_storage.get_toolkit_traces(
                "test_exec_e2e"
            )
            invocation_traces = await temp_postgres_storage.get_tool_invocation_traces(
                "test_exec_e2e"
            )

            assert len(lifecycle_traces) == 1
            assert len(invocation_traces) == 2

            # Verify lifecycle trace
            assert lifecycle_traces[0].operation == "create"
            assert lifecycle_traces[0].success is True

            # Verify invocation traces
            tool_names = {trace.tool_name for trace in invocation_traces}
            assert tool_names == {"search_web", "get_price"}

            # Get aggregated summary
            summary = await temp_postgres_storage.get_toolkit_metrics_summary(
                "test_exec_e2e"
            )

            assert summary["execution_id"] == "test_exec_e2e"
            assert summary["toolkit_lifecycle"]["total_created"] == 1
            assert summary["tool_invocations"]["total_calls"] == 2
            assert summary["tool_invocations"]["successful_calls"] == 2
            assert summary["tool_invocations"]["success_rate"] == 1.0

        finally:
            ExecutionContext.reset(token)

    @pytest.mark.asyncio
    async def test_failure_tracking(self, temp_postgres_storage, mock_file_storage):
        """Test that failures are properly tracked and persisted."""

        token = ExecutionContext.set(
            execution_id="test_exec_e2e", file_storage=mock_file_storage
        )

        try:
            ctx = ExecutionContext.get()

            # Simulate failing tool
            @track_tool_invocation("failing_tool", "TestToolkit")
            async def failing_tool():
                await asyncio.sleep(0.01)
                raise ValueError("Tool execution failed")

            # Execute and catch error
            with pytest.raises(ValueError):
                await failing_tool()

            # Verify failure tracked
            assert len(ctx.tool_invocations) == 1
            event = ctx.tool_invocations[0]
            assert event.success is False
            assert event.error == "Tool execution failed"
            assert event.metadata["error_type"] == "ValueError"

            # Persist to storage
            await temp_postgres_storage.save_tool_invocation_trace(
                execution_id=event.execution_id,
                toolkit_class=event.toolkit_class,
                tool_name=event.tool_name,
                duration_ms=event.duration_ms,
                input_size_bytes=event.input_size_bytes,
                output_size_bytes=event.output_size_bytes,
                success=event.success,
                error=event.error,
                metadata=event.metadata,
            )

            # Query and verify
            summary = await temp_postgres_storage.get_toolkit_metrics_summary(
                "test_exec_e2e"
            )
            assert summary["tool_invocations"]["failed_calls"] == 1
            assert summary["tool_invocations"]["success_rate"] == 0.0

        finally:
            ExecutionContext.reset(token)

    @pytest.mark.asyncio
    async def test_filtering_queries(self, temp_postgres_storage, mock_file_storage):
        """Test filtering toolkit traces and tool invocations."""

        token = ExecutionContext.set(
            execution_id="test_exec_e2e", file_storage=mock_file_storage
        )

        try:
            ctx = ExecutionContext.get()

            # Create multiple operations
            @track_toolkit_lifecycle("create")
            async def create_toolkit1():
                return "toolkit1"

            @track_toolkit_lifecycle("cache_hit")
            async def cache_hit():
                return "cached"

            @track_tool_invocation("tool_a", "Toolkit1")
            async def tool_a():
                return "a"

            @track_tool_invocation("tool_b", "Toolkit2")
            async def tool_b():
                return "b"

            # Execute
            await create_toolkit1()
            await cache_hit()
            await tool_a()
            await tool_b()

            # Persist all events
            for event in ctx.toolkit_events:
                await temp_postgres_storage.save_toolkit_trace(
                    execution_id=event.execution_id,
                    operation=event.operation,
                    toolkit_class=event.toolkit_class,
                    duration_ms=event.duration_ms,
                    success=event.success,
                    error=event.error,
                    metadata=event.metadata,
                )

            for event in ctx.tool_invocations:
                await temp_postgres_storage.save_tool_invocation_trace(
                    execution_id=event.execution_id,
                    toolkit_class=event.toolkit_class,
                    tool_name=event.tool_name,
                    duration_ms=event.duration_ms,
                    input_size_bytes=event.input_size_bytes,
                    output_size_bytes=event.output_size_bytes,
                    success=event.success,
                    error=event.error,
                    metadata=event.metadata,
                )

            # Test filtering by operation
            create_traces = await temp_postgres_storage.get_toolkit_traces(
                "test_exec_e2e", operation="create"
            )
            assert len(create_traces) == 1
            assert create_traces[0].operation == "create"

            cache_traces = await temp_postgres_storage.get_toolkit_traces(
                "test_exec_e2e", operation="cache_hit"
            )
            assert len(cache_traces) == 1
            assert cache_traces[0].operation == "cache_hit"

            # Test filtering by toolkit_class
            toolkit1_invocations = (
                await temp_postgres_storage.get_tool_invocation_traces(
                    "test_exec_e2e", toolkit_class="Toolkit1"
                )
            )
            assert len(toolkit1_invocations) == 1
            assert toolkit1_invocations[0].tool_name == "tool_a"

            # Test filtering by tool_name
            tool_b_invocations = await temp_postgres_storage.get_tool_invocation_traces(
                "test_exec_e2e", tool_name="tool_b"
            )
            assert len(tool_b_invocations) == 1
            assert tool_b_invocations[0].toolkit_class == "Toolkit2"

        finally:
            ExecutionContext.reset(token)

    @pytest.mark.asyncio
    async def test_aggregation_accuracy(self, temp_postgres_storage, mock_file_storage):
        """Test that aggregated metrics are calculated correctly."""

        token = ExecutionContext.set(
            execution_id="test_exec_e2e", file_storage=mock_file_storage
        )

        try:
            ctx = ExecutionContext.get()

            # Create multiple tool invocations with known durations
            @track_tool_invocation("fast_tool", "TestToolkit")
            async def fast_tool():
                await asyncio.sleep(0.01)  # 10ms
                return "fast"

            @track_tool_invocation("slow_tool", "TestToolkit")
            async def slow_tool():
                await asyncio.sleep(0.03)  # 30ms
                return "slow"

            await fast_tool()
            await slow_tool()

            # Persist events
            for event in ctx.tool_invocations:
                await temp_postgres_storage.save_tool_invocation_trace(
                    execution_id=event.execution_id,
                    toolkit_class=event.toolkit_class,
                    tool_name=event.tool_name,
                    duration_ms=event.duration_ms,
                    input_size_bytes=event.input_size_bytes,
                    output_size_bytes=event.output_size_bytes,
                    success=event.success,
                    error=event.error,
                    metadata=event.metadata,
                )

            # Get summary and verify calculations
            summary = await temp_postgres_storage.get_toolkit_metrics_summary(
                "test_exec_e2e"
            )

            # Average should be around 20ms (10ms + 30ms) / 2
            avg_duration = summary["tool_invocations"]["avg_duration_ms"]
            assert 15 < avg_duration < 25  # Allow some tolerance

            # Total duration should be around 40ms
            total_duration = summary["tool_invocations"]["total_duration_ms"]
            assert 35 < total_duration < 45

            # Check per-tool breakdown
            by_tool = summary["by_tool"]
            assert "TestToolkit.fast_tool" in by_tool
            assert "TestToolkit.slow_tool" in by_tool

        finally:
            ExecutionContext.reset(token)

    @pytest.mark.asyncio
    async def test_toolkit_auto_wrapping_tracking(self, mock_file_storage):
        """Test that toolkit tools are automatically wrapped with tracking via BaseToolkit._register_all_tools()."""
        from roma_dspy.tools.core.calculator import CalculatorToolkit

        token = ExecutionContext.set(
            execution_id="test_exec_autowrap", file_storage=mock_file_storage
        )

        try:
            ctx = ExecutionContext.get()

            # Create real toolkit - auto-wrapping happens in __init__ via _register_all_tools()
            calculator = CalculatorToolkit(
                enabled=True,
                include_tools=None,
                exclude_tools=None,
                file_storage=mock_file_storage,
            )

            # Get enabled tools
            enabled_tools = calculator.get_enabled_tools()

            # Verify tools are registered
            assert "add" in enabled_tools, "add tool should be registered"

            # Call a tool - should automatically track via auto-wrapping
            # Note: calculator tools are synchronous, not async
            result = enabled_tools["add"](a=5, b=3)

            # Verify result is correct (calculator returns JSON string)
            import json

            result_dict = json.loads(result)
            assert result_dict["success"] is True
            assert result_dict["result"] == 8, (
                "Calculator add should return correct result"
            )

            # ===  CRITICAL VALIDATION: Automatic tracking without manual decorators ===
            # This validates that BaseToolkit._register_all_tools() automatically wraps
            # all tools with track_tool_invocation, eliminating the need for manual decorators
            assert len(ctx.tool_invocations) == 1, (
                "Tool invocation should be tracked automatically"
            )
            event = ctx.tool_invocations[0]
            assert event.execution_id == "test_exec_autowrap"
            assert event.toolkit_class == "CalculatorToolkit"
            assert event.tool_name == "add"
            assert event.success is True
            assert event.duration_ms > 0, "Duration should be measured"
            assert event.duration_ms < 1000, "Duration should be reasonable (<1s)"

            # Verify metadata
            assert "error_type" not in event.metadata, (
                "Should not have error_type on success"
            )

            # Call another tool to verify multiple invocations
            result2 = enabled_tools["multiply"](a=4, b=5)
            result2_dict = json.loads(result2)
            assert result2_dict["result"] == 20

            # Verify second invocation tracked
            assert len(ctx.tool_invocations) == 2, (
                "Second invocation should also be tracked"
            )
            event2 = ctx.tool_invocations[1]
            assert event2.toolkit_class == "CalculatorToolkit"
            assert event2.tool_name == "multiply"
            assert event2.success is True

        finally:
            ExecutionContext.reset(token)
