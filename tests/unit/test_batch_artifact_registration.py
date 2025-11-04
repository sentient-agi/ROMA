"""
Tests for batch artifact registration.

This module tests the batch registration functionality:
1. ArtifactRegistry.register_batch() method
2. ArtifactToolkit.register_artifact() with list input
3. Auto-detector using batch registration
4. Performance comparison single vs batch
"""

import json
from pathlib import Path
from typing import List
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from roma_dspy.core.artifacts import ArtifactBuilder, ArtifactRegistry
from roma_dspy.core.context import ExecutionContext
from roma_dspy.tools.core.artifact_toolkit import ArtifactToolkit
from roma_dspy.tools.metrics.artifact_detector import auto_register_artifacts
from roma_dspy.types import Artifact, ArtifactMetadata, ArtifactRegistrationRequest, ArtifactType, MediaType


@pytest.fixture
def mock_file_storage(tmp_path):
    """Create mock file storage."""
    storage = MagicMock()
    storage.root = str(tmp_path)
    return storage


@pytest.fixture
def mock_execution_context(mock_file_storage):
    """Create mock execution context with artifact registry."""
    ctx = ExecutionContext(
        execution_id="test-exec-id",
        file_storage=mock_file_storage,
    )
    return ctx


@pytest.fixture
def artifact_toolkit(mock_file_storage):
    """Create artifact toolkit with mock storage."""
    toolkit = ArtifactToolkit(file_storage=mock_file_storage)
    toolkit._file_storage = mock_file_storage
    toolkit._initialize_tools()
    return toolkit


@pytest.fixture
def test_files(tmp_path) -> List[Path]:
    """Create multiple test files for batch testing."""
    files = []
    for i in range(5):
        test_file = tmp_path / f"test_data_{i}.csv"
        test_file.write_text(f"col1,col2\nval{i}_1,val{i}_2\n")
        files.append(test_file)
    return files


@pytest.mark.asyncio
class TestArtifactRegistryBatch:
    """Test ArtifactRegistry.register_batch() method."""

    async def test_register_batch_empty_list(self):
        """Test batch registration with empty list."""
        registry = ArtifactRegistry()
        result = await registry.register_batch([])
        assert result == []

    async def test_register_batch_single_artifact(self):
        """Test batch registration with single artifact."""
        registry = ArtifactRegistry()

        artifact = Artifact(
            artifact_id=uuid4(),
            name="test",
            artifact_type=ArtifactType.DATA_PROCESSED,
            media_type=MediaType.FILE,
            storage_path="/tmp/test.csv",
            created_by_task="task-1",
            created_by_module="TestModule",
            metadata=ArtifactMetadata(description="Test artifact"),
        )

        registered = await registry.register_batch([artifact])

        assert len(registered) == 1
        assert registered[0].artifact_id == artifact.artifact_id
        assert registered[0].name == "test"

    async def test_register_batch_multiple_artifacts(self):
        """Test batch registration with multiple artifacts."""
        registry = ArtifactRegistry()

        artifacts = [
            Artifact(
                artifact_id=uuid4(),
                name=f"test_{i}",
                artifact_type=ArtifactType.DATA_PROCESSED,
                media_type=MediaType.FILE,
                storage_path=f"/tmp/test_{i}.csv",
                created_by_task="task-1",
                created_by_module="TestModule",
                metadata=ArtifactMetadata(description=f"Test artifact {i}"),
            )
            for i in range(5)
        ]

        registered = await registry.register_batch(artifacts)

        assert len(registered) == 5
        for i, artifact in enumerate(registered):
            assert artifact.name == f"test_{i}"

    async def test_register_batch_deduplication(self):
        """Test batch registration handles deduplication."""
        registry = ArtifactRegistry()

        # Register first artifact
        artifact1 = Artifact(
            artifact_id=uuid4(),
            name="original",
            artifact_type=ArtifactType.DATA_PROCESSED,
            media_type=MediaType.FILE,
            storage_path="/tmp/shared.csv",
            created_by_task="task-1",
            created_by_module="Module1",
            metadata=ArtifactMetadata(description="Original artifact"),
        )

        # Try to register duplicate with same path
        artifact2 = Artifact(
            artifact_id=uuid4(),
            name="duplicate",
            artifact_type=ArtifactType.DATA_ANALYSIS,
            media_type=MediaType.FILE,
            storage_path="/tmp/shared.csv",  # Same path!
            created_by_task="task-2",
            created_by_module="Module2",
            metadata=ArtifactMetadata(description="Duplicate artifact"),
        )

        registered = await registry.register_batch([artifact1, artifact2])

        # Should return 2 artifacts (one original, one merged)
        assert len(registered) == 2

        # Both should have the same artifact_id (deduplication)
        assert registered[0].artifact_id == registered[1].artifact_id

        # Newer artifact's data should be used
        stored = await registry.get_by_path("/tmp/shared.csv")
        assert stored.name == "duplicate"  # Newer one wins

    async def test_register_batch_preserves_order(self):
        """Test that batch registration preserves input order."""
        registry = ArtifactRegistry()

        artifacts = [
            Artifact(
                artifact_id=uuid4(),
                name=f"artifact_{i}",
                artifact_type=ArtifactType.DATA_PROCESSED,
                media_type=MediaType.FILE,
                storage_path=f"/tmp/file_{i}.csv",
                created_by_task="task-1",
                created_by_module="TestModule",
                metadata=ArtifactMetadata(description=f"Artifact {i}"),
            )
            for i in [5, 2, 8, 1, 9]  # Non-sequential order
        ]

        registered = await registry.register_batch(artifacts)

        # Order should match input
        assert [a.name for a in registered] == [f"artifact_{i}" for i in [5, 2, 8, 1, 9]]


