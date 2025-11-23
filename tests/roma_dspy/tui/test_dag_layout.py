"""Tests for DAG layout algorithms.

This module tests the layout engine's ability to position nodes
in a DAG for visualization using various algorithms.
"""

from __future__ import annotations

import pytest

from roma_dspy.tui.models import DAGEdge, DAGViewModel, TaskViewModel
from roma_dspy.tui.rendering.dag_layout import (
    DAGLayoutEngine,
    Position,
    compute_layout,
)
from roma_dspy.types import EdgeType


class TestDAGLayoutEngine:
    """Test DAG layout engine algorithms."""

    def _create_simple_dag(self) -> DAGViewModel:
        """Create a simple linear DAG for testing."""
        nodes = {
            "task1": TaskViewModel(task_id="task1", goal="Task 1", status="completed"),
            "task2": TaskViewModel(task_id="task2", goal="Task 2", status="completed"),
            "task3": TaskViewModel(task_id="task3", goal="Task 3", status="completed"),
        }

        edges = [
            DAGEdge("task1", "task2", EdgeType.DEPENDENCY),
            DAGEdge("task2", "task3", EdgeType.DEPENDENCY),
        ]

        return DAGViewModel(
            nodes=nodes,
            edges=edges,
            execution_id="test",
            total_nodes=3,
            total_edges=2,
        )

    def _create_parallel_dag(self) -> DAGViewModel:
        """Create a DAG with parallel branches."""
        nodes = {
            "root": TaskViewModel(task_id="root", goal="Root", status="completed"),
            "branch1": TaskViewModel(
                task_id="branch1", goal="Branch 1", status="completed"
            ),
            "branch2": TaskViewModel(
                task_id="branch2", goal="Branch 2", status="completed"
            ),
            "merge": TaskViewModel(task_id="merge", goal="Merge", status="completed"),
        }

        edges = [
            DAGEdge("root", "branch1", EdgeType.DEPENDENCY),
            DAGEdge("root", "branch2", EdgeType.DEPENDENCY),
            DAGEdge("branch1", "merge", EdgeType.DEPENDENCY),
            DAGEdge("branch2", "merge", EdgeType.DEPENDENCY),
        ]

        return DAGViewModel(
            nodes=nodes,
            edges=edges,
            execution_id="test",
            total_nodes=4,
            total_edges=4,
        )

    def test_hierarchical_layout(self):
        """Test hierarchical layout algorithm."""
        dag = self._create_simple_dag()
        engine = DAGLayoutEngine(dag)

        positions = engine.compute_hierarchical_layout(spacing_x=1.0, spacing_y=1.0)

        # Verify all nodes positioned
        assert len(positions) == 3
        assert "task1" in positions
        assert "task2" in positions
        assert "task3" in positions

        # Verify positions are Position objects
        assert isinstance(positions["task1"], Position)

        # Verify vertical ordering (task1 should be above task2, etc.)
        assert positions["task1"].y < positions["task2"].y
        assert positions["task2"].y < positions["task3"].y

    def test_topological_layout(self):
        """Test topological layout algorithm."""
        dag = self._create_simple_dag()
        engine = DAGLayoutEngine(dag)

        positions = engine.compute_topological_layout(spacing_x=2.0, spacing_y=1.0)

        # Verify all nodes positioned
        assert len(positions) == 3

        # Verify horizontal ordering
        assert positions["task1"].x < positions["task2"].x
        assert positions["task2"].x < positions["task3"].x

    def test_compact_layout(self):
        """Test compact layout algorithm."""
        dag = self._create_simple_dag()
        engine = DAGLayoutEngine(dag)

        positions = engine.compute_compact_layout(max_width=2)

        # Verify all nodes positioned
        assert len(positions) == 3

        # Verify positions fit within max_width constraint
        for pos in positions.values():
            assert pos.x < 2 * 1.5  # max_width * spacing

    def test_parallel_dag_layout(self):
        """Test layout of parallel DAG structure."""
        dag = self._create_parallel_dag()
        engine = DAGLayoutEngine(dag)

        positions = engine.compute_hierarchical_layout()

        # Verify all nodes positioned
        assert len(positions) == 4

        # Branch nodes should be at same level (y coordinate)
        assert positions["branch1"].y == positions["branch2"].y

        # Root should be above branches
        assert positions["root"].y < positions["branch1"].y

        # Merge should be below branches
        assert positions["merge"].y > positions["branch1"].y

    def test_edge_routing(self):
        """Test edge path computation."""
        dag = self._create_simple_dag()
        engine = DAGLayoutEngine(dag)

        engine.compute_hierarchical_layout()
        edge_paths = engine.route_edges()

        # Verify edge paths created
        assert len(edge_paths) == 2

        # Verify each path has from/to positions
        for path in edge_paths:
            assert path.from_pos is not None
            assert path.to_pos is not None
            assert path.edge_type is not None

    def test_bounding_box(self):
        """Test bounding box computation."""
        dag = self._create_simple_dag()
        engine = DAGLayoutEngine(dag)

        engine.compute_hierarchical_layout()
        min_pos, max_pos = engine.get_bounding_box()

        # Verify bounding box
        assert isinstance(min_pos, Position)
        assert isinstance(max_pos, Position)
        assert min_pos.x <= max_pos.x
        assert min_pos.y <= max_pos.y

    def test_normalize_positions(self):
        """Test position normalization."""
        dag = self._create_simple_dag()
        engine = DAGLayoutEngine(dag)

        engine.compute_hierarchical_layout()
        engine.normalize_positions(margin=1.0)

        # All positions should be >= margin
        for pos in engine.positions.values():
            assert pos.x >= 1.0
            assert pos.y >= 1.0

    def test_empty_dag_layout(self):
        """Test layout of empty DAG."""
        dag = DAGViewModel(
            nodes={},
            edges=[],
            execution_id="test",
            total_nodes=0,
            total_edges=0,
        )

        engine = DAGLayoutEngine(dag)
        positions = engine.compute_hierarchical_layout()

        # Should return empty positions
        assert len(positions) == 0

    def test_compute_layout_convenience_function(self):
        """Test compute_layout convenience function."""
        dag = self._create_simple_dag()

        # Test hierarchical
        positions = compute_layout(dag, algorithm="hierarchical")
        assert len(positions) == 3

        # Test topological
        positions = compute_layout(dag, algorithm="topological")
        assert len(positions) == 3

        # Test compact
        positions = compute_layout(dag, algorithm="compact")
        assert len(positions) == 3

        # Test unknown algorithm (should fall back to hierarchical)
        positions = compute_layout(dag, algorithm="unknown")
        assert len(positions) == 3


class TestPosition:
    """Test Position class."""

    def test_position_creation(self):
        """Test Position object creation."""
        pos = Position(1.5, 2.5)
        assert pos.x == 1.5
        assert pos.y == 2.5

    def test_position_to_grid(self):
        """Test conversion to grid coordinates."""
        pos = Position(1.5, 2.5)
        grid_x, grid_y = pos.to_grid(cell_width=4, cell_height=2)

        assert grid_x == 6  # 1.5 * 4
        assert grid_y == 5  # 2.5 * 2

    def test_position_repr(self):
        """Test string representation."""
        pos = Position(1.0, 2.0)
        repr_str = repr(pos)
        assert "Position" in repr_str
        assert "1.0" in repr_str
        assert "2.0" in repr_str
