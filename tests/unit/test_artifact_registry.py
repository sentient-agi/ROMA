"""Unit tests for ArtifactRegistry."""

import pytest
from uuid import uuid4

from roma_dspy.core.artifacts import ArtifactRegistry
from roma_dspy.types import (
    Artifact,
    ArtifactMetadata,
    ArtifactType,
    MediaType,
)


@pytest.fixture
def registry():
    """Create empty artifact registry."""
    return ArtifactRegistry()


@pytest.fixture
def sample_artifact():
    """Create sample artifact for testing."""
    return Artifact(
        name="test.csv",
        artifact_type=ArtifactType.DATA_FETCH,
        media_type=MediaType.FILE,
        storage_path="/tmp/test.csv",
        created_by_task="task_1",
        created_by_module="Executor",
        metadata=ArtifactMetadata(description="Test data"),
    )


class TestArtifactRegistry:
    """Test ArtifactRegistry class."""

    @pytest.mark.asyncio
    async def test_register_artifact(self, registry, sample_artifact):
        """Test registering a new artifact."""
        result = await registry.register(sample_artifact)

        assert result.artifact_id == sample_artifact.artifact_id
        assert result.name == sample_artifact.name

        # Verify artifact is in registry
        retrieved = await registry.get_by_id(sample_artifact.artifact_id)
        assert retrieved is not None
        assert retrieved.artifact_id == sample_artifact.artifact_id

    @pytest.mark.asyncio
    async def test_register_duplicate_path(self, registry):
        """Test deduplication by storage_path."""
        import asyncio

        artifact1 = Artifact(
            name="test.csv",
            artifact_type=ArtifactType.DATA_FETCH,
            media_type=MediaType.FILE,
            storage_path="/tmp/test.csv",
            created_by_task="task_1",
            created_by_module="Executor",
            metadata=ArtifactMetadata(description="First version"),
        )

        # Register first
        result1 = await registry.register(artifact1)
        artifact1_id = result1.artifact_id

        # Small delay to ensure different timestamp
        await asyncio.sleep(0.01)

        artifact2 = Artifact(
            name="test_renamed.csv",
            artifact_type=ArtifactType.DATA_PROCESSED,
            media_type=MediaType.FILE,
            storage_path="/tmp/test.csv",  # Same path!
            created_by_task="task_2",
            created_by_module="Executor",
            metadata=ArtifactMetadata(description="Second version"),
        )

        # Verify second artifact has later timestamp
        assert artifact2.created_at > artifact1.created_at

        # Register second (should deduplicate)
        result2 = await registry.register(artifact2)

        # Should return same artifact_id (deduplicated)
        assert result2.artifact_id == artifact1_id

        # Should keep newer artifact's data (second one)
        assert result2.name == "test_renamed.csv"
        assert result2.artifact_type == ArtifactType.DATA_PROCESSED

    @pytest.mark.asyncio
    async def test_get_by_id(self, registry, sample_artifact):
        """Test retrieving artifact by ID."""
        await registry.register(sample_artifact)

        result = await registry.get_by_id(sample_artifact.artifact_id)

        assert result is not None
        assert result.artifact_id == sample_artifact.artifact_id

    @pytest.mark.asyncio
    async def test_get_by_id_not_found(self, registry):
        """Test retrieving non-existent artifact."""
        result = await registry.get_by_id(uuid4())

        assert result is None

    @pytest.mark.asyncio
    async def test_get_by_path(self, registry, sample_artifact):
        """Test retrieving artifact by storage path."""
        await registry.register(sample_artifact)

        result = await registry.get_by_path("/tmp/test.csv")

        assert result is not None
        assert result.storage_path == "/tmp/test.csv"

    @pytest.mark.asyncio
    async def test_get_by_path_not_found(self, registry):
        """Test retrieving artifact with non-existent path."""
        result = await registry.get_by_path("/tmp/nonexistent.csv")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_by_task(self, registry):
        """Test retrieving artifacts by task ID."""
        artifact1 = Artifact(
            name="test1.csv",
            artifact_type=ArtifactType.DATA_FETCH,
            media_type=MediaType.FILE,
            storage_path="/tmp/test1.csv",
            created_by_task="task_1",
            created_by_module="Executor",
            metadata=ArtifactMetadata(description="Test 1"),
        )

        artifact2 = Artifact(
            name="test2.csv",
            artifact_type=ArtifactType.DATA_FETCH,
            media_type=MediaType.FILE,
            storage_path="/tmp/test2.csv",
            created_by_task="task_1",  # Same task!
            created_by_module="Executor",
            metadata=ArtifactMetadata(description="Test 2"),
        )

        artifact3 = Artifact(
            name="test3.csv",
            artifact_type=ArtifactType.DATA_FETCH,
            media_type=MediaType.FILE,
            storage_path="/tmp/test3.csv",
            created_by_task="task_2",  # Different task
            created_by_module="Executor",
            metadata=ArtifactMetadata(description="Test 3"),
        )

        await registry.register(artifact1)
        await registry.register(artifact2)
        await registry.register(artifact3)

        results = await registry.get_by_task("task_1")

        assert len(results) == 2
        assert all(a.created_by_task == "task_1" for a in results)

    @pytest.mark.asyncio
    async def test_get_by_type(self, registry):
        """Test retrieving artifacts by artifact type."""
        artifact1 = Artifact(
            name="fetch.json",
            artifact_type=ArtifactType.DATA_FETCH,
            media_type=MediaType.FILE,
            storage_path="/tmp/fetch.json",
            created_by_task="task_1",
            created_by_module="Executor",
            metadata=ArtifactMetadata(description="Fetch"),
        )

        artifact2 = Artifact(
            name="report.md",
            artifact_type=ArtifactType.REPORT,
            media_type=MediaType.TEXT,
            storage_path="/tmp/report.md",
            created_by_task="task_2",
            created_by_module="Executor",
            metadata=ArtifactMetadata(description="Report"),
        )

        await registry.register(artifact1)
        await registry.register(artifact2)

        results = await registry.get_by_type(ArtifactType.DATA_FETCH)

        assert len(results) == 1
        assert results[0].artifact_type == ArtifactType.DATA_FETCH

    @pytest.mark.asyncio
    async def test_get_by_media(self, registry):
        """Test retrieving artifacts by media type."""
        artifact1 = Artifact(
            name="doc.txt",
            artifact_type=ArtifactType.DOCUMENT,
            media_type=MediaType.TEXT,
            storage_path="/tmp/doc.txt",
            created_by_task="task_1",
            created_by_module="Executor",
            metadata=ArtifactMetadata(description="Text doc"),
        )

        artifact2 = Artifact(
            name="data.parquet",
            artifact_type=ArtifactType.DATA_FETCH,
            media_type=MediaType.FILE,
            storage_path="/tmp/data.parquet",
            created_by_task="task_2",
            created_by_module="Executor",
            metadata=ArtifactMetadata(description="Binary file"),
        )

        await registry.register(artifact1)
        await registry.register(artifact2)

        results = await registry.get_by_media(MediaType.TEXT)

        assert len(results) == 1
        assert results[0].media_type == MediaType.TEXT

    @pytest.mark.asyncio
    async def test_get_all(self, registry, sample_artifact):
        """Test retrieving all artifacts."""
        artifact2 = Artifact(
            name="test2.csv",
            artifact_type=ArtifactType.DATA_FETCH,
            media_type=MediaType.FILE,
            storage_path="/tmp/test2.csv",
            created_by_task="task_2",
            created_by_module="Executor",
            metadata=ArtifactMetadata(description="Test 2"),
        )

        await registry.register(sample_artifact)
        await registry.register(artifact2)

        results = await registry.get_all()

        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_get_lineage(self, registry):
        """Test retrieving artifact lineage."""
        parent = Artifact(
            name="parent.csv",
            artifact_type=ArtifactType.DATA_FETCH,
            media_type=MediaType.FILE,
            storage_path="/tmp/parent.csv",
            created_by_task="task_1",
            created_by_module="Executor",
            metadata=ArtifactMetadata(description="Parent"),
        )

        await registry.register(parent)

        child = Artifact(
            name="child.parquet",
            artifact_type=ArtifactType.DATA_PROCESSED,
            media_type=MediaType.FILE,
            storage_path="/tmp/child.parquet",
            created_by_task="task_2",
            created_by_module="Executor",
            metadata=ArtifactMetadata(description="Child"),
            derived_from=[parent.artifact_id],
        )

        await registry.register(child)

        lineage = await registry.get_lineage(child.artifact_id)

        assert len(lineage) == 1
        assert lineage[0].artifact_id == parent.artifact_id

    @pytest.mark.asyncio
    async def test_get_descendants(self, registry):
        """Test retrieving artifact descendants."""
        parent = Artifact(
            name="parent.csv",
            artifact_type=ArtifactType.DATA_FETCH,
            media_type=MediaType.FILE,
            storage_path="/tmp/parent.csv",
            created_by_task="task_1",
            created_by_module="Executor",
            metadata=ArtifactMetadata(description="Parent"),
        )

        await registry.register(parent)

        child1 = Artifact(
            name="child1.parquet",
            artifact_type=ArtifactType.DATA_PROCESSED,
            media_type=MediaType.FILE,
            storage_path="/tmp/child1.parquet",
            created_by_task="task_2",
            created_by_module="Executor",
            metadata=ArtifactMetadata(description="Child 1"),
            derived_from=[parent.artifact_id],
        )

        child2 = Artifact(
            name="child2.parquet",
            artifact_type=ArtifactType.DATA_PROCESSED,
            media_type=MediaType.FILE,
            storage_path="/tmp/child2.parquet",
            created_by_task="task_3",
            created_by_module="Executor",
            metadata=ArtifactMetadata(description="Child 2"),
            derived_from=[parent.artifact_id],
        )

        await registry.register(child1)
        await registry.register(child2)

        descendants = await registry.get_descendants(parent.artifact_id)

        assert len(descendants) == 2
        assert all(parent.artifact_id in d.derived_from for d in descendants)

    @pytest.mark.asyncio
    async def test_remove_artifact(self, registry, sample_artifact):
        """Test removing artifact from registry."""
        await registry.register(sample_artifact)

        result = await registry.remove(sample_artifact.artifact_id)

        assert result is True

        # Verify artifact is gone
        retrieved = await registry.get_by_id(sample_artifact.artifact_id)
        assert retrieved is None

    @pytest.mark.asyncio
    async def test_remove_nonexistent(self, registry):
        """Test removing non-existent artifact."""
        result = await registry.remove(uuid4())

        assert result is False

    @pytest.mark.asyncio
    async def test_clear_registry(self, registry, sample_artifact):
        """Test clearing all artifacts."""
        artifact2 = Artifact(
            name="test2.csv",
            artifact_type=ArtifactType.DATA_FETCH,
            media_type=MediaType.FILE,
            storage_path="/tmp/test2.csv",
            created_by_task="task_2",
            created_by_module="Executor",
            metadata=ArtifactMetadata(description="Test 2"),
        )

        await registry.register(sample_artifact)
        await registry.register(artifact2)

        count = await registry.clear()

        assert count == 2

        # Verify registry is empty
        results = await registry.get_all()
        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_get_stats(self, registry):
        """Test getting registry statistics."""
        artifact1 = Artifact(
            name="fetch.json",
            artifact_type=ArtifactType.DATA_FETCH,
            media_type=MediaType.FILE,
            storage_path="/tmp/fetch.json",
            created_by_task="task_1",
            created_by_module="Executor",
            metadata=ArtifactMetadata(description="Fetch"),
        )

        artifact2 = Artifact(
            name="report.md",
            artifact_type=ArtifactType.REPORT,
            media_type=MediaType.TEXT,
            storage_path="/tmp/report.md",
            created_by_task="task_2",
            created_by_module="Executor",
            metadata=ArtifactMetadata(description="Report"),
        )

        await registry.register(artifact1)
        await registry.register(artifact2)

        stats = await registry.get_stats()

        assert stats["total_artifacts"] == 2
        assert stats["unique_tasks"] == 2
        assert "by_artifact_type" in stats
        assert "by_media_type" in stats
        assert stats["by_artifact_type"]["data_fetch"] == 1
        assert stats["by_artifact_type"]["report"] == 1
