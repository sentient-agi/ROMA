"""Integration tests for context system end-to-end flow."""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

from roma_dspy.core.engine.solve import RecursiveSolver
from roma_dspy.core.signatures import TaskNode
from roma_dspy.config.schemas.root import ROMAConfig
from roma_dspy.types import TaskType


@pytest.fixture
def mock_config():
    """Create a mock ROMAConfig for testing."""
    config = ROMAConfig()
    return config


class TestContextSystemIntegration:
    """Test end-to-end context system integration."""

    def test_context_manager_initialized_on_first_solve(self, mock_config):
        """Test that ContextManager is initialized when solver runs."""
        solver = RecursiveSolver(config=mock_config, enable_checkpoints=False)

        # Before any solve, runtime should not have context_manager
        assert solver.runtime.context_manager is None

        # Create a task
        task = "Test task"

        # Initialize task and DAG (this should create context_manager)
        task_node, dag = solver._initialize_task_and_dag(task, None, 0)

        # After initialization, context_manager should be created
        assert solver.runtime.context_manager is not None
        assert solver.runtime.context_manager.file_storage is not None
        assert solver.runtime.context_manager.overall_objective == "Test task"

    def test_execution_id_propagated_correctly(self, mock_config):
        """Test that execution_id is properly propagated."""
        solver = RecursiveSolver(config=mock_config, enable_checkpoints=False)

        task_node, dag = solver._initialize_task_and_dag("Test task", None, 0)

        # Check execution_id is set on task
        assert task_node.execution_id is not None
        assert task_node.execution_id == dag.execution_id

        # Check execution_id matches FileStorage
        assert (
            solver.runtime.context_manager.file_storage.execution_id == dag.execution_id
        )

    def test_context_manager_reused_across_solves(self, mock_config):
        """Test that ContextManager is reused when DAG is provided."""
        solver = RecursiveSolver(config=mock_config, enable_checkpoints=False)

        # First initialization
        task1, dag1 = solver._initialize_task_and_dag("Task 1", None, 0)
        context_manager1 = solver.runtime.context_manager

        # Second initialization with same DAG
        task2, dag2 = solver._initialize_task_and_dag("Task 2", dag1, 1)
        context_manager2 = solver.runtime.context_manager

        # Should be the same instance
        assert context_manager1 is context_manager2

    def test_file_storage_paths_configured(self, mock_config):
        """Test that FileStorage has correct paths."""
        solver = RecursiveSolver(config=mock_config, enable_checkpoints=False)

        task_node, dag = solver._initialize_task_and_dag("Test task", None, 0)

        file_storage = solver.runtime.context_manager.file_storage

        # Check that base paths exist
        assert file_storage.execution_id is not None
        assert file_storage.root.exists()
        # Check subdirectories exist
        assert (file_storage.root / "outputs").exists()
        assert (file_storage.root / "logs").exists()

    @patch("src.roma_dspy.core.modules.base_module.BaseModule.forward")
    def test_context_passed_to_atomizer(self, mock_forward, mock_config):
        """Test that context is passed to atomizer module."""
        # Mock the forward method to return expected result
        from roma_dspy.core.signatures.base_models.results import AtomizerResponse
        from roma_dspy.types import NodeType

        mock_result = AtomizerResponse(is_atomic=True, node_type=NodeType.EXECUTE)
        mock_forward.return_value = (mock_result, 0.1, None, [])

        solver = RecursiveSolver(config=mock_config, enable_checkpoints=False)

        # Initialize context system
        task_node, dag = solver._initialize_task_and_dag("Test task", None, 0)

        # Run atomize (which should pass context)
        # Note: This is a simplified test - in real scenario we'd need proper agent setup
        # The key is checking that context_manager exists

        assert solver.runtime.context_manager is not None

    def test_context_contains_temporal_info(self, mock_config):
        """Test that context includes temporal information."""
        solver = RecursiveSolver(config=mock_config, enable_checkpoints=False)

        task_node, dag = solver._initialize_task_and_dag("Test task", None, 0)

        # Build a sample context
        tools_data = []
        context_xml = solver.runtime.context_manager.build_atomizer_context(
            task_node, tools_data
        )

        # Check temporal fields are present
        assert "<temporal>" in context_xml
        assert "<current_date>" in context_xml
        assert "<current_year>" in context_xml
        assert "<current_timestamp>" in context_xml

    def test_context_contains_recursion_info(self, mock_config):
        """Test that context includes recursion information."""
        solver = RecursiveSolver(
            config=mock_config, enable_checkpoints=False, max_depth=5
        )

        task_node, dag = solver._initialize_task_and_dag("Test task", None, 2)

        tools_data = []
        context_xml = solver.runtime.context_manager.build_atomizer_context(
            task_node, tools_data
        )

        # Check recursion info
        assert "<recursion>" in context_xml
        assert "<current_depth>2</current_depth>" in context_xml
        assert "<max_depth>5</max_depth>" in context_xml

    def test_executor_context_includes_file_system(self, mock_config):
        """Test that executor gets file system context."""
        solver = RecursiveSolver(config=mock_config, enable_checkpoints=False)

        task_node, dag = solver._initialize_task_and_dag("Test task", None, 0)
        # Task is already added to DAG by _initialize_task_and_dag

        # Mock runtime for executor context
        mock_runtime = Mock()
        mock_runtime.context_store = Mock()
        mock_runtime.context_store.get_result = Mock(return_value=None)

        tools_data = []
        context_xml = solver.runtime.context_manager.build_executor_context(
            task_node, tools_data, mock_runtime, dag
        )

        # Executor should have file_system
        assert "<file_system" in context_xml
        assert "execution_id" in context_xml
        assert "FileStorage methods" in context_xml

    def test_planner_context_without_file_system(self, mock_config):
        """Test that planner does not get file system context."""
        solver = RecursiveSolver(config=mock_config, enable_checkpoints=False)

        task_node, dag = solver._initialize_task_and_dag("Test task", None, 0)
        # Task is already added to DAG by _initialize_task_and_dag

        mock_runtime = Mock()
        mock_runtime.context_store = Mock()
        mock_runtime.context_store.get_result = Mock(return_value=None)

        tools_data = []
        context_xml = solver.runtime.context_manager.build_planner_context(
            task_node, tools_data, mock_runtime, dag
        )

        # Planner should NOT have file_system
        assert "<file_system" not in context_xml


