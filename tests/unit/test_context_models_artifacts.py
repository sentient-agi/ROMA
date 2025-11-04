"""
Unit tests for artifact integration in context models.

Tests that context models can include artifact references and serialize them to XML.
"""

import pytest
from uuid import uuid4
from roma_dspy.core.context.models import (
    ExecutorSpecificContext,
    PlannerSpecificContext,
    DependencyResult,
)
from roma_dspy.types.artifact_models import ArtifactReference
from roma_dspy.types import ArtifactType


@pytest.fixture
def sample_artifact_reference():
    """Create a sample artifact reference for testing."""
    return ArtifactReference(
        artifact_id=uuid4(),
        name="bitcoin_prices.parquet",
        artifact_type=ArtifactType.DATA_FETCH,
        storage_path="/path/to/bitcoin_prices.parquet",
        description="Bitcoin price data for last 30 days (10 rows, 5 columns)",
        created_by_task="task_001",
        relevance_score=0.95,
    )


class TestExecutorSpecificContextWithArtifacts:
    """Test ExecutorSpecificContext with artifact references."""

    def test_empty_artifacts_field(self):
        """Test that available_artifacts field exists and defaults to empty list."""
        context = ExecutorSpecificContext(dependency_results=[])
        assert hasattr(context, "available_artifacts")
        assert context.available_artifacts == []

    def test_add_single_artifact_reference(self, sample_artifact_reference):
        """Test adding a single artifact reference."""
        context = ExecutorSpecificContext(
            dependency_results=[],
            available_artifacts=[sample_artifact_reference]
        )
        assert len(context.available_artifacts) == 1
        assert context.available_artifacts[0].name == "bitcoin_prices.parquet"

    def test_add_multiple_artifact_references(self, sample_artifact_reference):
        """Test adding multiple artifact references."""
        artifact2 = ArtifactReference(
            artifact_id=uuid4(),
            name="analysis.md",
            artifact_type=ArtifactType.REPORT,
            storage_path="/path/to/analysis.md",
            description="Analysis report",
            created_by_task="task_002",
        )

        context = ExecutorSpecificContext(
            dependency_results=[],
            available_artifacts=[sample_artifact_reference, artifact2]
        )
        assert len(context.available_artifacts) == 2

    def test_to_xml_with_artifacts(self, sample_artifact_reference):
        """Test XML serialization with artifacts."""
        context = ExecutorSpecificContext(
            dependency_results=[
                DependencyResult(
                    goal="Fetch Bitcoin price data",
                    output="Fetched 30 days of data"
                )
            ],
            available_artifacts=[sample_artifact_reference]
        )

        xml = context.to_xml()
        assert "<executor_specific>" in xml
        assert "<dependency_results>" in xml
        assert "<available_artifacts>" in xml
        assert "bitcoin_prices.parquet" in xml
        assert "data_fetch" in xml  # Enum values are lowercase in XML
        assert "</executor_specific>" in xml

    def test_to_xml_empty_artifacts(self):
        """Test XML serialization with no artifacts."""
        context = ExecutorSpecificContext(
            dependency_results=[],
            available_artifacts=[]
        )

        xml = context.to_xml()
        # Should handle empty artifacts gracefully (either omit section or show empty)
        assert "<executor_specific>" in xml

    def test_backward_compatibility(self):
        """Test that context works without available_artifacts parameter (backward compat)."""
        # Old code that doesn't pass available_artifacts should still work
        context = ExecutorSpecificContext(
            dependency_results=[
                DependencyResult(goal="Task", output="Result")
            ]
        )
        assert hasattr(context, "available_artifacts")
        assert context.available_artifacts == []


class TestPlannerSpecificContextWithArtifacts:
    """Test PlannerSpecificContext with artifact references."""

    def test_empty_artifacts_field(self):
        """Test that available_artifacts field exists and defaults to empty list."""
        context = PlannerSpecificContext(parent_results=[], sibling_results=[])
        assert hasattr(context, "available_artifacts")
        assert context.available_artifacts == []

    def test_add_artifact_references(self, sample_artifact_reference):
        """Test adding artifact references to planner context."""
        context = PlannerSpecificContext(
            parent_results=[],
            sibling_results=[],
            available_artifacts=[sample_artifact_reference]
        )
        assert len(context.available_artifacts) == 1

    def test_to_xml_with_artifacts(self, sample_artifact_reference):
        """Test XML serialization with artifacts in planner context."""
        context = PlannerSpecificContext(
            parent_results=[],
            sibling_results=[],
            available_artifacts=[sample_artifact_reference]
        )

        xml = context.to_xml()
        assert "<planner_specific>" in xml
        assert "<available_artifacts>" in xml
        assert "bitcoin_prices.parquet" in xml


class TestArtifactReferenceXMLFormat:
    """Test XML formatting of artifact references."""

    def test_artifact_xml_format(self, sample_artifact_reference):
        """Test that artifact reference serializes to correct XML format."""
        xml = sample_artifact_reference.to_xml_element()

        # Check attributes
        assert f'id="{sample_artifact_reference.artifact_id}"' in xml
        assert 'name="bitcoin_prices.parquet"' in xml
        assert 'type="data_fetch"' in xml  # lowercase enum value
        assert 'task="task_001"' in xml
        assert 'relevance="0.95"' in xml

        # Check content
        assert "Bitcoin price data for last 30 days" in xml

    def test_artifact_xml_without_relevance(self):
        """Test artifact XML without relevance score."""
        artifact = ArtifactReference(
            artifact_id=uuid4(),
            name="test.txt",
            artifact_type=ArtifactType.REPORT,
            storage_path="/path/to/test.txt",
            description="Test file",
            created_by_task="task_003",
            relevance_score=None,
        )

        xml = artifact.to_xml_element()
        assert 'relevance=' not in xml  # Should omit relevance attribute if None


class TestArtifactListXMLSerialization:
    """Test serialization of multiple artifacts in context."""

    def test_multiple_artifacts_in_xml(self, sample_artifact_reference):
        """Test that multiple artifacts serialize correctly."""
        artifact2 = ArtifactReference(
            artifact_id=uuid4(),
            name="chart.png",
            artifact_type=ArtifactType.PLOT,
            storage_path="/path/to/chart.png",
            description="Price trend chart",
            created_by_task="task_002",
        )

        context = ExecutorSpecificContext(
            dependency_results=[],
            available_artifacts=[sample_artifact_reference, artifact2]
        )

        xml = context.to_xml()

        # Both artifacts should be in XML
        assert xml.count("<artifact ") == 2
        assert "bitcoin_prices.parquet" in xml
        assert "chart.png" in xml
        assert "data_fetch" in xml  # Enum values are lowercase in XML
        assert "plot" in xml  # Enum values are lowercase in XML

    def test_artifact_ordering_preserved(self):
        """Test that artifact order is preserved in XML."""
        artifacts = [
            ArtifactReference(
                artifact_id=uuid4(),
                name=f"file_{i}.txt",
                artifact_type=ArtifactType.REPORT,
                storage_path=f"/path/file_{i}.txt",
                description=f"File {i}",
                created_by_task=f"task_{i}",
            )
            for i in range(3)
        ]

        context = ExecutorSpecificContext(
            dependency_results=[],
            available_artifacts=artifacts
        )

        xml = context.to_xml()

        # Check order is preserved
        idx_0 = xml.find("file_0.txt")
        idx_1 = xml.find("file_1.txt")
        idx_2 = xml.find("file_2.txt")

        assert idx_0 < idx_1 < idx_2
