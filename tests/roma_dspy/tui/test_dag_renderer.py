"""Tests for DAG ASCII renderer.

This module tests the renderer's ability to convert positioned DAG
nodes and edges into ASCII art visualization.
"""

from __future__ import annotations

import pytest
from rich.text import Text

from roma_dspy.tui.models import DAGEdge, DAGViewModel, TaskViewModel
from roma_dspy.tui.rendering.dag_layout import Position
from roma_dspy.tui.rendering.dag_renderer import (
    DAGRenderer,
    render_dag_ascii,
    render_dag_rich,
)
from roma_dspy.types import EdgeType


class TestDAGRenderer:
    """Test DAG ASCII renderer."""

    def _create_test_dag(self) -> DAGViewModel:
        """Create a simple test DAG."""
        nodes = {
            "task1": TaskViewModel(
                task_id="task1",
                goal="Task 1",
                status="completed",
                module="TestModule",
                total_duration=1.5,
                total_cost=0.05,
            ),
            "task2": TaskViewModel(
                task_id="task2",
                goal="Task 2",
                status="running",
                module="TestModule",
                total_duration=0.5,
                total_cost=0.02,
            ),
        }

        edges = [DAGEdge("task1", "task2", EdgeType.DEPENDENCY)]

        return DAGViewModel(
            nodes=nodes,
            edges=edges,
            execution_id="test",
            total_nodes=2,
            total_edges=1,
        )

    def _create_test_positions(self) -> dict[str, Position]:
        """Create test node positions."""
        return {
            "task1": Position(0.0, 0.0),
            "task2": Position(0.0, 2.0),
        }

    def test_renderer_initialization(self):
        """Test DAGRenderer initialization."""
        dag = self._create_test_dag()
        positions = self._create_test_positions()

        renderer = DAGRenderer(dag, positions, cell_width=20, cell_height=3)

        assert renderer.dag == dag
        assert renderer.positions == positions
        assert renderer.cell_width == 20
        assert renderer.cell_height == 3

    def test_ascii_rendering(self):
        """Test ASCII art rendering."""
        dag = self._create_test_dag()
        positions = self._create_test_positions()

        renderer = DAGRenderer(dag, positions)
        output = renderer.render()

        # Verify output is a string
        assert isinstance(output, str)
        assert len(output) > 0

        # Verify contains box drawing characters
        assert any(char in output for char in ["─", "│", "┌", "┐", "└", "┘"])

    def test_rich_rendering(self):
        """Test Rich formatted rendering."""
        dag = self._create_test_dag()
        positions = self._create_test_positions()

        renderer = DAGRenderer(dag, positions, colorize=True)
        output = renderer.render_rich()

        # Verify output is Rich Text
        assert isinstance(output, Text)

    def test_status_icons(self):
        """Test status icon rendering."""
        dag = self._create_test_dag()
        positions = self._create_test_positions()

        renderer = DAGRenderer(dag, positions)
        output = renderer.render()

        # Should contain status icons for completed and running
        assert "●" in output or "◐" in output

    def test_metrics_display(self):
        """Test metrics display in nodes."""
        dag = self._create_test_dag()
        positions = self._create_test_positions()

        renderer = DAGRenderer(dag, positions, show_metrics=True)
        output = renderer.render()

        # Should contain duration and cost indicators
        assert "s" in output  # seconds
        assert "$" in output  # cost

    def test_no_metrics_display(self):
        """Test rendering without metrics."""
        dag = self._create_test_dag()
        positions = self._create_test_positions()

        renderer = DAGRenderer(dag, positions, show_metrics=False)
        # Should still render without errors
        output = renderer.render()
        assert isinstance(output, str)

    def test_empty_dag_rendering(self):
        """Test rendering of empty DAG."""
        dag = DAGViewModel(
            nodes={},
            edges=[],
            execution_id="test",
            total_nodes=0,
            total_edges=0,
        )

        renderer = DAGRenderer(dag, {})
        output = renderer.render()

        assert "No layout" in output

    def test_edge_rendering(self):
        """Test edge line rendering."""
        dag = self._create_test_dag()
        positions = self._create_test_positions()

        renderer = DAGRenderer(dag, positions)
        output = renderer.render()

        # Should contain edge characters
        assert "→" in output or "─" in output

    def test_render_dag_ascii_convenience(self):
        """Test render_dag_ascii convenience function."""
        dag = self._create_test_dag()
        positions = self._create_test_positions()

        output = render_dag_ascii(dag, positions)

        assert isinstance(output, str)
        assert len(output) > 0

    def test_render_dag_rich_convenience(self):
        """Test render_dag_rich convenience function."""
        dag = self._create_test_dag()
        positions = self._create_test_positions()

        output = render_dag_rich(dag, positions)

        assert isinstance(output, Text)

    def test_cell_sizing(self):
        """Test different cell sizes."""
        dag = self._create_test_dag()
        positions = self._create_test_positions()

        # Small cells
        renderer_small = DAGRenderer(dag, positions, cell_width=10, cell_height=2)
        output_small = renderer_small.render()
        assert isinstance(output_small, str)

        # Large cells
        renderer_large = DAGRenderer(dag, positions, cell_width=30, cell_height=5)
        output_large = renderer_large.render()
        assert isinstance(output_large, str)

        # Large output should be larger than small
        assert len(output_large) > len(output_small)
