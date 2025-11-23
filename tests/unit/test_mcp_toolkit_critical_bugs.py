"""Comprehensive tests for P0 critical bugs in MCP toolkit.

Tests the fixes for:
- Bug #1: isError field handling
- Bug #2: Content array safety
- Bug #3: Silent JSON parse failures
"""

import json
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from roma_dspy.tools.mcp import MCPToolError, MCPToolkit


class MockCallToolResult:
    """Mock FastMCP CallToolResult for testing."""

    def __init__(self, content=None, is_error=False, isError=None, data=None):
        self.content = content or []
        self.is_error = is_error
        self.isError = isError if isError is not None else is_error
        self.data = data


class MockTextContent:
    """Mock FastMCP TextContent."""

    def __init__(self, text):
        self.text = text
        self.type = "text"


class MockTool:
    """Mock MCP tool metadata."""

    def __init__(self, name, description="Test tool"):
        self.name = name
        self.description = description
        self.inputSchema = {}


@pytest.fixture
def mock_client():
    """Create a mock FastMCP client."""
    client = AsyncMock()
    client.list_tools = AsyncMock(return_value=[MockTool("test_tool")])
    return client


@pytest.fixture
async def toolkit(mock_client):
    """Create MCPToolkit instance with mocked client."""
    with patch("roma_dspy.tools.mcp.toolkit.Client") as mock_client_class:
        # Setup context manager
        mock_context = AsyncMock()
        mock_context.__aenter__ = AsyncMock(return_value=mock_client)
        mock_context.__aexit__ = AsyncMock(return_value=None)
        mock_client_class.return_value = mock_context

        # Create toolkit
        toolkit = MCPToolkit(
            server_name="test",
            server_type="stdio",
            command="python",
            args=["test.py"],
        )

        # Initialize
        await toolkit.initialize()

        yield toolkit

        # Cleanup
        await toolkit.cleanup()


# ============================================================================
# Bug #1: isError Field Handling
# ============================================================================


@pytest.mark.asyncio
async def test_tool_error_is_detected_snake_case(mock_client):
    """Tool with is_error=True raises MCPToolError."""
    # Mock client.call_tool to return error result
    error_result = MockCallToolResult(
        content=[MockTextContent("API key invalid")], is_error=True
    )
    mock_client.call_tool = AsyncMock(return_value=error_result)

    # Create toolkit with mocked client
    with patch("roma_dspy.tools.mcp.toolkit.Client") as mock_client_class:
        mock_context = AsyncMock()
        mock_context.__aenter__ = AsyncMock(return_value=mock_client)
        mock_context.__aexit__ = AsyncMock(return_value=None)
        mock_client_class.return_value = mock_context

        toolkit = MCPToolkit(
            server_name="test",
            server_type="stdio",
            command="python",
            args=["test.py"],
        )
        await toolkit.initialize()

        tools = toolkit.get_enabled_tools()
        assert "test_tool" in tools

        # Call should raise MCPToolError
        with pytest.raises(MCPToolError) as exc_info:
            await tools["test_tool"]()

        assert "test_tool failed" in str(exc_info.value)
        assert "API key invalid" in str(exc_info.value)

        await toolkit.cleanup()


@pytest.mark.asyncio
async def test_tool_error_is_detected_camel_case(mock_client):
    """Tool with isError=True (camelCase) raises MCPToolError."""
    # Mock client.call_tool to return error result with camelCase
    error_result = MockCallToolResult(
        content=[MockTextContent("Rate limit exceeded")],
        is_error=False,  # snake_case is False
        isError=True,  # but camelCase is True
    )
    mock_client.call_tool = AsyncMock(return_value=error_result)

    with patch("roma_dspy.tools.mcp.toolkit.Client") as mock_client_class:
        mock_context = AsyncMock()
        mock_context.__aenter__ = AsyncMock(return_value=mock_client)
        mock_context.__aexit__ = AsyncMock(return_value=None)
        mock_client_class.return_value = mock_context

        toolkit = MCPToolkit(
            server_name="test",
            server_type="stdio",
            command="python",
            args=["test.py"],
        )
        await toolkit.initialize()

        tools = toolkit.get_enabled_tools()

        with pytest.raises(MCPToolError) as exc_info:
            await tools["test_tool"]()

        assert "Rate limit exceeded" in str(exc_info.value)

        await toolkit.cleanup()


@pytest.mark.asyncio
async def test_tool_error_with_empty_content(mock_client):
    """Tool error with empty content uses default message."""
    error_result = MockCallToolResult(
        content=[],  # Empty content
        is_error=True,
    )
    mock_client.call_tool = AsyncMock(return_value=error_result)

    with patch("roma_dspy.tools.mcp.toolkit.Client") as mock_client_class:
        mock_context = AsyncMock()
        mock_context.__aenter__ = AsyncMock(return_value=mock_client)
        mock_context.__aexit__ = AsyncMock(return_value=None)
        mock_client_class.return_value = mock_context

        toolkit = MCPToolkit(
            server_name="test",
            server_type="stdio",
            command="python",
            args=["test.py"],
        )
        await toolkit.initialize()

        tools = toolkit.get_enabled_tools()

        with pytest.raises(MCPToolError) as exc_info:
            await tools["test_tool"]()

        assert "Unknown error" in str(exc_info.value)

        await toolkit.cleanup()


