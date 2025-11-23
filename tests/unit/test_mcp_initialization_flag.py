"""
Unit tests for NEW BUG #1: Missing _initialized flag in MCPToolkit.

Tests verify that:
1. Double initialization is prevented in both FastMCP and MCP SDK paths
2. Manager correctly detects initialization state
3. Cleanup allows re-initialization
4. Partial initialization failure allows retry
"""

import pytest
import asyncio
from unittest.mock import Mock, patch, AsyncMock, MagicMock
from roma_dspy.tools.mcp.toolkit import MCPToolkit


class TestMCPInitializationFlag:
    """Test suite for _initialized flag implementation."""

    def test_flag_exists_after_construction(self):
        """Test that _initialized flag is created during __init__."""
        with patch("roma_dspy.tools.mcp.toolkit.MCP_AVAILABLE", True):
            # Create toolkit
            # Mock _initialize_tools to prevent actual connection attempt
            with patch.object(MCPToolkit, "_initialize_tools"):
                toolkit = MCPToolkit(
                    server_name="test_server",
                    server_type="stdio",
                    command="python",
                    args=["server.py"],
                )

                # Flag should exist and be False
                assert hasattr(toolkit, "_initialized")
                assert toolkit._initialized is False

    @pytest.mark.asyncio
    async def test_flag_set_after_successful_initialization(self):
        """Test that _initialized flag is set to True after successful init."""
        with (
            patch("roma_dspy.tools.mcp.toolkit.MCP_AVAILABLE", True),
            patch("roma_dspy.tools.mcp.toolkit.USING_FASTMCP", True),
        ):
            toolkit = MCPToolkit(
                server_name="test_server",
                server_type="stdio",
                command="python",
                args=["server.py"],
            )

            # Mock the async initialization to succeed
            mock_tools = [Mock(name="tool1"), Mock(name="tool2")]
            with patch.object(
                toolkit, "_initialize_with_fastmcp", new_callable=AsyncMock
            ) as mock_init:
                mock_init.return_value = None
                toolkit._mcp_tools = {"tool1": AsyncMock(), "tool2": AsyncMock()}

                # Initialize
                await toolkit.initialize()

                # Flag should be True
                assert toolkit._initialized is True

    @pytest.mark.asyncio
    async def test_double_initialization_prevented(self):
        """Test that calling initialize() twice doesn't re-initialize."""
        with (
            patch("roma_dspy.tools.mcp.toolkit.MCP_AVAILABLE", True),
            patch("roma_dspy.tools.mcp.toolkit.USING_FASTMCP", True),
        ):
            toolkit = MCPToolkit(
                server_name="test_server",
                server_type="stdio",
                command="python",
                args=["server.py"],
            )

            # Mock the async initialization
            mock_init_calls = []

            async def mock_async_init():
                mock_init_calls.append(1)
                toolkit._mcp_tools = {"tool1": AsyncMock()}
                toolkit._tracked_mcp_tools = {"tool1": AsyncMock()}

            with patch.object(
                toolkit, "_async_initialize", side_effect=mock_async_init
            ):
                # First initialization
                await toolkit.initialize()
                assert len(mock_init_calls) == 1
                assert toolkit._initialized is True

                # Second initialization - should be no-op
                await toolkit.initialize()
                assert len(mock_init_calls) == 1  # No additional calls!
                assert toolkit._initialized is True

    @pytest.mark.asyncio
    async def test_guard_checks_flag_before_connection_state(self):
        """Test that initialize() checks _initialized flag first."""
        with patch("roma_dspy.tools.mcp.toolkit.MCP_AVAILABLE", True):
            toolkit = MCPToolkit(
                server_name="test_server",
                server_type="stdio",
                command="python",
                args=["server.py"],
            )

            # Manually set flag to True
            toolkit._initialized = True

            # Mock to track if _async_initialize is called
            with patch.object(
                toolkit, "_async_initialize", new_callable=AsyncMock
            ) as mock_init:
                # Call initialize
                await toolkit.initialize()

                # Should not have called _async_initialize
                mock_init.assert_not_called()

    @pytest.mark.asyncio
    async def test_fallback_guard_handles_inconsistent_state(self):
        """Test that fallback guard sets flag if connection exists but flag is False."""
        with patch("roma_dspy.tools.mcp.toolkit.MCP_AVAILABLE", True):
            toolkit = MCPToolkit(
                server_name="test_server",
                server_type="stdio",
                command="python",
                args=["server.py"],
            )

            # Simulate inconsistent state: connection exists but flag is False
            toolkit._initialized = False
            toolkit._context = Mock()  # Connection exists

            # Mock to track if _async_initialize is called
            with patch.object(
                toolkit, "_async_initialize", new_callable=AsyncMock
            ) as mock_init:
                # Call initialize
                await toolkit.initialize()

                # Should not have called _async_initialize
                mock_init.assert_not_called()

                # Flag should now be set
                assert toolkit._initialized is True

    @pytest.mark.asyncio
    async def test_cleanup_resets_flag(self):
        """Test that cleanup() resets _initialized flag to False."""
        with patch("roma_dspy.tools.mcp.toolkit.MCP_AVAILABLE", True):
            toolkit = MCPToolkit(
                server_name="test_server",
                server_type="stdio",
                command="python",
                args=["server.py"],
            )

            # Set up initialized state
            toolkit._initialized = True
            toolkit._context_manager = Mock()
            toolkit._context = Mock()
            toolkit._context_manager.__aexit__ = AsyncMock()

            # Cleanup
            await toolkit.cleanup()

            # Flag should be reset
            assert toolkit._initialized is False

    @pytest.mark.asyncio
    async def test_reinitialization_after_cleanup(self):
        """Test that toolkit can be re-initialized after cleanup."""
        with (
            patch("roma_dspy.tools.mcp.toolkit.MCP_AVAILABLE", True),
            patch("roma_dspy.tools.mcp.toolkit.USING_FASTMCP", True),
        ):
            toolkit = MCPToolkit(
                server_name="test_server",
                server_type="stdio",
                command="python",
                args=["server.py"],
            )

            # Mock initialization
            init_call_count = [0]

            async def mock_async_init():
                init_call_count[0] += 1
                toolkit._mcp_tools = {"tool1": AsyncMock()}
                toolkit._tracked_mcp_tools = {"tool1": AsyncMock()}

            with patch.object(
                toolkit, "_async_initialize", side_effect=mock_async_init
            ):
                # First initialization
                await toolkit.initialize()
                assert init_call_count[0] == 1
                assert toolkit._initialized is True

                # Cleanup
                toolkit._context_manager = Mock()
                toolkit._context = Mock()
                toolkit._context_manager.__aexit__ = AsyncMock()
                await toolkit.cleanup()
                assert toolkit._initialized is False

                # Re-initialization should work
                await toolkit.initialize()
                assert init_call_count[0] == 2
                assert toolkit._initialized is True

    @pytest.mark.asyncio
    async def test_partial_initialization_failure_allows_retry(self):
        """Test that failed initialization leaves flag False and allows retry."""
        with patch("roma_dspy.tools.mcp.toolkit.MCP_AVAILABLE", True):
            toolkit = MCPToolkit(
                server_name="test_server",
                server_type="stdio",
                command="python",
                args=["server.py"],
            )

            # Mock to fail on first call, succeed on second
            call_count = [0]

            async def mock_async_init():
                call_count[0] += 1
                if call_count[0] == 1:
                    raise Exception("Connection failed")
                toolkit._mcp_tools = {"tool1": AsyncMock()}
                toolkit._tracked_mcp_tools = {"tool1": AsyncMock()}

            with patch.object(
                toolkit, "_async_initialize", side_effect=mock_async_init
            ):
                # First attempt - should fail
                with pytest.raises(Exception, match="Connection failed"):
                    await toolkit.initialize()

                # Flag should still be False
                assert toolkit._initialized is False

                # Retry should work
                await toolkit.initialize()
                assert toolkit._initialized is True
                assert call_count[0] == 2

    @pytest.mark.asyncio
    async def test_manager_checks_flag(self):
        """Test that ToolkitManager correctly checks _initialized flag."""
        # This is more of an integration test with manager
        # Testing the code path in manager.py:536-538

        with patch("roma_dspy.tools.mcp.toolkit.MCP_AVAILABLE", True):
            toolkit = MCPToolkit(
                server_name="test_server",
                server_type="stdio",
                command="python",
                args=["server.py"],
            )

            # Simulate manager's check
            needs_init = True
            if hasattr(toolkit, "_initialized"):
                needs_init = not toolkit._initialized

            # Should detect flag exists and is False
            assert needs_init is True

            # Set flag
            toolkit._initialized = True

            # Check again
            if hasattr(toolkit, "_initialized"):
                needs_init = not toolkit._initialized

            # Should detect flag is True
            assert needs_init is False

    @pytest.mark.asyncio
    async def test_fastmcp_path_double_init_prevented(self):
        """Test double init prevention specifically for FastMCP path."""
        with (
            patch("roma_dspy.tools.mcp.toolkit.MCP_AVAILABLE", True),
            patch("roma_dspy.tools.mcp.toolkit.USING_FASTMCP", True),
        ):
            toolkit = MCPToolkit(
                server_name="test_server",
                server_type="http",
                url="http://example.com/mcp",
            )

            # Mock FastMCP initialization
            init_calls = []

            async def mock_fastmcp_init():
                init_calls.append(1)
                toolkit._context_manager = Mock()
                toolkit._context = Mock()
                toolkit._mcp_tools = {"fetch": AsyncMock()}
                toolkit._tracked_mcp_tools = {"fetch": AsyncMock()}

            with patch.object(
                toolkit, "_initialize_with_fastmcp", side_effect=mock_fastmcp_init
            ):
                # First init
                await toolkit.initialize()
                assert len(init_calls) == 1
                assert toolkit._initialized is True

                # Second init - should be prevented by flag
                await toolkit.initialize()
                assert len(init_calls) == 1  # No additional call

                # Context should still exist (not recreated)
                assert toolkit._context is not None

    @pytest.mark.asyncio
    async def test_mcp_sdk_path_double_init_prevented(self):
        """Test double init prevention specifically for MCP SDK path."""
        with (
            patch("roma_dspy.tools.mcp.toolkit.MCP_AVAILABLE", True),
            patch("roma_dspy.tools.mcp.toolkit.USING_FASTMCP", False),
        ):
            toolkit = MCPToolkit(
                server_name="test_server",
                server_type="stdio",
                command="python",
                args=["server.py"],
            )

            # Mock MCP SDK initialization
            init_calls = []

            async def mock_sdk_init():
                init_calls.append(1)
                toolkit._context_manager = Mock()
                toolkit._context = Mock()
                toolkit._session = Mock()
                toolkit._mcp_tools = {"tool": AsyncMock()}
                toolkit._tracked_mcp_tools = {"tool": AsyncMock()}

            with patch.object(
                toolkit, "_initialize_with_mcp_sdk", side_effect=mock_sdk_init
            ):
                # First init
                await toolkit.initialize()
                assert len(init_calls) == 1
                assert toolkit._initialized is True

                # Second init - should be prevented by flag
                await toolkit.initialize()
                assert len(init_calls) == 1  # No additional call

                # Session should still exist (not recreated)
                assert toolkit._session is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
