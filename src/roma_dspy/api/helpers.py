"""Helper utilities for API operations."""

from datetime import datetime
from typing import Any, Dict, List, Optional
from roma_dspy.api.schemas import (
    ExecutionResponse,
    ExecutionDetailResponse,
    TaskNodeResponse,
    CheckpointResponse,
    TaskTraceResponse,
    LMTraceResponse,
    DAGStatisticsResponse,
)
from roma_dspy.core.storage.models import (
    Execution,
    Checkpoint,
    TaskTrace,
    LMTrace,
)
from roma_dspy.core.engine.dag import TaskDAG
from roma_dspy.core.signatures.base_models.task_node import TaskNode


def execution_to_response(execution: Execution) -> ExecutionResponse:
    """Convert Execution model to ExecutionResponse schema."""
    return ExecutionResponse(
        execution_id=execution.execution_id,
        status=execution.status,
        initial_goal=execution.initial_goal,
        max_depth=execution.max_depth,
        profile=execution.profile,
        experiment_name=execution.experiment_name,
        total_tasks=execution.total_tasks,
        completed_tasks=execution.completed_tasks,
        failed_tasks=execution.failed_tasks,
        created_at=execution.created_at,
        updated_at=execution.updated_at,
        config=execution.config,
        metadata=execution.execution_metadata,
    )


async def execution_to_detail_response(
    execution: Execution,
    storage: Optional[Any] = None,
    dag: Optional[TaskDAG] = None
) -> ExecutionDetailResponse:
    """
    Convert Execution model to ExecutionDetailResponse with statistics.

    Args:
        execution: Execution model from database
        storage: PostgresStorage instance for fetching checkpoints
        dag: Optional live TaskDAG (fallback if no checkpoint available)

    Returns:
        ExecutionDetailResponse with statistics
    """
    base = execution_to_response(execution)

    statistics = None

    # Try to get latest checkpoint first
    if storage:
        try:
            checkpoint = await storage.get_latest_checkpoint(execution.execution_id, valid_only=True)
            if checkpoint and checkpoint.root_dag:
                # Convert DAGSnapshot model to dict if needed
                dag_snapshot = checkpoint.root_dag
                if hasattr(dag_snapshot, 'model_dump'):
                    dag_snapshot = dag_snapshot.model_dump(mode="python")

                # Extract statistics from checkpoint DAG snapshot
                if 'statistics' in dag_snapshot:
                    stats_data = dag_snapshot['statistics']
                    statistics = DAGStatisticsResponse(
                        dag_id=stats_data.get('dag_id', ''),
                        total_tasks=stats_data.get('total_tasks', 0),
                        status_counts=stats_data.get('status_counts', {}),
                        depth_distribution={
                            int(k): v for k, v in stats_data.get('depth_distribution', {}).items()
                        },
                        num_subgraphs=stats_data.get('num_subgraphs', 0),
                        is_complete=stats_data.get('is_complete', False),
                    )
        except Exception:
            pass

    # Fallback to live DAG if checkpoint not available
    if not statistics and dag:
        stats = dag.get_statistics()
        statistics = DAGStatisticsResponse(
            dag_id=stats['dag_id'],
            total_tasks=stats['total_tasks'],
            status_counts=stats['status_counts'],
            depth_distribution={int(k): v for k, v in stats['depth_distribution'].items()},
            num_subgraphs=stats['num_subgraphs'],
            is_complete=stats['is_complete'],
        )

    return ExecutionDetailResponse(
        **base.model_dump(),
        statistics=statistics,
    )


def task_node_to_response(task: TaskNode) -> TaskNodeResponse:
    """Convert TaskNode to TaskNodeResponse schema."""
    return TaskNodeResponse(
        task_id=task.task_id,
        goal=task.goal,
        status=task.status.value,
        depth=task.depth,
        node_type=task.node_type.value if task.node_type else None,
        parent_id=task.parent_id,
        result=task.result,
        error=task.error,
        created_at=task.created_at,
        started_at=task.started_at,
        completed_at=task.completed_at,
    )


def checkpoint_to_response(checkpoint: Checkpoint) -> CheckpointResponse:
    """Convert Checkpoint model to CheckpointResponse schema."""
    return CheckpointResponse(
        checkpoint_id=checkpoint.checkpoint_id,
        execution_id=checkpoint.execution_id,
        created_at=checkpoint.created_at,
        trigger=checkpoint.trigger,
        state=checkpoint.state,
        file_path=checkpoint.file_path,
        file_size_bytes=checkpoint.file_size_bytes,
        compressed=checkpoint.compressed,
    )


