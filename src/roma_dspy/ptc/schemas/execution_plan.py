"""
PTCExecutionPlan Schema

Defines the input contract from ROMA to PTC agent.
This schema encapsulates all information needed for PTC to generate code.
"""

from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field, field_validator


class LLMProvider(str, Enum):
    """Supported LLM providers for code generation."""
    CLAUDE = "claude"
    KIMI = "kimi"
    OPENAI = "openai"


class CacheStrategy(str, Enum):
    """Cache invalidation strategies."""
    ALWAYS = "always"  # Always use cache if available
    NEVER = "never"    # Never use cache, always generate fresh
    SMART = "smart"    # Use cache but validate freshness


class ScaffoldingSpec(BaseModel):
    """
    Scaffolding specification from ROMA's output.
    This is the core input that drives code generation.
    """
    task_description: str = Field(
        ...,
        description="High-level description of what to build"
    )
    requirements: List[str] = Field(
        default_factory=list,
        description="Functional and non-functional requirements"
    )
    architecture: Optional[Dict[str, Any]] = Field(
        None,
        description="Architectural decisions and patterns to follow"
    )
    dependencies: List[str] = Field(
        default_factory=list,
        description="Required libraries, frameworks, or services"
    )
    file_structure: Optional[Dict[str, str]] = Field(
        None,
        description="Proposed file/directory structure with descriptions"
    )
    context: Optional[str] = Field(
        None,
        description="Additional context or constraints"
    )


class PTCExecutionPlan(BaseModel):
    """
    Complete execution plan sent from ROMA to PTC.

    This schema defines all parameters needed for PTC to:
    1. Generate code based on scaffolding spec
    2. Execute and test the generated code
    3. Return validated artifacts to ROMA
    """

    # Unique identifier for this execution
    execution_id: str = Field(
        ...,
        description="Unique ID for tracking this execution (UUID recommended)"
    )

    # Core input: What to build
    scaffolding: ScaffoldingSpec = Field(
        ...,
        description="Scaffolding specification from ROMA"
    )

    # LLM Configuration
    primary_llm: LLMProvider = Field(
        default=LLMProvider.CLAUDE,
        description="Primary LLM to use for code generation"
    )

    fallback_llm: Optional[LLMProvider] = Field(
        default=LLMProvider.KIMI,
        description="Fallback LLM if primary fails or hits rate limits"
    )

    # Execution Configuration
    max_iterations: int = Field(
        default=3,
        ge=1,
        le=10,
        description="Maximum refinement iterations if tests fail"
    )

    timeout_seconds: int = Field(
        default=300,
        ge=30,
        le=3600,
        description="Maximum execution time in seconds"
    )

    enable_testing: bool = Field(
        default=True,
        description="Whether to execute and test generated code"
    )

    # Cache Configuration
    cache_strategy: CacheStrategy = Field(
        default=CacheStrategy.SMART,
        description="How to handle caching for this execution"
    )

    cache_ttl: Optional[int] = Field(
        default=3600,
        ge=0,
        description="Cache TTL in seconds (None = use default)"
    )

    # Metadata
    project_name: Optional[str] = Field(
        None,
        description="Name of the project/module being built"
    )

    roma_task_id: Optional[str] = Field(
        None,
        description="Reference to parent ROMA task"
    )

    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="Timestamp when plan was created"
    )

    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional metadata for tracking/logging"
    )

    @field_validator('execution_id')
    @classmethod
    def validate_execution_id(cls, v: str) -> str:
        """Ensure execution_id is not empty."""
        if not v or not v.strip():
            raise ValueError("execution_id cannot be empty")
        return v.strip()

    @field_validator('scaffolding')
    @classmethod
    def validate_scaffolding(cls, v: ScaffoldingSpec) -> ScaffoldingSpec:
        """Ensure scaffolding has minimum required information."""
        if not v.task_description or not v.task_description.strip():
            raise ValueError("scaffolding.task_description cannot be empty")
        return v

    class Config:
        """Pydantic model configuration."""
        json_schema_extra = {
            "example": {
                "execution_id": "ptc-exec-123e4567-e89b-12d3-a456-426614174000",
                "scaffolding": {
                    "task_description": "Build a REST API for user authentication",
                    "requirements": [
                        "Support JWT token-based auth",
                        "Include password hashing with bcrypt",
                        "Provide login and signup endpoints"
                    ],
                    "dependencies": [
                        "fastapi",
                        "pyjwt",
                        "passlib"
                    ],
                    "file_structure": {
                        "main.py": "FastAPI application entry point",
                        "auth/": "Authentication module",
                        "auth/routes.py": "Auth endpoints",
                        "auth/models.py": "User models",
                        "auth/security.py": "Password hashing and JWT utilities"
                    }
                },
                "primary_llm": "claude",
                "fallback_llm": "kimi",
                "max_iterations": 3,
                "timeout_seconds": 300,
                "enable_testing": True,
                "cache_strategy": "smart",
                "project_name": "user-auth-api",
                "roma_task_id": "roma-task-789"
            }
        }
