"""
Unit tests for ArtifactToolkit basic functionality.

Tests the minimal toolkit interface for artifact management.
Only essential tools to minimize LLM overhead.
"""

import json
import pytest
from unittest.mock import Mock, patch, AsyncMock
from pathlib import Path

from roma_dspy.tools.core.artifact_toolkit import ArtifactToolkit
from roma_dspy.types import ArtifactType, ArtifactRegistrationRequest, MediaType


@pytest.fixture
def mock_file_storage(tmp_path):
    """Create mock FileStorage with temporary directory."""
    storage = Mock()
    storage.root = tmp_path
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
    return context


class TestArtifactToolkitInitialization:
    """Test ArtifactToolkit initialization."""

    def test_toolkit_requires_file_storage(self):
        """Test that toolkit declares it requires FileStorage."""
        assert ArtifactToolkit.REQUIRES_FILE_STORAGE is True

    def test_toolkit_type_is_builtin(self):
        """Test that toolkit type is 'builtin'."""
        assert ArtifactToolkit.TOOLKIT_TYPE == "builtin"

    @patch('roma_dspy.core.context.ExecutionContext.get')
    def test_initialize_with_execution_context(self, mock_get_context, mock_execution_context, mock_file_storage):
        """Test toolkit initialization with ExecutionContext."""
        mock_get_context.return_value = mock_execution_context

        toolkit = ArtifactToolkit(config={}, file_storage=mock_file_storage)

        # Should have initialized successfully
        assert toolkit is not None
        assert hasattr(toolkit, 'artifacts_dir')

    @patch('roma_dspy.core.context.ExecutionContext.get')
    def test_initialize_creates_artifacts_directory(self, mock_get_context, mock_execution_context, mock_file_storage):
        """Test that initialization creates artifacts directory."""
        mock_get_context.return_value = mock_execution_context

        toolkit = ArtifactToolkit(config={}, file_storage=mock_file_storage)

        artifacts_dir = mock_file_storage.root / "artifacts"
        assert artifacts_dir.exists()


class TestRegisterArtifactTool:
    """Test register_artifact tool (minimal essential tool)."""

    @patch('roma_dspy.core.context.ExecutionContext.get')
    @pytest.mark.asyncio
    async def test_register_artifact_success(self, mock_get_context, mock_execution_context, mock_file_storage, tmp_path):
        """Test successful artifact registration."""
        mock_get_context.return_value = mock_execution_context

        # Create a test file
        test_file = tmp_path / "test.txt"
        test_file.write_text("test content")

        toolkit = ArtifactToolkit(config={}, file_storage=mock_file_storage)

        result_json = await toolkit.register_artifact(
            artifacts=ArtifactRegistrationRequest(
                file_path=str(test_file),
                name="test.txt",
                artifact_type="data_fetch",
                description="Test artifact"
            )
        )

        result = json.loads(result_json)
        assert "success" in result
        assert result["success"] is True
        assert "artifact_id" in result
        assert "name" in result
        assert result["name"] == "test.txt"
        # Verify description is included in response (from fix)
        assert "description" in result
        assert result["description"] == "Test artifact"

    @patch('roma_dspy.core.context.ExecutionContext.get')
    @pytest.mark.asyncio
    async def test_register_artifact_validates_file_exists(self, mock_get_context, mock_execution_context, mock_file_storage):
        """Test that register_artifact validates file exists."""
        mock_get_context.return_value = mock_execution_context

        toolkit = ArtifactToolkit(config={}, file_storage=mock_file_storage)

        result_json = await toolkit.register_artifact(
            artifacts=ArtifactRegistrationRequest(
                file_path="/nonexistent/file.txt",
                name="missing.txt",
                artifact_type="data_fetch",
                description="Missing file"
            )
        )

        result = json.loads(result_json)
        assert "success" in result
        assert result["success"] is False
        assert "error" in result

    @patch('roma_dspy.core.context.ExecutionContext.get')
    @pytest.mark.asyncio
    async def test_register_artifact_validates_artifact_type(self, mock_get_context, mock_execution_context, mock_file_storage, tmp_path):
        """Test that register_artifact validates artifact type."""
        mock_get_context.return_value = mock_execution_context

        test_file = tmp_path / "test.txt"
        test_file.write_text("test")

        toolkit = ArtifactToolkit(config={}, file_storage=mock_file_storage)

        result_json = await toolkit.register_artifact(
            artifacts=ArtifactRegistrationRequest(
                file_path=str(test_file),
                name="test.txt",
                artifact_type="invalid_type",  # Invalid!
                description="Test"
            )
        )

        result = json.loads(result_json)
        assert "success" in result
        assert result["success"] is False
        # Error could be in main error or in details
        if "details" in result:
            assert any("Invalid artifact type" in detail["error"] for detail in result["details"])
        else:
            assert "Invalid artifact type" in result["error"]


class TestToolkitMinimalism:
    """Test that toolkit is minimal (only essential tools)."""

    @patch('roma_dspy.core.context.ExecutionContext.get')
    def test_toolkit_has_minimal_tools(self, mock_get_context, mock_execution_context, mock_file_storage):
        """Test that toolkit exposes only minimal essential tools."""
        mock_get_context.return_value = mock_execution_context

        toolkit = ArtifactToolkit(config={}, file_storage=mock_file_storage)

        # Get all public methods (tools)
        tools = [method for method in dir(toolkit) if not method.startswith('_') and callable(getattr(toolkit, method))]

        # Should only have ONE essential tool (minimal overhead)
        essential_tools = {'register_artifact'}

        # Filter out inherited BaseToolkit methods
        toolkit_specific_tools = {
            tool for tool in tools
            if tool in essential_tools
        }

        # Should have exactly this essential tool, no more
        assert toolkit_specific_tools == essential_tools

    @patch('roma_dspy.core.context.ExecutionContext.get')
    def test_no_unnecessary_tools(self, mock_get_context, mock_execution_context, mock_file_storage):
        """Test that toolkit doesn't have unnecessary tools that add LLM overhead."""
        mock_get_context.return_value = mock_execution_context

        toolkit = ArtifactToolkit(config={}, file_storage=mock_file_storage)

        # Get all public methods
        tools = [method for method in dir(toolkit) if not method.startswith('_') and callable(getattr(toolkit, method))]

        # These tools should NOT exist (they add overhead)
        # Note: list_artifacts removed since artifacts are injected into context
        unnecessary_tools = {
            'list_artifacts',
            'update_artifact',
            'delete_artifact',
            'get_artifact_details',
            'search_artifacts',
            'export_artifacts',
            'import_artifacts',
            'validate_artifact',
        }

        for unnecessary_tool in unnecessary_tools:
            assert unnecessary_tool not in tools, f"Unnecessary tool {unnecessary_tool} found - adds LLM overhead"
