"""
Tests for PTC artifact processor.

Tests processing and writing artifacts to filesystem.
"""

import pytest
import tempfile
from pathlib import Path
from datetime import datetime

from roma_dspy.ptc import (
    ArtifactProcessor,
    ArtifactProcessorError,
    PTCArtifactResult,
    CodeArtifact,
    TestResult,
    ExecutionStatus,
    ArtifactType,
)


@pytest.fixture
def temp_dir():
    """Create a temporary directory for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def sample_artifact():
    """Create a sample code artifact."""
    return CodeArtifact(
        file_path="src/main.py",
        content="print('Hello World')",
        artifact_type=ArtifactType.SOURCE_CODE,
        language="python",
        description="Main entry point"
    )


@pytest.fixture
def sample_result_with_artifacts():
    """Create a sample result with multiple artifacts."""
    now = datetime.utcnow()
    return PTCArtifactResult(
        execution_id="test-001",
        status=ExecutionStatus.SUCCESS,
        artifacts=[
            CodeArtifact(
                file_path="main.py",
                content="print('Hello')",
                artifact_type=ArtifactType.SOURCE_CODE,
                language="python"
            ),
            CodeArtifact(
                file_path="tests/test_main.py",
                content="def test_main(): pass",
                artifact_type=ArtifactType.TEST,
                language="python"
            ),
            CodeArtifact(
                file_path="README.md",
                content="# Project",
                artifact_type=ArtifactType.DOCUMENTATION
            )
        ],
        test_results=TestResult(
            test_command="pytest",
            exit_code=0,
            stdout="1 passed",
            tests_passed=1,
            tests_failed=0,
            duration_seconds=0.5
        ),
        started_at=now,
        completed_at=now,
        duration_seconds=1.0
    )


class TestArtifactProcessor:
    """Test basic artifact processor functionality."""

    def test_write_single_artifact(self, temp_dir, sample_artifact):
        """Test writing a single artifact."""
        processor = ArtifactProcessor(base_path=temp_dir)

        written = processor.write_artifact(sample_artifact)

        assert written is True
        file_path = temp_dir / "src" / "main.py"
        assert file_path.exists()
        assert file_path.read_text() == "print('Hello World')"

    def test_process_result(self, temp_dir, sample_result_with_artifacts):
        """Test processing a complete result."""
        processor = ArtifactProcessor(base_path=temp_dir)

        stats = processor.process_result(sample_result_with_artifacts)

        assert stats["written"] == 3
        assert stats["skipped"] == 0
        assert stats["errors"] == 0
        assert stats["total_artifacts"] == 3

        # Verify files exist
        assert (temp_dir / "main.py").exists()
        assert (temp_dir / "tests" / "test_main.py").exists()
        assert (temp_dir / "README.md").exists()

    def test_overwrite_existing_file(self, temp_dir, sample_artifact):
        """Test overwriting existing files."""
        processor = ArtifactProcessor(base_path=temp_dir, overwrite=True)

        # Write once
        (temp_dir / "src").mkdir(parents=True)
        (temp_dir / "src" / "main.py").write_text("old content")

        # Write again (should overwrite)
        written = processor.write_artifact(sample_artifact)

        assert written is True
        content = (temp_dir / "src" / "main.py").read_text()
        assert content == "print('Hello World')"

    def test_skip_existing_file(self, temp_dir, sample_artifact):
        """Test skipping existing files when overwrite=False."""
        processor = ArtifactProcessor(base_path=temp_dir, overwrite=False)

        # Create existing file
        (temp_dir / "src").mkdir(parents=True)
        (temp_dir / "src" / "main.py").write_text("existing content")

        # Try to write (should skip)
        written = processor.write_artifact(sample_artifact)

        assert written is False
        # Content should be unchanged
        content = (temp_dir / "src" / "main.py").read_text()
        assert content == "existing content"

    def test_create_directories(self, temp_dir, sample_artifact):
        """Test automatic directory creation."""
        processor = ArtifactProcessor(base_path=temp_dir, create_dirs=True)

        # Directory doesn't exist yet
        assert not (temp_dir / "src").exists()

        written = processor.write_artifact(sample_artifact)

        assert written is True
        # Directory should be created
        assert (temp_dir / "src").exists()
        assert (temp_dir / "src" / "main.py").exists()

    def test_dry_run_mode(self, temp_dir, sample_artifact):
        """Test dry run mode doesn't write files."""
        processor = ArtifactProcessor(base_path=temp_dir, dry_run=True)

        written = processor.write_artifact(sample_artifact)

        assert written is True  # Returns True but doesn't write
        # File should NOT exist
        assert not (temp_dir / "src" / "main.py").exists()

    def test_files_by_type_statistics(self, temp_dir, sample_result_with_artifacts):
        """Test files_by_type statistics."""
        processor = ArtifactProcessor(base_path=temp_dir)

        stats = processor.process_result(sample_result_with_artifacts)

        assert stats["files_by_type"]["source_code"] == 1
        assert stats["files_by_type"]["test"] == 1
        assert stats["files_by_type"]["documentation"] == 1


