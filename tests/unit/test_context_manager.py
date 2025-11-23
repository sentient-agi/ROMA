"""Unit tests for ContextManager."""

import pytest
from pathlib import Path
from unittest.mock import Mock, MagicMock

from roma_dspy.core.context.manager import ContextManager
from roma_dspy.core.storage import FileStorage
from roma_dspy.core.signatures import TaskNode
from roma_dspy.core.engine.dag import TaskDAG
from roma_dspy.types import TaskType


@pytest.fixture
def file_storage():
    """Create a FileStorage instance for testing."""
    return FileStorage(execution_id="test_exec_123")


@pytest.fixture
def context_manager(file_storage):
    """Create a ContextManager instance for testing."""
    return ContextManager(
        file_storage=file_storage, overall_objective="Analyze Bitcoin market trends"
    )


@pytest.fixture
def task_node():
    """Create a TaskNode for testing."""
    return TaskNode(
        goal="Fetch Bitcoin price data",
        depth=1,
        max_depth=3,
        execution_id="test_exec_123",
    )


@pytest.fixture
def dag():
    """Create a DAG for testing."""
    return TaskDAG(execution_id="test_exec_123")


@pytest.fixture
def tools_data():
    """Create tools data for testing."""
    return [
        {"name": "search_web", "description": "Search the web for information"},
        {"name": "calculate", "description": "Perform calculations"},
    ]


@pytest.fixture
def mock_runtime():
    """Create a mock ModuleRuntime for testing."""
    runtime = Mock()
    runtime.context_store = Mock()
    runtime.context_store.get_result = Mock(return_value=None)
    return runtime


class TestContextManagerInitialization:
    """Test ContextManager initialization."""

    def test_create_context_manager(self, file_storage):
        """Test creating ContextManager."""
        manager = ContextManager(
            file_storage=file_storage, overall_objective="Test objective"
        )

        assert manager.file_storage == file_storage
        assert manager.overall_objective == "Test objective"

    def test_context_manager_stores_execution_info(self, context_manager, file_storage):
        """Test that ContextManager has access to execution info."""
        assert context_manager.file_storage.execution_id == "test_exec_123"


class TestAtomizerContext:
    """Test atomizer context building."""

    def test_build_atomizer_context(self, context_manager, task_node, tools_data):
        """Test building atomizer context."""
        context_xml = context_manager.build_atomizer_context(task_node, tools_data)

        # Check structure
        assert "<context>" in context_xml
        assert "</context>" in context_xml
        assert "<fundamental_context>" in context_xml

        # Check fundamental components
        assert "Analyze Bitcoin market trends" in context_xml  # overall_objective
        assert "<temporal>" in context_xml
        assert "<recursion>" in context_xml
        assert "<current_depth>1</current_depth>" in context_xml
        assert "<max_depth>3</max_depth>" in context_xml
        assert "<available_tools>" in context_xml
        assert "search_web" in context_xml
        assert "calculate" in context_xml

        # Atomizer should NOT have file_system
        assert "<file_system" not in context_xml

    def test_atomizer_context_with_empty_tools(self, context_manager, task_node):
        """Test atomizer context with no tools."""
        context_xml = context_manager.build_atomizer_context(task_node, [])

        assert "No tools available" in context_xml

    def test_atomizer_context_at_max_depth(self, context_manager, tools_data):
        """Test atomizer context when at max depth."""
        task = TaskNode(
            goal="Test task", depth=3, max_depth=3, execution_id="test_exec_123"
        )

        context_xml = context_manager.build_atomizer_context(task, tools_data)

        assert "<current_depth>3</current_depth>" in context_xml
        assert "<max_depth>3</max_depth>" in context_xml
        assert "<at_limit>true</at_limit>" in context_xml