# ============================================================================
# Bug #2: Content Array Safety
# ============================================================================


@pytest.mark.asyncio
async def test_empty_content_list_handled(mock_client):
    """Empty content[] doesn't crash - returns empty string."""
    result = MockCallToolResult(
        content=[],  # Empty list
        is_error=False,
    )
    mock_client.call_tool = AsyncMock(return_value=result)

    with patch("roma_dspy.tools.mcp.toolkit.Client") as mock_client_class:
        mock_context = AsyncMock()
        mock_context.__aenter__ = AsyncMock(return_value=mock_client)
        mock_context.__aexit__ = AsyncMock(return_value=None)
        mock_client_class.return_value = mock_context

        toolkit = MCPToolkit(
            server_name="test",
            server_type="stdio",
            command="python",
            args=["test.py"],
        )
        await toolkit.initialize()

        tools = toolkit.get_enabled_tools()

        # Should not crash - returns stringified result
        response = await tools["test_tool"]()
        assert isinstance(response, str)

        await toolkit.cleanup()


@pytest.mark.asyncio
async def test_non_list_content_handled(mock_client):
    """content="string" (not a list) doesn't crash."""
    result = MockCallToolResult(
        content="not a list",  # String instead of list
        is_error=False,
    )
    mock_client.call_tool = AsyncMock(return_value=result)

    with patch("roma_dspy.tools.mcp.toolkit.Client") as mock_client_class:
        mock_context = AsyncMock()
        mock_context.__aenter__ = AsyncMock(return_value=mock_client)
        mock_context.__aexit__ = AsyncMock(return_value=None)
        mock_client_class.return_value = mock_context

        toolkit = MCPToolkit(
            server_name="test",
            server_type="stdio",
            command="python",
            args=["test.py"],
        )
        await toolkit.initialize()

        tools = toolkit.get_enabled_tools()

        # Should not crash - falls back to str(result)
        response = await tools["test_tool"]()
        assert isinstance(response, str)

        await toolkit.cleanup()


@pytest.mark.asyncio
async def test_content_without_text_attribute(mock_client):
    """Content items without .text attribute are handled."""
    # Create mock content without text attribute
    mock_content = Mock()
    mock_content.text = None  # No text
    delattr(mock_content, "text")  # Remove attribute entirely

    result = MockCallToolResult(content=[mock_content], is_error=False)
    mock_client.call_tool = AsyncMock(return_value=result)

    with patch("roma_dspy.tools.mcp.toolkit.Client") as mock_client_class:
        mock_context = AsyncMock()
        mock_context.__aenter__ = AsyncMock(return_value=mock_client)
        mock_context.__aexit__ = AsyncMock(return_value=None)
        mock_client_class.return_value = mock_context

        toolkit = MCPToolkit(
            server_name="test",
            server_type="stdio",
            command="python",
            args=["test.py"],
        )
        await toolkit.initialize()

        tools = toolkit.get_enabled_tools()

        # Should convert to string instead of crashing
        response = await tools["test_tool"]()
        assert isinstance(response, str)

        await toolkit.cleanup()


# ============================================================================
# Bug #3: JSON Parsing
# ============================================================================


@pytest.mark.asyncio
async def test_non_json_text_returned_without_storage(mock_client):
    """Plain text tools work without Parquet storage."""
    # Return plain text (not JSON)
    plain_text = "This is plain text response, not JSON"
    result = MockCallToolResult(content=[MockTextContent(plain_text)], is_error=False)
    mock_client.call_tool = AsyncMock(return_value=result)

    # Mock FileStorage
    from roma_dspy.config.schemas.storage import StorageConfig
    from roma_dspy.core.storage.file_storage import FileStorage
    import tempfile

    temp_dir = tempfile.mkdtemp()
    storage_config = StorageConfig(base_path=temp_dir)
    file_storage = FileStorage(config=storage_config, execution_id="test")

    with patch("roma_dspy.tools.mcp.toolkit.Client") as mock_client_class:
        mock_context = AsyncMock()
        mock_context.__aenter__ = AsyncMock(return_value=mock_client)
        mock_context.__aexit__ = AsyncMock(return_value=None)
        mock_client_class.return_value = mock_context

        toolkit = MCPToolkit(
            server_name="test",
            server_type="stdio",
            command="python",
            args=["test.py"],
            use_storage=True,  # Enable storage
            storage_threshold_kb=0.001,  # Very low threshold
            file_storage=file_storage,
        )
        await toolkit.initialize()

        tools = toolkit.get_enabled_tools()

        # Should return plain text without attempting storage
        response = await tools["test_tool"]()
        assert response == plain_text
        # Should NOT be a "Data stored at..." message
        assert "Data stored" not in response

        await toolkit.cleanup()


