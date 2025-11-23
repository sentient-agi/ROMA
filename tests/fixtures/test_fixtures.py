"""Reusable test fixtures and utilities for resilience system testing."""

import asyncio
import pytest
import tempfile
from pathlib import Path
from typing import Dict, List, Any
from unittest.mock import Mock, AsyncMock

from roma_dspy.core.engine.dag import TaskDAG
from roma_dspy.core.modules import Atomizer, Planner, Executor, Aggregator
from roma_dspy.resilience.checkpoint_manager import CheckpointManager
from roma_dspy.core.signatures import TaskNode, SubTask
from roma_dspy.types import (
    TaskType,
    TaskStatus,
    NodeType,
    ModuleResult,
    PredictionStrategy,
    AgentType,
)
from roma_dspy.types.checkpoint_models import CheckpointConfig


class MockModuleFactory:
    """Factory for creating consistent mock modules across tests."""

    @staticmethod
    def create_atomizer(is_atomic: bool = False) -> Mock:
        """Create mock atomizer with configurable atomicity decision."""
        atomizer = Mock(spec=Atomizer)

        result = ModuleResult(
            is_atomic=is_atomic,
            node_type=NodeType.EXECUTE if is_atomic else NodeType.PLAN,
            reasoning=f"Task is {'atomic' if is_atomic else 'complex and needs decomposition'}",
        )

        atomizer.forward.return_value = result
        atomizer.aforward = AsyncMock(return_value=result)
        return atomizer

    @staticmethod
    def create_planner(subtasks: List[Dict[str, Any]] = None) -> Mock:
        """Create mock planner with configurable subtasks."""
        planner = Mock(spec=Planner)

        if subtasks is None:
            subtasks = [
                {
                    "goal": "Research and gather information",
                    "task_type": TaskType.RETRIEVE,
                    "dependencies": [],
                },
                {
                    "goal": "Analyze the gathered data",
                    "task_type": TaskType.THINK,
                    "dependencies": ["subtask_0"],
                },
                {
                    "goal": "Generate final output",
                    "task_type": TaskType.WRITE,
                    "dependencies": ["subtask_1"],
                },
            ]

        # Convert dict subtasks to SubTask objects
        subtask_objects = []
        dependencies_graph = {}

        for i, subtask_data in enumerate(subtasks):
            subtask = SubTask(
                goal=subtask_data["goal"],
                task_type=subtask_data["task_type"],
                dependencies=subtask_data.get("dependencies", []),
            )
            subtask_objects.append(subtask)

            # Build dependencies graph
            if subtask_data.get("dependencies"):
                dependencies_graph[f"subtask_{i}"] = subtask_data["dependencies"]

        # Create planning result
        planning_result = Mock()
        planning_result.subtasks = subtask_objects
        planning_result.dependencies_graph = dependencies_graph

        planner.forward.return_value = planning_result
        planner.aforward = AsyncMock(return_value=planning_result)
        return planner

    @staticmethod
    def create_executor(
        result: str = "Execution completed successfully", should_fail: bool = False
    ) -> Mock:
        """Create mock executor with configurable result or failure."""
        executor = Mock(spec=Executor)

        if should_fail:
            error = RuntimeError("Execution failed")
            executor.forward.side_effect = error
            executor.aforward = AsyncMock(side_effect=error)
        else:
            executor.forward.return_value = result
            executor.aforward = AsyncMock(return_value=result)

        return executor

    @staticmethod
    def create_aggregator(
        result: str = "Final aggregated result", should_fail: bool = False
    ) -> Mock:
        """Create mock aggregator with configurable result or failure."""
        aggregator = Mock(spec=Aggregator)

        if should_fail:
            error = ValueError("Aggregation failed")
            aggregator.forward.side_effect = error
            aggregator.aforward = AsyncMock(side_effect=error)
        else:
            aggregator.forward.return_value = result
            aggregator.aforward = AsyncMock(return_value=result)

        return aggregator

    @classmethod
    def create_full_module_set(
        self,
        atomizer_atomic: bool = False,
        planner_subtasks: List[Dict[str, Any]] = None,
        executor_result: str = "Success",
        aggregator_result: str = "Final result",
        executor_should_fail: bool = False,
        aggregator_should_fail: bool = False,
    ) -> Dict[str, Mock]:
        """Create a complete set of mock modules."""
        return {
            "atomizer": self.create_atomizer(atomizer_atomic),
            "planner": self.create_planner(planner_subtasks),
            "executor": self.create_executor(executor_result, executor_should_fail),
            "aggregator": self.create_aggregator(
                aggregator_result, aggregator_should_fail
            ),
        }


