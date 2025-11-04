"""
Tests for artifact description propagation.

This module tests that artifact descriptions are properly:
1. Returned in tool outputs (register_artifact)
2. Stored in registry
3. Injected into agent context
4. Available to downstream tasks
"""

import json
from pathlib import Path
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from roma_dspy.core.artifacts import ArtifactBuilder, ArtifactRegistry
from roma_dspy.core.artifacts.query_service import ArtifactQueryService
from roma_dspy.core.context import ExecutionContext
from roma_dspy.tools.core.artifact_toolkit import ArtifactToolkit
from roma_dspy.tools.metrics.artifact_detector import auto_register_artifacts
from roma_dspy.types import Artifact, ArtifactMetadata, ArtifactReference, ArtifactType, MediaType
from roma_dspy.types.artifact_injection import ArtifactInjectionMode


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
    # ExecutionContext creates artifact_registry internally
    return ctx


@pytest.fixture
def artifact_toolkit(mock_file_storage):
    """Create artifact toolkit with mock storage."""
    toolkit = ArtifactToolkit(file_storage=mock_file_storage)
    toolkit._file_storage = mock_file_storage
    toolkit._initialize_tools()
    return toolkit


@pytest.fixture
def test_file(tmp_path):
    """Create a test file for artifact registration."""
    test_file = tmp_path / "test_data.csv"
    test_file.write_text("col1,col2\nval1,val2\nval3,val4\n")
    return str(test_file)


@pytest.mark.asyncio
class TestRegisterArtifactReturnsDescription:
    """Test that register_artifact tool returns description in output."""

    async def test_register_artifact_includes_description(
        self, artifact_toolkit, test_file, mock_execution_context
    ):
        """Test that register_artifact returns description in JSON response."""
        # Setup execution context
        with patch.object(ExecutionContext, "get", return_value=mock_execution_context):
            # Call register_artifact
            result_json = await artifact_toolkit.register_artifact(
                file_path=test_file,
                name="test_data",
                artifact_type="data_processed",
                description="Test dataset with 2 rows and 2 columns",
            )

            # Parse result
            result = json.loads(result_json)

            # Verify success
            assert result["success"] is True

            # Verify description is present
            assert "description" in result, "Description should be in response"
            assert result["description"] == "Test dataset with 2 rows and 2 columns"

    async def test_register_artifact_includes_all_metadata(
        self, artifact_toolkit, test_file, mock_execution_context
    ):
        """Test that register_artifact returns complete artifact summary."""
        with patch.object(ExecutionContext, "get", return_value=mock_execution_context):
            result_json = await artifact_toolkit.register_artifact(
                file_path=test_file,
                name="test_data",
                artifact_type="data_processed",
                description="Complete metadata test",
            )

            result = json.loads(result_json)

            # Verify all expected fields are present
            expected_fields = {
                "success",
                "artifact_id",
                "name",
                "type",
                "media",
                "path",
                "created_by",
                "created_at",
                "description",
            }

            assert expected_fields.issubset(result.keys()), (
                f"Missing fields: {expected_fields - result.keys()}"
            )

            # Verify values
            assert result["name"] == "test_data"
            assert result["type"] == "data_processed"
            assert result["description"] == "Complete metadata test"
            assert result["path"] == test_file

    async def test_register_artifact_description_matches_stored(
        self, artifact_toolkit, test_file, mock_execution_context
    ):
        """Test that returned description matches what was stored in registry."""
        registry = mock_execution_context.artifact_registry

        with patch.object(ExecutionContext, "get", return_value=mock_execution_context):
            # Register artifact
            result_json = await artifact_toolkit.register_artifact(
                file_path=test_file,
                name="test_data",
                artifact_type="data_processed",
                description="Description consistency test",
            )

            result = json.loads(result_json)

            # Get artifact from registry
            artifact_id = result["artifact_id"]
            from uuid import UUID
            stored_artifact = await registry.get_by_id(UUID(artifact_id))

            # Verify stored description matches returned description
            assert stored_artifact is not None
            assert stored_artifact.metadata.description == result["description"]
            assert result["description"] == "Description consistency test"


