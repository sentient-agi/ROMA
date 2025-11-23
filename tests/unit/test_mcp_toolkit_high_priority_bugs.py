"""Comprehensive tests for P1 high priority bugs in MCP toolkit.

Tests the fixes for:
- Bug #4: Multiple content items support
- Bug #5: structured_content support
- Bug #6: Explicit transport_type parameter
- Bug #7: Error messages triggering storage
"""

import json
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from roma_dspy.tools.mcp import MCPToolError, MCPToolkit


class MockCallToolResult:
    """Mock FastMCP CallToolResult for testing."""

    def __init__(
        self, content=None, is_error=False, data=None, structured_content=None
    ):
        self.content = content or []
        self.is_error = is_error
        self.data = data
        self.structured_content = structured_content


class MockTextContent:
    """Mock FastMCP TextContent."""

    def __init__(self, text):
        self.text = text
        self.type = "text"


class MockImageContent:
    """Mock FastMCP ImageContent."""

    def __init__(self, url):
        self.url = url
        self.type = "image"


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


# ============================================================================
# Bug #4: Multiple Content Items Support
# ============================================================================


@pytest.mark.asyncio
async def test_multiple_text_content_items_concatenated(mock_client):
    """Multiple text content items are concatenated with separator."""
    result = MockCallToolResult(
        content=[
            MockTextContent("First result"),
            MockTextContent("Second result"),
            MockTextContent("Third result"),
        ],
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
        response = await tools["test_tool"]()

        # Should concatenate all three text items with separator
        assert "First result" in response
        assert "Second result" in response
        assert "Third result" in response
        assert "\n---\n" in response  # Separator between items

        await toolkit.cleanup()


@pytest.mark.asyncio
async def test_mixed_content_types_handled(mock_client):
    """Mixed text and non-text content items are handled."""
    result = MockCallToolResult(
        content=[
            MockTextContent("Text content"),
            MockImageContent("https://example.com/image.png"),
            MockTextContent("More text"),
        ],
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
        response = await tools["test_tool"]()

        # Should include text content and stringified image content
        assert "Text content" in response
        assert "More text" in response
        assert isinstance(response, str)

        await toolkit.cleanup()


@pytest.mark.asyncio
async def test_single_content_item_no_separator(mock_client):
    """Single content item returns text without separator."""
    result = MockCallToolResult(
        content=[MockTextContent("Single result")], is_error=False
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
        response = await tools["test_tool"]()

        # Should return single text without separator
        assert response == "Single result"
        assert "\n---\n" not in response

        await toolkit.cleanup()


# ============================================================================
# Bug #5: structured_content Support
# ============================================================================


@pytest.mark.asyncio
async def test_structured_content_returned_directly(mock_client):
    """structured_content is returned directly without JSON parsing."""
    structured_data = {"id": 123, "name": "Test Item", "nested": {"key": "value"}}
    result = MockCallToolResult(
        content=[MockTextContent(json.dumps(structured_data))],
        structured_content=structured_data,
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
        response = await tools["test_tool"]()

        # Should return structured_content dict directly
        assert response == structured_data
        assert isinstance(response, dict)

        await toolkit.cleanup()


@pytest.mark.asyncio
async def test_structured_content_priority_over_content(mock_client):
    """structured_content takes priority over content."""
    structured_data = {"structured": True}
    result = MockCallToolResult(
        content=[MockTextContent("text content")],
        structured_content=structured_data,
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
        response = await tools["test_tool"]()

        # Should return structured_content, not content
        assert response == structured_data
        assert "text content" not in str(response)

        await toolkit.cleanup()


# ============================================================================
# Bug #6: Explicit transport_type Parameter
# ============================================================================


def test_transport_type_validation():
    """Invalid transport_type values are rejected."""
    with pytest.raises(ValueError, match="transport_type must be"):
        MCPToolkit(
            server_name="test",
            server_type="http",
            url="https://example.com",
            transport_type="invalid",
        )


def test_transport_type_sse_accepted():
    """transport_type='sse' is accepted."""
    # Mock Client to prevent initialization
    with patch("roma_dspy.tools.mcp.toolkit.Client"):
        toolkit = MCPToolkit(
            server_name="test",
            server_type="stdio",
            command="python",
            args=["test.py"],
            transport_type="sse",  # Will be ignored for stdio but should be stored
        )
        assert toolkit._transport_type == "sse"


def test_transport_type_streamable_accepted():
    """transport_type='streamable' is accepted."""
    # Mock Client to prevent initialization
    with patch("roma_dspy.tools.mcp.toolkit.Client"):
        toolkit = MCPToolkit(
            server_name="test",
            server_type="stdio",
            command="python",
            args=["test.py"],
            transport_type="streamable",  # Will be ignored for stdio but should be stored
        )
        assert toolkit._transport_type == "streamable"


def test_transport_type_none_auto_detect():
    """transport_type=None enables auto-detection."""
    # Mock Client to prevent initialization
    with patch("roma_dspy.tools.mcp.toolkit.Client"):
        toolkit = MCPToolkit(
            server_name="test",
            server_type="stdio",
            command="python",
            args=["test.py"],
            transport_type=None,
        )
        assert toolkit._transport_type is None


@pytest.mark.asyncio
async def test_explicit_sse_transport_used(mock_client):
    """Explicit transport_type='sse' uses SSETransport."""
    with (
        patch("roma_dspy.tools.mcp.toolkit.Client") as mock_client_class,
        patch("roma_dspy.tools.mcp.toolkit.SSETransport") as mock_sse,
        patch("roma_dspy.tools.mcp.toolkit.StreamableHttpTransport") as mock_streamable,
    ):
        mock_context = AsyncMock()
        mock_context.__aenter__ = AsyncMock(return_value=mock_client)
        mock_context.__aexit__ = AsyncMock(return_value=None)
        mock_client_class.return_value = mock_context

        toolkit = MCPToolkit(
            server_name="test",
            server_type="http",
            url="https://example.com/mcp",
            transport_type="sse",  # Explicit SSE
        )
        await toolkit.initialize()

        # Should use SSETransport
        mock_sse.assert_called_once()
        mock_streamable.assert_not_called()

        await toolkit.cleanup()


@pytest.mark.asyncio
async def test_explicit_streamable_transport_used(mock_client):
    """Explicit transport_type='streamable' uses StreamableHttpTransport."""
    with (
        patch("roma_dspy.tools.mcp.toolkit.Client") as mock_client_class,
        patch("roma_dspy.tools.mcp.toolkit.SSETransport") as mock_sse,
        patch("roma_dspy.tools.mcp.toolkit.StreamableHttpTransport") as mock_streamable,
    ):
        mock_context = AsyncMock()
        mock_context.__aenter__ = AsyncMock(return_value=mock_client)
        mock_context.__aexit__ = AsyncMock(return_value=None)
        mock_client_class.return_value = mock_context

        toolkit = MCPToolkit(
            server_name="test",
            server_type="http",
            url="https://example.com/mcp",
            transport_type="streamable",  # Explicit StreamableHTTP
        )
        await toolkit.initialize()

        # Should use StreamableHttpTransport
        mock_streamable.assert_called_once()
        mock_sse.assert_not_called()

        await toolkit.cleanup()


# ============================================================================
# Bug #7: Error Messages Triggering Storage
# ============================================================================


@pytest.mark.asyncio
async def test_tool_exception_raises_not_returns_string(mock_client):
    """Tool execution exceptions raise MCPToolError, not return error strings."""
    # Mock tool that raises exception
    mock_client.call_tool = AsyncMock(side_effect=RuntimeError("Tool crashed"))

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

        # Should raise MCPToolError, not return error string
        with pytest.raises(MCPToolError) as exc_info:
            await tools["test_tool"]()

        assert "execution failed" in str(exc_info.value)
        assert "Tool crashed" in str(exc_info.value)

        await toolkit.cleanup()


@pytest.mark.asyncio
async def test_large_error_message_truncated(mock_client):
    """Large error messages are truncated to prevent storage triggers."""
    # Create very large error message
    large_error = "ERROR: " + "x" * 10000  # 10KB error
    mock_client.call_tool = AsyncMock(side_effect=RuntimeError(large_error))

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

        with pytest.raises(MCPToolError) as exc_info:
            await tools["test_tool"]()

        # Error message should be truncated to 500 chars
        error_str = str(exc_info.value)
        # The original error was 10K+, truncated error should be much smaller
        assert len(error_str) < 600  # Some overhead for wrapper text

        await toolkit.cleanup()


@pytest.mark.asyncio
async def test_error_exception_chaining_preserved(mock_client):
    """Exception chaining is preserved for debugging."""
    original_error = ValueError("Original cause")
    mock_client.call_tool = AsyncMock(side_effect=original_error)

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
            use_storage=True,  # Enable storage wrapper to test error handling
            storage_threshold_kb=0.001,
            file_storage=file_storage,
        )
        await toolkit.initialize()

        tools = toolkit.get_enabled_tools()

        with pytest.raises(MCPToolError) as exc_info:
            await tools["test_tool"]()

        # Should preserve exception chain
        assert exc_info.value.__cause__ is original_error

        await toolkit.cleanup()