class TaskNodeFactory:
    """Factory for creating TaskNode instances with various configurations."""

    @staticmethod
    def create_simple_task(
        task_id: str = "test_task",
        goal: str = "Simple test task",
        task_type: TaskType = TaskType.THINK,
        status: TaskStatus = TaskStatus.PENDING,
    ) -> TaskNode:
        """Create a simple TaskNode."""
        return TaskNode(task_id=task_id, goal=goal, task_type=task_type, status=status)

    @staticmethod
    def create_completed_task(
        task_id: str = "completed_task",
        goal: str = "Completed test task",
        result: Any = "Task completed successfully",
    ) -> TaskNode:
        """Create a completed TaskNode with result."""
        return TaskNode(
            task_id=task_id,
            goal=goal,
            task_type=TaskType.THINK,
            status=TaskStatus.COMPLETED,
            result=result,
        )

    @staticmethod
    def create_failed_task(
        task_id: str = "failed_task",
        goal: str = "Failed test task",
        error: str = "Task execution failed",
    ) -> TaskNode:
        """Create a failed TaskNode with error."""
        return TaskNode(
            task_id=task_id,
            goal=goal,
            task_type=TaskType.CODE_INTERPRET,
            status=TaskStatus.FAILED,
            error=error,
        )

    @staticmethod
    def create_hierarchy_tasks() -> List[TaskNode]:
        """Create a set of tasks representing a typical hierarchy."""
        return [
            TaskNode(
                task_id="root_task",
                goal="Root task that requires decomposition",
                task_type=TaskType.THINK,
                status=TaskStatus.PLAN_DONE,
                depth=0,
            ),
            TaskNode(
                task_id="subtask_1",
                goal="First subtask - data retrieval",
                task_type=TaskType.RETRIEVE,
                status=TaskStatus.COMPLETED,
                depth=1,
                parent_id="root_task",
                result="Retrieved data successfully",
            ),
            TaskNode(
                task_id="subtask_2",
                goal="Second subtask - analysis",
                task_type=TaskType.THINK,
                status=TaskStatus.FAILED,
                depth=1,
                parent_id="root_task",
                error="Analysis failed due to invalid data",
            ),
            TaskNode(
                task_id="subtask_3",
                goal="Third subtask - report generation",
                task_type=TaskType.WRITE,
                status=TaskStatus.PENDING,
                depth=1,
                parent_id="root_task",
            ),
        ]

    @staticmethod
    def create_deep_hierarchy() -> List[TaskNode]:
        """Create tasks with deeper nesting for advanced testing."""
        tasks = []

        # Root task
        tasks.append(
            TaskNode(
                task_id="deep_root",
                goal="Deep hierarchical task",
                task_type=TaskType.THINK,
                status=TaskStatus.PLAN_DONE,
                depth=0,
            )
        )

        # Level 1 tasks
        for i in range(3):
            tasks.append(
                TaskNode(
                    task_id=f"level1_task_{i}",
                    goal=f"Level 1 task {i}",
                    task_type=TaskType.THINK,
                    status=TaskStatus.PLAN_DONE if i < 2 else TaskStatus.FAILED,
                    depth=1,
                    parent_id="deep_root",
                )
            )

            # Level 2 tasks (for first two level 1 tasks)
            if i < 2:
                for j in range(2):
                    tasks.append(
                        TaskNode(
                            task_id=f"level2_task_{i}_{j}",
                            goal=f"Level 2 task {i}-{j}",
                            task_type=TaskType.CODE_INTERPRET,
                            status=TaskStatus.COMPLETED
                            if j == 0
                            else TaskStatus.PENDING,
                            depth=2,
                            parent_id=f"level1_task_{i}",
                            result=f"Level 2 result {i}-{j}" if j == 0 else None,
                        )
                    )

        return tasks