def task_trace_to_response(trace: TaskTrace) -> TaskTraceResponse:
    """Convert TaskTrace model to TaskTraceResponse schema."""
    return TaskTraceResponse(
        trace_id=trace.trace_id,
        execution_id=trace.execution_id,
        task_id=trace.task_id,
        parent_task_id=trace.parent_task_id,
        created_at=trace.created_at,
        updated_at=trace.updated_at,
        task_type=trace.task_type,
        node_type=trace.node_type,
        status=trace.status,
        depth=trace.depth,
        retry_count=trace.retry_count,
        goal=trace.goal,
        result=trace.result,
        error=trace.error,
    )


def lm_trace_to_response(trace: LMTrace) -> LMTraceResponse:
    """Convert LMTrace model to LMTraceResponse schema."""
    return LMTraceResponse(
        trace_id=trace.trace_id,
        execution_id=trace.execution_id,
        task_id=trace.task_id,
        module_name=trace.module_name,
        created_at=trace.created_at,
        model=trace.model,
        temperature=trace.temperature,
        prompt_tokens=trace.prompt_tokens,
        completion_tokens=trace.completion_tokens,
        total_tokens=trace.total_tokens,
        cost_usd=float(trace.cost_usd) if trace.cost_usd else None,
        latency_ms=trace.latency_ms,
        prompt=trace.prompt,
        response=trace.response,
        error=trace.error,
        metadata=trace.lm_metadata or {},
    )


def calculate_progress(execution: Execution) -> float:
    """Calculate execution progress as a float between 0.0 and 1.0."""
    if execution.total_tasks == 0:
        return 0.0

    completed = execution.completed_tasks + execution.failed_tasks
    return min(1.0, completed / execution.total_tasks)


def estimate_remaining_time(
    execution: Execution,
    avg_task_duration_seconds: Optional[float] = None
) -> Optional[int]:
    """Estimate remaining execution time in seconds."""
    if not avg_task_duration_seconds or execution.total_tasks == 0:
        return None

    remaining_tasks = execution.total_tasks - (execution.completed_tasks + execution.failed_tasks)
    if remaining_tasks <= 0:
        return 0

    return int(remaining_tasks * avg_task_duration_seconds)


def validate_execution_status(status: str) -> bool:
    """Validate execution status string."""
    valid_statuses = {'pending', 'running', 'completed', 'failed', 'cancelled'}
    return status.lower() in valid_statuses


def validate_checkpoint_trigger(trigger: str) -> bool:
    """Validate checkpoint trigger string."""
    valid_triggers = {'manual', 'automatic', 'failure', 'periodic', 'depth_limit'}
    return trigger.lower() in valid_triggers


def build_task_tree(tasks: List[TaskNode]) -> Dict[str, Any]:
    """
    Build a hierarchical tree structure from flat task list.

    Args:
        tasks: List of TaskNode objects

    Returns:
        Dictionary representing the task tree
    """
    task_map = {task.task_id: task for task in tasks}
    root_tasks = []
    task_tree = {}

    for task in tasks:
        task_dict = {
            'task_id': task.task_id,
            'goal': task.goal,
            'status': task.status.value,
            'depth': task.depth,
            'children': []
        }

        if task.parent_id and task.parent_id in task_map:
            # Find parent in tree and add as child
            parent_id = task.parent_id
            if parent_id not in task_tree:
                task_tree[parent_id] = {'children': []}
            task_tree[parent_id]['children'].append(task_dict)
        else:
            # Root task
            root_tasks.append(task_dict)

        task_tree[task.task_id] = task_dict

    return {
        'root_tasks': root_tasks,
        'task_tree': task_tree
    }


def format_duration(seconds: float) -> str:
    """Format duration in seconds to human-readable string."""
    if seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        minutes = seconds / 60
        return f"{minutes:.1f}m"
    else:
        hours = seconds / 3600
        return f"{hours:.1f}h"


def sanitize_metadata(metadata: Dict[str, Any], max_depth: int = 3) -> Dict[str, Any]:
    """
    Sanitize metadata for API response by limiting depth and size.

    Args:
        metadata: Metadata dictionary
        max_depth: Maximum nesting depth

    Returns:
        Sanitized metadata dictionary
    """
    def _sanitize(obj: Any, depth: int) -> Any:
        if depth >= max_depth:
            return str(obj) if obj is not None else None

        if isinstance(obj, dict):
            return {k: _sanitize(v, depth + 1) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [_sanitize(item, depth + 1) for item in obj[:100]]  # Limit list size
        else:
            return obj

    return _sanitize(metadata, 0)