class TestPlannerContext:
    """Test planner context building."""

    def test_build_planner_context_no_parent(
        self, context_manager, task_node, tools_data, mock_runtime, dag
    ):
        """Test building planner context with no parent."""
        dag.add_node(task_node)

        context_xml = context_manager.build_planner_context(
            task_node, tools_data, mock_runtime, dag
        )

        # Check fundamental context
        assert "<fundamental_context>" in context_xml
        assert "Analyze Bitcoin market trends" in context_xml

        # Check planner-specific context
        assert "<planner_specific>" in context_xml

    def test_build_planner_context_with_parent(
        self, context_manager, tools_data, mock_runtime, dag
    ):
        """Test building planner context with parent result."""
        # Create parent task
        parent = TaskNode(
            goal="Parent task", depth=0, max_depth=3, execution_id="test_exec_123"
        )
        dag.add_node(parent)

        # Create child task
        child = TaskNode(
            goal="Child task",
            parent_id=parent.task_id,
            depth=1,
            max_depth=3,
            execution_id="test_exec_123",
        )
        dag.add_node(child)

        # Mock parent result
        mock_runtime.context_store.get_result.return_value = "Parent result data"

        context_xml = context_manager.build_planner_context(
            child, tools_data, mock_runtime, dag
        )

        assert "<planner_specific>" in context_xml
        assert "<parent_results>" in context_xml
        assert "Parent task" in context_xml
        assert "Parent result data" in context_xml

    def test_planner_context_no_file_system(
        self, context_manager, task_node, tools_data, mock_runtime, dag
    ):
        """Test that planner context does not include file_system."""
        dag.add_node(task_node)

        context_xml = context_manager.build_planner_context(
            task_node, tools_data, mock_runtime, dag
        )

        assert "<file_system" not in context_xml


class TestExecutorContext:
    """Test executor context building."""

    def test_build_executor_context_no_dependencies(
        self, context_manager, task_node, tools_data, mock_runtime, dag
    ):
        """Test building executor context with no dependencies."""
        dag.add_node(task_node)

        context_xml = context_manager.build_executor_context(
            task_node, tools_data, mock_runtime, dag
        )

        # Check fundamental context
        assert "<fundamental_context>" in context_xml
        assert "Analyze Bitcoin market trends" in context_xml

        # Check file_system is included for executor
        assert "<file_system" in context_xml
        assert "test_exec_123" in context_xml

        # Check executor-specific context
        assert "<executor_specific>" in context_xml
        assert "No dependencies" in context_xml

    def test_build_executor_context_with_dependencies(
        self, context_manager, tools_data, mock_runtime, dag
    ):
        """Test building executor context with dependency results."""
        # Create dependency task
        dep_task = TaskNode(
            goal="Dependency task", depth=1, max_depth=3, execution_id="test_exec_123"
        )
        dag.add_node(dep_task)

        # Create main task with dependency
        main_task = TaskNode(
            goal="Main task",
            depth=1,
            max_depth=3,
            execution_id="test_exec_123",
            dependencies={dep_task.task_id},
        )
        dag.add_node(main_task)

        # Mock dependency result
        def mock_get_result(task_id):
            if task_id == dep_task.task_id:
                return "Dependency result data"
            return None

        mock_runtime.context_store.get_result.side_effect = mock_get_result

        context_xml = context_manager.build_executor_context(
            main_task, tools_data, mock_runtime, dag
        )

        assert "<executor_specific>" in context_xml
        assert "<dependency_results>" in context_xml
        assert "Dependency task" in context_xml
        assert "Dependency result data" in context_xml

    def test_executor_context_includes_file_system(
        self, context_manager, task_node, tools_data, mock_runtime, dag
    ):
        """Test that executor context includes file_system."""
        dag.add_node(task_node)

        context_xml = context_manager.build_executor_context(
            task_node, tools_data, mock_runtime, dag
        )

        assert "<file_system" in context_xml
        assert 'execution_id="test_exec_123"' in context_xml
        assert "FileStorage methods" in context_xml


