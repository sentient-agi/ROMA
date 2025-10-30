"""Checkpoint data models for state serialization and recovery."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set
from pathlib import Path

from pydantic import BaseModel, Field

from roma_dspy.types.checkpoint_types import CheckpointState, RecoveryStrategy, CheckpointTrigger


class CacheStatistics(BaseModel):
    """Cache performance statistics for checkpoint analysis."""
    total_calls: int = Field(default=0, description="Total LM calls during execution")
    cache_hits: int = Field(default=0, description="Number of cache hits")
    cache_misses: int = Field(default=0, description="Number of cache misses")
    hit_rate: float = Field(default=0.0, description="Cache hit rate (0-1)")
    time_saved_ms: int = Field(default=0, description="Estimated time saved by cache (milliseconds)")
    cost_saved_usd: float = Field(default=0.0, description="Estimated cost saved (USD)")


class TaskSnapshot(BaseModel):
    """Serializable snapshot of a task node state."""
    task_id: str = Field(description="Unique task identifier")
    goal: str = Field(description="Task goal description")
    status: str = Field(description="Current task status")
    task_type: str = Field(description="Task type classification")
    depth: int = Field(description="Task depth in hierarchy")
    retry_count: int = Field(default=0, description="Current retry attempt count")
    max_retries: int = Field(default=3, description="Maximum allowed retries")
    result: Optional[Any] = Field(default=None, description="Task execution result")
    error: Optional[str] = Field(default=None, description="Last error message if failed")
    subgraph_id: Optional[str] = Field(default=None, description="Associated subgraph ID")
    dependencies: List[str] = Field(default_factory=list, description="Task dependency IDs")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional task metadata")


class DAGSnapshot(BaseModel):
    """Serializable snapshot of a TaskDAG state."""
    dag_id: str = Field(description="DAG identifier")
    tasks: Dict[str, TaskSnapshot] = Field(description="Task snapshots by ID")
    completed_tasks: Set[str] = Field(default_factory=set, description="Completed task IDs")
    failed_tasks: Set[str] = Field(default_factory=set, description="Failed task IDs")
    dependencies: Dict[str, List[str]] = Field(default_factory=dict, description="Task dependencies")
    subgraphs: Dict[str, "DAGSnapshot"] = Field(default_factory=dict, description="Nested subgraph snapshots")
    statistics: Optional[Dict[str, Any]] = Field(
        default=None,
        description="DAG execution statistics (task counts, status distribution, depth info)"
    )


class CheckpointData(BaseModel):
    """Complete checkpoint data for state recovery."""
    checkpoint_id: str = Field(description="Unique checkpoint identifier")
    execution_id: str = Field(description="Execution identifier (for Postgres FK)")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Checkpoint creation time (UTC timezone-aware)"
    )
    trigger: CheckpointTrigger = Field(description="Event that triggered checkpoint creation")
    state: CheckpointState = Field(default=CheckpointState.CREATED, description="Checkpoint validity state")

    # Core execution state
    root_dag: DAGSnapshot = Field(description="Root DAG snapshot")
    current_depth: int = Field(default=0, description="Current recursion depth")
    max_depth: int = Field(default=5, description="Maximum allowed depth")

    # Recovery metadata
    recovery_strategy: RecoveryStrategy = Field(default=RecoveryStrategy.PARTIAL, description="Preferred recovery strategy")
    failed_task_ids: Set[str] = Field(default_factory=set, description="Tasks that failed and need retry")
    preserved_results: Dict[str, Any] = Field(default_factory=dict, description="Results to preserve during recovery")

    # Runtime context
    solver_config: Dict[str, Any] = Field(default_factory=dict, description="RecursiveSolver configuration")
    module_states: Dict[str, Dict[str, Any]] = Field(default_factory=dict, description="Module instance states")

    # Cache statistics
    cache_stats: Optional[CacheStatistics] = Field(
        default=None,
        description="Cache performance stats at checkpoint time"
    )

    # Tool invocations for observability and recovery
    tool_invocations: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Tool invocation history from ExecutionContext"
    )

    # File path for hybrid storage
    file_path: Optional[str] = Field(default=None, description="Path to file-based checkpoint")

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat(),
            set: lambda v: list(v)
        }


class RecoveryPlan(BaseModel):
    """Plan for recovering from a checkpoint."""
    checkpoint_id: str = Field(description="Source checkpoint ID")
    strategy: RecoveryStrategy = Field(description="Recovery strategy to use")

    # Task recovery scope
    tasks_to_retry: List[str] = Field(description="Task IDs to retry from checkpoint")
    tasks_to_preserve: List[str] = Field(description="Task IDs with results to preserve")

    # State restoration
    restore_dag_state: bool = Field(default=True, description="Whether to restore full DAG state")
    restore_module_states: bool = Field(default=False, description="Whether to restore module states")

    # Recovery parameters
    reset_retry_counts: bool = Field(default=False, description="Whether to reset task retry counters")
    apply_backoff: bool = Field(default=True, description="Whether to apply exponential backoff")

    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional recovery metadata")


class CheckpointConfig(BaseModel):
    """Configuration for checkpoint behavior."""
    enabled: bool = Field(default=True, description="Enable checkpoint system")
    storage_path: Path = Field(default=Path(".checkpoints"), description="Checkpoint storage directory")

    # Checkpoint creation
    auto_checkpoint_triggers: List[CheckpointTrigger] = Field(
        default=[CheckpointTrigger.BEFORE_PLANNING, CheckpointTrigger.BEFORE_AGGREGATION],
        description="Events that automatically create checkpoints"
    )
    max_checkpoints: int = Field(default=10, description="Maximum checkpoints to retain")

    # Checkpoint retention
    max_age_hours: float = Field(default=24.0, description="Maximum checkpoint age in hours")
    cleanup_interval_minutes: int = Field(default=60, description="Cleanup interval in minutes")

    # Recovery settings
    default_recovery_strategy: RecoveryStrategy = Field(
        default=RecoveryStrategy.PARTIAL,
        description="Default recovery strategy"
    )
    preserve_partial_results: bool = Field(
        default=True,
        description="Preserve partial results during recovery"
    )

    # Compression and storage
    compress_checkpoints: bool = Field(default=True, description="Compress checkpoint data")
    verify_integrity: bool = Field(default=True, description="Verify checkpoint integrity on load")

    # Periodic checkpoints
    periodic_checkpoints_enabled: bool = Field(
        default=True,
        description="Enable periodic background checkpoints during execution"
    )
    periodic_interval_seconds: float = Field(
        default=30.0,
        description="Interval between periodic checkpoints (seconds)"
    )
    min_execution_time_for_periodic: float = Field(
        default=10.0,
        description="Minimum execution time before periodic checkpoints start (seconds)"
    )