class DAGFactory:
    """Factory for creating TaskDAG instances with various configurations."""

    @staticmethod
    def create_simple_dag(tasks: List[TaskNode] = None) -> TaskDAG:
        """Create a simple DAG with basic tasks."""
        dag = TaskDAG("simple_test_dag")

        if tasks is None:
            tasks = [TaskNodeFactory.create_simple_task()]

        for task in tasks:
            dag.add_node(task)

        return dag

    @staticmethod
    def create_hierarchical_dag() -> TaskDAG:
        """Create a DAG with hierarchical structure."""
        dag = TaskDAG("hierarchical_test_dag")
        tasks = TaskNodeFactory.create_hierarchy_tasks()

        # Add root task
        root_task = tasks[0]
        dag.add_node(root_task)

        # Add subtasks as subgraph
        subtasks = tasks[1:]
        dependencies = {
            "subtask_2": ["subtask_1"],  # Analysis depends on retrieval
            "subtask_3": ["subtask_2"],  # Report depends on analysis
        }

        dag.create_subgraph(root_task.task_id, subtasks, dependencies)
        return dag

    @staticmethod
    def create_failed_dag() -> TaskDAG:
        """Create a DAG with some failed tasks."""
        dag = TaskDAG("failed_test_dag")

        tasks = [
            TaskNodeFactory.create_completed_task("success_1", "First successful task"),
            TaskNodeFactory.create_failed_task("failed_1", "First failed task"),
            TaskNodeFactory.create_completed_task(
                "success_2", "Second successful task"
            ),
            TaskNodeFactory.create_failed_task("failed_2", "Second failed task"),
            TaskNodeFactory.create_simple_task(
                "pending_1", "Pending task", status=TaskStatus.PENDING
            ),
        ]

        for task in tasks:
            dag.add_node(task)

        return dag


class ConfigurationFactory:
    """Factory for creating various test configurations."""

    @staticmethod
    def create_test_checkpoint_config(temp_dir: Path) -> CheckpointConfig:
        """Create checkpoint config optimized for testing."""
        return CheckpointConfig(
            enabled=True,
            storage_path=temp_dir,
            max_checkpoints=5,
            max_age_hours=1.0,
            compress_checkpoints=False,  # Easier for test inspection
            verify_integrity=True,
            preserve_partial_results=True,
        )

    @staticmethod
    def create_minimal_checkpoint_config(temp_dir: Path) -> CheckpointConfig:
        """Create minimal checkpoint config for lightweight tests."""
        return CheckpointConfig(
            enabled=True,
            storage_path=temp_dir,
            max_checkpoints=2,
            max_age_hours=0.1,  # Very short for quick cleanup testing
            compress_checkpoints=False,
            verify_integrity=False,  # Skip verification for speed
        )

    @staticmethod
    def create_production_like_config(temp_dir: Path) -> CheckpointConfig:
        """Create config that simulates production settings."""
        return CheckpointConfig(
            enabled=True,
            storage_path=temp_dir,
            max_checkpoints=20,
            max_age_hours=24.0,
            compress_checkpoints=True,
            verify_integrity=True,
            preserve_partial_results=True,
            cleanup_interval_minutes=60,
        )


# ==================== Pytest Fixtures ====================


@pytest.fixture
def temp_checkpoint_storage():
    """Temporary directory for checkpoint storage."""
    with tempfile.TemporaryDirectory(prefix="pytest_checkpoints_") as temp_dir:
        yield Path(temp_dir)


