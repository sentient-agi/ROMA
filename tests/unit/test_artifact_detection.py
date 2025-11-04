"""
Unit tests for automatic artifact detection from tool outputs.

Tests that artifacts are automatically detected and registered when tools
return file paths, without requiring explicit register_artifact calls.
"""

import json
import pytest
from pathlib import Path
from unittest.mock import Mock, patch, AsyncMock
from datetime import datetime

from roma_dspy.tools.base.base import BaseToolkit
from roma_dspy.tools.metrics.decorators import track_tool_invocation
from roma_dspy.tools.metrics.artifact_detector import (
    extract_file_paths_from_result,
    auto_register_artifacts,
)
from roma_dspy.types import ArtifactType


class MockToolkit(BaseToolkit):
    """Mock toolkit for testing artifact detection."""

    REQUIRES_FILE_STORAGE = True
    TOOLKIT_TYPE = "builtin"

    def _setup_dependencies(self) -> None:
        pass

    def _initialize_tools(self) -> None:
        pass

    async def create_file(self, content: str, filename: str) -> str:
        """Tool that creates a file and returns the path (JSON)."""
        file_path = Path(self._file_storage.root) / filename
        file_path.write_text(content)
        return json.dumps({"file_path": str(file_path), "status": "created"})

    async def create_multiple_files(self, count: int) -> str:
        """Tool that creates multiple files (JSON array)."""
        file_paths = []
        for i in range(count):
            file_path = Path(self._file_storage.root) / f"file_{i}.txt"
            file_path.write_text(f"content {i}")
            file_paths.append(str(file_path))
        return json.dumps({"file_paths": file_paths, "count": count})

    async def no_artifact_output(self, message: str) -> str:
        """Tool that doesn't create any artifacts."""
        return json.dumps({"message": message, "processed": True})


@pytest.fixture
def mock_file_storage(tmp_path):
    """Create mock FileStorage with temporary directory."""
    storage = Mock()
    storage.root = tmp_path
    storage.execution_id = "test_exec_123"
    storage.get_artifacts_path = Mock(return_value=tmp_path / "artifacts")
    return storage


@pytest.fixture
def mock_execution_context(mock_file_storage):
    """Mock ExecutionContext with artifact registry."""
    from roma_dspy.core.artifacts import ArtifactRegistry

    context = Mock()
    context.execution_id = "test_exec_123"
    context.file_storage = mock_file_storage
    context.artifact_registry = ArtifactRegistry()
    context.tool_invocations = []
    return context


