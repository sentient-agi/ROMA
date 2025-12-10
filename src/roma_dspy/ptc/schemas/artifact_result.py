"""
PTCArtifactResult Schema

Defines the output contract from PTC to ROMA.
This schema encapsulates all artifacts and metadata from code generation.
"""

from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field, field_validator


class ExecutionStatus(str, Enum):
    """Status of PTC execution."""
    SUCCESS = "SUCCESS"              # Code generated and tested successfully
    PARTIAL_SUCCESS = "PARTIAL_SUCCESS"      # Code generated but tests failed
    FAILURE = "FAILURE"              # Code generation failed
    TIMEOUT = "TIMEOUT"              # Execution timed out
    CACHE_HIT = "CACHE_HIT"          # Result served from cache


class ArtifactType(str, Enum):
    """Type of generated artifact."""
    SOURCE_CODE = "source_code"      # Python, JS, etc.
    CONFIG = "config"                # YAML, JSON, TOML, etc.
    DOCUMENTATION = "documentation"   # Markdown, RST, etc.
    TEST = "test"                    # Test files
    DATA = "data"                    # Data files, fixtures


class CodeArtifact(BaseModel):
    """
    A single generated code artifact (file).
    """
    file_path: str = Field(
        ...,
        description="Relative path where file should be created"
    )

    content: str = Field(
        ...,
        description="Full content of the file"
    )

    artifact_type: ArtifactType = Field(
        default=ArtifactType.SOURCE_CODE,
        description="Type of artifact"
    )

    language: Optional[str] = Field(
        None,
        description="Programming language (python, javascript, etc.)"
    )

    description: Optional[str] = Field(
        None,
        description="Brief description of what this file does"
    )

    @field_validator('file_path')
    @classmethod
    def validate_file_path(cls, v: str) -> str:
        """Ensure file_path is valid."""
        if not v or not v.strip():
            raise ValueError("file_path cannot be empty")
        # Remove leading slashes to ensure relative path
        return v.lstrip('/')


class TestResult(BaseModel):
    """
    Results from executing tests on generated code.
    """
    test_command: str = Field(
        ...,
        description="Command used to run tests"
    )

    exit_code: int = Field(
        ...,
        description="Exit code from test execution"
    )

    stdout: str = Field(
        default="",
        description="Standard output from tests"
    )

    stderr: str = Field(
        default="",
        description="Standard error from tests"
    )

    tests_passed: int = Field(
        default=0,
        ge=0,
        description="Number of tests that passed"
    )

    tests_failed: int = Field(
        default=0,
        ge=0,
        description="Number of tests that failed"
    )

    duration_seconds: float = Field(
        ...,
        ge=0,
        description="Test execution duration"
    )

    @property
    def success(self) -> bool:
        """Whether tests passed successfully."""
        return self.exit_code == 0 and self.tests_failed == 0


class LLMUsage(BaseModel):
    """
    Token usage statistics from LLM calls.
    """
    provider: str = Field(
        ...,
        description="LLM provider used (claude, kimi, etc.)"
    )

    model: str = Field(
        ...,
        description="Specific model used (claude-3-sonnet, etc.)"
    )

    prompt_tokens: int = Field(
        default=0,
        ge=0,
        description="Number of tokens in prompts"
    )

    completion_tokens: int = Field(
        default=0,
        ge=0,
        description="Number of tokens in completions"
    )

    total_tokens: int = Field(
        default=0,
        ge=0,
        description="Total tokens used"
    )

    api_calls: int = Field(
        default=1,
        ge=0,
        description="Number of API calls made"
    )

    cost_usd: Optional[float] = Field(
        None,
        ge=0,
        description="Estimated cost in USD (if available)"
    )


