"""Tests for DAG data extraction from execution state.

This module tests the transformer's ability to extract DAG structures
from execution checkpoints, including nodes, edges, and graph metrics.
"""

from __future__ import annotations

import pytest

from roma_dspy.tui.models import DAGViewModel, TaskViewModel
from roma_dspy.tui.transformer import DataTransformer
from roma_dspy.types import EdgeType


class TestDAGExtraction:
    """Test DAG extraction from execution state."""

    def _create_checkpoint_data(self, tasks, execution_id="test_exec"):
        """Helper to create checkpoint data structure with DAG dependencies."""
        dependencies = {}
        for task_id, task in tasks.items():
            if task.dependencies:
                dependencies[task_id] = task.dependencies

        return {
            "execution_id": execution_id,
            "dag": {
                "dag_id": f"dag_{execution_id}",
                "dependencies": dependencies,
            }
        }

    def test_simple_linear_dag(self):
        """Test extraction of simple linear DAG."""
        tasks = {
            "task1": TaskViewModel(
                task_id="task1",
                goal="Task 1",
                status="completed",
                dependencies=[],
                dependents=["task2"],
            ),
            "task2": TaskViewModel(
                task_id="task2",
                goal="Task 2",
                status="completed",
                dependencies=["task1"],
                dependents=[],
            ),
        }

        checkpoint_data = self._create_checkpoint_data(tasks)
        transformer = DataTransformer()
        dag = transformer._build_dag_view_model(checkpoint_data, tasks)

        assert len(dag.nodes) == 2
        assert len(dag.edges) >= 1
        assert dag.total_nodes == 2

    def test_parallel_dag_structure(self):
        """Test extraction of DAG with parallel branches."""
        tasks = {
            "root": TaskViewModel(
                task_id="root",
                goal="Root",
                status="completed",
                dependencies=[],
                dependents=["branch1", "branch2"],
            ),
            "branch1": TaskViewModel(
                task_id="branch1",
                goal="Branch 1",
                status="completed",
                dependencies=["root"],
                dependents=["merge"],
            ),
            "branch2": TaskViewModel(
                task_id="branch2",
                goal="Branch 2",
                status="completed",
                dependencies=["root"],
                dependents=["merge"],
            ),
            "merge": TaskViewModel(
                task_id="merge",
                goal="Merge",
                status="completed",
                dependencies=["branch1", "branch2"],
                dependents=[],
            ),
        }

        checkpoint_data = self._create_checkpoint_data(tasks)
        transformer = DataTransformer()
        dag = transformer._build_dag_view_model(checkpoint_data, tasks)

        assert len(dag.nodes) == 4
        assert len(dag.parallel_clusters) > 0

    def test_subgraph_extraction_for_planning_nodes(self):
        """Test subgraph extraction for planning nodes with subtasks."""
        parent = TaskViewModel(
            task_id="parent",
            goal="Parent Task",
            status="completed",
            node_type="PLAN",
            subtask_ids=["child1", "child2"],
        )

        child1 = TaskViewModel(
            task_id="child1",
            goal="Child 1",
            status="completed",
            parent_task_id="parent",
        )

        child2 = TaskViewModel(
            task_id="child2",
            goal="Child 2",
            status="completed",
            parent_task_id="parent",
        )

        tasks = {"parent": parent, "child1": child1, "child2": child2}

        checkpoint_data = self._create_checkpoint_data(tasks)
        transformer = DataTransformer()
        dag = transformer._build_dag_view_model(checkpoint_data, tasks)

        assert "parent" in dag.subgraphs
        subgraph = dag.subgraphs["parent"]
        assert len(subgraph.nodes) == 2

    def test_blocked_tasks_detection(self):
        """Test detection of tasks blocked by dependencies."""
        tasks = {
            "running": TaskViewModel(
                task_id="running",
                goal="Running task",
                status="running",
                dependencies=[],
                dependents=["blocked"],
            ),
            "blocked": TaskViewModel(
                task_id="blocked",
                goal="Blocked task",
                status="pending",
                dependencies=["running"],
                dependents=[],
            ),
        }

        checkpoint_data = self._create_checkpoint_data(tasks)
        transformer = DataTransformer()
        dag = transformer._build_dag_view_model(checkpoint_data, tasks)

        assert "blocked" in dag.blocked_tasks

    def test_ready_tasks_detection(self):
        """Test detection of tasks ready to execute."""
        tasks = {
            "ready": TaskViewModel(
                task_id="ready",
                goal="Ready task",
                status="pending",
                dependencies=[],
                dependents=[],
            ),
        }

        checkpoint_data = self._create_checkpoint_data(tasks)
        transformer = DataTransformer()
        dag = transformer._build_dag_view_model(checkpoint_data, tasks)

        assert "ready" in dag.ready_tasks

    def test_empty_dag_handling(self):
        """Test handling of empty task dictionary."""
        checkpoint_data = self._create_checkpoint_data({})
        transformer = DataTransformer()
        dag = transformer._build_dag_view_model(checkpoint_data, {})

        assert len(dag.nodes) == 0
        assert len(dag.edges) == 0
        # Empty DAG has parallelism factor of 1.0 (0 tasks / 0 critical path = fallback to 1.0)
        assert dag.parallelism_factor == 1.0

    def test_dag_metrics_computation(self):
        """Test computation of DAG metrics."""
        tasks = {
            "task1": TaskViewModel(
                task_id="task1",
                goal="Task 1",
                status="completed",
                depth=0,
                total_duration=1.5,
            ),
            "task2": TaskViewModel(
                task_id="task2",
                goal="Task 2",
                status="completed",
                depth=1,
                total_duration=2.0,
            ),
        }

        checkpoint_data = self._create_checkpoint_data(tasks)
        transformer = DataTransformer()
        dag = transformer._build_dag_view_model(checkpoint_data, tasks)

        assert dag.total_nodes == 2
        assert dag.max_depth >= 0
        assert dag.parallelism_factor >= 0.0