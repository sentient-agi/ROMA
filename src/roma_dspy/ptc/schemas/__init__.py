"""
PTC Integration Schemas

Shared Pydantic models for type-safe communication between ROMA and PTC.
"""

from .execution_plan import PTCExecutionPlan
from .artifact_result import PTCArtifactResult

__all__ = [
    "PTCExecutionPlan",
    "PTCArtifactResult",
]
