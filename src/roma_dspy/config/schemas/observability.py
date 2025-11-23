"""Observability configuration schemas for ROMA-DSPy."""

from pydantic.dataclasses import dataclass
from pydantic import field_validator, Field
from typing import Optional


@dataclass
class MLflowConfig:
    """MLflow tracing configuration.

    MLflow provides observability for DSPy programs through automatic trace generation.
    This config controls what gets logged and where traces are stored.
    """

    enabled: bool = False
    tracking_uri: str = "http://127.0.0.1:5000"
    experiment_name: str = "ROMA-DSPy"

    # Autolog parameters
    log_traces: bool = True
    log_traces_from_compile: bool = False  # Expensive - disabled by default
    log_traces_from_eval: bool = True
    log_compiles: bool = True
    log_evals: bool = True

    # Optional storage configuration
    backend_store_uri: Optional[str] = None  # e.g., "sqlite:///mlflow.db"
    artifact_location: Optional[str] = None

    @field_validator("tracking_uri")
    @classmethod
    def validate_tracking_uri(cls, v: str) -> str:
        """Validate tracking URI is not empty."""
        if not v or not v.strip():
            raise ValueError("tracking_uri cannot be empty")
        return v.strip()

    @field_validator("experiment_name")
    @classmethod
    def validate_experiment_name(cls, v: str) -> str:
        """Validate experiment name is not empty."""
        if not v or not v.strip():
            raise ValueError("experiment_name cannot be empty")
        return v.strip()


@dataclass
class ToolkitMetricsConfig:
    """Toolkit metrics and traceability configuration.

    Controls collection of toolkit lifecycle and tool invocation metrics.
    """

    enabled: bool = True

    # Lifecycle tracking
    track_lifecycle: bool = True  # Track toolkit creation/caching/cleanup
    track_invocations: bool = True  # Track individual tool calls

    # Sampling (for high-volume environments)
    sample_rate: float = Field(default=1.0, ge=0.0, le=1.0)  # 1.0 = 100% sampling

    # Storage
    persist_to_db: bool = True  # Save to PostgreSQL
    persist_to_mlflow: bool = False  # Save to MLflow (if enabled)

    # Performance
    batch_size: int = Field(default=100, ge=1, le=1000)  # Batch persistence size
    async_persist: bool = True  # Persist asynchronously

    @field_validator("sample_rate")
    @classmethod
    def validate_sample_rate(cls, v: float) -> float:
        """Validate sample rate is between 0 and 1."""
        if not 0.0 <= v <= 1.0:
            raise ValueError("sample_rate must be between 0.0 and 1.0")
        return v


@dataclass
class EventTracesConfig:
    """Event traces configuration for execution flow tracking.

    Tracks execution events from RecursiveSolver for debugging and monitoring.
    Events capture the hierarchical task decomposition and execution flow.
    """

    enabled: bool = True

    # Event types to track
    track_execution_events: bool = True  # Track execution start/complete
    track_module_events: bool = True  # Track atomize/plan/execute/aggregate
    track_task_lifecycle: bool = True  # Track task status transitions
    track_failures: bool = True  # Track error/failure events

    # Sampling (for high-volume environments)
    sample_rate: float = Field(default=1.0, ge=0.0, le=1.0)  # 1.0 = 100% sampling

    # Storage
    persist_to_db: bool = True  # Save to PostgreSQL
    persist_to_mlflow: bool = False  # Save to MLflow traces (if enabled)

    # Performance
    batch_size: int = Field(default=50, ge=1, le=500)  # Batch persistence size
    async_persist: bool = True  # Persist asynchronously

    # Detail level
    include_task_details: bool = True  # Include task goal/result in events
    include_timing: bool = True  # Include timing metrics
    max_goal_length: int = Field(
        default=200, ge=50, le=1000
    )  # Max goal length in events

    @field_validator("sample_rate")
    @classmethod
    def validate_sample_rate(cls, v: float) -> float:
        """Validate sample rate is between 0 and 1."""
        if not 0.0 <= v <= 1.0:
            raise ValueError("sample_rate must be between 0.0 and 1.0")
        return v


@dataclass
class ObservabilityConfig:
    """Observability configuration for debugging and monitoring."""

    mlflow: Optional[MLflowConfig] = None
    toolkit_metrics: Optional[ToolkitMetricsConfig] = None
    event_traces: Optional[EventTracesConfig] = None

    def __post_init__(self):
        """Initialize defaults after creation."""
        if self.mlflow is None:
            self.mlflow = MLflowConfig()
        if self.toolkit_metrics is None:
            self.toolkit_metrics = ToolkitMetricsConfig()
        if self.event_traces is None:
            self.event_traces = EventTracesConfig()
