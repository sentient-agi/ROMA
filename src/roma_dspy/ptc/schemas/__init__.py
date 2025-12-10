"""
PTC Integration Schemas

Shared Pydantic models for type-safe communication between ROMA and PTC.
"""

from .execution_plan import (
    PTCExecutionPlan,
    ScaffoldingSpec,
    LLMProvider,
    CacheStrategy,
)
from .artifact_result import (
    PTCArtifactResult,
    CodeArtifact,
    TestResult,
    LLMUsage,
    ExecutionStatus,
    ArtifactType,
)

__all__ = [
    # Execution Plan
    "PTCExecutionPlan",
    "ScaffoldingSpec",
    "LLMProvider",
    "CacheStrategy",
    # Artifact Result
    "PTCArtifactResult",
    "CodeArtifact",
    "TestResult",
    "LLMUsage",
    "ExecutionStatus",
    "ArtifactType",
]