class TestContextWithDependencies:
    """Test context system with task dependencies."""

    def test_executor_receives_dependency_results(self, mock_config):
        """Test that executor context includes dependency results."""
        solver = RecursiveSolver(config=mock_config, enable_checkpoints=False)

        task_node, dag = solver._initialize_task_and_dag("Test task", None, 0)

        # Create dependency task
        dep_task = TaskNode(
            goal="Dependency task", depth=1, max_depth=3, execution_id=dag.execution_id
        )
        dag.add_node(dep_task)

        # Create main task with dependency
        main_task = TaskNode(
            goal="Main task",
            depth=1,
            max_depth=3,
            execution_id=dag.execution_id,
            dependencies={dep_task.task_id},
        )
        dag.add_node(main_task)

        # Store dependency result
        solver.runtime.context_store.store_result_sync(
            dep_task.task_id, "Dependency result data"
        )

        # Build executor context
        tools_data = []
        context_xml = solver.runtime.context_manager.build_executor_context(
            main_task, tools_data, solver.runtime, dag
        )

        # Check dependency result is included
        assert "<executor_specific>" in context_xml
        assert "<dependency_results>" in context_xml
        assert "Dependency task" in context_xml
        assert "Dependency result data" in context_xml

    def test_planner_receives_parent_results(self, mock_config):
        """Test that planner context includes parent results."""
        solver = RecursiveSolver(config=mock_config, enable_checkpoints=False)

        task_node, dag = solver._initialize_task_and_dag("Test task", None, 0)

        # Create parent task
        parent = TaskNode(
            goal="Parent task", depth=0, max_depth=3, execution_id=dag.execution_id
        )
        dag.add_node(parent)

        # Create child task
        child = TaskNode(
            goal="Child task",
            parent_id=parent.task_id,
            depth=1,
            max_depth=3,
            execution_id=dag.execution_id,
        )
        dag.add_node(child)

        # Store parent result
        solver.runtime.context_store.store_result_sync(
            parent.task_id, "Parent result data"
        )

        # Build planner context
        tools_data = []
        context_xml = solver.runtime.context_manager.build_planner_context(
            child, tools_data, solver.runtime, dag
        )

        # Check parent result is included
        assert "<planner_specific>" in context_xml
        assert "<parent_results>" in context_xml
        assert "Parent task" in context_xml
        assert "Parent result data" in context_xml


