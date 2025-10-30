"""Unit tests for ROMAToolSpanCallback."""

import pytest
from unittest.mock import MagicMock, patch

from roma_dspy.core.observability.tool_span_callback import ROMAToolSpanCallback


class TestROMAToolSpanCallback:
    """Tests for ROMAToolSpanCallback."""

    def test_init(self):
        """Test callback initialization."""
        callback = ROMAToolSpanCallback()
        assert callback._pending_calls == {}
        assert callback.enhanced_count == 0

    @patch('roma_dspy.core.observability.tool_span_callback.MLFLOW_AVAILABLE', True)
    @patch('roma_dspy.core.observability.tool_span_callback.mlflow')
    def test_on_tool_start_with_mlflow_span(self, mock_mlflow):
        """Test on_tool_start enhances MLflow span with ROMA attributes."""
        # Setup
        callback = ROMAToolSpanCallback()

        # Mock tool instance
        mock_tool = MagicMock()
        mock_tool.name = "test_tool"
        mock_tool.func = MagicMock()
        mock_tool.func.__module__ = "test_module"

        # Mock MLflow span
        mock_span = MagicMock()
        mock_mlflow.get_current_active_span.return_value = mock_span

        # Mock ExecutionContext
        with patch('roma_dspy.core.observability.tool_span_callback.ExecutionContext') as mock_ctx_class:
            mock_ctx = MagicMock()
            mock_ctx.execution_id = "test_exec_001"
            mock_ctx_class.get.return_value = mock_ctx

            # Execute
            callback.on_tool_start(
                call_id="call_123",
                instance=mock_tool,
                inputs={"arg1": "value1"}
            )

        # Verify span was enhanced
        mock_span.set_attributes.assert_called_once()
        attrs = mock_span.set_attributes.call_args[0][0]

        assert attrs["roma.execution_id"] == "test_exec_001"
        assert attrs["roma.tool_name"] == "test_tool"
        assert attrs["roma.enhanced"] == "true"
        assert "roma.tool_type" in attrs
        assert "roma.toolkit_name" in attrs

        # Verify call was tracked
        assert "call_123" in callback._pending_calls
        assert callback.enhanced_count == 1

    @patch('roma_dspy.core.observability.tool_span_callback.MLFLOW_AVAILABLE', True)
    @patch('roma_dspy.core.observability.tool_span_callback.mlflow')
    def test_on_tool_start_no_active_span(self, mock_mlflow):
        """Test on_tool_start handles missing span gracefully."""
        callback = ROMAToolSpanCallback()

        mock_tool = MagicMock()
        mock_tool.name = "test_tool"
        mock_mlflow.get_current_active_span.return_value = None

        # Should not raise
        callback.on_tool_start(
            call_id="call_123",
            instance=mock_tool,
            inputs={}
        )

        assert callback.enhanced_count == 0

    @patch('roma_dspy.core.observability.tool_span_callback.MLFLOW_AVAILABLE', False)
    def test_on_tool_start_mlflow_not_available(self):
        """Test on_tool_start when MLflow is not available."""
        callback = ROMAToolSpanCallback()

        mock_tool = MagicMock()
        mock_tool.name = "test_tool"

        # Should not raise
        callback.on_tool_start(
            call_id="call_123",
            instance=mock_tool,
            inputs={}
        )

        assert callback.enhanced_count == 0

    def test_on_tool_end_records_in_context(self):
        """Test on_tool_end records tool call in ExecutionContext."""
        import time
        callback = ROMAToolSpanCallback()

        # Setup pending call with timestamp (required for duration calculation)
        callback._pending_calls["call_123"] = {
            "tool_name": "test_tool",
            "toolkit_name": "TestToolkit",
            "tool_type": "builtin",
            "inputs": {"arg1": "value1"},
            "timestamp": time.time()
        }

        # Mock ExecutionContext
        with patch('roma_dspy.core.observability.tool_span_callback.ExecutionContext') as mock_ctx_class:
            mock_ctx = MagicMock()
            mock_ctx.execution_id = "test_exec_001"
            mock_ctx.tool_invocations = []
            mock_ctx_class.get.return_value = mock_ctx

            # Execute
            callback.on_tool_end(
                call_id="call_123",
                outputs="test result",
                exception=None
            )

        # Verify ToolInvocationEvent was appended
        assert len(mock_ctx.tool_invocations) == 1
        event = mock_ctx.tool_invocations[0]
        assert event.execution_id == "test_exec_001"
        assert event.toolkit_class == "TestToolkit"
        assert event.tool_name == "test_tool"
        assert event.success is True
        assert event.error is None
        assert event.metadata['tool_type'] == "builtin"

        # Verify call was removed from pending
        assert "call_123" not in callback._pending_calls

    def test_on_tool_end_with_exception(self):
        """Test on_tool_end records exception."""
        import time
        callback = ROMAToolSpanCallback()

        callback._pending_calls["call_123"] = {
            "tool_name": "test_tool",
            "toolkit_name": "TestToolkit",
            "tool_type": "builtin",
            "inputs": {},
            "timestamp": time.time()
        }

        with patch('roma_dspy.core.observability.tool_span_callback.ExecutionContext') as mock_ctx_class:
            mock_ctx = MagicMock()
            mock_ctx.execution_id = "test_exec_001"
            mock_ctx.tool_invocations = []
            mock_ctx_class.get.return_value = mock_ctx

            test_exception = ValueError("Test error")

            callback.on_tool_end(
                call_id="call_123",
                outputs=None,
                exception=test_exception
            )

        # Verify ToolInvocationEvent was appended with error
        assert len(mock_ctx.tool_invocations) == 1
        event = mock_ctx.tool_invocations[0]
        assert event.success is False
        assert event.error == "Test error"

    def test_identify_toolkit_mcp_metadata(self):
        """Test _identify_toolkit recognizes MCP tools with metadata."""
        callback = ROMAToolSpanCallback()

        # Mock tool with MCP metadata
        mock_tool = MagicMock()
        mock_func = MagicMock()
        mock_func._mcp_server_name = "exa"
        mock_tool.func = mock_func

        toolkit_name, tool_type = callback._identify_toolkit(mock_tool)

        assert toolkit_name == "mcp_exa"
        assert tool_type == "mcp"

    def test_identify_toolkit_roma_metadata(self):
        """Test _identify_toolkit uses explicit ROMA metadata."""
        callback = ROMAToolSpanCallback()

        mock_tool = MagicMock()
        mock_func = MagicMock(spec=['_roma_toolkit_type', '_roma_toolkit_name', '__module__'])
        mock_func._roma_toolkit_type = "builtin"
        mock_func._roma_toolkit_name = "BinanceToolkit"
        mock_tool.func = mock_func

        toolkit_name, tool_type = callback._identify_toolkit(mock_tool)

        assert toolkit_name == "BinanceToolkit"
        assert tool_type == "builtin"

    def test_identify_toolkit_module_inference(self):
        """Test _identify_toolkit infers from module path."""
        callback = ROMAToolSpanCallback()

        mock_tool = MagicMock()
        mock_func = MagicMock(spec=['__module__'])
        mock_func.__module__ = "roma_dspy.tools.crypto.binance.toolkit"
        mock_tool.func = mock_func

        toolkit_name, tool_type = callback._identify_toolkit(mock_tool)

        assert "Toolkit" in toolkit_name
        assert tool_type == "builtin"

    def test_identify_toolkit_fallback(self):
        """Test _identify_toolkit fallback behavior."""
        callback = ROMAToolSpanCallback()

        mock_tool = MagicMock()
        mock_tool.func = None

        toolkit_name, tool_type = callback._identify_toolkit(mock_tool)

        assert toolkit_name == "UnknownToolkit"
        assert tool_type == "builtin"

    def test_cleanup_stale_calls_by_age(self):
        """Test that stale calls are cleaned up after TTL."""
        import time
        callback = ROMAToolSpanCallback()

        # Add old call (5 minutes ago)
        callback._pending_calls["old_call"] = {
            "tool_name": "old_tool",
            "timestamp": time.time() - 400  # 400 seconds ago (> 300 TTL)
        }

        # Add recent call
        callback._pending_calls["recent_call"] = {
            "tool_name": "recent_tool",
            "timestamp": time.time() - 10  # 10 seconds ago
        }

        # Run cleanup
        callback._cleanup_stale_calls()

        # Old call should be removed
        assert "old_call" not in callback._pending_calls
        # Recent call should remain
        assert "recent_call" in callback._pending_calls
        # Cleanup count should be incremented
        assert callback.cleanup_count == 1

    def test_cleanup_max_size_limit(self):
        """Test that excess calls are removed when limit exceeded."""
        import time
        callback = ROMAToolSpanCallback()

        # Add calls exceeding MAX_PENDING_CALLS
        for i in range(callback.MAX_PENDING_CALLS + 10):
            callback._pending_calls[f"call_{i}"] = {
                "tool_name": f"tool_{i}",
                "timestamp": time.time() - (100 - i)  # Oldest first
            }

        # Run cleanup
        callback._cleanup_stale_calls()

        # Should have exactly MAX_PENDING_CALLS remaining
        assert len(callback._pending_calls) <= callback.MAX_PENDING_CALLS
        # Cleanup count should reflect removed calls
        assert callback.cleanup_count >= 10

    def test_internal_tools_filtered(self):
        """Test that DSPy internal tools are not tracked."""
        callback = ROMAToolSpanCallback()

        mock_tool = MagicMock()
        mock_tool.name = "finish"  # Internal DSPy tool

        # Should return early without enhancing
        callback.on_tool_start(
            call_id="test_call",
            instance=mock_tool,
            inputs={}
        )

        # Should not be in pending calls
        assert "test_call" not in callback._pending_calls
        # Should not increment enhanced count
        assert callback.enhanced_count == 0

    def test_duplicate_call_id_logged(self):
        """Test that duplicate call_ids are logged but handled."""
        import time
        callback = ROMAToolSpanCallback()

        # Add initial call
        callback._pending_calls["dup_call"] = {
            "tool_name": "first_tool",
            "timestamp": time.time()
        }

        mock_tool = MagicMock()
        mock_tool.name = "second_tool"

        # Mock MLflow span
        with patch('roma_dspy.core.observability.tool_span_callback.mlflow') as mock_mlflow:
            mock_span = MagicMock()
            mock_mlflow.get_current_active_span.return_value = mock_span
            mock_mlflow_available = patch('roma_dspy.core.observability.tool_span_callback.MLFLOW_AVAILABLE', True)

            with mock_mlflow_available:
                with patch('roma_dspy.core.observability.tool_span_callback.ExecutionContext') as mock_ctx_class:
                    mock_ctx = MagicMock()
                    mock_ctx.execution_id = "test_exec"
                    mock_ctx_class.get.return_value = mock_ctx

                    # Should log error but continue
                    callback.on_tool_start(
                        call_id="dup_call",
                        instance=mock_tool,
                        inputs={}
                    )

        # Should overwrite with new tool name
        assert callback._pending_calls["dup_call"]["tool_name"] == "second_tool"

    def test_safe_size_calculation_json(self):
        """Test size calculation with JSON-serializable objects."""
        callback = ROMAToolSpanCallback()

        # Normal dict
        obj = {"key": "value", "nested": {"data": [1, 2, 3]}}
        size = callback._calculate_size(obj)
        assert size > 0
        assert size < 1000  # Reasonable size

    def test_safe_size_calculation_non_serializable(self):
        """Test size calculation with non-serializable objects."""
        callback = ROMAToolSpanCallback()

        # Thread object (non-serializable)
        import threading
        obj = threading.Thread()
        size = callback._calculate_size(obj)
        # Should fall back to repr and return non-zero
        assert size >= 0  # At least doesn't crash

    def test_safe_size_calculation_huge_object(self):
        """Test size calculation is capped for huge objects."""
        callback = ROMAToolSpanCallback()

        # Create huge object
        obj = {"data": "x" * 20_000_000}  # 20MB of data
        size = callback._calculate_size(obj)
        # Should be capped at 10MB limit
        assert size <= 10_000_000

    def test_duration_calculated_from_timestamp(self):
        """Test that duration is calculated from tracked timestamp."""
        import time
        callback = ROMAToolSpanCallback()

        start_time = time.time()
        callback._pending_calls["call_123"] = {
            "tool_name": "test_tool",
            "toolkit_name": "TestToolkit",
            "tool_type": "builtin",
            "inputs": {},
            "timestamp": start_time
        }

        # Simulate some delay
        time.sleep(0.01)  # 10ms delay

        with patch('roma_dspy.core.observability.tool_span_callback.ExecutionContext') as mock_ctx_class:
            mock_ctx = MagicMock()
            mock_ctx.execution_id = "test_exec_001"
            mock_ctx.tool_invocations = []
            mock_ctx_class.get.return_value = mock_ctx

            callback.on_tool_end(
                call_id="call_123",
                outputs="result",
                exception=None
            )

        # Verify duration was calculated and is non-zero
        assert len(mock_ctx.tool_invocations) == 1
        event = mock_ctx.tool_invocations[0]
        assert event.duration_ms > 0  # Should be at least 10ms
        assert event.duration_ms < 1000  # Sanity check (less than 1 second)

    def test_missing_call_id_logged(self):
        """Test that missing call_id in on_tool_end is logged."""
        callback = ROMAToolSpanCallback()

        # Call on_tool_end without corresponding on_tool_start
        # Should log debug message and return gracefully
        callback.on_tool_end(
            call_id="nonexistent_call",
            outputs="result",
            exception=None
        )

        # Should not crash, just return
        assert len(callback._pending_calls) == 0