class TestArtifactProcessorValidation:
    """Test validation functionality."""

    def test_validate_successful_result(self, sample_result_with_artifacts):
        """Test validation of successful result."""
        processor = ArtifactProcessor()

        warnings = processor.validate_result(sample_result_with_artifacts)

        assert len(warnings) == 0  # No warnings for successful result

    def test_validate_failed_result(self):
        """Test validation of failed result."""
        processor = ArtifactProcessor()

        failed_result = PTCArtifactResult(
            execution_id="test-002",
            status=ExecutionStatus.FAILURE,
            error_message="Code generation failed",
            started_at=datetime.utcnow(),
            completed_at=datetime.utcnow(),
            duration_seconds=1.0
        )

        warnings = processor.validate_result(failed_result)

        assert len(warnings) > 0
        assert any("FAILURE" in w for w in warnings)

    def test_validate_no_artifacts(self):
        """Test validation warns when no artifacts."""
        processor = ArtifactProcessor()

        result = PTCArtifactResult(
            execution_id="test-003",
            status=ExecutionStatus.SUCCESS,
            artifacts=[],  # No artifacts
            started_at=datetime.utcnow(),
            completed_at=datetime.utcnow(),
            duration_seconds=1.0
        )

        warnings = processor.validate_result(result)

        assert any("No artifacts" in w for w in warnings)

    def test_validate_duplicate_paths(self):
        """Test validation detects duplicate file paths."""
        processor = ArtifactProcessor()

        result = PTCArtifactResult(
            execution_id="test-004",
            status=ExecutionStatus.SUCCESS,
            artifacts=[
                CodeArtifact(file_path="main.py", content="v1"),
                CodeArtifact(file_path="main.py", content="v2"),  # Duplicate!
            ],
            started_at=datetime.utcnow(),
            completed_at=datetime.utcnow(),
            duration_seconds=1.0
        )

        warnings = processor.validate_result(result)

        assert any("Duplicate file paths" in w for w in warnings)

    def test_validate_failed_tests(self, sample_result_with_artifacts):
        """Test validation detects failed tests."""
        processor = ArtifactProcessor()

        # Modify to have failed tests
        sample_result_with_artifacts.test_results.tests_failed = 2
        sample_result_with_artifacts.test_results.exit_code = 1

        warnings = processor.validate_result(sample_result_with_artifacts)

        assert any("test(s) failed" in w for w in warnings)

    def test_process_with_validation(self, temp_dir, sample_result_with_artifacts):
        """Test process_with_validation."""
        processor = ArtifactProcessor(base_path=temp_dir)

        stats = processor.process_with_validation(sample_result_with_artifacts)

        assert "validation_warnings" in stats
        assert stats["written"] == 3

    def test_process_with_validation_fail_on_warnings(self):
        """Test fail_on_warnings raises exception."""
        processor = ArtifactProcessor()

        failed_result = PTCArtifactResult(
            execution_id="test-005",
            status=ExecutionStatus.FAILURE,
            error_message="Failed",
            started_at=datetime.utcnow(),
            completed_at=datetime.utcnow(),
            duration_seconds=1.0
        )

        with pytest.raises(ArtifactProcessorError, match="Validation failed"):
            processor.process_with_validation(
                failed_result,
                fail_on_warnings=True
            )


class TestArtifactProcessorSummary:
    """Test summary generation."""

    def test_get_artifact_summary(self, sample_result_with_artifacts):
        """Test artifact summary generation."""
        processor = ArtifactProcessor()

        summary = processor.get_artifact_summary(sample_result_with_artifacts)

        assert "test-001" in summary
        assert "SUCCESS" in summary
        assert "3" in summary  # 3 artifacts
        assert "main.py" in summary
        assert "Test Results:" in summary
        assert "Passed: 1" in summary

    def test_summary_with_llm_usage(self):
        """Test summary includes LLM usage when present."""
        from roma_dspy.ptc import LLMUsage

        now = datetime.utcnow()
        result = PTCArtifactResult(
            execution_id="test-006",
            status=ExecutionStatus.SUCCESS,
            artifacts=[
                CodeArtifact(file_path="main.py", content="code")
            ],
            llm_usage=[
                LLMUsage(
                    provider="claude",
                    model="claude-3-sonnet",
                    prompt_tokens=100,
                    completion_tokens=50,
                    total_tokens=150,
                    api_calls=1,
                    cost_usd=0.005
                )
            ],
            started_at=now,
            completed_at=now,
            duration_seconds=1.0
        )

        processor = ArtifactProcessor()
        summary = processor.get_artifact_summary(result)

        assert "LLM Usage:" in summary
        assert "150" in summary  # Total tokens
        assert "$0.0050" in summary  # Cost
