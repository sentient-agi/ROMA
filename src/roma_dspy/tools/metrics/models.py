"""Data models for toolkit metrics and traceability."""

from __future__ import annotations

from datetime import datetime
from typing import Dict, Any, Optional, Union

from pydantic import BaseModel, Field, computed_field

from roma_dspy.types import ExecutionEventType


class ToolkitLifecycleEvent(BaseModel):
    """
    Event capturing toolkit lifecycle operations.

    Tracks creation, caching, cleanup operations with timing and outcomes.
    Used for analyzing toolkit performance and reliability.

    Attributes:
        execution_id: Unique execution identifier
        timestamp: When the operation occurred
        operation: Type of operation (create, cache_hit, cache_miss, cleanup)
        toolkit_class: Name of the toolkit class (e.g., "CalculatorToolkit")
        duration_ms: Operation duration in milliseconds
        success: Whether the operation succeeded
        error: Error message if failed
        metadata: Additional context (error_type, config, etc.)
    """

    execution_id: str
    timestamp: datetime
    operation: str
    toolkit_class: Optional[str] = None
    duration_ms: float
    success: bool
    error: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        """Pydantic config."""

        json_encoders = {datetime: lambda v: v.isoformat()}


class ToolInvocationEvent(BaseModel):
    """
    Event capturing individual tool invocations.

    Tracks every tool call with timing, input/output sizes, and outcomes.
    Provides granular visibility into tool usage patterns.

    Attributes:
        execution_id: Unique execution identifier
        toolkit_class: Name of the parent toolkit
        tool_name: Name of the tool invoked
        invoked_at: Invocation timestamp
        duration_ms: Call duration in milliseconds
        input_size_bytes: Size of input data (approximate)
        output_size_bytes: Size of output data (approximate)
        success: Whether the call succeeded
        error: Error message if failed
        metadata: Additional context (error_type, params, etc.)
    """

    execution_id: str
    toolkit_class: str
    tool_name: str
    invoked_at: datetime
    duration_ms: float
    input_size_bytes: int
    output_size_bytes: int
    success: bool
    error: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        """Pydantic config."""

        json_encoders = {datetime: lambda v: v.isoformat()}


class ExecutionEventData(BaseModel):
    """
    Event capturing execution flow from RecursiveSolver.

    Tracks hierarchical task decomposition and module execution flow.
    Used for debugging, monitoring, and execution trace reconstruction.

    Attributes:
        execution_id: Unique execution identifier
        timestamp: When the event occurred
        event_type: Type of event (execution_start, atomize_complete, plan_complete, etc.)
        priority: Event priority (used for ordering, default 0)
        task_id: Optional task identifier
        dag_id: Optional DAG identifier
        event_data: Event payload (module results, timing, error info, etc.)
        dropped: Whether event was dropped due to queue overflow
    """

    execution_id: str
    timestamp: datetime
    event_type: Union[ExecutionEventType, str]
    priority: int = 0
    task_id: Optional[str] = None
    dag_id: Optional[str] = None
    event_data: Dict[str, Any] = Field(default_factory=dict)
    dropped: bool = False

    class Config:
        """Pydantic config."""

        json_encoders = {
            datetime: lambda v: v.isoformat(),
            ExecutionEventType: lambda v: v.value,
        }


