"""Lightweight trace formatter for inline execution visualization.

This module provides simple trace formatting for RecursiveSolver predictions,
separate from the deprecated LLMTraceVisualizer class.
"""

from typing import Any, Optional
from roma_dspy.core.engine.dag import TaskDAG
from roma_dspy.core.signatures import TaskNode


def format_solver_trace(solver: Any) -> str:
    """
    Format a simple trace from RecursiveSolver for DSPy prediction output.

    Args:
        solver: RecursiveSolver instance with last_dag attribute

    Returns:
        Formatted trace string showing task hierarchy and results
    """
    dag = getattr(solver, "last_dag", None)
    if not dag:
        return "No trace available"

    lines = []
    lines.append("=" * 80)
    lines.append("EXECUTION TRACE")
    lines.append("=" * 80)

    # Get root task
    root_task = None
    if hasattr(dag, "graph"):
        for node_id in dag.graph.nodes():
            candidate = dag.get_node(node_id)
            if candidate and getattr(candidate, "is_root", False):
                root_task = candidate
                break

    if root_task:
        _format_task_tree(root_task, dag, lines, indent=0)
    else:
        lines.append("No root task found")

    lines.append("=" * 80)
    return "\n".join(lines)


def _format_task_tree(
    task: TaskNode, dag: TaskDAG, lines: list, indent: int = 0
) -> None:
    """Recursively format task tree."""
    prefix = "  " * indent

    # Task header
    task_id_short = task.task_id[:8] if task.task_id else "unknown"
    status = getattr(task, "status", "unknown")
    lines.append(f"{prefix}[{task_id_short}] {status.upper()}")

    # Goal
    goal = getattr(task, "goal", "")
    if goal:
        goal_display = goal if len(goal) <= 80 else f"{goal[:77]}..."
        lines.append(f"{prefix}  Goal: {goal_display}")

    # Result
    result = getattr(task, "result", None)
    if result:
        result_str = str(result)
        result_display = (
            result_str if len(result_str) <= 80 else f"{result_str[:77]}..."
        )
        lines.append(f"{prefix}  Result: {result_display}")

    # Module/Agent
    module = getattr(task, "module", None)
    if module:
        lines.append(f"{prefix}  Module: {module}")

    lines.append("")

    # Subtasks
    subtask_ids = getattr(task, "subtask_ids", [])
    if subtask_ids and hasattr(dag, "get_node"):
        for subtask_id in subtask_ids:
            subtask = dag.get_node(subtask_id)
            if subtask:
                _format_task_tree(subtask, dag, lines, indent + 1)


def format_dag_summary(dag: TaskDAG) -> str:
    """
    Format a brief summary of a TaskDAG.

    Args:
        dag: TaskDAG instance

    Returns:
        Summary string with task counts and status
    """
    if not dag or not hasattr(dag, "graph"):
        return "Empty DAG"

    total_tasks = len(dag.graph.nodes())

    # Count by status
    status_counts = {}
    if hasattr(dag, "get_node"):
        for node_id in dag.graph.nodes():
            node = dag.get_node(node_id)
            if node:
                status = getattr(node, "status", "unknown")
                status_counts[status] = status_counts.get(status, 0) + 1

    summary = [
        f"DAG Summary: {total_tasks} tasks",
    ]

    if status_counts:
        status_parts = [
            f"{status}: {count}" for status, count in sorted(status_counts.items())
        ]
        summary.append(f"  Status: {', '.join(status_parts)}")

    return "\n".join(summary)
