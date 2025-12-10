"""
ROMA + PTC Integration Module

This module handles the integration between ROMA (Recursive Open Meta-Agents)
and PTC (Prompt-Test-Code) agent for code generation and execution.
"""

from .client import PTCClient, PTCClientError, PTCTimeoutError, PTCServiceError
from .processor import ArtifactProcessor, ArtifactProcessorError
from .cache import PTCCacheManager
from .schemas import (
    PTCExecutionPlan,
    PTCArtifactResult,
    ScaffoldingSpec,
    CodeArtifact,
    TestResult,
    LLMUsage,
    LLMProvider,
    CacheStrategy,
    ExecutionStatus,
    ArtifactType,
)

__version__ = "0.1.0"

__all__ = [
    # Client
    "PTCClient",
    "PTCClientError",
    "PTCTimeoutError",
    "PTCServiceError",
    # Processor
    "ArtifactProcessor",
    "ArtifactProcessorError",
    # Cache
    "PTCCacheManager",
    # Schemas
    "PTCExecutionPlan",
    "PTCArtifactResult",
    "ScaffoldingSpec",
    "CodeArtifact",
    "TestResult",
    "LLMUsage",
    "LLMProvider",
    "CacheStrategy",
    "ExecutionStatus",
    "ArtifactType",
]