@pytest.fixture
def test_checkpoint_config(temp_checkpoint_storage):
    """Standard test checkpoint configuration."""
    return ConfigurationFactory.create_test_checkpoint_config(temp_checkpoint_storage)


@pytest.fixture
def checkpoint_manager(test_checkpoint_config):
    """CheckpointManager instance for testing."""
    return CheckpointManager(test_checkpoint_config)


@pytest.fixture
def mock_modules():
    """Standard set of mock modules."""
    return MockModuleFactory.create_full_module_set()


@pytest.fixture
def simple_task():
    """Simple TaskNode for basic testing."""
    return TaskNodeFactory.create_simple_task()


@pytest.fixture
def simple_dag(simple_task):
    """Simple TaskDAG for basic testing."""
    return DAGFactory.create_simple_dag([simple_task])


@pytest.fixture
def hierarchical_dag():
    """Hierarchical TaskDAG for complex testing."""
    return DAGFactory.create_hierarchical_dag()


@pytest.fixture
def failed_dag():
    """DAG with failed tasks for recovery testing."""
    return DAGFactory.create_failed_dag()


# ==================== Test Utilities ====================


class TestErrorSimulator:
    """Utility for simulating various error conditions."""

    @staticmethod
    def create_network_errors() -> List[Exception]:
        """Create list of network-related errors."""
        return [
            ConnectionError("Connection refused"),
            TimeoutError("Request timeout"),
            OSError("Network unreachable"),
        ]

    @staticmethod
    def create_validation_errors() -> List[Exception]:
        """Create list of validation errors."""
        return [
            ValueError("Invalid input value"),
            TypeError("Wrong argument type"),
            KeyError("Missing required key"),
        ]

    @staticmethod
    def create_resource_errors() -> List[Exception]:
        """Create list of resource-related errors."""
        return [
            MemoryError("Out of memory"),
            PermissionError("Access denied"),
            OSError("Disk full"),
        ]

    @staticmethod
    def simulate_intermittent_failure(
        mock_method,
        failure_count: int = 2,
        success_result: Any = "Success after retries",
    ):
        """Configure mock to fail N times then succeed."""
        failures = [RuntimeError(f"Failure {i + 1}") for i in range(failure_count)]
        mock_method.side_effect = failures + [success_result]


class TestAssertionHelpers:
    """Helper methods for common test assertions."""

    @staticmethod
    def assert_checkpoint_valid(checkpoint_data):
        """Assert that checkpoint data is valid."""
        assert checkpoint_data is not None
        assert hasattr(checkpoint_data, "checkpoint_id")
        assert hasattr(checkpoint_data, "created_at")
        assert hasattr(checkpoint_data, "root_dag")
        assert checkpoint_data.checkpoint_id is not None
        assert checkpoint_data.root_dag is not None

    @staticmethod
    def assert_task_status(task: TaskNode, expected_status: TaskStatus):
        """Assert task has expected status."""
        assert task.status == expected_status, (
            f"Expected {expected_status}, got {task.status}"
        )

    @staticmethod
    def assert_error_context_enhanced(
        error: Exception, agent_type: AgentType, task_id: str
    ):
        """Assert that error has been enhanced with proper context."""
        error_msg = str(error)
        assert f"[{agent_type.value.upper()}]" in error_msg
        assert task_id in error_msg

    @staticmethod
    async def assert_checkpoint_exists(
        checkpoint_manager: CheckpointManager, checkpoint_id: str
    ):
        """Assert that checkpoint exists and is loadable."""
        checkpoints = await checkpoint_manager.list_checkpoints()
        checkpoint_ids = [cp["checkpoint_id"] for cp in checkpoints]
        assert checkpoint_id in checkpoint_ids

        # Should be loadable without error
        checkpoint_data = await checkpoint_manager.load_checkpoint(checkpoint_id)
        assert checkpoint_data.checkpoint_id == checkpoint_id
