"""
Unit tests for ArtifactQueryService.

Tests the service that queries artifacts based on injection modes.
"""

import pytest
import pytest_asyncio
from uuid import uuid4
from pathlib import Path
from roma_dspy.core.artifacts.query_service import ArtifactQueryService
from roma_dspy.core.artifacts.artifact_registry import ArtifactRegistry
from roma_dspy.types.artifact_models import Artifact, ArtifactMetadata
from roma_dspy.types import ArtifactType, MediaType
from roma_dspy.types.artifact_injection import ArtifactInjectionMode


@pytest_asyncio.fixture
async def registry_with_artifacts():
    """Create registry with sample artifacts from different tasks."""
    registry = ArtifactRegistry()

    # Task 1 artifacts
    artifact1 = Artifact(
        artifact_id=uuid4(),
        name="data_fetch.parquet",
        artifact_type=ArtifactType.DATA_FETCH,
        media_type=MediaType.FILE,
        storage_path="/execution/artifacts/data_fetch.parquet",
        created_by_task="task_001",
        created_by_module="Executor",
        metadata=ArtifactMetadata(description="Fetched data", size_bytes=1024),
    )
    await registry.register(artifact1)

    # Task 2 artifacts
    artifact2 = Artifact(
        artifact_id=uuid4(),
        name="analysis.md",
        artifact_type=ArtifactType.DATA_ANALYSIS,
        media_type=MediaType.TEXT,
        storage_path="/execution/artifacts/analysis.md",
        created_by_task="task_002",
        created_by_module="Executor",
        metadata=ArtifactMetadata(description="Analysis report", size_bytes=512),
    )
    await registry.register(artifact2)

    # Task 3 artifacts
    artifact3 = Artifact(
        artifact_id=uuid4(),
        name="chart.png",
        artifact_type=ArtifactType.PLOT,
        media_type=MediaType.IMAGE,
        storage_path="/execution/artifacts/chart.png",
        created_by_task="task_003",
        created_by_module="Executor",
        metadata=ArtifactMetadata(description="Price chart", size_bytes=2048),
    )
    await registry.register(artifact3)

    return registry


@pytest.fixture
def query_service():
    """Create ArtifactQueryService instance."""
    return ArtifactQueryService()


class TestArtifactQueryServiceDependenciesMode:
    """Test DEPENDENCIES injection mode."""

    @pytest.mark.asyncio
    async def test_query_single_dependency(self, registry_with_artifacts, query_service):
        """Test querying artifacts from a single dependency task."""
        references = await query_service.get_artifacts_for_dependencies(
            registry=registry_with_artifacts,
            dependency_task_ids=["task_001"],
            mode=ArtifactInjectionMode.DEPENDENCIES
        )

        assert len(references) == 1
        assert references[0].name == "data_fetch.parquet"
        assert references[0].created_by_task == "task_001"

    @pytest.mark.asyncio
    async def test_query_multiple_dependencies(self, registry_with_artifacts, query_service):
        """Test querying artifacts from multiple dependency tasks."""
        references = await query_service.get_artifacts_for_dependencies(
            registry=registry_with_artifacts,
            dependency_task_ids=["task_001", "task_002"],
            mode=ArtifactInjectionMode.DEPENDENCIES
        )

        assert len(references) == 2
        task_ids = {ref.created_by_task for ref in references}
        assert task_ids == {"task_001", "task_002"}

    @pytest.mark.asyncio
    async def test_query_no_dependencies(self, registry_with_artifacts, query_service):
        """Test querying with no dependencies returns empty list."""
        references = await query_service.get_artifacts_for_dependencies(
            registry=registry_with_artifacts,
            dependency_task_ids=[],
            mode=ArtifactInjectionMode.DEPENDENCIES
        )

        assert references == []

    @pytest.mark.asyncio
    async def test_query_nonexistent_task(self, registry_with_artifacts, query_service):
        """Test querying for task with no artifacts returns empty."""
        references = await query_service.get_artifacts_for_dependencies(
            registry=registry_with_artifacts,
            dependency_task_ids=["task_999"],
            mode=ArtifactInjectionMode.DEPENDENCIES
        )

        assert references == []


class TestArtifactQueryServiceFullMode:
    """Test FULL injection mode."""

    @pytest.mark.asyncio
    async def test_query_all_artifacts(self, registry_with_artifacts, query_service):
        """Test querying all artifacts in FULL mode."""
        references = await query_service.get_all_artifacts(
            registry=registry_with_artifacts,
            mode=ArtifactInjectionMode.FULL
        )

        assert len(references) == 3
        names = {ref.name for ref in references}
        assert names == {"data_fetch.parquet", "analysis.md", "chart.png"}

    @pytest.mark.asyncio
    async def test_full_mode_with_empty_registry(self, query_service):
        """Test FULL mode with empty registry."""
        empty_registry = ArtifactRegistry()
        references = await query_service.get_all_artifacts(
            registry=empty_registry,
            mode=ArtifactInjectionMode.FULL
        )

        assert references == []


