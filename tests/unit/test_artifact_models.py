"""Unit tests for artifact Pydantic models."""

import pytest
from datetime import datetime
from uuid import UUID, uuid4

from roma_dspy.types import (
    ArtifactMetadata,
    Artifact,
    ArtifactReference,
    ArtifactType,
    MediaType,
)


class TestArtifactMetadata:
    """Test ArtifactMetadata model."""

    def test_minimal_metadata(self):
        """Test creating metadata with minimal fields."""
        metadata = ArtifactMetadata(description="Test artifact")

        assert metadata.description == "Test artifact"
        assert metadata.mime_type is None
        assert metadata.size_bytes is None
        assert metadata.row_count is None
        assert metadata.column_count is None
        assert metadata.data_schema is None
        assert metadata.preview is None
        assert metadata.usage_hints is None
        assert metadata.custom == {}

    def test_full_metadata(self):
        """Test creating metadata with all fields."""
        schema = {"col1": "int64", "col2": "string"}
        usage_hints = ["Use for analysis", "Filter by date"]
        custom = {"key": "value"}

        metadata = ArtifactMetadata(
            description="Full metadata test",
            mime_type="text/csv",
            size_bytes=1024,
            row_count=100,
            column_count=2,
            data_schema=schema,
            preview="col1,col2\n1,test",
            usage_hints=usage_hints,
            custom=custom,
        )

        assert metadata.description == "Full metadata test"
        assert metadata.mime_type == "text/csv"
        assert metadata.size_bytes == 1024
        assert metadata.row_count == 100
        assert metadata.column_count == 2
        assert metadata.data_schema == schema
        assert metadata.preview == "col1,col2\n1,test"
        assert metadata.usage_hints == usage_hints
        assert metadata.custom == custom

    def test_preview_truncation(self):
        """Test that preview is truncated to 1000 chars."""
        long_preview = "x" * 1500
        metadata = ArtifactMetadata(
            description="Test", preview=long_preview
        )

        assert len(metadata.preview) == 1000
        assert metadata.preview.endswith("...")

    def test_negative_size_validation(self):
        """Test that negative size is rejected."""
        with pytest.raises(ValueError):
            ArtifactMetadata(description="Test", size_bytes=-1)

    def test_negative_row_count_validation(self):
        """Test that negative row count is rejected."""
        with pytest.raises(ValueError):
            ArtifactMetadata(description="Test", row_count=-1)


class TestArtifact:
    """Test Artifact model."""

    def test_minimal_artifact(self):
        """Test creating artifact with minimal fields."""
        artifact = Artifact(
            name="test.csv",
            artifact_type=ArtifactType.DATA_FETCH,
            media_type=MediaType.FILE,
            storage_path="/tmp/test.csv",
            created_by_task="task_1",
            created_by_module="Executor",
            metadata=ArtifactMetadata(description="Test data"),
        )

        assert artifact.name == "test.csv"
        assert artifact.artifact_type == ArtifactType.DATA_FETCH
        assert artifact.media_type == MediaType.FILE
        assert artifact.storage_path == "/tmp/test.csv"
        assert artifact.created_by_task == "task_1"
        assert artifact.created_by_module == "Executor"
        assert isinstance(artifact.artifact_id, UUID)
        assert isinstance(artifact.created_at, datetime)
        assert artifact.derived_from == []

    def test_artifact_with_lineage(self):
        """Test artifact with parent lineage."""
        parent_id = uuid4()
        artifact = Artifact(
            name="processed.parquet",
            artifact_type=ArtifactType.DATA_PROCESSED,
            media_type=MediaType.FILE,
            storage_path="/tmp/processed.parquet",
            created_by_task="task_2",
            created_by_module="Executor",
            metadata=ArtifactMetadata(description="Processed data"),
            derived_from=[parent_id],
        )

        assert artifact.derived_from == [parent_id]

    def test_relative_path_validation(self):
        """Test that relative paths are rejected."""
        with pytest.raises(ValueError, match="must be absolute"):
            Artifact(
                name="test.csv",
                artifact_type=ArtifactType.DATA_FETCH,
                media_type=MediaType.FILE,
                storage_path="relative/path.csv",
                created_by_task="task_1",
                created_by_module="Executor",
                metadata=ArtifactMetadata(description="Test"),
            )

    def test_path_traversal_validation(self):
        """Test that path traversal is rejected."""
        with pytest.raises(ValueError, match="Path traversal detected|Invalid storage path"):
            Artifact(
                name="test.csv",
                artifact_type=ArtifactType.DATA_FETCH,
                media_type=MediaType.FILE,
                storage_path="/tmp/../etc/passwd",
                created_by_task="task_1",
                created_by_module="Executor",
                metadata=ArtifactMetadata(description="Test"),
            )

    def test_model_dump_summary(self):
        """Test model_dump_summary output."""
        artifact = Artifact(
            artifact_id=uuid4(),
            name="test.csv",
            artifact_type=ArtifactType.DATA_FETCH,
            media_type=MediaType.FILE,
            storage_path="/tmp/test.csv",
            created_by_task="task_1",
            created_by_module="Executor",
            metadata=ArtifactMetadata(description="Test data"),
        )

        summary = artifact.model_dump_summary()

        assert "artifact_id" in summary
        assert summary["name"] == "test.csv"
        assert summary["type"] == "data_fetch"
        assert summary["media"] == "file"
        assert summary["path"] == "/tmp/test.csv"
        assert summary["created_by"] == "Executor/task_1"
        assert summary["description"] == "Test data"


