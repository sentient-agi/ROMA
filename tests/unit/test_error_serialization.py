"""Test JSON serialization of error types."""

import json
import pytest
from datetime import datetime

from roma_dspy.types.error_types import (
    TaskHierarchyError,
    ModuleError,
    ExecutionError,
    PlanningError,
    AggregationError,
    RetryExhaustedError,
    ErrorCategory,
    ErrorSeverity,
)


class TestErrorSerialization:
    """Test that all error types are JSON serializable."""

    def test_task_hierarchy_error_to_dict(self):
        """Test TaskHierarchyError.to_dict() method."""
        error = TaskHierarchyError(
            message="Test error",
            task_id="task_123",
            task_goal="Do something",
            error_category=ErrorCategory.NETWORK,
            severity=ErrorSeverity.HIGH,
            original_error=ValueError("Original error"),
            context={"key": "value"},
            recovery_suggestions=["Try again", "Check network"],
        )

        error_dict = error.to_dict()

        assert error_dict["message"] == "Test error"
        assert error_dict["task_id"] == "task_123"
        assert error_dict["task_goal"] == "Do something"
        assert error_dict["error_category"] == "network"
        assert error_dict["severity"] == "high"
        assert error_dict["original_error"] == "Original error"
        assert error_dict["context"] == {"key": "value"}
        assert error_dict["recovery_suggestions"] == ["Try again", "Check network"]
        assert "timestamp" in error_dict
        assert error_dict["task_path"] == []
        assert error_dict["depth"] == 0
        assert error_dict["child_errors"] == []

    def test_task_hierarchy_error_json_dumps(self):
        """Test that TaskHierarchyError can be serialized to JSON."""
        error = TaskHierarchyError(message="Test error", task_id="task_123")

        # Should not raise TypeError
        json_str = json.dumps(error.to_dict())
        assert json_str is not None

        # Should be deserializable
        data = json.loads(json_str)
        assert data["message"] == "Test error"
        assert data["task_id"] == "task_123"

    def test_module_error_to_dict(self):
        """Test ModuleError.to_dict() includes module_name."""
        error = ModuleError(
            module_name="test_module", message="Module failed", task_id="task_456"
        )

        error_dict = error.to_dict()

        assert error_dict["module_name"] == "test_module"
        assert error_dict["message"] == "Module failed"
        assert error_dict["task_id"] == "task_456"

        # Should be JSON serializable
        json_str = json.dumps(error_dict)
        assert json_str is not None

    def test_execution_error_json_serializable(self):
        """Test ExecutionError is JSON serializable."""
        error = ExecutionError(message="Execution failed", task_id="task_789")

        error_dict = error.to_dict()

        assert error_dict["module_name"] == "executor"
        assert error_dict["message"] == "Execution failed"

        # Should be JSON serializable
        json_str = json.dumps(error_dict)
        data = json.loads(json_str)
        assert data["module_name"] == "executor"

    def test_planning_error_json_serializable(self):
        """Test PlanningError is JSON serializable."""
        error = PlanningError(message="Planning failed", task_id="task_plan")

        error_dict = error.to_dict()

        assert error_dict["module_name"] == "planner"
        assert error_dict["error_category"] == "logic"

        # Should be JSON serializable
        json_str = json.dumps(error_dict)
        assert json_str is not None

    def test_aggregation_error_json_serializable(self):
        """Test AggregationError is JSON serializable."""
        error = AggregationError(message="Aggregation failed", task_id="task_agg")

        error_dict = error.to_dict()

        assert error_dict["module_name"] == "aggregator"

        # Should be JSON serializable
        json_str = json.dumps(error_dict)
        assert json_str is not None

    def test_retry_exhausted_error_to_dict(self):
        """Test RetryExhaustedError.to_dict() includes retry info."""
        original_error = ValueError("Something went wrong")
        error = RetryExhaustedError(
            task_id="task_retry", attempts=3, last_error=original_error
        )

        error_dict = error.to_dict()

        assert error_dict["attempts"] == 3
        assert error_dict["last_error"] == "Something went wrong"
        assert error_dict["severity"] == "high"
        assert "Task failed after 3 attempts" in error_dict["message"]

        # Should be JSON serializable
        json_str = json.dumps(error_dict)
        assert json_str is not None

    def test_nested_errors_json_serializable(self):
        """Test that nested error hierarchies are JSON serializable."""
        child_error = ExecutionError(message="Child task failed", task_id="child_task")

        parent_error = PlanningError(
            message="Parent task failed", task_id="parent_task"
        )
        parent_error.add_child_error(child_error)
        child_error.add_parent_context("parent_task", "Parent goal")

        error_dict = parent_error.to_dict()

        assert len(error_dict["child_errors"]) == 1
        assert error_dict["child_errors"][0]["task_id"] == "child_task"
        assert error_dict["child_errors"][0]["task_path"] == ["parent_task"]

        # Should be JSON serializable
        json_str = json.dumps(error_dict)
        data = json.loads(json_str)
        assert len(data["child_errors"]) == 1

    def test_error_str_method(self):
        """Test __str__ method returns error summary."""
        error = ExecutionError(message="Test error", task_id="task_123")

        error_str = str(error)
        assert "task_123" in error_str
        assert "Test error" in error_str

    def test_complex_context_serialization(self):
        """Test that complex context dictionaries are serialized."""
        error = TaskHierarchyError(
            message="Complex error",
            task_id="task_complex",
            context={
                "nested": {"key": "value"},
                "list": [1, 2, 3],
                "string": "text",
                "number": 42,
            },
        )

        error_dict = error.to_dict()

        # Should preserve complex context
        assert error_dict["context"]["nested"]["key"] == "value"
        assert error_dict["context"]["list"] == [1, 2, 3]

        # Should be JSON serializable
        json_str = json.dumps(error_dict)
        data = json.loads(json_str)
        assert data["context"]["nested"]["key"] == "value"

    def test_datetime_serialization(self):
        """Test that datetime is properly serialized to ISO format."""
        error = TaskHierarchyError(message="Test error", task_id="task_time")

        error_dict = error.to_dict()

        # Timestamp should be ISO format string
        assert isinstance(error_dict["timestamp"], str)

        # Should be parseable back to datetime
        timestamp = datetime.fromisoformat(error_dict["timestamp"])
        assert isinstance(timestamp, datetime)

        # Should be JSON serializable
        json_str = json.dumps(error_dict)
        assert json_str is not None