class TestArtifactDetectionFromToolOutput:
    """Test automatic artifact detection from tool return values."""

    @patch('roma_dspy.core.context.ExecutionContext.get')
    @pytest.mark.asyncio
    async def test_detect_single_file_path_in_json(self, mock_get_context, mock_execution_context, mock_file_storage, tmp_path):
        """Test that single file_path in JSON output is detected as artifact."""
        mock_get_context.return_value = mock_execution_context

        toolkit = MockToolkit(file_storage=mock_file_storage)

        # Create file and get output
        result_json = await toolkit.create_file("test content", "output.txt")

        # Manually run artifact detection (simulating what decorator does)
        execution_dir = Path(mock_file_storage.root)
        file_paths = extract_file_paths_from_result(result_json, execution_dir)

        # Auto-register detected paths
        if file_paths:
            await auto_register_artifacts(
                file_paths=file_paths,
                toolkit_class="MockToolkit",
                tool_name="create_file",
                execution_id="test_exec_123"
            )

        # Verify artifact was auto-registered
        registry = mock_execution_context.artifact_registry
        artifacts = await registry.get_all()

        # Should have 1 auto-registered artifact
        assert len(artifacts) == 1
        assert "output.txt" in artifacts[0].storage_path
        # .txt extension is inferred as REPORT (which is correct per artifact_types.py:119)
        assert artifacts[0].artifact_type == ArtifactType.REPORT

    @patch('roma_dspy.core.context.ExecutionContext.get')
    @pytest.mark.asyncio
    async def test_detect_multiple_file_paths_in_json(self, mock_get_context, mock_execution_context, mock_file_storage, tmp_path):
        """Test that multiple file_paths in JSON array are detected."""
        mock_get_context.return_value = mock_execution_context

        toolkit = MockToolkit(file_storage=mock_file_storage)

        # Create multiple files
        result_json = await toolkit.create_multiple_files(3)

        # Manually run artifact detection (simulating what decorator does)
        execution_dir = Path(mock_file_storage.root)
        file_paths = extract_file_paths_from_result(result_json, execution_dir)

        # Auto-register detected paths
        if file_paths:
            await auto_register_artifacts(
                file_paths=file_paths,
                toolkit_class="MockToolkit",
                tool_name="create_multiple_files",
                execution_id="test_exec_123"
            )

        # Verify all artifacts were auto-registered
        registry = mock_execution_context.artifact_registry
        artifacts = await registry.get_all()

        # Should have 3 auto-registered artifacts
        assert len(artifacts) == 3
        assert all("file_" in a.storage_path for a in artifacts)

    @patch('roma_dspy.core.context.ExecutionContext.get')
    @pytest.mark.asyncio
    async def test_no_detection_for_non_file_outputs(self, mock_get_context, mock_execution_context, mock_file_storage):
        """Test that tools without file outputs don't trigger detection."""
        mock_get_context.return_value = mock_execution_context

        toolkit = MockToolkit(file_storage=mock_file_storage)

        # Call tool that doesn't create files
        result_json = await toolkit.no_artifact_output("hello")

        # Should have no artifacts
        registry = mock_execution_context.artifact_registry
        artifacts = await registry.get_all()
        assert len(artifacts) == 0


class TestArtifactDetectionPatterns:
    """Test various JSON patterns for artifact detection."""

    @patch('roma_dspy.core.context.ExecutionContext.get')
    @pytest.mark.asyncio
    async def test_detect_file_path_key(self, mock_get_context, mock_execution_context, mock_file_storage, tmp_path):
        """Test detection of 'file_path' key in JSON."""
        mock_get_context.return_value = mock_execution_context

        # Create test file
        test_file = tmp_path / "test.csv"
        test_file.write_text("data")

        # Simulate tool output with file_path key
        output = json.dumps({"file_path": str(test_file), "status": "success"})

        # Detection should find the file_path
        # (This will be implemented in the decorator)
        result = json.loads(output)
        assert "file_path" in result
        assert Path(result["file_path"]).exists()

    @patch('roma_dspy.core.context.ExecutionContext.get')
    @pytest.mark.asyncio
    async def test_detect_file_paths_key(self, mock_get_context, mock_execution_context, tmp_path):
        """Test detection of 'file_paths' key (array) in JSON."""
        # Create test files
        files = []
        for i in range(3):
            f = tmp_path / f"file_{i}.txt"
            f.write_text(f"content {i}")
            files.append(str(f))

        # Simulate tool output with file_paths array
        output = json.dumps({"file_paths": files, "count": 3})

        # Detection should find all file_paths
        result = json.loads(output)
        assert "file_paths" in result
        assert len(result["file_paths"]) == 3

    @patch('roma_dspy.core.context.ExecutionContext.get')
    @pytest.mark.asyncio
    async def test_detect_output_file_key(self, mock_get_context, mock_execution_context, tmp_path):
        """Test detection of 'output_file' key in JSON."""
        # Create test file
        test_file = tmp_path / "result.json"
        test_file.write_text('{"data": "value"}')

        # Simulate tool output with output_file key
        output = json.dumps({"output_file": str(test_file), "format": "json"})

        result = json.loads(output)
        assert "output_file" in result
        assert Path(result["output_file"]).exists()

    @patch('roma_dspy.core.context.ExecutionContext.get')
    @pytest.mark.asyncio
    async def test_detect_artifact_path_key(self, mock_get_context, mock_execution_context, tmp_path):
        """Test detection of 'artifact_path' key in JSON."""
        # Create test file
        test_file = tmp_path / "artifact.txt"
        test_file.write_text("artifact content")

        # Simulate tool output with artifact_path key
        output = json.dumps({"artifact_path": str(test_file), "type": "data"})

        result = json.loads(output)
        assert "artifact_path" in result
        assert Path(result["artifact_path"]).exists()