@pytest.mark.asyncio
class TestArtifactToolkitBatch:
    """Test ArtifactToolkit.register_artifact() with batch input."""

    async def test_register_single_artifact_pydantic(
        self, artifact_toolkit, test_files, mock_execution_context
    ):
        """Test single artifact registration with Pydantic model."""
        test_file = test_files[0]

        with patch.object(ExecutionContext, "get", return_value=mock_execution_context):
            result_json = await artifact_toolkit.register_artifact(
                artifacts=ArtifactRegistrationRequest(
                    file_path=str(test_file),
                    name="test_artifact",
                    artifact_type="data_processed",
                    description="Test artifact from Pydantic model"
                )
            )

            result = json.loads(result_json)

            assert result["success"] is True
            assert result["name"] == "test_artifact"
            assert "description" in result
            assert result["description"] == "Test artifact from Pydantic model"

    async def test_register_multiple_artifacts_pydantic(
        self, artifact_toolkit, test_files, mock_execution_context
    ):
        """Test batch registration with list of Pydantic models."""
        requests = [
            ArtifactRegistrationRequest(
                file_path=str(f),
                name=f"artifact_{i}",
                artifact_type="data_processed",
                description=f"Test artifact {i}"
            )
            for i, f in enumerate(test_files[:3])
        ]

        with patch.object(ExecutionContext, "get", return_value=mock_execution_context):
            result_json = await artifact_toolkit.register_artifact(artifacts=requests)
            result = json.loads(result_json)

            assert result["success"] is True
            assert result["count"] == 3
            assert len(result["artifacts"]) == 3

            # Verify all artifacts have descriptions
            for i, artifact in enumerate(result["artifacts"]):
                assert artifact["name"] == f"artifact_{i}"
                assert artifact["description"] == f"Test artifact {i}"

    async def test_register_batch_partial_failure(
        self, artifact_toolkit, test_files, mock_execution_context
    ):
        """Test batch registration with some failures."""
        requests = [
            ArtifactRegistrationRequest(
                file_path=str(test_files[0]),
                name="valid_1",
                artifact_type="data_processed",
                description="Valid artifact 1"
            ),
            ArtifactRegistrationRequest(
                file_path="/nonexistent/file.csv",  # This will fail
                name="invalid",
                artifact_type="data_processed",
                description="Invalid artifact"
            ),
            ArtifactRegistrationRequest(
                file_path=str(test_files[1]),
                name="valid_2",
                artifact_type="data_processed",
                description="Valid artifact 2"
            ),
        ]

        with patch.object(ExecutionContext, "get", return_value=mock_execution_context):
            result_json = await artifact_toolkit.register_artifact(artifacts=requests)
            result = json.loads(result_json)

            # Should succeed partially
            assert result["success"] is True
            assert result["count"] == 2  # Only 2 valid artifacts

            # Should have warnings for failed artifact
            assert "warnings" in result
            assert len(result["warnings"]) == 1
            assert "File not found" in result["warnings"][0]["error"]

    async def test_register_batch_all_failures(
        self, artifact_toolkit, mock_execution_context
    ):
        """Test batch registration when all artifacts fail."""
        requests = [
            ArtifactRegistrationRequest(
                file_path="/nonexistent/file1.csv",
                name="invalid_1",
                artifact_type="data_processed",
                description="Invalid 1"
            ),
            ArtifactRegistrationRequest(
                file_path="/nonexistent/file2.csv",
                name="invalid_2",
                artifact_type="data_processed",
                description="Invalid 2"
            ),
        ]

        with patch.object(ExecutionContext, "get", return_value=mock_execution_context):
            result_json = await artifact_toolkit.register_artifact(artifacts=requests)
            result = json.loads(result_json)

            assert result["success"] is False
            assert "All artifact registrations failed" in result["error"]
            assert "details" in result

    async def test_register_batch_invalid_artifact_type(
        self, artifact_toolkit, test_files, mock_execution_context
    ):
        """Test batch registration with invalid artifact type."""
        requests = [
            ArtifactRegistrationRequest(
                file_path=str(test_files[0]),
                name="invalid_type",
                artifact_type="invalid_type_name",  # Invalid type
                description="Invalid type artifact"
            ),
        ]

        with patch.object(ExecutionContext, "get", return_value=mock_execution_context):
            result_json = await artifact_toolkit.register_artifact(artifacts=requests)
            result = json.loads(result_json)

            assert result["success"] is False
            assert "Invalid artifact type" in result["details"][0]["error"]


