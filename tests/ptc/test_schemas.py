"""
Tests for PTC integration schemas.

Tests schema validation, serialization, and edge cases.
"""

import pytest
from datetime import datetime, timedelta
from pydantic import ValidationError

from roma_dspy.ptc.schemas import (
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


class TestScaffoldingSpec:
    """Test ScaffoldingSpec model."""

    def test_minimal_scaffolding(self):
        """Test creating minimal valid scaffolding."""
        spec = ScaffoldingSpec(
            task_description="Build a simple API"
        )
        assert spec.task_description == "Build a simple API"
        assert spec.requirements == []
        assert spec.dependencies == []

    def test_full_scaffolding(self):
        """Test creating fully populated scaffolding."""
        spec = ScaffoldingSpec(
            task_description="Build user auth API",
            requirements=["JWT auth", "Password hashing"],
            dependencies=["fastapi", "pyjwt", "passlib"],
            architecture={"pattern": "REST"},
            file_structure={
                "main.py": "Entry point",
                "auth/routes.py": "Auth endpoints"
            },
            context="Use bcrypt for hashing"
        )
        assert len(spec.requirements) == 2
        assert len(spec.dependencies) == 3
        assert spec.architecture["pattern"] == "REST"


class TestPTCExecutionPlan:
    """Test PTCExecutionPlan model."""

    def test_minimal_execution_plan(self):
        """Test creating minimal valid execution plan."""
        plan = PTCExecutionPlan(
            execution_id="test-exec-001",
            scaffolding=ScaffoldingSpec(
                task_description="Build API"
            )
        )
        assert plan.execution_id == "test-exec-001"
        assert plan.primary_llm == LLMProvider.CLAUDE
        assert plan.cache_strategy == CacheStrategy.SMART
        assert plan.enable_testing is True

    def test_execution_plan_validation(self):
        """Test validation rules."""
        # Empty execution_id should fail
        with pytest.raises(ValidationError, match="execution_id cannot be empty"):
            PTCExecutionPlan(
                execution_id="",
                scaffolding=ScaffoldingSpec(task_description="Test")
            )

        # Empty task_description should fail
        with pytest.raises(ValidationError, match="task_description cannot be empty"):
            PTCExecutionPlan(
                execution_id="test-001",
                scaffolding=ScaffoldingSpec(task_description="")
            )

    def test_execution_plan_constraints(self):
        """Test field constraints."""
        plan = PTCExecutionPlan(
            execution_id="test-002",
            scaffolding=ScaffoldingSpec(task_description="Test"),
            max_iterations=5,
            timeout_seconds=600
        )
        assert plan.max_iterations == 5
        assert plan.timeout_seconds == 600

        # Test bounds
        with pytest.raises(ValidationError):
            PTCExecutionPlan(
                execution_id="test-003",
                scaffolding=ScaffoldingSpec(task_description="Test"),
                max_iterations=0  # Below minimum
            )

    def test_execution_plan_serialization(self):
        """Test JSON serialization and deserialization."""
        original = PTCExecutionPlan(
            execution_id="test-004",
            scaffolding=ScaffoldingSpec(
                task_description="Build API",
                requirements=["Auth", "Logging"]
            ),
            primary_llm=LLMProvider.CLAUDE,
            project_name="test-project"
        )

        # Serialize
        json_str = original.model_dump_json()

        # Deserialize
        restored = PTCExecutionPlan.model_validate_json(json_str)

        assert restored.execution_id == original.execution_id
        assert restored.scaffolding.task_description == original.scaffolding.task_description
        assert restored.scaffolding.requirements == original.scaffolding.requirements


class TestCodeArtifact:
    """Test CodeArtifact model."""

    def test_valid_artifact(self):
        """Test creating valid artifact."""
        artifact = CodeArtifact(
            file_path="src/main.py",
            content="print('Hello')",
            artifact_type=ArtifactType.SOURCE_CODE,
            language="python"
        )
        assert artifact.file_path == "src/main.py"
        assert artifact.language == "python"

    def test_file_path_normalization(self):
        """Test file path is normalized to relative path."""
        artifact = CodeArtifact(
            file_path="/absolute/path/file.py",
            content="content"
        )
        # Leading slash should be removed
        assert artifact.file_path == "absolute/path/file.py"


class TestTestResult:
    """Test TestResult model."""

    def test_successful_test_result(self):
        """Test successful test result."""
        result = TestResult(
            test_command="pytest",
            exit_code=0,
            stdout="1 passed",
            tests_passed=1,
            tests_failed=0,
            duration_seconds=0.5
        )
        assert result.success is True

    def test_failed_test_result(self):
        """Test failed test result."""
        result = TestResult(
            test_command="pytest",
            exit_code=1,
            stderr="1 failed",
            tests_passed=0,
            tests_failed=1,
            duration_seconds=0.3
        )
        assert result.success is False


class TestPTCArtifactResult:
    """Test PTCArtifactResult model."""

    def test_successful_result(self):
        """Test creating successful result."""
        now = datetime.utcnow()
        result = PTCArtifactResult(
            execution_id="test-exec-001",
            status=ExecutionStatus.SUCCESS,
            artifacts=[
                CodeArtifact(
                    file_path="main.py",
                    content="code"
                )
            ],
            started_at=now,
            completed_at=now + timedelta(seconds=10),
            duration_seconds=10.0
        )
        assert result.success is True
        assert len(result.artifacts) == 1
        assert result.duration_seconds == 10.0

    def test_cache_hit_result(self):
        """Test cache hit result."""
        now = datetime.utcnow()
        result = PTCArtifactResult(
            execution_id="test-exec-002",
            status=ExecutionStatus.CACHE_HIT,
            artifacts=[],
            from_cache=True,
            cache_key="abc123",
            started_at=now,
            completed_at=now,
            duration_seconds=0.001
        )
        assert result.success is True
        assert result.from_cache is True

    def test_failed_result(self):
        """Test failed result."""
        now = datetime.utcnow()
        result = PTCArtifactResult(
            execution_id="test-exec-003",
            status=ExecutionStatus.FAILURE,
            error_message="Code generation failed",
            started_at=now,
            completed_at=now + timedelta(seconds=5),
            duration_seconds=5.0
        )
        assert result.success is False
        assert result.error_message is not None

    def test_llm_usage_aggregation(self):
        """Test LLM usage aggregation properties."""
        result = PTCArtifactResult(
            execution_id="test-exec-004",
            status=ExecutionStatus.SUCCESS,
            llm_usage=[
                LLMUsage(
                    provider="claude",
                    model="claude-3-sonnet",
                    prompt_tokens=100,
                    completion_tokens=50,
                    total_tokens=150,
                    cost_usd=0.005
                ),
                LLMUsage(
                    provider="kimi",
                    model="kimi-1",
                    prompt_tokens=80,
                    completion_tokens=40,
                    total_tokens=120,
                    cost_usd=0.003
                )
            ],
            started_at=datetime.utcnow(),
            completed_at=datetime.utcnow(),
            duration_seconds=1.0
        )
        assert result.total_tokens_used == 270  # 150 + 120
        assert result.total_cost_usd == 0.008  # 0.005 + 0.003

    def test_result_serialization(self):
        """Test JSON serialization and deserialization."""
        now = datetime.utcnow()
        original = PTCArtifactResult(
            execution_id="test-exec-005",
            status=ExecutionStatus.SUCCESS,
            artifacts=[
                CodeArtifact(
                    file_path="test.py",
                    content="# test",
                    language="python"
                )
            ],
            iterations_used=2,
            warnings=["Warning 1", "Warning 2"],
            started_at=now,
            completed_at=now + timedelta(seconds=15),
            duration_seconds=15.0
        )

        # Serialize
        json_str = original.model_dump_json()

        # Deserialize
        restored = PTCArtifactResult.model_validate_json(json_str)

        assert restored.execution_id == original.execution_id
        assert restored.status == original.status
        assert len(restored.artifacts) == len(original.artifacts)
        assert restored.iterations_used == original.iterations_used
        assert restored.warnings == original.warnings
