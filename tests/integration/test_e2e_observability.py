"""End-to-end observability integration test covering all tracking layers."""

import asyncio

import pytest

from roma_dspy.core.context import ExecutionContext
from roma_dspy.core.storage import FileStorage
from roma_dspy.config.schemas import StorageConfig
from roma_dspy.types import ExecutionEventType


@pytest.fixture
def mock_file_storage(tmp_path):
    """Create mock FileStorage for testing."""
    config = StorageConfig(
        base_path=str(tmp_path),
        max_file_size=100 * 1024 * 1024,  # 100MB
        buffer_size=8192,
    )
    storage = FileStorage(config=config, execution_id="test_exec_e2e_obs")
    return storage


class TestE2EObservability:
    """End-to-end tests for complete observability system."""

    @pytest.mark.asyncio
    async def test_three_layer_observability_buffering(self, mock_file_storage):
        """
        Test all three observability layers buffer events correctly:
        1. Toolkit Metrics (ToolkitTrace, ToolInvocationTrace)
        2. Execution Events (EventTrace)
        3. Ready for persistence
        """

        # Set up execution context
        token = ExecutionContext.set(
            execution_id="test_exec_e2e_obs", file_storage=mock_file_storage
        )

        try:
            ctx = ExecutionContext.get()
            assert ctx is not None

            # ==================== Layer 1: Toolkit Metrics ====================

            # Simulate toolkit lifecycle
            from roma_dspy.tools.metrics.decorators import (
                track_toolkit_lifecycle,
                track_tool_invocation,
            )

            @track_toolkit_lifecycle("create")
            async def create_toolkit():
                await asyncio.sleep(0.01)
                return "toolkit_instance"

            @track_tool_invocation("search", "TestToolkit")
            async def search_tool(query: str):
                await asyncio.sleep(0.02)
                return {"results": [f"Result for {query}"]}

            # Execute toolkit operations
            await create_toolkit()
            await search_tool("test query")

            # Verify toolkit metrics buffered
            assert len(ctx.toolkit_events) == 1, "Should have 1 toolkit lifecycle event"
            assert len(ctx.tool_invocations) == 1, "Should have 1 tool invocation"
            assert ctx.toolkit_events[0].operation == "create"
            assert ctx.tool_invocations[0].tool_name == "search"

            # ==================== Layer 2: Execution Events ====================

            # Simulate execution events
            ctx.emit_execution_event(
                event_type=ExecutionEventType.EXECUTION_START,
                task_id="task_1",
                dag_id="test_exec_e2e_obs",
                event_data={"goal": "test goal", "depth": 0},
            )

            ctx.emit_execution_event(
                event_type=ExecutionEventType.PLAN_COMPLETE,
                task_id="task_1",
                dag_id="test_exec_e2e_obs",
                event_data={"subtasks": 3},
            )

            ctx.emit_execution_event(
                event_type=ExecutionEventType.EXECUTION_COMPLETE,
                task_id="task_1",
                dag_id="test_exec_e2e_obs",
                event_data={"status": "completed", "duration_ms": 100},
            )

            # Verify execution events buffered
            assert len(ctx.execution_events) == 3, "Should have 3 execution events"
            assert (
                ctx.execution_events[0].event_type
                == ExecutionEventType.EXECUTION_START.value
            )
            assert (
                ctx.execution_events[1].event_type
                == ExecutionEventType.PLAN_COMPLETE.value
            )
            assert (
                ctx.execution_events[2].event_type
                == ExecutionEventType.EXECUTION_COMPLETE.value
            )

            # Verify event data preserved
            assert ctx.execution_events[0].event_data["goal"] == "test goal"
            assert ctx.execution_events[1].event_data["subtasks"] == 3
            assert ctx.execution_events[2].event_data["status"] == "completed"

            # ==================== Verify Complete Buffering ====================

            print("\n✅ All three observability layers buffering correctly:")
            print(f"  - Toolkit lifecycle events: {len(ctx.toolkit_events)}")
            print(f"  - Tool invocations: {len(ctx.tool_invocations)}")
            print(f"  - Execution events: {len(ctx.execution_events)}")

        finally:
            ExecutionContext.reset(token)

    @pytest.mark.asyncio
    async def test_execution_event_types(self, mock_file_storage):
        """Test that different execution event types are buffered correctly."""

        token = ExecutionContext.set(
            execution_id="test_exec_e2e_obs", file_storage=mock_file_storage
        )

        try:
            ctx = ExecutionContext.get()

            # Emit various event types
            ctx.emit_execution_event(
                event_type=ExecutionEventType.EXECUTION_START,
                task_id="task_1",
                dag_id="test_exec_e2e_obs",
                event_data={"test": "data"},
            )

            ctx.emit_execution_event(
                event_type=ExecutionEventType.ATOMIZE_COMPLETE,
                task_id="task_1",
                dag_id="test_exec_e2e_obs",
                event_data={"atomic": True},
            )

            ctx.emit_execution_event(
                event_type=ExecutionEventType.EXECUTION_FAILED,
                task_id="task_1",
                dag_id="test_exec_e2e_obs",
                event_data={"error": "test error"},
            )

            # Verify all events buffered
            assert len(ctx.execution_events) == 3

            # Verify event types
            event_types = {event.event_type for event in ctx.execution_events}
            assert ExecutionEventType.EXECUTION_START.value in event_types
            assert ExecutionEventType.ATOMIZE_COMPLETE.value in event_types
            assert ExecutionEventType.EXECUTION_FAILED.value in event_types

        finally:
            ExecutionContext.reset(token)

    @pytest.mark.asyncio
    async def test_event_enum_usage(self, mock_file_storage):
        """Test that ExecutionEventType enum works correctly."""

        token = ExecutionContext.set(
            execution_id="test_exec_e2e_obs", file_storage=mock_file_storage
        )

        try:
            ctx = ExecutionContext.get()

            # Test with enum
            ctx.emit_execution_event(
                event_type=ExecutionEventType.PLAN_COMPLETE,
                task_id="task_1",
                dag_id="test_exec_e2e_obs",
                event_data={"count": 5},
            )

            # Test with string (should also work)
            ctx.emit_execution_event(
                event_type="execute_complete",
                task_id="task_1",
                dag_id="test_exec_e2e_obs",
                event_data={"result": "done"},
            )

            # Verify both work
            assert len(ctx.execution_events) == 2
            assert ctx.execution_events[0].event_type == "plan_complete"
            assert ctx.execution_events[1].event_type == "execute_complete"

        finally:
            ExecutionContext.reset(token)