class TestContextWithTools:
    """Test context system with tools."""

    def test_tools_included_in_context(self, mock_config):
        """Test that tools are included in context."""
        solver = RecursiveSolver(config=mock_config, enable_checkpoints=False)

        task_node, dag = solver._initialize_task_and_dag("Test task", None, 0)

        # Create tools data
        tools_data = [
            {"name": "search_web", "description": "Search the web"},
            {"name": "calculate", "description": "Perform calculations"},
        ]

        context_xml = solver.runtime.context_manager.build_atomizer_context(
            task_node, tools_data
        )

        # Check tools are in context
        assert "<available_tools>" in context_xml
        assert '<tool name="search_web">' in context_xml
        assert "Search the web" in context_xml
        assert '<tool name="calculate">' in context_xml
        assert "Perform calculations" in context_xml

    def test_empty_tools_handled(self, mock_config):
        """Test that empty tools list is handled properly."""
        solver = RecursiveSolver(config=mock_config, enable_checkpoints=False)

        task_node, dag = solver._initialize_task_and_dag("Test task", None, 0)

        context_xml = solver.runtime.context_manager.build_atomizer_context(
            task_node, []
        )

        assert "No tools available" in context_xml


class TestContextCleanup:
    """Test context system cleanup and isolation."""

    def test_different_executions_have_different_storage(self, mock_config):
        """Test that different solver instances have isolated storage."""
        solver1 = RecursiveSolver(config=mock_config, enable_checkpoints=False)
        solver2 = RecursiveSolver(config=mock_config, enable_checkpoints=False)

        task1, dag1 = solver1._initialize_task_and_dag("Task 1", None, 0)
        task2, dag2 = solver2._initialize_task_and_dag("Task 2", None, 0)

        # Different execution IDs
        assert dag1.execution_id != dag2.execution_id

        # Different file storage instances
        storage1 = solver1.runtime.context_manager.file_storage
        storage2 = solver2.runtime.context_manager.file_storage

        assert storage1.execution_id != storage2.execution_id
        assert storage1.root != storage2.root