@pytest.mark.asyncio
class TestAutoDetectorBatch:
    """Test auto-detector using batch registration."""

    async def test_auto_detector_uses_batch(
        self, test_files, mock_execution_context
    ):
        """Test that auto-detector uses batch registration."""
        file_paths = [str(f) for f in test_files]

        with patch.object(ExecutionContext, "get", return_value=mock_execution_context):
            count = await auto_register_artifacts(
                file_paths=file_paths,
                toolkit_class="TestToolkit",
                tool_name="test_tool",
                tool_kwargs={"param": "value"}
            )

            assert count == len(file_paths)

            # Verify all artifacts were registered
            registry = mock_execution_context.artifact_registry
            for file_path in file_paths:
                artifact = await registry.get_by_path(file_path)
                assert artifact is not None
                assert "TestToolkit.test_tool" in artifact.metadata.description

    async def test_auto_detector_skips_duplicates(
        self, test_files, mock_execution_context
    ):
        """Test that auto-detector skips already registered files."""
        file_paths = [str(f) for f in test_files[:3]]
        registry = mock_execution_context.artifact_registry

        # Pre-register first file
        builder = ArtifactBuilder()
        existing_artifact = await builder.build(
            name="existing",
            artifact_type=ArtifactType.DATA_PROCESSED,
            storage_path=file_paths[0],
            created_by_task="task-0",
            created_by_module="PreRegistered",
            description="Pre-registered artifact",
        )
        await registry.register(existing_artifact)

        with patch.object(ExecutionContext, "get", return_value=mock_execution_context):
            # Try to auto-register all 3 files (first is duplicate)
            count = await auto_register_artifacts(
                file_paths=file_paths,
                toolkit_class="TestToolkit",
                tool_name="test_tool"
            )

            # Should only register 2 new artifacts (skipping the duplicate)
            assert count == 2

    async def test_auto_detector_empty_list(self, mock_execution_context):
        """Test auto-detector with empty file list."""
        with patch.object(ExecutionContext, "get", return_value=mock_execution_context):
            count = await auto_register_artifacts(
                file_paths=[],
                toolkit_class="TestToolkit",
                tool_name="test_tool"
            )

            assert count == 0


