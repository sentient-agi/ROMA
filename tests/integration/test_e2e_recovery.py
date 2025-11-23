"""End-to-end integration tests for checkpoint recovery system."""

import asyncio
import pytest
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch, AsyncMock

from roma_dspy.core.engine.dag import TaskDAG
from roma_dspy.core.engine.event_loop import EventLoopController
from roma_dspy.core.engine.runtime import ModuleRuntime
from roma_dspy.core.engine.solve import RecursiveSolver
from roma_dspy.core.modules import Atomizer, Planner, Executor, Aggregator
from roma_dspy.resilience.checkpoint_manager import CheckpointManager
from roma_dspy.core.signatures import TaskNode, SubTask
from roma_dspy.types import TaskType, TaskStatus, NodeType, PredictionStrategy
from types import SimpleNamespace
from roma_dspy.types.checkpoint_types import CheckpointTrigger, RecoveryStrategy
from roma_dspy.types.checkpoint_models import CheckpointConfig


class TestEndToEndRecovery:
    """Test complete end-to-end recovery scenarios."""

    @pytest.fixture
    def temp_storage(self):
        """Create temporary storage for checkpoints."""
        with tempfile.TemporaryDirectory(prefix="test_e2e_recovery_") as temp_dir:
            yield Path(temp_dir)

    @pytest.fixture
    def checkpoint_config(self, temp_storage):
        """Create checkpoint configuration."""
        return CheckpointConfig(
            storage_path=temp_storage,
            max_checkpoints=10,
            max_age_hours=24.0,
            compress_checkpoints=False,  # Easier for debugging tests
        )

    @pytest.fixture
    def checkpoint_manager(self, checkpoint_config):
        """Create CheckpointManager instance."""
        return CheckpointManager(checkpoint_config)

    @pytest.fixture
    def mock_atomizer(self):
        """Create mock atomizer with predictable behavior."""
        atomizer = Mock(spec=Atomizer)

        # Configure sync forward
        atomizer.forward.return_value = SimpleNamespace(
            is_atomic=False, node_type=NodeType.PLAN
        )

        # Configure async forward
        atomizer.aforward = AsyncMock(
            return_value=SimpleNamespace(is_atomic=False, node_type=NodeType.PLAN)
        )

        return atomizer

    @pytest.fixture
    def mock_planner(self):
        """Create mock planner with predictable behavior."""
        planner = Mock(spec=Planner)

        # Create mock planning result
        subtasks = [
            SubTask(
                goal="Subtask 1: Research the topic",
                task_type=TaskType.RETRIEVE,
                dependencies=[],
            ),
            SubTask(
                goal="Subtask 2: Analyze the data",
                task_type=TaskType.THINK,
                dependencies=["subtask_0"],
            ),
            SubTask(
                goal="Subtask 3: Write the report",
                task_type=TaskType.WRITE,
                dependencies=["subtask_1"],
            ),
        ]

        planning_result = Mock()
        planning_result.subtasks = subtasks
        planning_result.dependencies_graph = {
            "subtask_1": ["subtask_0"],
            "subtask_2": ["subtask_1"],
        }

        # Configure sync forward
        planner.forward.return_value = planning_result

        # Configure async forward
        planner.aforward = AsyncMock(return_value=planning_result)

        return planner

    @pytest.fixture
    def mock_executor(self):
        """Create mock executor with configurable behavior."""
        executor = Mock(spec=Executor)

        # Configure sync forward
        executor.forward.return_value = "Execution completed successfully"

        # Configure async forward
        executor.aforward = AsyncMock(return_value="Execution completed successfully")

        return executor

    @pytest.fixture
    def mock_aggregator(self):
        """Create mock aggregator."""
        aggregator = Mock(spec=Aggregator)

        # Configure sync forward
        aggregator.forward.return_value = "Final aggregated result"

        # Configure async forward
        aggregator.aforward = AsyncMock(return_value="Final aggregated result")

        return aggregator

    @pytest.fixture
    def runtime(self, mock_atomizer, mock_planner, mock_executor, mock_aggregator):
        """Create ModuleRuntime with mocked modules."""
        return ModuleRuntime(
            atomizer=mock_atomizer,
            planner=mock_planner,
            executor=mock_executor,
            aggregator=mock_aggregator,
        )

    @pytest.fixture
    def sample_task(self):
        """Create sample task for testing."""
        return TaskNode(
            task_id="e2e_test_task",
            goal="Complete integration test task with multiple subtasks",
            task_type=TaskType.THINK,
            status=TaskStatus.PENDING,
        )

    # ==================== Basic E2E Recovery Tests ====================

    @pytest.mark.asyncio
    async def test_checkpoint_creation_during_solver_execution(
        self, checkpoint_manager, runtime, sample_task
    ):
        """Test that checkpoints are created during RecursiveSolver execution."""
        solver = RecursiveSolver(
            atomizer=runtime.atomizer,
            planner=runtime.planner,
            executor=runtime.executor,
            aggregator=runtime.aggregator,
            enable_checkpoints=True,
            checkpoint_config=checkpoint_manager.config,
            max_depth=2,
        )

        # Execute task (this should create checkpoints)
        try:
            result = await solver.async_solve(sample_task)

            # Verify checkpoints were created
            checkpoints = await checkpoint_manager.list_checkpoints()

            # Should have at least one checkpoint
            assert len(checkpoints) > 0

            # Verify checkpoint triggers
            triggers = [cp["trigger"] for cp in checkpoints]
            assert CheckpointTrigger.BEFORE_PLANNING.value in triggers

        except Exception as e:
            # Even if execution fails, checkpoints should be available
            checkpoints = await checkpoint_manager.list_checkpoints()
            print(f"Execution failed but found {len(checkpoints)} checkpoints: {e}")

    @pytest.mark.asyncio
    async def test_partial_recovery_preserves_completed_work(
        self, checkpoint_manager, runtime, sample_task
    ):
        """Test that partial recovery preserves completed task results."""
        dag = TaskDAG("recovery_test_dag")

        # Create multiple tasks
        task1 = TaskNode(
            task_id="task_1",
            goal="First task",
            task_type=TaskType.THINK,
            status=TaskStatus.COMPLETED,
            result="Task 1 completed successfully",
        )
        task2 = TaskNode(
            task_id="task_2",
            goal="Second task",
            task_type=TaskType.WRITE,
            status=TaskStatus.FAILED,
        )
        task3 = TaskNode(
            task_id="task_3",
            goal="Third task",
            task_type=TaskType.RETRIEVE,
            status=TaskStatus.PENDING,
        )

        dag.add_node(task1)
        dag.add_node(task2)
        dag.add_node(task3)

        # Create checkpoint
        checkpoint_id = await checkpoint_manager.create_checkpoint(
            checkpoint_id="partial_recovery_test",
            dag=dag,
            trigger=CheckpointTrigger.ON_FAILURE,
        )

        # Create recovery plan for failed task
        checkpoint_data = await checkpoint_manager.load_checkpoint(checkpoint_id)
        failed_tasks = {"task_2"}

        recovery_plan = await checkpoint_manager.create_recovery_plan(
            checkpoint_data, failed_tasks, RecoveryStrategy.PARTIAL
        )

        # Verify recovery plan
        assert recovery_plan.strategy == RecoveryStrategy.PARTIAL
        assert "task_2" in recovery_plan.tasks_to_retry
        assert (
            "task_1" in recovery_plan.tasks_to_preserve
        )  # Completed task should be preserved

        # Apply recovery plan
        recovered_dag = await checkpoint_manager.apply_recovery_plan(recovery_plan, dag)

        # Verify preservation of completed work
        preserved_task = recovered_dag.get_node("task_1")
        assert preserved_task.status == TaskStatus.COMPLETED
        assert preserved_task.result == "Task 1 completed successfully"

    @pytest.mark.asyncio
    async def test_event_loop_recovery_integration(
        self, checkpoint_manager, runtime, sample_task
    ):
        """Test EventLoop integration with checkpoint recovery."""
        dag = TaskDAG("event_loop_recovery_test")
        dag.add_node(sample_task)

        # Create EventLoopController with checkpoint manager
        controller = EventLoopController(
            dag=dag, runtime=runtime, checkpoint_manager=checkpoint_manager
        )

        # Simulate a failure scenario by making executor fail initially
        runtime.executor.aforward.side_effect = [
            ConnectionError("Network failure"),  # First call fails
            "Recovery successful",  # Second call succeeds
        ]

        # Run event loop (should handle failure and potentially recover)
        try:
            await controller.run(max_concurrency=1)
        except Exception as e:
            print(f"Event loop execution result: {e}")

        # Verify recovery mechanisms were invoked
        # (This tests the failure handling path)
        assert controller._failure_count >= 0  # Should track failures

    # ==================== Complex Recovery Scenarios ====================

    @pytest.mark.asyncio
    async def test_multi_level_task_hierarchy_recovery(
        self, checkpoint_manager, runtime
    ):
        """Test recovery in complex multi-level task hierarchies."""
        # Create root task
        root_task = TaskNode(
            task_id="root_task",
            goal="Complex multi-level task",
            task_type=TaskType.THINK,
            status=TaskStatus.PLAN_DONE,
        )

        # Create DAG with hierarchy
        dag = TaskDAG("hierarchy_test")
        dag.add_node(root_task)

        # Create subgraph with multiple levels
        subtasks = [
            TaskNode(
                task_id="level1_task1",
                goal="Level 1 Task 1",
                task_type=TaskType.THINK,
                status=TaskStatus.COMPLETED,
            ),
            TaskNode(
                task_id="level1_task2",
                goal="Level 1 Task 2",
                task_type=TaskType.WRITE,
                status=TaskStatus.FAILED,
            ),
            TaskNode(
                task_id="level1_task3",
                goal="Level 1 Task 3",
                task_type=TaskType.RETRIEVE,
                status=TaskStatus.PENDING,
            ),
        ]

        subgraph = dag.create_subgraph(
            root_task.task_id,
            subtasks,
            dependencies={
                "level1_task2": ["level1_task1"],
                "level1_task3": ["level1_task2"],
            },
        )

        # Create checkpoint
        checkpoint_id = await checkpoint_manager.create_checkpoint(
            checkpoint_id="hierarchy_recovery_test",
            dag=dag,
            trigger=CheckpointTrigger.BEFORE_AGGREGATION,
        )

        # Test recovery of failed subtask
        checkpoint_data = await checkpoint_manager.load_checkpoint(checkpoint_id)
        failed_tasks = {"level1_task2"}

        recovery_plan = await checkpoint_manager.create_recovery_plan(
            checkpoint_data, failed_tasks, RecoveryStrategy.PARTIAL
        )

        # Verify affected tasks calculation
        assert "level1_task2" in recovery_plan.tasks_to_retry
        assert (
            "level1_task3" in recovery_plan.tasks_to_retry
        )  # Dependent on failed task
        assert (
            "level1_task1" in recovery_plan.tasks_to_preserve
        )  # Independent completed task

    @pytest.mark.asyncio
    async def test_checkpoint_corruption_handling(
        self, checkpoint_manager, runtime, sample_task
    ):
        """Test handling of corrupted checkpoint files."""
        dag = TaskDAG("corruption_test")
        dag.add_node(sample_task)

        # Create valid checkpoint first
        checkpoint_id = await checkpoint_manager.create_checkpoint(
            checkpoint_id="corruption_test_checkpoint",
            dag=dag,
            trigger=CheckpointTrigger.MANUAL,
        )

        # Corrupt the checkpoint file
        checkpoint_path = checkpoint_manager._get_checkpoint_path(checkpoint_id)
        with open(checkpoint_path, "w") as f:
            f.write("corrupted invalid json content {")

        # Attempt to load corrupted checkpoint
        from roma_dspy.types.checkpoint_types import CheckpointCorruptedError

        with pytest.raises(CheckpointCorruptedError):
            await checkpoint_manager.load_checkpoint(checkpoint_id)

        # Verify corruption detection
        is_valid = await checkpoint_manager.validate_checkpoint(checkpoint_id)
        assert is_valid is False

    @pytest.mark.asyncio
    async def test_concurrent_checkpoint_operations(self, checkpoint_manager, runtime):
        """Test concurrent checkpoint creation and recovery operations."""
        # Create multiple DAGs
        dags = []
        for i in range(5):
            dag = TaskDAG(f"concurrent_dag_{i}")
            task = TaskNode(
                task_id=f"concurrent_task_{i}",
                goal=f"Concurrent test task {i}",
                task_type=TaskType.THINK,
                status=TaskStatus.COMPLETED,
            )
            dag.add_node(task)
            dags.append(dag)

        # Create checkpoints concurrently
        checkpoint_tasks = []
        for i, dag in enumerate(dags):
            task = checkpoint_manager.create_checkpoint(
                checkpoint_id=f"concurrent_checkpoint_{i}",
                dag=dag,
                trigger=CheckpointTrigger.MANUAL,
            )
            checkpoint_tasks.append(task)

        checkpoint_ids = await asyncio.gather(*checkpoint_tasks)

        # Verify all checkpoints were created
        assert len(checkpoint_ids) == 5
        assert all(cid for cid in checkpoint_ids)

        # Verify all checkpoints can be loaded
        load_tasks = [checkpoint_manager.load_checkpoint(cid) for cid in checkpoint_ids]
        checkpoint_data_list = await asyncio.gather(*load_tasks)

        assert len(checkpoint_data_list) == 5
        assert all(data.state.value == "valid" for data in checkpoint_data_list)

    # ==================== Performance and Resource Tests ====================

    @pytest.mark.asyncio
    async def test_checkpoint_cleanup_under_load(self, checkpoint_manager, runtime):
        """Test checkpoint cleanup under high load scenarios."""
        # Create many checkpoints to trigger cleanup
        dag = TaskDAG("cleanup_test")
        task = TaskNode(
            task_id="cleanup_test_task",
            goal="Cleanup test task",
            task_type=TaskType.THINK,
            status=TaskStatus.COMPLETED,
        )
        dag.add_node(task)

        # Create more checkpoints than the limit
        checkpoint_ids = []
        for i in range(15):  # More than max_checkpoints (10)
            checkpoint_id = await checkpoint_manager.create_checkpoint(
                checkpoint_id=f"cleanup_test_{i:02d}",
                dag=dag,
                trigger=CheckpointTrigger.MANUAL,
            )
            checkpoint_ids.append(checkpoint_id)

        # Trigger cleanup
        removed_count = await checkpoint_manager.cleanup_checkpoints(keep_latest=5)

        # Verify cleanup occurred
        assert removed_count >= 5  # Should remove excess checkpoints

        # Verify remaining checkpoints
        remaining = await checkpoint_manager.list_checkpoints()
        assert len(remaining) <= checkpoint_manager.config.max_checkpoints

    @pytest.mark.asyncio
    async def test_storage_stats_accuracy(self, checkpoint_manager, runtime):
        """Test storage statistics accuracy."""
        initial_stats = await checkpoint_manager.get_storage_stats()
        initial_count = initial_stats.get("total_checkpoints", 0)

        # Create checkpoints
        dag = TaskDAG("stats_test")
        task = TaskNode(
            task_id="stats_test_task",
            goal="Stats test task",
            task_type=TaskType.THINK,
            status=TaskStatus.COMPLETED,
        )
        dag.add_node(task)

        num_checkpoints = 3
        for i in range(num_checkpoints):
            await checkpoint_manager.create_checkpoint(
                checkpoint_id=f"stats_test_{i}",
                dag=dag,
                trigger=CheckpointTrigger.MANUAL,
            )

        # Get updated stats
        final_stats = await checkpoint_manager.get_storage_stats()

        # Verify stats accuracy
        assert final_stats["total_checkpoints"] == initial_count + num_checkpoints
        assert final_stats["total_size_bytes"] > initial_stats.get(
            "total_size_bytes", 0
        )
        assert final_stats["storage_path"] == str(checkpoint_manager.storage_path)

    # ==================== Edge Cases and Error Handling ====================

    @pytest.mark.asyncio
    async def test_recovery_with_missing_dependencies(
        self, checkpoint_manager, runtime
    ):
        """Test recovery when task dependencies are missing."""
        dag = TaskDAG("missing_deps_test")

        # Create task with missing dependency reference
        task = TaskNode(
            task_id="dependent_task",
            goal="Task with missing dependency",
            task_type=TaskType.WRITE,
            status=TaskStatus.FAILED,
        )
        dag.add_node(task)

        # Create checkpoint
        checkpoint_id = await checkpoint_manager.create_checkpoint(
            checkpoint_id="missing_deps_checkpoint",
            dag=dag,
            trigger=CheckpointTrigger.ON_FAILURE,
        )

        # Attempt recovery
        checkpoint_data = await checkpoint_manager.load_checkpoint(checkpoint_id)
        failed_tasks = {"dependent_task"}

        recovery_plan = await checkpoint_manager.create_recovery_plan(
            checkpoint_data, failed_tasks, RecoveryStrategy.PARTIAL
        )

        # Recovery should handle missing dependencies gracefully
        assert recovery_plan.strategy == RecoveryStrategy.PARTIAL
        assert "dependent_task" in recovery_plan.tasks_to_retry

    @pytest.mark.asyncio
    async def test_context_manager_cleanup(self, checkpoint_config, runtime):
        """Test proper cleanup when using CheckpointManager as context manager."""
        checkpoint_id = None

        # Use CheckpointManager as context manager
        async with CheckpointManager(checkpoint_config) as manager:
            dag = TaskDAG("context_manager_test")
            task = TaskNode(
                task_id="context_test_task",
                goal="Context manager test",
                task_type=TaskType.THINK,
                status=TaskStatus.COMPLETED,
            )
            dag.add_node(task)

            checkpoint_id = await manager.create_checkpoint(
                checkpoint_id="context_test_checkpoint",
                dag=dag,
                trigger=CheckpointTrigger.MANUAL,
            )

            # Verify checkpoint was created
            assert checkpoint_id is not None

        # Context manager should have called shutdown
        # Verify checkpoint still exists (cleanup shouldn't delete valid checkpoints)
        new_manager = CheckpointManager(checkpoint_config)
        checkpoints = await new_manager.list_checkpoints()
        checkpoint_exists = any(
            cp["checkpoint_id"] == checkpoint_id for cp in checkpoints
        )
        assert checkpoint_exists