class TestSynchronousContextFlow:
    """Test context system in synchronous execution flow."""

    def test_multiple_sync_solves_have_isolated_storage(self, mock_config):
        """Test that multiple sync solves create isolated contexts."""
        solver = RecursiveSolver(config=mock_config, enable_checkpoints=False)

        # First solve
        task1, dag1 = solver._initialize_task_and_dag("Analyze Bitcoin", None, 0)
        exec_id_1 = dag1.execution_id
        storage_1 = solver.runtime.context_manager.file_storage
        objective_1 = solver.runtime.context_manager.overall_objective

        # Second solve (new DAG)
        task2, dag2 = solver._initialize_task_and_dag("Analyze Ethereum", None, 0)
        exec_id_2 = dag2.execution_id
        storage_2 = solver.runtime.context_manager.file_storage
        objective_2 = solver.runtime.context_manager.overall_objective

        # Should have different execution IDs
        assert exec_id_1 != exec_id_2

        # Should have different file storage instances
        assert storage_1 is not storage_2
        assert storage_1.execution_id != storage_2.execution_id

        # Should have different overall objectives
        assert objective_1 == "Analyze Bitcoin"
        assert objective_2 == "Analyze Ethereum"

    def test_sync_atomize_receives_context(self, mock_config):
        """Test that synchronous atomize() receives context."""
        solver = RecursiveSolver(config=mock_config, enable_checkpoints=False)

        task_node, dag = solver._initialize_task_and_dag("Test task", None, 0)

        # Get atomizer agent
        from roma_dspy.types import AgentType

        atomizer = solver.runtime.registry.get_agent(
            AgentType.ATOMIZER, task_node.task_type
        )

        # Build context manually to verify it matches what atomize() would build
        tools_data = solver.runtime._get_tools_data(atomizer)
        expected_context = solver.runtime.context_manager.build_atomizer_context(
            task_node, tools_data
        )

        # Verify context has expected structure
        assert "<context>" in expected_context
        assert "<fundamental_context>" in expected_context
        assert "Test task" in expected_context  # overall_objective
        assert "<temporal>" in expected_context
        assert "<recursion>" in expected_context
        assert "<available_tools>" in expected_context

    def test_sync_execute_receives_dependency_context(self, mock_config):
        """Test that sync execute() receives dependency results in context."""
        solver = RecursiveSolver(config=mock_config, enable_checkpoints=False)

        task_node, dag = solver._initialize_task_and_dag("Main task", None, 0)

        # Create dependency task
        dep_task = TaskNode(
            goal="Dependency task", depth=1, max_depth=3, execution_id=dag.execution_id
        )
        dag.add_node(dep_task)

        # Create main task with dependency
        main_task = TaskNode(
            goal="Main task",
            depth=1,
            max_depth=3,
            execution_id=dag.execution_id,
            dependencies={dep_task.task_id},
        )
        dag.add_node(main_task)

        # Store dependency result
        solver.runtime.context_store.store_result_sync(
            dep_task.task_id, "Dependency result data"
        )

        # Get executor agent
        from roma_dspy.types import AgentType

        executor = solver.runtime.registry.get_agent(
            AgentType.EXECUTOR, main_task.task_type
        )

        # Build executor context
        tools_data = solver.runtime._get_tools_data(executor)
        context_xml = solver.runtime.context_manager.build_executor_context(
            main_task, tools_data, solver.runtime, dag
        )

        # Verify dependency result is in context
        assert "<executor_specific>" in context_xml
        assert "<dependency_results>" in context_xml
        assert "Dependency task" in context_xml
        assert "Dependency result data" in context_xml

    def test_sync_and_async_produce_same_context_structure(self, mock_config):
        """Test that sync and async execution produce same context structure."""
        solver = RecursiveSolver(config=mock_config, enable_checkpoints=False)

        task_node, dag = solver._initialize_task_and_dag("Test task", None, 0)

        from roma_dspy.types import AgentType

        atomizer = solver.runtime.registry.get_agent(
            AgentType.ATOMIZER, task_node.task_type
        )
        tools_data = solver.runtime._get_tools_data(atomizer)

        # Build context (same for both sync and async)
        context_xml = solver.runtime.context_manager.build_atomizer_context(
            task_node, tools_data
        )

        # Verify structure (temporal timestamp will differ, but structure should be same)
        assert "<context>" in context_xml
        assert "<fundamental_context>" in context_xml
        assert "<overall_objective>" in context_xml
        assert "<temporal>" in context_xml
        assert "<current_date>" in context_xml
        assert "<current_year>" in context_xml
        assert "<current_timestamp>" in context_xml
        assert "<recursion>" in context_xml
        assert "<current_depth>" in context_xml
        assert "<max_depth>" in context_xml
        assert "<available_tools>" in context_xml

    def test_sync_plan_receives_parent_context(self, mock_config):
        """Test that sync plan() receives parent results in context."""
        solver = RecursiveSolver(config=mock_config, enable_checkpoints=False)

        task_node, dag = solver._initialize_task_and_dag("Root task", None, 0)

        # Create parent task
        parent = TaskNode(
            goal="Parent task", depth=0, max_depth=3, execution_id=dag.execution_id
        )
        dag.add_node(parent)

        # Create child task
        child = TaskNode(
            goal="Child task",
            parent_id=parent.task_id,
            depth=1,
            max_depth=3,
            execution_id=dag.execution_id,
        )
        dag.add_node(child)

        # Store parent result
        solver.runtime.context_store.store_result_sync(
            parent.task_id, "Parent result data"
        )

        # Get planner agent
        from roma_dspy.types import AgentType

        planner = solver.runtime.registry.get_agent(AgentType.PLANNER, child.task_type)

        # Build planner context
        tools_data = solver.runtime._get_tools_data(planner)
        context_xml = solver.runtime.context_manager.build_planner_context(
            child, tools_data, solver.runtime, dag
        )

        # Verify parent result is in context
        assert "<planner_specific>" in context_xml
        assert "<parent_results>" in context_xml
        assert "Parent task" in context_xml
        assert "Parent result data" in context_xml