class PTCArtifactResult(BaseModel):
    """
    Complete result from PTC code generation.

    This schema defines everything PTC returns to ROMA after
    processing a PTCExecutionPlan.
    """

    # Execution tracking
    execution_id: str = Field(
        ...,
        description="Matches the execution_id from PTCExecutionPlan"
    )

    status: ExecutionStatus = Field(
        ...,
        description="Overall status of execution"
    )

    # Generated artifacts
    artifacts: List[CodeArtifact] = Field(
        default_factory=list,
        description="List of generated code artifacts"
    )

    # Test results (if testing was enabled)
    test_results: Optional[TestResult] = Field(
        None,
        description="Results from executing tests on generated code"
    )

    # Iteration history
    iterations_used: int = Field(
        default=1,
        ge=0,
        description="Number of refinement iterations performed"
    )

    # Error information
    error_message: Optional[str] = Field(
        None,
        description="Error message if execution failed"
    )

    warnings: List[str] = Field(
        default_factory=list,
        description="Non-fatal warnings during execution"
    )

    # LLM usage tracking
    llm_usage: List[LLMUsage] = Field(
        default_factory=list,
        description="Token usage for all LLM calls"
    )

    # Timing information
    started_at: datetime = Field(
        ...,
        description="When execution started"
    )

    completed_at: datetime = Field(
        ...,
        description="When execution completed"
    )

    duration_seconds: float = Field(
        ...,
        ge=0,
        description="Total execution duration"
    )

    # Cache information
    from_cache: bool = Field(
        default=False,
        description="Whether result was served from cache"
    )

    cache_key: Optional[str] = Field(
        None,
        description="Cache key used (for debugging)"
    )

    # Metadata
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional metadata from PTC"
    )

    @field_validator('execution_id')
    @classmethod
    def validate_execution_id(cls, v: str) -> str:
        """Ensure execution_id is not empty."""
        if not v or not v.strip():
            raise ValueError("execution_id cannot be empty")
        return v.strip()

    @field_validator('duration_seconds')
    @classmethod
    def validate_duration(cls, v: float, info) -> float:
        """Validate duration is consistent with timestamps."""
        if v < 0:
            raise ValueError("duration_seconds must be non-negative")
        return v

    @property
    def success(self) -> bool:
        """Whether execution was successful."""
        return self.status in (ExecutionStatus.SUCCESS, ExecutionStatus.CACHE_HIT)

    @property
    def total_tokens_used(self) -> int:
        """Total tokens across all LLM calls."""
        return sum(usage.total_tokens for usage in self.llm_usage)

    @property
    def total_cost_usd(self) -> float:
        """Total estimated cost across all LLM calls."""
        return sum(
            usage.cost_usd for usage in self.llm_usage
            if usage.cost_usd is not None
        )

    class Config:
        """Pydantic model configuration."""
        json_schema_extra = {
            "example": {
                "execution_id": "ptc-exec-123e4567-e89b-12d3-a456-426614174000",
                "status": "success",
                "artifacts": [
                    {
                        "file_path": "main.py",
                        "content": "from fastapi import FastAPI\n\napp = FastAPI()\n\n@app.get('/')\ndef root():\n    return {'message': 'Hello World'}",
                        "artifact_type": "source_code",
                        "language": "python",
                        "description": "FastAPI application entry point"
                    },
                    {
                        "file_path": "tests/test_main.py",
                        "content": "from fastapi.testclient import TestClient\nfrom main import app\n\nclient = TestClient(app)\n\ndef test_root():\n    response = client.get('/')\n    assert response.status_code == 200",
                        "artifact_type": "test",
                        "language": "python",
                        "description": "Tests for main.py"
                    }
                ],
                "test_results": {
                    "test_command": "pytest tests/",
                    "exit_code": 0,
                    "stdout": "===== 1 passed in 0.12s =====",
                    "stderr": "",
                    "tests_passed": 1,
                    "tests_failed": 0,
                    "duration_seconds": 0.12
                },
                "iterations_used": 1,
                "warnings": [],
                "llm_usage": [
                    {
                        "provider": "claude",
                        "model": "claude-3-sonnet-20240229",
                        "prompt_tokens": 1250,
                        "completion_tokens": 850,
                        "total_tokens": 2100,
                        "api_calls": 1,
                        "cost_usd": 0.0063
                    }
                ],
                "started_at": "2025-12-06T18:00:00Z",
                "completed_at": "2025-12-06T18:02:15Z",
                "duration_seconds": 135.0,
                "from_cache": False,
                "metadata": {
                    "sandbox_id": "daytona-sbx-abc123"
                }
            }
        }
