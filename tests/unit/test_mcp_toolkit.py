"""Unit tests for MCPToolkit.

Tests cover:
- Parameter validation
- use_storage flag behavior
- Storage threshold configuration
- Tool wrapping and unwrapping
- Cleanup functionality
- DSPy compatibility
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any, Dict

import pytest
import pytest_asyncio

from roma_dspy.config.schemas.storage import StorageConfig
from roma_dspy.core.storage import FileStorage
from roma_dspy.tools.mcp.toolkit import MCPToolkit

# Add fixtures directory to path for importing test server
FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"
sys.path.insert(0, str(FIXTURES_DIR))


class TestMCPToolkitParameterValidation:
    """Test parameter validation in MCPToolkit.__init__()."""

    def test_server_name_required(self):
        """Test that server_name is required."""
        with pytest.raises(ValueError, match="server_name is required"):
            MCPToolkit(
                server_name="",
                server_type="stdio",
                command="python",
            )

    def test_server_type_validation(self):
        """Test that server_type must be 'stdio' or 'http'."""
        with pytest.raises(ValueError, match="server_type must be 'stdio' or 'http'"):
            MCPToolkit(
                server_name="test",
                server_type="invalid",
                command="python",
            )

    def test_stdio_requires_command(self):
        """Test that stdio server_type requires command."""
        with pytest.raises(ValueError, match="command is required for stdio"):
            MCPToolkit(
                server_name="test",
                server_type="stdio",
            )

    def test_http_requires_url(self):
        """Test that http server_type requires url."""
        with pytest.raises(ValueError, match="url is required for http"):
            MCPToolkit(
                server_name="test",
                server_type="http",
            )

    def test_use_storage_requires_file_storage(self):
        """Test that use_storage=True requires file_storage."""
        with pytest.raises(ValueError, match="use_storage=True requires file_storage"):
            MCPToolkit(
                server_name="test",
                server_type="stdio",
                command="python",
                args=["test_server.py"],
                use_storage=True,
                # file_storage not provided
            )

    def test_storage_threshold_ignored_without_use_storage(self):
        """Test that storage_threshold_kb is ignored when use_storage=False."""
        toolkit = MCPToolkit(
            server_name="test",
            server_type="stdio",
            command="python",
            args=[str(FIXTURES_DIR / "mcp_test_server.py")],
            use_storage=False,
            storage_threshold_kb=50,  # Should be ignored
            enabled=False,  # Don't actually connect
        )

        # Check that wrapping is disabled
        assert toolkit._enable_wrapping is False
        assert toolkit._storage_threshold_kb is None


class TestMCPToolkitStorageConfiguration:
    """Test storage configuration with use_storage flag."""

    def test_use_storage_false_no_wrapping(self):
        """Test that use_storage=False disables wrapping."""
        toolkit = MCPToolkit(
            server_name="test",
            server_type="stdio",
            command="python",
            args=[str(FIXTURES_DIR / "mcp_test_server.py")],
            use_storage=False,
            enabled=False,  # Don't connect
        )

        assert toolkit._use_storage is False
        assert toolkit._enable_wrapping is False
        assert toolkit._storage_threshold_kb is None

    def test_use_storage_true_enables_wrapping(self, tmp_path):
        """Test that use_storage=True enables wrapping."""
        # Create proper StorageConfig
        storage_config = StorageConfig(base_path=str(tmp_path))
        file_storage = FileStorage(config=storage_config, execution_id="test_exec")

        toolkit = MCPToolkit(
            server_name="test",
            server_type="stdio",
            command="python",
            args=[str(FIXTURES_DIR / "mcp_test_server.py")],
            use_storage=True,
            file_storage=file_storage,
            enabled=False,  # Don't connect
        )

        assert toolkit._use_storage is True
        assert toolkit._enable_wrapping is True
        assert toolkit._storage_threshold_kb == 100  # Default

    def test_custom_threshold(self, tmp_path):
        """Test custom storage threshold."""
        # Create proper StorageConfig
        storage_config = StorageConfig(base_path=str(tmp_path))
        file_storage = FileStorage(config=storage_config, execution_id="test_exec")

        toolkit = MCPToolkit(
            server_name="test",
            server_type="stdio",
            command="python",
            args=[str(FIXTURES_DIR / "mcp_test_server.py")],
            use_storage=True,
            storage_threshold_kb=10,  # Custom threshold
            file_storage=file_storage,
            enabled=False,  # Don't connect
        )

        assert toolkit._storage_threshold_kb == 10


class TestMCPToolkitIntegration:
    """Integration tests with real MCP server."""

    @pytest_asyncio.fixture
    async def toolkit_without_storage(self):
        """Create toolkit without storage wrapper."""
        toolkit = MCPToolkit(
            server_name="test_server",
            server_type="stdio",
            command="python",
            args=[str(FIXTURES_DIR / "mcp_test_server.py")],
            use_storage=False,
        )

        # Explicitly initialize in async context
        await toolkit.initialize()

        yield toolkit

        # Cleanup
        await toolkit.cleanup()

    @pytest_asyncio.fixture
    async def toolkit_with_storage(self, tmp_path):
        """Create toolkit with storage wrapper."""
        # Create proper StorageConfig
        storage_config = StorageConfig(base_path=str(tmp_path))
        file_storage = FileStorage(config=storage_config, execution_id="test_exec")

        toolkit = MCPToolkit(
            server_name="test_server",
            server_type="stdio",
            command="python",
            args=[str(FIXTURES_DIR / "mcp_test_server.py")],
            use_storage=True,
            storage_threshold_kb=50,  # Aggressive threshold for testing
            file_storage=file_storage,
        )

        # Explicitly initialize in async context
        await toolkit.initialize()

        yield toolkit

        # Cleanup
        await toolkit.cleanup()

    @pytest.mark.asyncio
    async def test_tool_discovery(self, toolkit_without_storage):
        """Test that tools are discovered from MCP server."""
        available_tools = toolkit_without_storage.get_available_tool_names()

        assert "get_small_data" in available_tools
        assert "get_big_data" in available_tools
        assert "failing_tool" in available_tools

    @pytest.mark.asyncio
    async def test_enabled_tools_filtering(self):
        """Test include/exclude filtering of tools."""
        # Create toolkit with include filter
        toolkit = MCPToolkit(
            server_name="filtered",
            server_type="stdio",
            command="python",
            args=[str(FIXTURES_DIR / "mcp_test_server.py")],
            include_tools=["get_small_data"],
        )

        try:
            # Initialize in async context
            await toolkit.initialize()

            enabled = toolkit.get_enabled_tools()
            assert "get_small_data" in enabled
            assert "get_big_data" not in enabled
        finally:
            await toolkit.cleanup()

    @pytest.mark.asyncio
    async def test_small_data_unwrapped(self, toolkit_without_storage):
        """Test that small data passes through unwrapped."""
        tools = toolkit_without_storage.get_enabled_tools()
        get_small_data = tools["get_small_data"]

        result = await get_small_data(key="test_key")

        # Result should be raw string (DSPy compatible)
        assert isinstance(result, str)
        assert "get_small_data" in result
        assert "test_key" in result
        # Should NOT contain storage path
        assert "Data stored at" not in result

    @pytest.mark.asyncio
    async def test_big_data_stored(self, toolkit_with_storage):
        """Test that big data triggers storage."""
        tools = toolkit_with_storage.get_enabled_tools()
        get_big_data = tools["get_big_data"]

        result = await get_big_data(rows=1000)

        # Result should be file path string (DSPy compatible)
        assert isinstance(result, str)
        assert "Data stored at" in result
        assert ".parquet" in result
        assert "Use file operations" in result

    @pytest.mark.asyncio
    async def test_error_handling(self, toolkit_without_storage):
        """Test error handling returns string message."""
        tools = toolkit_without_storage.get_enabled_tools()
        failing_tool = tools["failing_tool"]

        result = await failing_tool(message="Custom error")

        # Error should be returned as string (DSPy compatible)
        assert isinstance(result, str)
        assert "Error calling failing_tool" in result
        assert "Custom error" in result

    @pytest.mark.asyncio
    async def test_cleanup_closes_connection(self):
        """Test that cleanup properly closes MCP connection."""
        toolkit = MCPToolkit(
            server_name="cleanup_test",
            server_type="stdio",
            command="python",
            args=[str(FIXTURES_DIR / "mcp_test_server.py")],
        )

        # Initialize in async context
        await toolkit.initialize()

        # Verify connection is active
        assert toolkit._session is not None
        assert toolkit._context is not None

        # Cleanup
        await toolkit.cleanup()

        # Verify connection is closed
        assert toolkit._session is None
        assert toolkit._context is None
        assert toolkit._mcp_tools == {}

    @pytest.mark.asyncio
    async def test_multiple_tool_calls(self, toolkit_without_storage):
        """Test multiple sequential tool calls."""
        tools = toolkit_without_storage.get_enabled_tools()
        get_small_data = tools["get_small_data"]

        # Call same tool multiple times
        result1 = await get_small_data(key="call_1")
        result2 = await get_small_data(key="call_2")

        assert "call_1" in result1
        assert "call_2" in result2

    @pytest.mark.asyncio
    async def test_storage_wrapper_preserves_metadata(self, toolkit_with_storage):
        """Test that storage wrapper preserves tool metadata."""
        tools = toolkit_with_storage.get_enabled_tools()
        get_big_data = tools["get_big_data"]

        # Check function metadata
        assert get_big_data.__name__ == "get_big_data"


class TestMCPToolkitDSPyCompatibility:
    """Test DSPy compatibility of results."""

    @pytest.mark.asyncio
    async def test_never_returns_dict(self, tmp_path):
        """Test that wrapped tools never return dict (breaks DSPy)."""
        # Create proper StorageConfig
        storage_config = StorageConfig(base_path=str(tmp_path))
        file_storage = FileStorage(config=storage_config, execution_id="test_exec")

        toolkit = MCPToolkit(
            server_name="test",
            server_type="stdio",
            command="python",
            args=[str(FIXTURES_DIR / "mcp_test_server.py")],
            use_storage=True,
            storage_threshold_kb=50,
            file_storage=file_storage,
        )

        try:
            # Initialize in async context
            await toolkit.initialize()

            tools = toolkit.get_enabled_tools()

            # Test all tools
            for tool_name, tool_func in tools.items():
                if tool_name == "get_small_data":
                    result = await tool_func(key="test")
                elif tool_name == "get_big_data":
                    result = await tool_func(rows=1000)
                elif tool_name == "failing_tool":
                    result = await tool_func(message="test")

                # CRITICAL: Result must be string, never dict
                assert isinstance(result, str), f"{tool_name} returned {type(result)}"
                assert not isinstance(result, dict)

        finally:
            await toolkit.cleanup()


class TestMCPToolkitHTTPMode:
    """Test HTTP server mode configuration."""

    def test_http_mode_validation(self):
        """Test HTTP mode requires url parameter."""
        with pytest.raises(ValueError, match="url is required"):
            MCPToolkit(
                server_name="http_test",
                server_type="http",
                # url not provided
                enabled=False,
            )

    def test_http_mode_with_headers(self, tmp_path):
        """Test HTTP mode accepts headers."""
        # Create proper StorageConfig
        storage_config = StorageConfig(base_path=str(tmp_path))
        file_storage = FileStorage(config=storage_config, execution_id="test_exec")

        toolkit = MCPToolkit(
            server_name="http_test",
            server_type="http",
            url="http://localhost:3000/mcp",
            headers={"Authorization": "Bearer test_token"},
            use_storage=True,
            file_storage=file_storage,
            enabled=False,  # Don't actually connect
        )

        assert toolkit._url == "http://localhost:3000/mcp"
        assert toolkit._headers == {"Authorization": "Bearer test_token"}


class TestMCPToolkitSchemaExtraction:
    """Test DSPy Tool schema extraction and validation."""

    @pytest_asyncio.fixture
    async def initialized_toolkit(self):
        """Create and initialize toolkit with test MCP server."""
        toolkit = MCPToolkit(
            server_name="test",
            server_type="stdio",
            command="python",
            args=[str(FIXTURES_DIR / "mcp_test_server.py")],
            use_storage=False,
        )
        await toolkit.initialize()
        yield toolkit
        await toolkit.cleanup()

    @pytest.mark.asyncio
    async def test_tools_are_dspy_tool_objects(self, initialized_toolkit):
        """Test that tools are DSPy Tool objects."""
        import dspy

        tools = initialized_toolkit.get_enabled_tools()
        assert len(tools) > 0

        for tool_name, tool in tools.items():
            assert isinstance(tool, dspy.Tool), f"{tool_name} is not a Tool object"

    @pytest.mark.asyncio
    async def test_tool_schema_metadata(self, initialized_toolkit):
        """Test that Tool objects have schema metadata."""
        tools = initialized_toolkit.get_enabled_tools()

        # Check all tools have required attributes
        for tool_name, tool in tools.items():
            assert hasattr(tool, "args"), f"{tool_name} missing args"
            assert hasattr(tool, "arg_types"), f"{tool_name} missing arg_types"
            assert hasattr(tool, "arg_desc"), f"{tool_name} missing arg_desc"
            assert hasattr(tool, "name"), f"{tool_name} missing name"
            assert hasattr(tool, "desc"), f"{tool_name} missing desc"

    @pytest.mark.asyncio
    async def test_tool_objects_are_callable(self, initialized_toolkit):
        """Test that Tool objects are callable."""
        tools = initialized_toolkit.get_enabled_tools()

        for tool_name, tool in tools.items():
            assert callable(tool), f"{tool_name} is not callable"
            assert hasattr(tool, "acall"), f"{tool_name} missing acall method"

    @pytest.mark.asyncio
    async def test_storage_integration_with_tool_objects(self, tmp_path):
        """Test that storage wrapper works with Tool objects."""
        storage_config = StorageConfig(base_path=str(tmp_path))
        file_storage = FileStorage(config=storage_config, execution_id="test_schema")

        toolkit = MCPToolkit(
            server_name="test",
            server_type="stdio",
            command="python",
            args=[str(FIXTURES_DIR / "mcp_test_server.py")],
            use_storage=True,
            storage_threshold_kb=1,  # Aggressive
            file_storage=file_storage,
        )
        await toolkit.initialize()

        tools = toolkit.get_enabled_tools()

        # Verify tools are still Tool objects after wrapping
        import dspy

        for tool in tools.values():
            assert isinstance(tool, dspy.Tool)

        await toolkit.cleanup()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