class TestAggregatorContext:
    """Test aggregator context building."""

    def test_build_aggregator_context(self, context_manager, task_node, tools_data):
        """Test building aggregator context."""
        context_xml = context_manager.build_aggregator_context(task_node, tools_data)

        # Check fundamental context
        assert "<fundamental_context>" in context_xml
        assert "Analyze Bitcoin market trends" in context_xml

        # Check aggregator-specific note
        assert "<aggregator_specific>" in context_xml
        assert "Child results are provided in subtasks_results field" in context_xml

        # Should NOT have file_system
        assert "<file_system" not in context_xml


class TestVerifierContext:
    """Test verifier context building."""

    def test_build_verifier_context(self, context_manager, task_node, tools_data):
        """Test building verifier context."""
        context_xml = context_manager.build_verifier_context(task_node, tools_data)

        # Check fundamental context
        assert "<fundamental_context>" in context_xml
        assert "Analyze Bitcoin market trends" in context_xml

        # Verifier has only fundamental context, no specific context
        # Should NOT have file_system
        assert "<file_system" not in context_xml


class TestContextBuilderDRY:
    """Test that context builders follow DRY principle."""

    def test_all_contexts_share_fundamental(
        self, context_manager, task_node, tools_data, mock_runtime, dag
    ):
        """Test that all agent contexts include fundamental context."""
        dag.add_node(task_node)

        contexts = {
            "atomizer": context_manager.build_atomizer_context(task_node, tools_data),
            "planner": context_manager.build_planner_context(
                task_node, tools_data, mock_runtime, dag
            ),
            "executor": context_manager.build_executor_context(
                task_node, tools_data, mock_runtime, dag
            ),
            "aggregator": context_manager.build_aggregator_context(
                task_node, tools_data
            ),
            "verifier": context_manager.build_verifier_context(task_node, tools_data),
        }

        for agent_type, context_xml in contexts.items():
            # All should have fundamental context
            assert "<fundamental_context>" in context_xml, (
                f"{agent_type} missing fundamental context"
            )
            assert "Analyze Bitcoin market trends" in context_xml
            assert "<temporal>" in context_xml
            assert "<recursion>" in context_xml
            assert "<available_tools>" in context_xml

    def test_only_executor_has_file_system(
        self, context_manager, task_node, tools_data, mock_runtime, dag
    ):
        """Test that only executor context includes file_system."""
        dag.add_node(task_node)

        contexts = {
            "atomizer": context_manager.build_atomizer_context(task_node, tools_data),
            "planner": context_manager.build_planner_context(
                task_node, tools_data, mock_runtime, dag
            ),
            "executor": context_manager.build_executor_context(
                task_node, tools_data, mock_runtime, dag
            ),
            "aggregator": context_manager.build_aggregator_context(
                task_node, tools_data
            ),
            "verifier": context_manager.build_verifier_context(task_node, tools_data),
        }

        # Only executor should have file_system
        assert "<file_system" not in contexts["atomizer"]
        assert "<file_system" not in contexts["planner"]
        assert "<file_system" in contexts["executor"]
        assert "<file_system" not in contexts["aggregator"]
        assert "<file_system" not in contexts["verifier"]


class TestXMLEscaping:
    """Test XML escaping in context building."""

    def test_special_characters_in_objective(self, file_storage, task_node, tools_data):
        """Test that special XML characters are escaped in overall_objective."""
        manager = ContextManager(
            file_storage=file_storage,
            overall_objective="Test with <tags> & \"quotes\" and 'apostrophes'",
        )

        context_xml = manager.build_atomizer_context(task_node, tools_data)

        # Characters should be escaped
        assert "&lt;tags&gt;" in context_xml
        assert "&amp;" in context_xml
        assert "&quot;" in context_xml
        assert "&apos;" in context_xml

        # Raw characters should not appear
        assert "<tags>" not in context_xml

    def test_special_characters_in_tool_descriptions(self, context_manager, task_node):
        """Test XML escaping in tool descriptions."""
        tools_data = [
            {"name": "test_tool", "description": "Description with <special> & chars"}
        ]

        context_xml = context_manager.build_atomizer_context(task_node, tools_data)

        assert "&lt;special&gt;" in context_xml
        assert "&amp;" in context_xml