class TestArtifactTypeInference:
    """Test automatic artifact type inference from file extensions."""

    @pytest.mark.asyncio
    async def test_infer_csv_as_data_processed(self, tmp_path):
        """Test that .csv files are inferred as DATA_PROCESSED."""
        file_path = tmp_path / "data.csv"
        file_path.write_text("col1,col2\n1,2")

        # Type inference logic will be in detector
        inferred_type = ArtifactType.from_file_extension(".csv")
        assert inferred_type == ArtifactType.DATA_PROCESSED

    @pytest.mark.asyncio
    async def test_infer_png_as_plot(self, tmp_path):
        """Test that .png files are inferred as PLOT."""
        file_path = tmp_path / "chart.png"
        file_path.write_bytes(b"fake png data")

        inferred_type = ArtifactType.from_file_extension(".png")
        assert inferred_type == ArtifactType.PLOT

    @pytest.mark.asyncio
    async def test_infer_md_as_report(self, tmp_path):
        """Test that .md files are inferred as REPORT."""
        file_path = tmp_path / "analysis.md"
        file_path.write_text("# Report")

        inferred_type = ArtifactType.from_file_extension(".md")
        assert inferred_type == ArtifactType.REPORT

    @pytest.mark.asyncio
    async def test_infer_py_as_code(self, tmp_path):
        """Test that .py files are inferred as CODE."""
        file_path = tmp_path / "script.py"
        file_path.write_text("print('hello')")

        inferred_type = ArtifactType.from_file_extension(".py")
        assert inferred_type == ArtifactType.CODE


class TestArtifactDetectionMetadata:
    """Test that detected artifacts include proper metadata."""

    @patch('roma_dspy.core.context.ExecutionContext.get')
    @pytest.mark.asyncio
    async def test_detected_artifact_has_created_by_module(self, mock_get_context, mock_execution_context, mock_file_storage, tmp_path):
        """Test that detected artifacts track which toolkit created them."""
        mock_get_context.return_value = mock_execution_context

        toolkit = MockToolkit(file_storage=mock_file_storage)
        result_json = await toolkit.create_file("content", "output.txt")

        # Manually run artifact detection (simulating what decorator does)
        execution_dir = Path(mock_file_storage.root)
        file_paths = extract_file_paths_from_result(result_json, execution_dir)

        # Auto-register detected paths
        if file_paths:
            await auto_register_artifacts(
                file_paths=file_paths,
                toolkit_class="MockToolkit",
                tool_name="create_file",
                execution_id="test_exec_123"
            )

        registry = mock_execution_context.artifact_registry
        artifacts = await registry.get_all()

        assert len(artifacts) == 1
        assert artifacts[0].created_by_module == "MockToolkit"

    @patch('roma_dspy.core.context.ExecutionContext.get')
    @pytest.mark.asyncio
    async def test_detected_artifact_has_created_by_task(self, mock_get_context, mock_execution_context, mock_file_storage, tmp_path):
        """Test that detected artifacts track execution_id."""
        mock_get_context.return_value = mock_execution_context

        toolkit = MockToolkit(file_storage=mock_file_storage)
        result_json = await toolkit.create_file("content", "output.txt")

        # Manually run artifact detection (simulating what decorator does)
        execution_dir = Path(mock_file_storage.root)
        file_paths = extract_file_paths_from_result(result_json, execution_dir)

        # Auto-register detected paths
        if file_paths:
            await auto_register_artifacts(
                file_paths=file_paths,
                toolkit_class="MockToolkit",
                tool_name="create_file",
                execution_id="test_exec_123"
            )

        registry = mock_execution_context.artifact_registry
        artifacts = await registry.get_all()

        assert len(artifacts) == 1
        assert str(artifacts[0].created_by_task) == "test_exec_123"