@pytest.mark.asyncio
class TestAutoDetectionDescriptions:
    """Test that auto-detected artifacts have rich descriptions."""

    async def test_auto_detection_stores_description(
        self, tmp_path, mock_execution_context
    ):
        """Test that auto-detected artifacts are stored with descriptions."""
        # Create test file
        test_file = tmp_path / "auto_detected.txt"
        test_file.write_text("Auto-detected content")

        registry = mock_execution_context.artifact_registry

        with patch.object(ExecutionContext, "get", return_value=mock_execution_context):
            # Auto-register artifact
            count = await auto_register_artifacts(
                file_paths=[str(test_file)],
                toolkit_class="TestToolkit",
                tool_name="test_tool",
                tool_kwargs={"param": "value"},
            )

            # Verify registration
            assert count == 1

            # Get artifact from registry
            artifact = await registry.get_by_path(str(test_file))
            assert artifact is not None

            # Verify description was generated
            assert artifact.metadata.description
            assert "TestToolkit.test_tool" in artifact.metadata.description
            assert "param='value'" in artifact.metadata.description

    async def test_auto_detection_logs_description(
        self, tmp_path, mock_execution_context, caplog
    ):
        """Test that auto-detected artifacts log their descriptions."""
        import logging
        caplog.set_level(logging.INFO)

        # Create test file
        test_file = tmp_path / "logged.txt"
        test_file.write_text("Logged content")

        with patch.object(ExecutionContext, "get", return_value=mock_execution_context):
            # Auto-register artifact
            await auto_register_artifacts(
                file_paths=[str(test_file)],
                toolkit_class="LogToolkit",
                tool_name="log_tool",
            )

            # Check logs contain description info
            log_messages = [record.message for record in caplog.records]
            assert any("Auto-registered artifact with rich metadata" in msg for msg in log_messages)


@pytest.mark.asyncio
class TestDescriptionInContextInjection:
    """Test that descriptions are available in agent context."""

    async def test_artifact_reference_includes_description(self):
        """Test that ArtifactReference includes description."""
        # Create artifact with description
        artifact = Artifact(
            artifact_id=uuid4(),
            name="test_artifact",
            artifact_type=ArtifactType.DATA_PROCESSED,
            media_type=MediaType.FILE,
            storage_path="/tmp/test.csv",
            created_by_task="task-123",
            created_by_module="TestModule",
            metadata=ArtifactMetadata(
                description="Rich description for context",
                mime_type="text/csv",
                size_bytes=1024,
            ),
        )

        # Create reference
        ref = ArtifactReference.from_artifact(artifact)

        # Verify description is preserved
        assert ref.description == "Rich description for context"

    async def test_xml_serialization_includes_description(self):
        """Test that XML serialization includes description as content."""
        artifact = Artifact(
            artifact_id=uuid4(),
            name="xml_test",
            artifact_type=ArtifactType.REPORT,
            media_type=MediaType.TEXT,
            storage_path="/tmp/report.md",
            created_by_task="task-456",
            created_by_module="ReportModule",
            metadata=ArtifactMetadata(
                description="Report with analysis results",
            ),
        )

        ref = ArtifactReference.from_artifact(artifact)
        xml = ref.to_xml_element()

        # Verify description in XML content
        assert "Report with analysis results" in xml
        assert "<artifact" in xml
        assert f'name="xml_test"' in xml
        assert f'type="report"' in xml
        assert "</artifact>" in xml

    async def test_query_service_preserves_descriptions(self):
        """Test that ArtifactQueryService preserves descriptions."""
        registry = ArtifactRegistry()

        # Create and register artifact with description
        artifact = Artifact(
            artifact_id=uuid4(),
            name="query_test",
            artifact_type=ArtifactType.DATA_ANALYSIS,
            media_type=MediaType.FILE,
            storage_path="/tmp/analysis.parquet",
            created_by_task="task-789",
            created_by_module="AnalysisModule",
            metadata=ArtifactMetadata(
                description="Analysis with 1000 rows and 10 columns",
                row_count=1000,
                column_count=10,
            ),
        )

        await registry.register(artifact)

        # Query via service
        service = ArtifactQueryService()
        references = await service.get_artifacts_for_dependencies(
            registry=registry,
            dependency_task_ids=["task-789"],
            mode=ArtifactInjectionMode.DEPENDENCIES,
        )

        # Verify description is preserved
        assert len(references) == 1
        assert references[0].description == "Analysis with 1000 rows and 10 columns"


