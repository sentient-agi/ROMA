"""Tests for DAG visualization modal.

This module tests the DAG modal's filtering, interaction,
and state management functionality.
"""

from __future__ import annotations

import pytest

from roma_dspy.tui.models import DAGViewModel, TaskViewModel
from roma_dspy.tui.screens.dag_modal import DAGModal
from roma_dspy.types import EdgeType


class TestDAGModal:
    """Test DAG modal functionality."""

    def _create_test_dag(self) -> DAGViewModel:
        """Create a test DAG with various node types."""
        nodes = {
            "task1": TaskViewModel(
                task_id="task1",
                goal="Task 1",
                status="completed",
                module="TestModule",
            ),
            "task2": TaskViewModel(
                task_id="task2",
                goal="Task 2",
                status="running",
                module="TestModule",
            ),
            "task3": TaskViewModel(
                task_id="task3",
                goal="Task 3",
                status="pending",
                module="TestModule",
                dependencies=["task2"],
            ),
        }

        return DAGViewModel(
            nodes=nodes,
            edges=[],
            critical_path=["task1", "task2"],
            blocked_tasks=["task3"],
            ready_tasks=[],
            execution_id="test",
            total_nodes=3,
            total_edges=0,
        )

    def test_modal_initialization(self):
        """Test DAGModal initialization."""
        dag = self._create_test_dag()
        modal = DAGModal(dag)

        assert modal.dag == dag
        assert modal.layout_algorithm == "hierarchical"
        assert modal.cell_width == 20
        assert modal.cell_height == 4

    def test_default_enabled_edges(self):
        """Test default enabled edge types."""
        dag = self._create_test_dag()
        modal = DAGModal(dag)

        assert EdgeType.DEPENDENCY in modal.enabled_edges
        assert EdgeType.DATA_FLOW in modal.enabled_edges
        assert EdgeType.CONTROL_FLOW in modal.enabled_edges

    def test_filter_initialization(self):
        """Test filter state initialization."""
        dag = self._create_test_dag()
        modal = DAGModal(dag)

        assert modal.status_filter is None
        assert modal.module_filter is None
        assert modal.depth_filter is None
        assert modal.show_only_critical_path is False
        assert modal.show_only_blocked is False
        assert modal.show_only_ready is False

    def test_replay_state_initialization(self):
        """Test replay state initialization."""
        dag = self._create_test_dag()
        modal = DAGModal(dag)

        assert modal.replay_mode is False
        assert modal.replay_time == 0.0
        assert modal.replay_speed == 1.0

    def test_apply_status_filter(self):
        """Test status filtering."""
        dag = self._create_test_dag()
        modal = DAGModal(dag)

        # Apply completed filter
        modal.status_filter = {"completed"}
        filtered_nodes = modal._apply_node_filters(dag.nodes)

        assert len(filtered_nodes) == 1
        assert "task1" in filtered_nodes

    def test_apply_critical_path_filter(self):
        """Test critical path filtering."""
        dag = self._create_test_dag()
        modal = DAGModal(dag)

        modal.show_only_critical_path = True
        filtered_nodes = modal._apply_node_filters(dag.nodes)

        assert len(filtered_nodes) == 2
        assert "task1" in filtered_nodes
        assert "task2" in filtered_nodes

    def test_apply_blocked_filter(self):
        """Test blocked tasks filtering."""
        dag = self._create_test_dag()
        modal = DAGModal(dag)

        modal.show_only_blocked = True
        filtered_nodes = modal._apply_node_filters(dag.nodes)

        assert len(filtered_nodes) == 1
        assert "task3" in filtered_nodes

    def test_multiple_filters(self):
        """Test applying multiple filters together."""
        dag = self._create_test_dag()
        modal = DAGModal(dag)

        # Apply both status and module filters
        modal.status_filter = {"completed", "running"}
        modal.module_filter = {"TestModule"}
        filtered_nodes = modal._apply_node_filters(dag.nodes)

        assert len(filtered_nodes) == 2
        assert "task1" in filtered_nodes
        assert "task2" in filtered_nodes

    def test_no_filters_returns_all_nodes(self):
        """Test that no filters returns all nodes."""
        dag = self._create_test_dag()
        modal = DAGModal(dag)

        filtered_nodes = modal._apply_node_filters(dag.nodes)

        assert len(filtered_nodes) == 3

    def test_edge_filtering(self):
        """Test edge type filtering."""
        dag = self._create_test_dag()
        modal = DAGModal(dag)

        # Remove dependency edges
        modal.enabled_edges.remove(EdgeType.DEPENDENCY)

        filtered_dag = modal._filter_dag_by_edges()

        # Should only have edges of enabled types
        for edge in filtered_dag.edges:
            assert edge.edge_type in modal.enabled_edges

    def test_zoom_constraints(self):
        """Test zoom level constraints."""
        dag = self._create_test_dag()
        modal = DAGModal(dag)

        # Test minimum zoom
        modal.cell_width = 5
        modal.cell_height = 1
        # Zoom out would normally go below minimum
        modal.action_zoom_out()
        assert modal.cell_width >= 10
        assert modal.cell_height >= 2

        # Test maximum zoom
        modal.cell_width = 38
        modal.cell_height = 7
        # Zoom in would normally go above maximum
        modal.action_zoom_in()
        assert modal.cell_width <= 40
        assert modal.cell_height <= 8


class TestDAGModalFiltering:
    """Test advanced filtering logic."""

    def test_exclusive_path_filters(self):
        """Test mutual exclusivity of path filters."""
        dag = DAGViewModel(
            nodes={},
            edges=[],
            critical_path=[],
            blocked_tasks=[],
            ready_tasks=[],
            execution_id="test",
            total_nodes=0,
            total_edges=0,
        )

        modal = DAGModal(dag)

        # Enable critical path
        modal.show_only_critical_path = True
        modal.action_highlight_critical_path()

        # Enable blocked (should disable critical path)
        modal.show_only_blocked = True
        if modal.show_only_blocked:
            modal.show_only_critical_path = False
            modal.show_only_ready = False

        assert modal.show_only_blocked is True
        assert modal.show_only_critical_path is False

    def test_depth_filter(self):
        """Test depth-based filtering."""
        nodes = {
            "root": TaskViewModel(task_id="root", goal="Root", depth=0),
            "child": TaskViewModel(task_id="child", goal="Child", depth=1),
            "grandchild": TaskViewModel(
                task_id="grandchild", goal="Grandchild", depth=2
            ),
        }

        dag = DAGViewModel(
            nodes=nodes,
            edges=[],
            execution_id="test",
            total_nodes=3,
            total_edges=0,
        )

        modal = DAGModal(dag)
        modal.depth_filter = 1

        filtered_nodes = modal._apply_node_filters(dag.nodes)

        assert len(filtered_nodes) == 1
        assert "child" in filtered_nodes