@pytest.mark.asyncio
async def test_json_parse_error_logged(mock_client, caplog):
    """JSON parse failures are logged as warnings."""
    # Return invalid JSON
    invalid_json = '{"incomplete": '
    result = MockCallToolResult(content=[MockTextContent(invalid_json)], is_error=False)
    mock_client.call_tool = AsyncMock(return_value=result)

    # Mock FileStorage
    from roma_dspy.config.schemas.storage import StorageConfig
    from roma_dspy.core.storage.file_storage import FileStorage
    import tempfile

    temp_dir = tempfile.mkdtemp()
    storage_config = StorageConfig(base_path=temp_dir)
    file_storage = FileStorage(config=storage_config, execution_id="test")

    with patch("roma_dspy.tools.mcp.toolkit.Client") as mock_client_class:
        mock_context = AsyncMock()
        mock_context.__aenter__ = AsyncMock(return_value=mock_client)
        mock_context.__aexit__ = AsyncMock(return_value=None)
        mock_client_class.return_value = mock_context

        toolkit = MCPToolkit(
            server_name="test",
            server_type="stdio",
            command="python",
            args=["test.py"],
            use_storage=True,
            storage_threshold_kb=0.001,
            file_storage=file_storage,
        )
        await toolkit.initialize()

        tools = toolkit.get_enabled_tools()

        # Should log warning about non-JSON text
        with caplog.at_level("WARNING"):
            response = await tools["test_tool"]()

        # Check warning was logged
        assert any("non-JSON text" in record.message for record in caplog.records)

        await toolkit.cleanup()


@pytest.mark.asyncio
async def test_valid_json_is_parsed_and_stored(mock_client):
    """Valid JSON is properly parsed and stored."""
    # Return valid JSON that exceeds threshold
    large_json_data = [{"id": i, "name": f"Item {i}"} for i in range(100)]
    json_string = json.dumps(large_json_data)

    result = MockCallToolResult(content=[MockTextContent(json_string)], is_error=False)
    mock_client.call_tool = AsyncMock(return_value=result)

    # Mock FileStorage
    from roma_dspy.config.schemas.storage import StorageConfig
    from roma_dspy.core.storage.file_storage import FileStorage
    import tempfile

    temp_dir = tempfile.mkdtemp()
    storage_config = StorageConfig(base_path=temp_dir)
    file_storage = FileStorage(config=storage_config, execution_id="test")

    with patch("roma_dspy.tools.mcp.toolkit.Client") as mock_client_class:
        mock_context = AsyncMock()
        mock_context.__aenter__ = AsyncMock(return_value=mock_client)
        mock_context.__aexit__ = AsyncMock(return_value=None)
        mock_client_class.return_value = mock_context

        toolkit = MCPToolkit(
            server_name="test",
            server_type="stdio",
            command="python",
            args=["test.py"],
            use_storage=True,
            storage_threshold_kb=0.001,
            file_storage=file_storage,
        )
        await toolkit.initialize()

        tools = toolkit.get_enabled_tools()

        # Should parse JSON and store
        response = await tools["test_tool"]()

        # Response should be storage message
        assert "Data stored at" in response
        assert ".parquet" in response

        await toolkit.cleanup()


@pytest.mark.asyncio
async def test_malformed_json_doesnt_crash_storage(mock_client, caplog):
    """Malformed JSON doesn't trigger storage errors."""
    # Return malformed JSON that's large enough to trigger storage
    malformed = "not json but very long " * 1000
    result = MockCallToolResult(content=[MockTextContent(malformed)], is_error=False)
    mock_client.call_tool = AsyncMock(return_value=result)

    # Mock FileStorage
    from roma_dspy.config.schemas.storage import StorageConfig
    from roma_dspy.core.storage.file_storage import FileStorage
    import tempfile

    temp_dir = tempfile.mkdtemp()
    storage_config = StorageConfig(base_path=temp_dir)
    file_storage = FileStorage(config=storage_config, execution_id="test")

    with patch("roma_dspy.tools.mcp.toolkit.Client") as mock_client_class:
        mock_context = AsyncMock()
        mock_context.__aenter__ = AsyncMock(return_value=mock_client)
        mock_context.__aexit__ = AsyncMock(return_value=None)
        mock_client_class.return_value = mock_context

        toolkit = MCPToolkit(
            server_name="test",
            server_type="stdio",
            command="python",
            args=["test.py"],
            use_storage=True,
            storage_threshold_kb=0.001,  # Very low threshold
            file_storage=file_storage,
        )
        await toolkit.initialize()

        tools = toolkit.get_enabled_tools()

        # Should NOT crash - returns text without storage
        with caplog.at_level("WARNING"):
            response = await tools["test_tool"]()

        # Should return the malformed text
        assert response == malformed
        # Should NOT attempt storage
        assert "Data stored" not in response
        # Should log warning
        assert any("non-JSON text" in record.message for record in caplog.records)

        await toolkit.cleanup()
