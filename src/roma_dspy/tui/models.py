"""Clean view models for TUI visualization.

These models represent deduplicated, transformed data ready for UI rendering.
They separate concerns between data fetching (client), transformation (transformer),
and rendering (app).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class DataSource(Enum):
    """Source of trace data."""

    MLFLOW = "mlflow"
    LM_TRACE = "lm_trace"
    CHECKPOINT = "checkpoint"
    MERGED = "merged"


@dataclass
class TraceViewModel:
    """
    Unified trace representation (deduplicated).

    Built from ONE primary source + optional enrichment.
    """

    # Identity
    trace_id: str  # Unique ID (mlflow span_id or lm_trace.trace_id)
    task_id: str
    parent_trace_id: Optional[str] = None

    # Display
    name: str = "Unknown"
    module: Optional[str] = None

    # Metrics (always present)
    duration: float = 0.0  # seconds
    tokens: int = 0
    cost: float = 0.0  # USD

    # Rich data (optional - from MLflow)
    inputs: Optional[Dict[str, Any]] = None
    outputs: Optional[Dict[str, Any]] = None
    reasoning: Optional[str] = None
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)

    # Timestamps
    start_time: Optional[str] = None
    start_ts: Optional[float] = None

    # Model info
    model: Optional[str] = None
    temperature: Optional[float] = None

    # Error tracking
    error: Optional[str] = None  # Error message from span exception events
    exception: Optional[str] = None  # Exception type from span exception events

    # Metadata
    source: DataSource = DataSource.MERGED  # Where data came from
    has_full_io: bool = False  # Whether inputs/outputs are complete


@dataclass
class TaskViewModel:
    """Task with associated traces."""

    # Identity
    task_id: str
    parent_task_id: Optional[str] = None

    # Core info
    goal: str = ""
    status: str = "unknown"
    module: Optional[str] = None
    task_type: Optional[str] = None
    node_type: Optional[str] = None
    depth: int = 0

    # Results
    result: Optional[Any] = None
    error: Optional[str] = None

    # Traces (deduplicated!)
    traces: List[TraceViewModel] = field(default_factory=list)

    # Aggregated metrics (computed from traces)
    total_duration: float = 0.0
    total_tokens: int = 0
    total_cost: float = 0.0

    # Children
    subtask_ids: List[str] = field(default_factory=list)


@dataclass
class CheckpointViewModel:
    """Checkpoint metadata."""

    checkpoint_id: str
    created_at: datetime
    trigger: str
    state: str
    total_tasks: int
    completed_tasks: int
    file_size_bytes: Optional[int] = None


@dataclass
class MetricsSummary:
    """Aggregated metrics."""

    total_calls: int = 0
    total_tokens: int = 0
    total_cost: float = 0.0
    total_duration: float = 0.0  # Total duration in seconds
    avg_latency_ms: float = 0.0
    by_module: Dict[str, Dict[str, Any]] = field(default_factory=dict)


@dataclass
class AgentGroupViewModel:
    """Represents an agent execution group within a task."""

    task: TaskViewModel
    agent_type: str
    traces: List[TraceViewModel] = field(default_factory=list)
    tokens: int = 0
    duration: float = 0.0


@dataclass
class ExecutionViewModel:
    """Complete execution view (deduplicated)."""

    execution_id: str
    root_goal: str
    status: str

    # Hierarchy (from checkpoints)
    tasks: Dict[str, TaskViewModel] = field(default_factory=dict)
    root_task_ids: List[str] = field(default_factory=list)

    # Checkpoints
    checkpoints: List[CheckpointViewModel] = field(default_factory=list)

    # Metrics
    metrics: MetricsSummary = field(default_factory=MetricsSummary)

    # Data source availability
    data_sources: Dict[str, bool] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