class TestArtifactReference:
    """Test ArtifactReference model."""

    def test_minimal_reference(self):
        """Test creating reference with minimal fields."""
        ref = ArtifactReference(
            artifact_id=uuid4(),
            name="test.csv",
            artifact_type=ArtifactType.DATA_FETCH,
            storage_path="/tmp/test.csv",
            description="Test data",
            created_by_task="task_1",
        )

        assert ref.name == "test.csv"
        assert ref.artifact_type == ArtifactType.DATA_FETCH
        assert ref.storage_path == "/tmp/test.csv"
        assert ref.description == "Test data"
        assert ref.created_by_task == "task_1"
        assert ref.relevance_score is None

    def test_reference_with_relevance(self):
        """Test reference with relevance score."""
        ref = ArtifactReference(
            artifact_id=uuid4(),
            name="test.csv",
            artifact_type=ArtifactType.DATA_FETCH,
            storage_path="/tmp/test.csv",
            description="Test data",
            created_by_task="task_1",
            relevance_score=0.95,
        )

        assert ref.relevance_score == 0.95

    def test_relevance_score_validation(self):
        """Test relevance score bounds validation."""
        # Too low
        with pytest.raises(ValueError):
            ArtifactReference(
                artifact_id=uuid4(),
                name="test.csv",
                artifact_type=ArtifactType.DATA_FETCH,
                storage_path="/tmp/test.csv",
                description="Test",
                created_by_task="task_1",
                relevance_score=-0.1,
            )

        # Too high
        with pytest.raises(ValueError):
            ArtifactReference(
                artifact_id=uuid4(),
                name="test.csv",
                artifact_type=ArtifactType.DATA_FETCH,
                storage_path="/tmp/test.csv",
                description="Test",
                created_by_task="task_1",
                relevance_score=1.1,
            )

    def test_from_artifact(self):
        """Test creating reference from full artifact."""
        artifact = Artifact(
            name="test.csv",
            artifact_type=ArtifactType.DATA_FETCH,
            media_type=MediaType.FILE,
            storage_path="/tmp/test.csv",
            created_by_task="task_1",
            created_by_module="Executor",
            metadata=ArtifactMetadata(description="Test data"),
        )

        ref = ArtifactReference.from_artifact(artifact, relevance_score=0.8)

        assert ref.artifact_id == artifact.artifact_id
        assert ref.name == artifact.name
        assert ref.artifact_type == artifact.artifact_type
        assert ref.storage_path == artifact.storage_path
        assert ref.description == artifact.metadata.description
        assert ref.created_by_task == artifact.created_by_task
        assert ref.relevance_score == 0.8

    def test_to_xml_element_without_relevance(self):
        """Test XML serialization without relevance score."""
        artifact_id = uuid4()
        ref = ArtifactReference(
            artifact_id=artifact_id,
            name="test.csv",
            artifact_type=ArtifactType.DATA_FETCH,
            storage_path="/tmp/test.csv",
            description="Test data",
            created_by_task="task_1",
        )

        xml = ref.to_xml_element()

        assert f'id="{artifact_id}"' in xml
        assert 'name="test.csv"' in xml
        assert 'type="data_fetch"' in xml
        assert 'task="task_1"' in xml
        assert "Test data" in xml
        assert "relevance=" not in xml

    def test_to_xml_element_with_relevance(self):
        """Test XML serialization with relevance score."""
        artifact_id = uuid4()
        ref = ArtifactReference(
            artifact_id=artifact_id,
            name="test.csv",
            artifact_type=ArtifactType.DATA_FETCH,
            storage_path="/tmp/test.csv",
            description="Test data",
            created_by_task="task_1",
            relevance_score=0.9,
        )

        xml = ref.to_xml_element()

        assert f'id="{artifact_id}"' in xml
        assert 'relevance="0.9"' in xml