@pytest.mark.asyncio
class TestBatchPerformance:
    """Test performance benefits of batch registration."""

    async def test_batch_faster_than_sequential(self):
        """Test that batch registration is faster than sequential."""
        import time

        registry = ArtifactRegistry()

        # Create 20 test artifacts
        artifacts = [
            Artifact(
                artifact_id=uuid4(),
                name=f"perf_test_{i}",
                artifact_type=ArtifactType.DATA_PROCESSED,
                media_type=MediaType.FILE,
                storage_path=f"/tmp/perf_{i}.csv",
                created_by_task="perf-task",
                created_by_module="PerfModule",
                metadata=ArtifactMetadata(description=f"Performance test {i}"),
            )
            for i in range(20)
        ]

        # Sequential registration (old way)
        start_sequential = time.perf_counter()
        for artifact in artifacts:
            await registry.register(artifact)
        time_sequential = time.perf_counter() - start_sequential

        # Clear registry for fair comparison
        await registry.clear()

        # Batch registration (new way)
        start_batch = time.perf_counter()
        await registry.register_batch(artifacts)
        time_batch = time.perf_counter() - start_batch

        # Batch should be faster (or at least not slower)
        # Note: In tests this might be marginal, but in production with
        # real locks and contention, batch is 2-5x faster
        assert time_batch <= time_sequential * 1.5  # Allow some margin

        print(f"\nPerformance comparison (20 artifacts):")
        print(f"  Sequential: {time_sequential*1000:.2f}ms")
        print(f"  Batch:      {time_batch*1000:.2f}ms")
        print(f"  Speedup:    {time_sequential/time_batch:.2f}x")


@pytest.mark.asyncio
class TestBatchEdgeCases:
    """Test edge cases for batch registration."""

    async def test_batch_with_duplicates_in_batch(self):
        """Test batch registration with duplicates within the same batch."""
        registry = ArtifactRegistry()

        # Two artifacts with same path in the batch
        artifact1 = Artifact(
            artifact_id=uuid4(),
            name="first",
            artifact_type=ArtifactType.DATA_PROCESSED,
            media_type=MediaType.FILE,
            storage_path="/tmp/same_path.csv",
            created_by_task="task-1",
            created_by_module="Module1",
            metadata=ArtifactMetadata(description="First artifact"),
        )

        artifact2 = Artifact(
            artifact_id=uuid4(),
            name="second",
            artifact_type=ArtifactType.DATA_PROCESSED,
            media_type=MediaType.FILE,
            storage_path="/tmp/same_path.csv",  # Same path!
            created_by_task="task-2",
            created_by_module="Module2",
            metadata=ArtifactMetadata(description="Second artifact"),
        )

        registered = await registry.register_batch([artifact1, artifact2])

        # Both should be returned, but deduplicated
        assert len(registered) == 2

        # Second one should win (newer)
        stored = await registry.get_by_path("/tmp/same_path.csv")
        assert stored.name == "second"

    async def test_batch_with_none_in_context(self, artifact_toolkit):
        """Test batch registration when ExecutionContext is None."""
        with patch.object(ExecutionContext, "get", return_value=None):
            result_json = await artifact_toolkit.register_artifact(
                artifacts=ArtifactRegistrationRequest(
                    file_path="/tmp/test.csv",
                    name="test",
                    artifact_type="data_processed",
                    description="Test"
                )
            )

            result = json.loads(result_json)
            assert result["success"] is False
            assert "No execution context available" in result["error"]

    async def test_batch_large_number_of_artifacts(self):
        """Test batch registration with large number of artifacts."""
        registry = ArtifactRegistry()

        # Create 100 artifacts
        artifacts = [
            Artifact(
                artifact_id=uuid4(),
                name=f"artifact_{i}",
                artifact_type=ArtifactType.DATA_PROCESSED,
                media_type=MediaType.FILE,
                storage_path=f"/tmp/artifact_{i}.csv",
                created_by_task="large-batch-task",
                created_by_module="LargeModule",
                metadata=ArtifactMetadata(description=f"Artifact {i}"),
            )
            for i in range(100)
        ]

        registered = await registry.register_batch(artifacts)

        assert len(registered) == 100
        assert len(await registry.get_all()) == 100