@pytest.mark.asyncio
class TestModelDumpSummary:
    """Test that model_dump_summary includes description."""

    async def test_model_dump_summary_format(self):
        """Test that model_dump_summary returns expected format."""
        artifact = Artifact(
            artifact_id=uuid4(),
            name="summary_test",
            artifact_type=ArtifactType.PLOT,
            media_type=MediaType.IMAGE,
            storage_path="/tmp/plot.png",
            created_by_task="task-plot",
            created_by_module="PlotModule",
            metadata=ArtifactMetadata(
                description="Price chart visualization",
                mime_type="image/png",
                size_bytes=2048,
            ),
        )

        summary = artifact.model_dump_summary()

        # Verify all expected fields
        assert "artifact_id" in summary
        assert "name" in summary
        assert "type" in summary
        assert "media" in summary
        assert "path" in summary
        assert "created_by" in summary
        assert "created_at" in summary
        assert "description" in summary

        # Verify values
        assert summary["name"] == "summary_test"
        assert summary["type"] == "plot"
        assert summary["description"] == "Price chart visualization"


@pytest.mark.asyncio
class TestEndToEndDescriptionFlow:
    """Test complete flow from registration to context injection."""

    async def test_full_flow_manual_registration(
        self, artifact_toolkit, test_file, mock_execution_context
    ):
        """Test full flow: manual registration → storage → query → context."""
        registry = mock_execution_context.artifact_registry

        with patch.object(ExecutionContext, "get", return_value=mock_execution_context):
            # Step 1: Register artifact
            result_json = await artifact_toolkit.register_artifact(
                file_path=test_file,
                name="flow_test",
                artifact_type="data_processed",
                description="End-to-end flow test description",
            )

            result = json.loads(result_json)
            artifact_id = result["artifact_id"]

            # Verify description in tool output
            assert result["description"] == "End-to-end flow test description"

            # Step 2: Verify storage in registry
            from uuid import UUID
            stored = await registry.get_by_id(UUID(artifact_id))
            assert stored.metadata.description == "End-to-end flow test description"

            # Step 3: Query for context injection
            service = ArtifactQueryService()
            refs = await service.get_artifacts_for_dependencies(
                registry=registry,
                dependency_task_ids=[mock_execution_context.execution_id],
                mode=ArtifactInjectionMode.DEPENDENCIES,
            )

            # Verify description in reference
            assert len(refs) == 1
            assert refs[0].description == "End-to-end flow test description"

            # Step 4: Verify XML serialization
            xml = refs[0].to_xml_element()
            assert "End-to-end flow test description" in xml

    async def test_full_flow_auto_detection(
        self, tmp_path, mock_execution_context
    ):
        """Test full flow: auto-detection → storage → query → context."""
        # Create test file
        test_file = tmp_path / "auto_flow.txt"
        test_file.write_text("Auto flow content")

        registry = mock_execution_context.artifact_registry

        with patch.object(ExecutionContext, "get", return_value=mock_execution_context):
            # Step 1: Auto-register
            count = await auto_register_artifacts(
                file_paths=[str(test_file)],
                toolkit_class="FlowToolkit",
                tool_name="flow_tool",
                tool_kwargs={"key": "value"},
            )

            assert count == 1

            # Step 2: Verify storage
            stored = await registry.get_by_path(str(test_file))
            assert stored is not None
            assert "FlowToolkit.flow_tool" in stored.metadata.description

            # Step 3: Query for context
            service = ArtifactQueryService()
            refs = await service.get_artifacts_for_dependencies(
                registry=registry,
                dependency_task_ids=[mock_execution_context.execution_id],
                mode=ArtifactInjectionMode.DEPENDENCIES,
            )

            # Verify description preserved
            assert len(refs) == 1
            assert "FlowToolkit.flow_tool" in refs[0].description

            # Step 4: XML includes description
            xml = refs[0].to_xml_element()
            assert "FlowToolkit.flow_tool" in xml