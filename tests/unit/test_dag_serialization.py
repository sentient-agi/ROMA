"""Tests for DAG serialization and task state restoration."""

import pytest
from datetime import datetime
from typing import Any, Dict

from roma_dspy.core.engine.dag import TaskDAG
from roma_dspy.core.signatures.base_models.task_node import TaskNode
from roma_dspy.types import TaskType, TaskStatus, NodeType
from roma_dspy.types.module_result import NodeMetrics
from roma_dspy.types.checkpoint_models import TaskSnapshot, DAGSnapshot


class TestDAGSerialization:
    """Test TaskDAG serialization and deserialization for checkpoints."""

    @pytest.fixture
    def sample_task(self):
        """Create sample task with various data types."""
        # Retry configuration goes in metrics
        metrics = NodeMetrics(retry_count=2, max_retries=3)

        return TaskNode(
            task_id="serialization_test_task",
            goal="Test task with complex data for serialization",
            task_type=TaskType.THINK,
            status=TaskStatus.COMPLETED,
            result={
                "output": "Complex result",
                "metadata": {"count": 42, "success": True},
            },
            depth=1,
            execution_id="test_execution_123",  # Required field
            metrics=metrics,
            metadata={
                "custom_field": "custom_value",
                "timestamp": "2023-12-01T10:00:00",
            },
        )

    @pytest.fixture
    def complex_dag(self, sample_task):
        """Create complex DAG with multiple tasks and relationships."""
        dag = TaskDAG("complex_serialization_dag")

        # Add root task
        root_task = TaskNode(
            task_id="root_task",
            goal="Root task for serialization testing",
            task_type=TaskType.THINK,
            status=TaskStatus.PLAN_DONE,
            depth=0,
            execution_id=dag.execution_id,  # Use DAG's execution_id
        )
        dag.add_node(root_task)

        # Add various tasks with different states
        failed_metrics = NodeMetrics(retry_count=3, max_retries=3)

        tasks = [
            TaskNode(
                task_id="completed_task",
                goal="Completed task",
                task_type=TaskType.RETRIEVE,
                status=TaskStatus.COMPLETED,
                result="Successfully retrieved data",
                depth=1,
                parent_id="root_task",
                execution_id=dag.execution_id,
            ),
            TaskNode(
                task_id="failed_task",
                goal="Failed task",
                task_type=TaskType.CODE_INTERPRET,
                status=TaskStatus.FAILED,
                error="Execution failed due to network timeout",
                depth=1,
                parent_id="root_task",
                metrics=failed_metrics,  # Retry config in metrics
                execution_id=dag.execution_id,
            ),
            TaskNode(
                task_id="pending_task",
                goal="Pending task",
                task_type=TaskType.WRITE,
                status=TaskStatus.PENDING,
                depth=1,
                parent_id="root_task",
                execution_id=dag.execution_id,
            ),
        ]

        # Create subgraph with dependencies
        dependencies = {
            "failed_task": ["completed_task"],
            "pending_task": ["completed_task", "failed_task"],
        }

        dag.create_subgraph(root_task.task_id, tasks, dependencies)
        return dag

    # ==================== TaskSnapshot Tests ====================

    def test_task_snapshot_creation(self, sample_task):
        """Test creating TaskSnapshot from TaskNode."""
        snapshot = TaskSnapshot(
            task_id=sample_task.task_id,
            status=sample_task.status.value,
            task_type=sample_task.task_type.value,
            depth=sample_task.depth,
            retry_count=sample_task.retry_count,
            max_retries=sample_task.max_retries,
            result=sample_task.result,
            error=str(sample_task.error) if sample_task.error else None,
            subgraph_id=sample_task.subgraph_id,
            dependencies=[dep.task_id for dep in sample_task.dependencies],
            metadata=sample_task.metadata or {},
        )

        assert snapshot.task_id == sample_task.task_id
        assert snapshot.status == sample_task.status.value
        assert snapshot.task_type == sample_task.task_type.value
        assert snapshot.depth == sample_task.depth
        assert snapshot.retry_count == sample_task.retry_count
        assert snapshot.max_retries == sample_task.max_retries
        assert snapshot.result == sample_task.result
        assert snapshot.metadata == (sample_task.metadata or {})

    def test_task_snapshot_serialization(self, sample_task):
        """Test TaskSnapshot JSON serialization."""
        snapshot = TaskSnapshot(
            task_id=sample_task.task_id,
            status=sample_task.status.value,
            task_type=sample_task.task_type.value,
            depth=sample_task.depth,
            retry_count=sample_task.retry_count,
            max_retries=sample_task.max_retries,
            result=sample_task.result,
            metadata=sample_task.metadata or {},
        )

        # Test model_dump (Pydantic v2 serialization)
        serialized = snapshot.model_dump(mode="json")

        assert isinstance(serialized, dict)
        assert serialized["task_id"] == sample_task.task_id
        assert serialized["status"] == sample_task.status.value
        assert serialized["task_type"] == sample_task.task_type.value
        assert isinstance(serialized["result"], dict)

    def test_task_snapshot_deserialization(self, sample_task):
        """Test TaskSnapshot deserialization from dict."""
        data = {
            "task_id": sample_task.task_id,
            "status": sample_task.status.value,
            "task_type": sample_task.task_type.value,
            "depth": sample_task.depth,
            "retry_count": sample_task.retry_count,
            "max_retries": sample_task.max_retries,
            "result": sample_task.result,
            "error": None,
            "subgraph_id": None,
            "dependencies": [],
            "metadata": sample_task.metadata or {},
        }

        snapshot = TaskSnapshot.model_validate(data)

        assert snapshot.task_id == sample_task.task_id
        assert snapshot.status == sample_task.status.value
        assert snapshot.task_type == sample_task.task_type.value
        assert snapshot.result == sample_task.result

    def test_task_snapshot_with_error(self):
        """Test TaskSnapshot with error information."""
        error_message = "Task failed due to validation error"

        snapshot = TaskSnapshot(
            task_id="error_task",
            status=TaskStatus.FAILED.value,
            task_type=TaskType.CODE_INTERPRET.value,
            depth=1,
            retry_count=2,
            max_retries=3,
            error=error_message,
        )

        assert snapshot.error == error_message
        assert snapshot.status == TaskStatus.FAILED.value

        # Test serialization preserves error
        serialized = snapshot.model_dump()
        assert serialized["error"] == error_message

    # ==================== DAGSnapshot Tests ====================

    def test_dag_snapshot_creation(self, complex_dag):
        """Test creating DAGSnapshot from TaskDAG."""
        tasks = {}
        completed_tasks = set()
        failed_tasks = set()

        for task_id, task in complex_dag.get_all_tasks_dict().items():
            task_snapshot = TaskSnapshot(
                task_id=task.task_id,
                status=task.status.value,
                task_type=task.task_type.value,
                depth=task.depth,
                retry_count=task.retry_count,
                max_retries=task.max_retries,
                result=task.result,
                error=str(task.error) if task.error else None,
                subgraph_id=task.subgraph_id,
                dependencies=list(task.dependencies),
                metadata=task.metadata or {},
            )
            tasks[task_id] = task_snapshot

            if task.status.value == "COMPLETED":
                completed_tasks.add(task_id)
            elif task.status.value == "FAILED":
                failed_tasks.add(task_id)

        dag_snapshot = DAGSnapshot(
            dag_id=complex_dag.dag_id,
            tasks=tasks,
            completed_tasks=completed_tasks,
            failed_tasks=failed_tasks,
        )

        assert dag_snapshot.dag_id == complex_dag.dag_id
        assert len(dag_snapshot.tasks) > 0
        assert len(dag_snapshot.completed_tasks) > 0
        assert len(dag_snapshot.failed_tasks) > 0

    def test_dag_snapshot_serialization(self, complex_dag):
        """Test DAGSnapshot JSON serialization."""
        # Create minimal DAG snapshot
        tasks = {}
        for task_id, task in complex_dag.get_all_tasks_dict().items():
            tasks[task_id] = TaskSnapshot(
                task_id=task.task_id,
                status=task.status.value,
                task_type=task.task_type.value,
                depth=task.depth,
                retry_count=task.retry_count,
                max_retries=task.max_retries,
                result=task.result,
            )

        dag_snapshot = DAGSnapshot(
            dag_id=complex_dag.dag_id,
            tasks=tasks,
            completed_tasks={"completed_task"},
            failed_tasks={"failed_task"},
        )

        # Test serialization
        serialized = dag_snapshot.model_dump(mode="json")

        assert isinstance(serialized, dict)
        assert serialized["dag_id"] == complex_dag.dag_id
        assert isinstance(serialized["tasks"], dict)
        assert isinstance(
            serialized["completed_tasks"], list
        )  # Set becomes list in JSON
        assert isinstance(serialized["failed_tasks"], list)

    def test_dag_snapshot_with_subgraphs(self, complex_dag):
        """Test DAGSnapshot with nested subgraphs."""
        # Create main DAG snapshot
        main_tasks = {
            "root_task": TaskSnapshot(
                task_id="root_task",
                status=TaskStatus.PLAN_DONE.value,
                task_type=TaskType.THINK.value,
                depth=0,
            )
        }

        # Create subgraph snapshots
        subgraph_tasks = {}
        for task_id, task in complex_dag.get_all_tasks_dict().items():
            if task_id != "root_task":  # Exclude root task
                subgraph_tasks[task_id] = TaskSnapshot(
                    task_id=task.task_id,
                    status=task.status.value,
                    task_type=task.task_type.value,
                    depth=task.depth,
                )

        subgraph_snapshot = DAGSnapshot(
            dag_id=f"{complex_dag.dag_id}_sub_root_task",
            tasks=subgraph_tasks,
            completed_tasks={"completed_task"},
            failed_tasks={"failed_task"},
        )

        dag_snapshot = DAGSnapshot(
            dag_id=complex_dag.dag_id,
            tasks=main_tasks,
            subgraphs={"root_task_subgraph": subgraph_snapshot},
        )

        assert len(dag_snapshot.subgraphs) == 1
        assert "root_task_subgraph" in dag_snapshot.subgraphs

    # ==================== DAG State Restoration Tests ====================

    @pytest.mark.asyncio
    async def test_task_result_restoration(self):
        """Test restoring task results from checkpoint data."""
        dag = TaskDAG("restoration_test")

        # Add task to DAG
        task = TaskNode(
            task_id="restore_test_task",
            goal="Task for restoration testing",
            task_type=TaskType.THINK,
            status=TaskStatus.PENDING,
            execution_id=dag.execution_id,  # Required field
        )
        dag.add_node(task)

        # Test result restoration
        test_result = {"output": "Restored result", "metadata": {"restored": True}}
        restored_task = await dag.restore_task_result(
            "restore_test_task", test_result, TaskStatus.COMPLETED.value
        )

        assert restored_task.result == test_result
        assert restored_task.status == TaskStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_task_retry_counter_reset(self):
        """Test resetting task retry counters."""
        dag = TaskDAG("retry_reset_test")

        # Add task with retry count
        metrics = NodeMetrics(retry_count=3, max_retries=5)
        task = TaskNode(
            task_id="retry_test_task",
            goal="Task with retries",
            task_type=TaskType.CODE_INTERPRET,
            status=TaskStatus.FAILED,
            metrics=metrics,
            execution_id=dag.execution_id,  # Required field
        )
        dag.add_node(task)

        # Reset retry counter
        reset_task = await dag.reset_task_retry_counter("retry_test_task")

        assert reset_task.retry_count == 0
        assert reset_task.max_retries == 5  # Should preserve max retries

    @pytest.mark.asyncio
    async def test_task_preparation_for_retry(self):
        """Test preparing task for retry."""
        dag = TaskDAG("retry_prep_test")

        # Add failed task
        task = TaskNode(
            task_id="prep_test_task",
            goal="Task to prepare for retry",
            task_type=TaskType.CODE_INTERPRET,
            status=TaskStatus.FAILED,
            error="Previous execution failed",
            execution_id=dag.execution_id,  # Required field
        )
        dag.add_node(task)

        # Prepare for retry
        prepared_task = await dag.prepare_task_for_retry("prep_test_task")

        assert prepared_task.status == TaskStatus.READY
        # Error might still be preserved for debugging

    # ==================== Complex Data Type Tests ====================

    def test_complex_result_serialization(self):
        """Test serialization of complex result data types."""
        complex_result = {
            "text_output": "Generated text content",
            "metrics": {"accuracy": 0.95, "confidence": 0.87, "processing_time": 2.34},
            "metadata": {
                "model": "gpt-4",
                "tokens_used": 1500,
                "timestamp": "2023-12-01T10:00:00Z",
                "tags": ["analysis", "research", "summary"],
            },
            "nested_objects": [
                {"id": 1, "value": "first"},
                {"id": 2, "value": "second"},
            ],
        }

        snapshot = TaskSnapshot(
            task_id="complex_result_task",
            status=TaskStatus.COMPLETED.value,
            task_type=TaskType.THINK.value,
            depth=1,
            result=complex_result,
        )

        # Test serialization
        serialized = snapshot.model_dump(mode="json")
        assert serialized["result"] == complex_result

        # Test deserialization
        restored_snapshot = TaskSnapshot.model_validate(serialized)
        assert restored_snapshot.result == complex_result

    def test_error_data_serialization(self):
        """Test serialization of error information."""
        error_data = {
            "error_type": "ValidationError",
            "error_message": "Invalid input parameters",
            "stack_trace": ["File 'test.py', line 42", "File 'module.py', line 123"],
            "context": {
                "input_params": {"param1": "value1", "param2": None},
                "validation_rules": ["required", "non_empty"],
            },
        }

        snapshot = TaskSnapshot(
            task_id="error_data_task",
            status=TaskStatus.FAILED.value,
            task_type=TaskType.CODE_INTERPRET.value,
            depth=2,
            error="Detailed error information",
            metadata=error_data,
        )

        # Test serialization preserves error data
        serialized = snapshot.model_dump(mode="json")
        assert serialized["metadata"] == error_data

        # Test deserialization
        restored_snapshot = TaskSnapshot.model_validate(serialized)
        assert restored_snapshot.metadata == error_data

    # ==================== Edge Cases and Validation ====================

    def test_empty_dag_serialization(self):
        """Test serialization of empty DAG."""
        dag_snapshot = DAGSnapshot(
            dag_id="empty_dag", tasks={}, completed_tasks=set(), failed_tasks=set()
        )

        serialized = dag_snapshot.model_dump(mode="json")
        assert serialized["dag_id"] == "empty_dag"
        assert serialized["tasks"] == {}
        assert serialized["completed_tasks"] == []
        assert serialized["failed_tasks"] == []

    def test_task_with_none_values(self):
        """Test TaskSnapshot with None values."""
        snapshot = TaskSnapshot(
            task_id="none_values_task",
            status=TaskStatus.PENDING.value,
            task_type=TaskType.THINK.value,
            depth=0,
            result=None,
            error=None,
            subgraph_id=None,
            dependencies=[],
            metadata={},
        )

        serialized = snapshot.model_dump(mode="json")
        assert serialized["result"] is None
        assert serialized["error"] is None
        assert serialized["subgraph_id"] is None

    def test_large_dag_serialization_performance(self):
        """Test serialization performance with large DAG."""
        # Create large DAG
        dag = TaskDAG("large_dag")

        # Add many tasks
        tasks = {}
        for i in range(100):  # Moderate size for test performance
            task_id = f"task_{i:03d}"
            snapshot = TaskSnapshot(
                task_id=task_id,
                status=TaskStatus.COMPLETED.value
                if i % 2 == 0
                else TaskStatus.PENDING.value,
                task_type=TaskType.THINK.value,
                depth=1,
                result=f"Result for task {i}" if i % 2 == 0 else None,
            )
            tasks[task_id] = snapshot

        dag_snapshot = DAGSnapshot(
            dag_id="large_dag",
            tasks=tasks,
            completed_tasks={f"task_{i:03d}" for i in range(0, 100, 2)},
            failed_tasks=set(),
        )

        # Test serialization doesn't fail with reasonable size
        import time

        start_time = time.time()
        serialized = dag_snapshot.model_dump(mode="json")
        end_time = time.time()

        assert len(serialized["tasks"]) == 100
        assert (end_time - start_time) < 1.0  # Should complete within 1 second

    def test_unicode_and_special_characters(self):
        """Test serialization with unicode and special characters."""
        special_text = "Special chars: éñüñ™ 中文 🚀 \"quotes\" 'apostrophes' \n\t\r"

        snapshot = TaskSnapshot(
            task_id="unicode_task",
            status=TaskStatus.COMPLETED.value,
            task_type=TaskType.WRITE.value,
            depth=1,
            result={"text": special_text, "description": "Unicode test"},
            metadata={"note": special_text},
        )

        # Should serialize without errors
        serialized = snapshot.model_dump(mode="json")
        assert serialized["result"]["text"] == special_text
        assert serialized["metadata"]["note"] == special_text

        # Should deserialize correctly
        restored = TaskSnapshot.model_validate(serialized)
        assert restored.result["text"] == special_text
