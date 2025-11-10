"""Clean view models for TUI visualization.

These models represent deduplicated, transformed data ready for UI rendering.
They separate concerns between data fetching (client), transformation (transformer),
and rendering (app).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from roma_dspy.types import EdgeType


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

    # Dependencies (for DAG visualization)
    dependencies: List[str] = field(default_factory=list)  # Task IDs this task depends on
    dependents: List[str] = field(default_factory=list)    # Task IDs that depend on this task


@dataclass
class DAGEdge:
    """Edge in the task dependency graph."""

    from_task_id: str
    to_task_id: str
    edge_type: EdgeType
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def symbol(self) -> str:
        """ASCII symbol for rendering this edge."""
        return self.edge_type.symbol

    @property
    def description(self) -> str:
        """Human-readable description."""
        return self.edge_type.description


@dataclass
class DAGViewModel:
    """
    Complete DAG structure for visualization.

    This model represents the full execution graph with all nodes,
    edges, and computed metrics for visualization purposes.
    """

    # Graph structure
    nodes: Dict[str, TaskViewModel] = field(default_factory=dict)
    edges: List[DAGEdge] = field(default_factory=list)

    # Computed graph metrics
    critical_path: List[str] = field(default_factory=list)  # Task IDs in critical path
    parallel_clusters: List[List[str]] = field(default_factory=list)  # Groups of tasks that can run in parallel
    blocked_tasks: List[str] = field(default_factory=list)  # Task IDs blocked by dependencies
    ready_tasks: List[str] = field(default_factory=list)  # Task IDs ready to execute

    # Subgraph support
    subgraphs: Dict[str, DAGViewModel] = field(default_factory=dict)  # Nested DAGs for planning nodes

    # Metadata
    dag_id: str = ""
    execution_id: str = ""
    total_nodes: int = 0
    total_edges: int = 0
    max_depth: int = 0
    parallelism_factor: float = 0.0  # Average parallelism (total_nodes / critical_path_length)

    def get_edges_by_type(self, edge_type: EdgeType) -> List[DAGEdge]:
        """Filter edges by type."""
        return [edge for edge in self.edges if edge.edge_type == edge_type]

    def get_node_position_data(self) -> Dict[str, Tuple[int, int]]:
        """Get cached node positions if available (populated by layout engine)."""
        return getattr(self, '_positions', {})

    def set_node_positions(self, positions: Dict[str, Tuple[int, int]]) -> None:
        """Set node positions (used by layout engine)."""
        self._positions = positions


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

    # DAG structure (for graph visualization)
    dag: Optional[DAGViewModel] = None
