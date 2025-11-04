"""Type definitions and enumerations for ROMA DSPy."""

from .adapter_type import AdapterType, AdapterTypeLiteral
from .agent_type import AgentType, AgentTypeLiteral
from .artifact_types import ArtifactType, ArtifactTypeLiteral
from .artifact_models import ArtifactMetadata, Artifact, ArtifactReference, ArtifactRegistrationRequest
from .execution_event_type import ExecutionEventType
from .execution_status import ExecutionStatus, ExecutionStatusLiteral
from .media_type import MediaType, MediaTypeLiteral
from .module_result import ModuleResult, StateTransition, NodeMetrics, ExecutionEvent, TokenMetrics
from .node_type import NodeType, NodeTypeLiteral
from .prediction_strategy import PredictionStrategy
from .task_status import TaskStatus, TaskStatusLiteral
from .task_type import TaskType, TaskTypeLiteral
from .resilience_types import RetryStrategy, CircuitState, CircuitOpenError
from .resilience_models import RetryConfig, CircuitBreakerConfig, FailureContext, CircuitMetrics
from .checkpoint_types import (
    CheckpointState,
    RecoveryStrategy,
    CheckpointTrigger,
    RecoveryError,
    CheckpointCorruptedError,
    CheckpointExpiredError,
    CheckpointNotFoundError
)
from .checkpoint_models import (
    CacheStatistics,
    CheckpointData,
    CheckpointConfig,
    RecoveryPlan,
    TaskSnapshot,
    DAGSnapshot
)
from .error_types import (
    ErrorSeverity,
    ErrorCategory,
    TaskHierarchyError,
    ModuleError,
    PlanningError,
    ExecutionError,
    AggregationError,
    RetryExhaustedError,
    serialize_error,
    error_to_dict
)

__all__ = [
    "AdapterType",
    "AdapterTypeLiteral",
    "AgentType",
    "AgentTypeLiteral",
    "ArtifactType",
    "ArtifactTypeLiteral",
    "ArtifactMetadata",
    "Artifact",
    "ArtifactReference",
    "ArtifactRegistrationRequest",
    "ExecutionEventType",
    "ExecutionStatus",
    "ExecutionStatusLiteral",
    "MediaType",
    "MediaTypeLiteral",
    "ModuleResult",
    "StateTransition",
    "NodeMetrics",
    "ExecutionEvent",
    "TokenMetrics",
    "NodeType",
    "NodeTypeLiteral",
    "PredictionStrategy",
    "TaskStatus",
    "TaskStatusLiteral",
    "TaskType",
    "TaskTypeLiteral",
    "RetryStrategy",
    "CircuitState",
    "CircuitOpenError",
    "RetryConfig",
    "CircuitBreakerConfig",
    "FailureContext",
    "CircuitMetrics",
    "CheckpointState",
    "RecoveryStrategy",
    "CheckpointTrigger",
    "RecoveryError",
    "CheckpointCorruptedError",
    "CheckpointExpiredError",
    "CheckpointNotFoundError",
    "CacheStatistics",
    "CheckpointData",
    "CheckpointConfig",
    "RecoveryPlan",
    "TaskSnapshot",
    "DAGSnapshot",
    "ErrorSeverity",
    "ErrorCategory",
    "TaskHierarchyError",
    "ModuleError",
    "PlanningError",
    "ExecutionError",
    "AggregationError",
    "RetryExhaustedError",
    "serialize_error",
    "error_to_dict",
]