class ToolkitMetricsSummary(BaseModel):
    """
    Aggregated metrics for toolkit usage analysis.

    Provides high-level statistics for an execution's toolkit usage.
    Used by API endpoints and dashboards.

    Attributes:
        execution_id: Unique execution identifier
        total_toolkits_created: Number of toolkits instantiated
        cache_hit_rate: Ratio of cache hits to total lookups
        total_tool_invocations: Number of tool calls
        successful_invocations: Number of successful calls
        failed_invocations: Number of failed calls
        avg_tool_duration_ms: Average tool call duration
        total_duration_ms: Total time spent in tools
        by_toolkit: Per-toolkit breakdown {toolkit_class: {...}}
        by_tool: Per-tool breakdown {tool_name: {...}}
    """

    execution_id: str
    total_toolkits_created: int
    cache_hit_rate: float
    total_tool_invocations: int
    successful_invocations: int
    failed_invocations: int
    avg_tool_duration_ms: float
    total_duration_ms: float
    by_toolkit: Dict[str, Dict[str, Any]]
    by_tool: Dict[str, Dict[str, Any]]

    @computed_field  # type: ignore[misc]
    @property
    def success_rate(self) -> float:
        """Calculate tool invocation success rate."""
        if self.total_tool_invocations == 0:
            return 0.0
        return self.successful_invocations / self.total_tool_invocations

    def to_response_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses."""
        return {
            "execution_id": self.execution_id,
            "toolkit_lifecycle": {
                "total_created": self.total_toolkits_created,
                "cache_hit_rate": self.cache_hit_rate,
            },
            "tool_invocations": {
                "total_calls": self.total_tool_invocations,
                "successful_calls": self.successful_invocations,
                "failed_calls": self.failed_invocations,
                "success_rate": self.success_rate,
                "avg_duration_ms": self.avg_tool_duration_ms,
                "total_duration_ms": self.total_duration_ms,
            },
            "by_toolkit": self.by_toolkit,
            "by_tool": self.by_tool,
        }


def aggregate_toolkit_metrics(
    lifecycle_events: list[ToolkitLifecycleEvent],
    invocation_events: list[ToolInvocationEvent],
) -> ToolkitMetricsSummary:
    """
    Aggregate raw events into summary metrics.

    Args:
        lifecycle_events: List of toolkit lifecycle events
        invocation_events: List of tool invocation events

    Returns:
        Aggregated metrics summary
    """
    # Calculate lifecycle metrics
    create_events = [e for e in lifecycle_events if e.operation == "create"]
    cache_hits = [e for e in lifecycle_events if e.operation == "cache_hit"]
    cache_lookups = [
        e for e in lifecycle_events if e.operation in ("cache_hit", "cache_miss")
    ]

    total_created = len(create_events)
    cache_hit_rate = len(cache_hits) / len(cache_lookups) if cache_lookups else 0.0

    # Calculate invocation metrics
    total_invocations = len(invocation_events)
    successful = [e for e in invocation_events if e.success]
    failed = [e for e in invocation_events if not e.success]

    successful_count = len(successful)
    failed_count = len(failed)

    avg_duration = (
        sum(e.duration_ms for e in invocation_events) / len(invocation_events)
        if invocation_events
        else 0.0
    )

    total_duration = sum(e.duration_ms for e in invocation_events)

    # Aggregate by toolkit
    by_toolkit: Dict[str, Dict[str, Any]] = {}
    for event in invocation_events:
        toolkit = event.toolkit_class
        if toolkit not in by_toolkit:
            by_toolkit[toolkit] = {
                "calls": 0,
                "successful": 0,
                "failed": 0,
                "total_duration_ms": 0.0,
                "avg_duration_ms": 0.0,
            }

        by_toolkit[toolkit]["calls"] += 1
        by_toolkit[toolkit]["successful"] += 1 if event.success else 0
        by_toolkit[toolkit]["failed"] += 0 if event.success else 1
        by_toolkit[toolkit]["total_duration_ms"] += event.duration_ms

    # Calculate averages
    for toolkit in by_toolkit.values():
        if toolkit["calls"] > 0:
            toolkit["avg_duration_ms"] = toolkit["total_duration_ms"] / toolkit["calls"]

    # Aggregate by tool
    by_tool: Dict[str, Dict[str, Any]] = {}
    for event in invocation_events:
        tool_key = f"{event.toolkit_class}.{event.tool_name}"
        if tool_key not in by_tool:
            by_tool[tool_key] = {
                "toolkit": event.toolkit_class,
                "tool": event.tool_name,
                "calls": 0,
                "successful": 0,
                "failed": 0,
                "total_duration_ms": 0.0,
                "avg_duration_ms": 0.0,
            }

        by_tool[tool_key]["calls"] += 1
        by_tool[tool_key]["successful"] += 1 if event.success else 0
        by_tool[tool_key]["failed"] += 0 if event.success else 1
        by_tool[tool_key]["total_duration_ms"] += event.duration_ms

    # Calculate averages
    for tool in by_tool.values():
        if tool["calls"] > 0:
            tool["avg_duration_ms"] = tool["total_duration_ms"] / tool["calls"]

    execution_id = invocation_events[0].execution_id if invocation_events else "unknown"

    return ToolkitMetricsSummary(
        execution_id=execution_id,
        total_toolkits_created=total_created,
        cache_hit_rate=cache_hit_rate,
        total_tool_invocations=total_invocations,
        successful_invocations=successful_count,
        failed_invocations=failed_count,
        avg_tool_duration_ms=avg_duration,
        total_duration_ms=total_duration,
        by_toolkit=by_toolkit,
        by_tool=by_tool,
    )
