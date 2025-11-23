"""Unit tests for error propagation through the task hierarchy."""

import pytest
from unittest.mock import Mock, patch

from roma_dspy.core.engine.runtime import ModuleRuntime
from roma_dspy.core.registry import AgentRegistry
from roma_dspy.resilience import module_circuit_breaker
from roma_dspy.core.engine.dag import TaskDAG
from roma_dspy.core.modules import Atomizer, Planner, Executor, Aggregator
from roma_dspy.core.signatures import TaskNode
from roma_dspy.types import TaskType, TaskStatus, AgentType


class TestErrorPropagation:
    """Test error propagation and context enhancement."""

    @pytest.fixture(autouse=True)
    def reset_circuit_breaker(self):
        """Reset circuit breaker state before each test."""
        module_circuit_breaker.reset_all()
        yield
        module_circuit_breaker.reset_all()

    @pytest.fixture
    def mock_modules(self):
        """Create mock modules for testing."""
        return {
            "atomizer": Mock(spec=Atomizer),
            "planner": Mock(spec=Planner),
            "executor": Mock(spec=Executor),
            "aggregator": Mock(spec=Aggregator),
        }

    @pytest.fixture
    def runtime(self, mock_modules):
        """Create ModuleRuntime with mocked registry."""
        # Create a mock registry that returns our mock modules
        mock_registry = Mock(spec=AgentRegistry)
        mock_registry.get_agent.side_effect = (
            lambda agent_type, task_type=None: mock_modules[
                {
                    AgentType.ATOMIZER: "atomizer",
                    AgentType.PLANNER: "planner",
                    AgentType.EXECUTOR: "executor",
                    AgentType.AGGREGATOR: "aggregator",
                }[agent_type]
            ]
        )

        return ModuleRuntime(registry=mock_registry)

    @pytest.fixture
    def sample_task(self):
        """Create sample task for testing."""
        return TaskNode(
            task_id="error_test_task",
            goal="Task that will fail for testing",
            task_type=TaskType.THINK,
            status=TaskStatus.PENDING,
            execution_id="test_execution",
        )

    @pytest.fixture
    def test_dag(self, sample_task):
        """Create test DAG with sample task."""
        dag = TaskDAG("error_test_dag")
        dag.add_node(sample_task)
        return dag

    # ==================== Error Context Enhancement Tests ====================

    def test_enhance_error_context_atomizer(self, runtime, sample_task):
        """Test error context enhancement for atomizer failures."""
        original_error = ValueError("Atomizer failed")

        runtime._enhance_error_context(original_error, AgentType.ATOMIZER, sample_task)

        enhanced_message = str(original_error)
        assert "[ATOMIZER]" in enhanced_message
        assert sample_task.task_id in enhanced_message
        assert "Atomizer failed" in enhanced_message

    def test_enhance_error_context_planner(self, runtime, sample_task):
        """Test error context enhancement for planner failures."""
        original_error = RuntimeError("Planning failed due to LLM timeout")

        runtime._enhance_error_context(original_error, AgentType.PLANNER, sample_task)

        enhanced_message = str(original_error)
        assert "[PLANNER]" in enhanced_message
        assert sample_task.task_id in enhanced_message
        assert "Planning failed due to LLM timeout" in enhanced_message

    def test_enhance_error_context_executor(self, runtime, sample_task):
        """Test error context enhancement for executor failures."""
        original_error = ConnectionError("Network timeout during execution")

        runtime._enhance_error_context(original_error, AgentType.EXECUTOR, sample_task)

        enhanced_message = str(original_error)
        assert "[EXECUTOR]" in enhanced_message
        assert sample_task.task_id in enhanced_message

    def test_enhance_error_context_aggregator(self, runtime, sample_task):
        """Test error context enhancement for aggregator failures."""
        original_error = KeyError("Missing required result field")

        runtime._enhance_error_context(
            original_error, AgentType.AGGREGATOR, sample_task
        )

        enhanced_message = str(original_error)
        assert "[AGGREGATOR]" in enhanced_message
        assert sample_task.task_id in enhanced_message

    def test_enhance_error_context_preserves_original(self, runtime, sample_task):
        """Test that error enhancement preserves original error details."""
        original_error = ValueError("Original error message")
        original_args = original_error.args

        runtime._enhance_error_context(original_error, AgentType.EXECUTOR, sample_task)

        # Original error type should be preserved
        assert isinstance(original_error, ValueError)
        # Should have enhanced args
        assert len(original_error.args) >= len(original_args)

    # ==================== Module Error Handling Tests ====================

    @pytest.mark.asyncio
    async def test_atomize_async_error_handling(
        self, runtime, mock_modules, sample_task, test_dag
    ):
        """Test async atomizer error handling."""
        # Setup mock to raise exception
        mock_modules["atomizer"].aforward.side_effect = ConnectionError("Network error")

        with pytest.raises(ConnectionError) as exc_info:
            await runtime.atomize_async(sample_task, test_dag)

        # Verify error was enhanced
        error_msg = str(exc_info.value)
        assert "[ATOMIZER]" in error_msg
        assert sample_task.task_id in error_msg

    @pytest.mark.asyncio
    async def test_plan_async_error_handling(
        self, runtime, mock_modules, sample_task, test_dag
    ):
        """Test async planner error handling."""
        # Setup mock to raise exception
        mock_modules["planner"].aforward.side_effect = ValueError("Invalid input")

        with pytest.raises(ValueError) as exc_info:
            await runtime.plan_async(sample_task, test_dag)

        # Verify error was enhanced
        error_msg = str(exc_info.value)
        assert "[PLANNER]" in error_msg
        assert sample_task.task_id in error_msg

    @pytest.mark.asyncio
    async def test_execute_async_error_handling(
        self, runtime, mock_modules, sample_task, test_dag
    ):
        """Test async executor error handling."""
        # Setup mock to raise exception
        mock_modules["executor"].aforward.side_effect = OSError("File not found")

        with pytest.raises(OSError) as exc_info:
            await runtime.execute_async(sample_task, test_dag)

        # Verify error was enhanced
        error_msg = str(exc_info.value)
        assert "[EXECUTOR]" in error_msg
        assert sample_task.task_id in error_msg

    @pytest.mark.asyncio
    async def test_aggregate_async_error_handling(
        self, runtime, mock_modules, sample_task, test_dag
    ):
        """Test async aggregator error handling."""
        # Set task to PLAN_DONE status so aggregation runs - use restore_state to bypass transition validation
        sample_task = sample_task.restore_state(status=TaskStatus.PLAN_DONE)

        # Setup mock to raise exception - need to mock both __call__ and aforward
        error = AttributeError("Missing attribute")
        mock_modules["aggregator"].side_effect = error  # For __call__
        mock_modules["aggregator"].aforward.side_effect = error  # For aforward

        with pytest.raises(AttributeError) as exc_info:
            await runtime.aggregate_async(sample_task, None, test_dag)

        # Verify error was enhanced
        error_msg = str(exc_info.value)
        assert "[AGGREGATOR]" in error_msg
        assert sample_task.task_id in error_msg

    # ==================== Error Types and Categories ====================

    def test_network_error_handling(self, runtime, sample_task):
        """Test handling of network-related errors."""
        network_errors = [
            ConnectionError("Connection failed"),
            TimeoutError("Request timeout"),
            OSError("Network unreachable"),
        ]

        for error in network_errors:
            runtime._enhance_error_context(error, AgentType.EXECUTOR, sample_task)
            enhanced_msg = str(error)
            assert "[EXECUTOR]" in enhanced_msg
            assert sample_task.task_id in enhanced_msg

    def test_validation_error_handling(self, runtime, sample_task):
        """Test handling of validation errors."""
        validation_errors = [
            ValueError("Invalid value"),
            TypeError("Wrong type"),
            KeyError("Missing key"),
        ]

        for error in validation_errors:
            runtime._enhance_error_context(error, AgentType.PLANNER, sample_task)
            enhanced_msg = str(error)
            assert "[PLANNER]" in enhanced_msg
            assert sample_task.task_id in enhanced_msg

    def test_resource_error_handling(self, runtime, sample_task):
        """Test handling of resource-related errors."""
        resource_errors = [
            MemoryError("Out of memory"),
            PermissionError("Permission denied"),
            OSError("Disk full"),
        ]

        for error in resource_errors:
            runtime._enhance_error_context(error, AgentType.AGGREGATOR, sample_task)
            enhanced_msg = str(error)
            assert "[AGGREGATOR]" in enhanced_msg
            assert sample_task.task_id in enhanced_msg

    # ==================== Module Decorator Integration Tests ====================

    @patch("roma_dspy.core.engine.runtime.measure_execution_time")
    @patch("roma_dspy.core.engine.runtime.with_module_resilience")
    def test_resilience_decorators_applied(self, mock_resilience, mock_timing, runtime):
        """Test that resilience decorators are properly applied to module methods."""
        # Verify decorators are applied to the async execution method
        assert hasattr(runtime, "_async_execute_module")

        # Verify error context enhancement is available
        assert hasattr(runtime, "_enhance_error_context")

    # ==================== Edge Case Error Tests ====================

    def test_error_with_empty_args(self, runtime, sample_task):
        """Test error enhancement with empty args tuple."""
        error = Exception()  # No args
        runtime._enhance_error_context(error, AgentType.EXECUTOR, sample_task)

        enhanced_msg = str(error)
        assert "[EXECUTOR]" in enhanced_msg
        assert sample_task.task_id in enhanced_msg

    def test_error_with_multiple_args(self, runtime, sample_task):
        """Test error enhancement preserves multiple args."""
        error = ValueError("First arg", "Second arg", "Third arg")
        original_args_count = len(error.args)

        runtime._enhance_error_context(error, AgentType.PLANNER, sample_task)

        # Should have at least the original number of args
        assert len(error.args) >= original_args_count
        # First arg should be enhanced
        assert "[PLANNER]" in error.args[0]

    def test_error_enhancement_with_none_values(self, runtime):
        """Test error enhancement handles None task gracefully."""
        error = RuntimeError("Test error")

        # This should not crash even with None task
        try:
            runtime._enhance_error_context(error, AgentType.EXECUTOR, None)
        except Exception as e:
            pytest.fail(f"Error enhancement should handle None task gracefully: {e}")

    # ==================== Task Context Information Tests ====================

    def test_error_includes_task_details(self, runtime, sample_task):
        """Test that enhanced errors include relevant task details."""
        # Create task with more details
        detailed_task = TaskNode(
            task_id="detailed_task_123",
            goal="Complex task with detailed information for testing error context",
            task_type=TaskType.CODE_INTERPRET,
            status=TaskStatus.EXECUTING,
            depth=3,
            execution_id="test_execution",
        )

        error = RuntimeError("Detailed task failed")
        runtime._enhance_error_context(error, AgentType.EXECUTOR, detailed_task)

        enhanced_msg = str(error)
        assert "[EXECUTOR]" in enhanced_msg
        assert "detailed_task_123" in enhanced_msg
        assert "Detailed task failed" in enhanced_msg

    def test_error_context_different_task_types(self, runtime):
        """Test error context for different task types."""
        task_types = [
            TaskType.THINK,
            TaskType.RETRIEVE,
            TaskType.WRITE,
            TaskType.CODE_INTERPRET,
            TaskType.IMAGE_GENERATION,
        ]

        for task_type in task_types:
            task = TaskNode(
                task_id=f"task_{task_type.value}",
                goal=f"Test {task_type.value} task",
                task_type=task_type,
                status=TaskStatus.EXECUTING,
                execution_id="test_execution",
            )

            error = ValueError(f"Failed {task_type.value} task")
            runtime._enhance_error_context(error, AgentType.EXECUTOR, task)

            enhanced_msg = str(error)
            assert "[EXECUTOR]" in enhanced_msg
            assert task.task_id in enhanced_msg