class TestArtifactQueryServiceNoneMode:
    """Test NONE injection mode."""

    @pytest.mark.asyncio
    async def test_none_mode_returns_empty(self, registry_with_artifacts, query_service):
        """Test that NONE mode always returns empty list."""
        references = await query_service.get_artifacts_for_dependencies(
            registry=registry_with_artifacts,
            dependency_task_ids=["task_001", "task_002"],
            mode=ArtifactInjectionMode.NONE
        )

        assert references == []


class TestArtifactReferenceConversion:
    """Test conversion from Artifact to ArtifactReference."""

    @pytest.mark.asyncio
    async def test_reference_has_correct_fields(self, registry_with_artifacts, query_service):
        """Test that ArtifactReference has all necessary fields."""
        references = await query_service.get_artifacts_for_dependencies(
            registry=registry_with_artifacts,
            dependency_task_ids=["task_001"],
            mode=ArtifactInjectionMode.DEPENDENCIES
        )

        ref = references[0]
        assert hasattr(ref, "artifact_id")
        assert hasattr(ref, "name")
        assert hasattr(ref, "artifact_type")
        assert hasattr(ref, "storage_path")
        assert hasattr(ref, "description")
        assert hasattr(ref, "created_by_task")
        assert ref.description == "Fetched data"

    @pytest.mark.asyncio
    async def test_reference_is_lightweight(self, registry_with_artifacts, query_service):
        """Test that references don't include heavy metadata."""
        references = await query_service.get_artifacts_for_dependencies(
            registry=registry_with_artifacts,
            dependency_task_ids=["task_001"],
            mode=ArtifactInjectionMode.DEPENDENCIES
        )

        ref = references[0]
        # Should not have full metadata object
        assert not hasattr(ref, "metadata")
        # Should have extracted description from metadata
        assert ref.description is not None


class TestArtifactQueryServiceDeduplication:
    """Test deduplication of artifacts."""

    @pytest.mark.asyncio
    async def test_no_duplicate_artifacts(self, registry_with_artifacts, query_service):
        """Test that duplicate task IDs don't cause duplicate artifacts."""
        references = await query_service.get_artifacts_for_dependencies(
            registry=registry_with_artifacts,
            dependency_task_ids=["task_001", "task_001"],  # Duplicate
            mode=ArtifactInjectionMode.DEPENDENCIES
        )

        assert len(references) == 1  # Should be deduplicated
        assert references[0].created_by_task == "task_001"


class TestArtifactQueryServiceOrdering:
    """Test artifact ordering in results."""

    @pytest.mark.asyncio
    async def test_artifacts_ordered_by_task(self, query_service):
        """Test that artifacts maintain consistent ordering."""
        registry = ArtifactRegistry()

        # Add artifacts in specific order
        for i in range(3):
            artifact = Artifact(
                artifact_id=uuid4(),
                name=f"file_{i}.txt",
                artifact_type=ArtifactType.REPORT,
                media_type=MediaType.TEXT,
                storage_path=f"/path/file_{i}.txt",
                created_by_task=f"task_{i:03d}",
                created_by_module="Executor",
                metadata=ArtifactMetadata(description=f"File {i}"),
            )
            await registry.register(artifact)

        references = await query_service.get_all_artifacts(
            registry=registry,
            mode=ArtifactInjectionMode.FULL
        )

        # Check order is preserved
        names = [ref.name for ref in references]
        assert names == ["file_0.txt", "file_1.txt", "file_2.txt"]


class TestArtifactQueryServiceSubtaskMode:
    """Test SUBTASK injection mode."""

    @pytest.mark.asyncio
    async def test_subtask_mode_placeholder(self, registry_with_artifacts, query_service):
        """Test SUBTASK mode with mock DAG."""
        from unittest.mock import Mock

        # Create a simple mock DAG
        mock_dag = Mock()
        mock_task = Mock()
        mock_task.subgraph_id = None  # Task without subgraph
        mock_dag.find_node.return_value = mock_task
        mock_dag.get_all_tasks.return_value = []

        references = await query_service.get_artifacts_for_subtask(
            registry=registry_with_artifacts,
            dag=mock_dag,
            current_task_id="task_002",
            mode=ArtifactInjectionMode.SUBTASK
        )

        # Should return list (may be empty if task has no subgraph)
        assert isinstance(references, list)