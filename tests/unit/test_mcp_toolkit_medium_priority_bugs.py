"""Comprehensive tests for P2 medium priority bugs in MCP toolkit.

Tests the fixes for:
- Bug #8: Race condition in filename generation
- Bug #10: Timeout on tool execution
- Bug #9: Memory usage (deferred - goofys supports streaming)
"""

import asyncio
from unittest.mock import AsyncMock, patch
import tempfile
import re

import pytest

from roma_dspy.tools.mcp import MCPToolError, MCPToolTimeoutError, MCPToolkit


class MockCallToolResult:
    """Mock FastMCP CallToolResult for testing."""

    def __init__(self, content=None, is_error=False):
        self.content = content or []
        self.is_error = is_error


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


# ============================================================================
# Bug #8: Race Condition in Filename Generation
# ============================================================================


@pytest.mark.asyncio
async def test_concurrent_storage_generates_unique_filenames(mock_client):
    """Multiple concurrent tool calls generate unique filenames."""
    # Return large data that triggers storage
    large_data = {"items": [{"id": i} for i in range(1000)]}
    import json

    result = MockCallToolResult(
        content=[MockTextContent(json.dumps(large_data))], is_error=False
    )
    mock_client.call_tool = AsyncMock(return_value=result)

    from roma_dspy.config.schemas.storage import StorageConfig
    from roma_dspy.core.storage.file_storage import FileStorage

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

        # Execute tool multiple times concurrently
        results = await asyncio.gather(
            tools["test_tool"](),
            tools["test_tool"](),
            tools["test_tool"](),
            tools["test_tool"](),
            tools["test_tool"](),
        )

        # All results should indicate storage
        assert all("Data stored at" in result for result in results)

        # Extract filenames from results
        filenames = []
        for result in results:
            # Extract filename from "Data stored at /path/filename.parquet"
            match = re.search(r"/([^/]+\.parquet)", result)
            if match:
                filenames.append(match.group(1))

        # All filenames should be unique (no collisions)
        assert len(filenames) == len(set(filenames)), (
            f"Duplicate filenames found: {filenames}"
        )

        # Each filename should have microsecond timestamp and hex suffix
        for filename in filenames:
            # Format: prefix_YYYYMMDD_HHMMSS_microseconds_hexhexhex.parquet
            parts = filename.replace(".parquet", "").split("_")
            assert len(parts) >= 5, f"Filename {filename} missing components"
            # Last part should be 8-char hex
            hex_part = parts[-1]
            assert len(hex_part) == 8, f"Hex suffix {hex_part} should be 8 chars"
            assert all(c in "0123456789abcdef" for c in hex_part), (
                f"Hex suffix {hex_part} invalid"
            )

        await toolkit.cleanup()


@pytest.mark.asyncio
async def test_filename_includes_microseconds_and_hex(mock_client):
    """Filenames include microsecond precision and hex suffix."""
    large_data = {"test": "data" * 1000}
    import json

    result = MockCallToolResult(
        content=[MockTextContent(json.dumps(large_data))], is_error=False
    )
    mock_client.call_tool = AsyncMock(return_value=result)

    from roma_dspy.config.schemas.storage import StorageConfig
    from roma_dspy.core.storage.file_storage import FileStorage

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
        result = await tools["test_tool"]()

        # Should contain storage path
        assert "Data stored at" in result

        # Extract filename
        match = re.search(r"/([^/]+\.parquet)", result)
        assert match, "Could not find filename in result"
        filename = match.group(1)

        # Verify format: prefix_YYYYMMDD_HHMMSS_MMMMMM_hexhex.parquet
        # The timestamp should have microseconds (6 digits after seconds)
        assert re.search(r"_\d{8}_\d{6}_\d{6}_[0-9a-f]{8}\.parquet$", filename), (
            f"Filename {filename} doesn't match expected format with microseconds and hex"
        )

        await toolkit.cleanup()


# ============================================================================
# Bug #10: Timeout on Tool Execution
# ============================================================================


@pytest.mark.asyncio
async def test_tool_timeout_raises_exception(mock_client):
    """Tool execution that exceeds timeout raises MCPToolTimeoutError."""

    # Mock slow tool that takes 10 seconds
    async def slow_tool(**kwargs):
        await asyncio.sleep(10)
        return "result"

    # Mock call_tool to return a result, but the wrapper will timeout
    async def mock_slow_call_tool(tool_name, args):
        await asyncio.sleep(10)  # Simulate slow execution
        return MockCallToolResult(content=[MockTextContent("slow result")])

    mock_client.call_tool = mock_slow_call_tool

    from roma_dspy.config.schemas.storage import StorageConfig
    from roma_dspy.core.storage.file_storage import FileStorage

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
            tool_timeout=0.5,  # 500ms timeout
            use_storage=True,
            storage_threshold_kb=1000,
            file_storage=file_storage,
        )
        await toolkit.initialize()

        tools = toolkit.get_enabled_tools()

        # Should raise timeout error
        with pytest.raises(MCPToolTimeoutError) as exc_info:
            await tools["test_tool"]()

        assert "timed out after 0.5s" in str(exc_info.value)

        await toolkit.cleanup()


@pytest.mark.asyncio
async def test_custom_timeout_value(mock_client):
    """Custom timeout value is respected."""
    result = MockCallToolResult(
        content=[MockTextContent("fast result")], is_error=False
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
            tool_timeout=120.0,  # 2 minutes
        )
        await toolkit.initialize()

        # Verify timeout is stored
        assert toolkit._tool_timeout == 120.0

        await toolkit.cleanup()


@pytest.mark.asyncio
async def test_default_timeout_is_300_seconds(mock_client):
    """Default timeout is 300 seconds (5 minutes)."""
    result = MockCallToolResult(content=[MockTextContent("result")], is_error=False)
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
            # No tool_timeout specified
        )
        await toolkit.initialize()

        # Verify default timeout
        assert toolkit._tool_timeout == 300.0

        await toolkit.cleanup()


@pytest.mark.asyncio
async def test_fast_tool_completes_before_timeout(mock_client):
    """Fast tools complete successfully before timeout."""
    result = MockCallToolResult(
        content=[MockTextContent("quick result")], is_error=False
    )

    # Fast tool (completes in 100ms)
    async def fast_call_tool(tool_name, args):
        await asyncio.sleep(0.1)
        return result

    mock_client.call_tool = fast_call_tool

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
            tool_timeout=1.0,  # 1 second timeout
        )
        await toolkit.initialize()

        tools = toolkit.get_enabled_tools()

        # Should complete successfully
        response = await tools["test_tool"]()
        assert response == "quick result"

        await toolkit.cleanup()


# ============================================================================
# Bug #9: Memory Usage (Note: Deferred)
# ============================================================================


def test_bug_9_deferred_note():
    """Bug #9 (memory usage) is deferred - goofys supports sequential streaming.

    Goofys write characteristics:
    - Supports sequential writes (streaming)
    - Does not support random writes
    - Uses close-to-open consistency model
    - No local disk cache

    Future optimization: Implement streaming writes for very large datasets (>50MB)
    to reduce memory footprint during serialization.
    """
    # This is a documentation test - always passes
    assert True, "Bug #9 optimization deferred - goofys streaming compatible"
