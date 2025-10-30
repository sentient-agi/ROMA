"""MCP (Model Context Protocol) toolkit for ROMA-DSPy.

Enables agents to use tools from external MCP servers via stdio or HTTP.
"""

from __future__ import annotations

import asyncio
import functools
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional, Set

import dspy
from dspy.adapters.types.tool import convert_input_schema_to_tool_args
from loguru import logger

from roma_dspy.tools.base.base import BaseToolkit
from roma_dspy.tools.mcp.exceptions import MCPToolError, MCPToolTimeoutError
from roma_dspy.tools.metrics.decorators import track_tool_invocation

try:
    # Use FastMCP client (v2 by jlowin) instead of official MCP SDK
    # Fixes stdio transport issues: https://github.com/modelcontextprotocol/python-sdk/issues/395
    from fastmcp.client import Client
    from fastmcp.client.transports import (
        PythonStdioTransport,
        SSETransport,
        StdioTransport,
        StreamableHttpTransport,
    )
    MCP_AVAILABLE = True
    USING_FASTMCP = True
except ImportError:
    try:
        # Fallback to official MCP SDK (has stdio bugs but might work for HTTP/SSE)
        from mcp.client.session import ClientSession
        from mcp.client.stdio import StdioServerParameters, stdio_client
        from mcp.client.streamable_http import streamablehttp_client
        from mcp.client.sse import sse_client
        MCP_AVAILABLE = True
        USING_FASTMCP = False
    except ImportError:
        MCP_AVAILABLE = False
        USING_FASTMCP = False

# Import MCP error types for better error handling
try:
    from mcp.shared.exceptions import McpError
except ImportError:
    McpError = None

if TYPE_CHECKING:
    from roma_dspy.core.storage import FileStorage


def _convert_mcp_tool_result(call_tool_result) -> str | list:
    """Convert MCP CallToolResult to DSPy-compatible format.

    Handles both FastMCP (is_error) and official MCP SDK (isError) formats.

    Args:
        call_tool_result: MCP CallToolResult object

    Returns:
        Text content as string or list

    Raises:
        RuntimeError: If tool execution failed
    """
    from mcp.types import TextContent

    text_contents: list[TextContent] = []
    non_text_contents = []

    for content in call_tool_result.content:
        if isinstance(content, TextContent):
            text_contents.append(content)
        else:
            non_text_contents.append(content)

    tool_content = [content.text for content in text_contents]
    if len(text_contents) == 1:
        tool_content = tool_content[0]

    # Handle both FastMCP (is_error) and official MCP SDK (isError)
    is_error = getattr(call_tool_result, 'is_error', getattr(call_tool_result, 'isError', False))
    if is_error:
        raise RuntimeError(f"Failed to call MCP tool: {tool_content}")

    return tool_content or non_text_contents


def _convert_mcp_tool_to_dspy(client, tool):
    """Convert MCP tool to DSPy Tool with full schema extraction.

    Compatible with both FastMCP and official MCP SDK.

    Args:
        client: FastMCP Client or official MCP ClientSession
        tool: MCP Tool object with inputSchema

    Returns:
        DSPy Tool object with args, arg_types, arg_desc
    """
    # Extract schema from MCP tool's inputSchema
    args, arg_types, arg_desc = convert_input_schema_to_tool_args(tool.inputSchema)

    # Create async callable that calls MCP client
    async def func(*args_tuple, **kwargs):
        try:
            result = await client.call_tool(tool.name, arguments=kwargs)
            return _convert_mcp_tool_result(result)
        except Exception as e:
            # Handle MCP protocol errors (like JSON parse errors)
            if McpError and isinstance(e, McpError):
                error_msg = str(e)[:500]  # Limit error message size
                raise MCPToolError(
                    f"{tool.name} MCP protocol error: {error_msg}"
                ) from e
            # Re-raise other exceptions
            raise

    # Create Tool with extracted schema
    return dspy.Tool(
        func=func,
        name=tool.name,
        desc=tool.description,
        args=args,
        arg_types=arg_types,
        arg_desc=arg_desc
    )


class MCPToolkit(BaseToolkit):
    """
    MCP toolkit with DSPy Tool integration and smart data handling.

    Connects to MCP servers and exposes tools as DSPy Tool objects with
    full schema metadata (args, arg_types, arg_desc). This enables:
    - Parameter validation before MCP server calls
    - Better LLM tool selection via schema in prompts
    - Type-safe tool invocation
    - Optional storage for large datasets

    Features:
    - One toolkit per MCP server
    - Automatic tool discovery via MCP protocol
    - Full schema extraction (args, types, descriptions)
    - Optional storage for big data (opt-in via use_storage flag)
    - Raw result passthrough for small data (no overhead)
    - DSPy compatible (returns raw or string, never dict)

    Architecture:
    - FastMCP or official MCP SDK handles connection lifecycle
    - DSPy Tool.from_mcp_tool() extracts schema and wraps execution
    - Storage wrapper (optional) handles large datasets
    - Metrics tracking records all tool invocations

    Configuration Examples:

    Simple tools (no storage):
        ```yaml
        - class_name: MCPToolkit
          toolkit_config:
            server_name: time_tools
            server_type: stdio
            command: python
            args: ["servers/time_server.py"]
            use_storage: false  # Explicit - no wrapping
        ```

    Big data tools (with storage, default threshold):
        ```yaml
        - class_name: MCPToolkit
          toolkit_config:
            server_name: database
            server_type: stdio
            command: python
            args: ["servers/db_server.py"]
            use_storage: true  # Enable wrapping
            # storage_threshold_kb: 100 (default)
        ```

    Big data tools (with storage, custom threshold):
        ```yaml
        - class_name: MCPToolkit
          toolkit_config:
            server_name: analytics
            server_type: stdio
            command: python
            args: ["servers/analytics_server.py"]
            use_storage: true
            storage_threshold_kb: 10  # Aggressive protection
        ```

    Security:
    - MCP servers are external processes
    - Tool results are untrusted
    - Storage wrapper provides size protection
    - File paths are execution-isolated via FileStorage
    """

    # FileStorage is OPTIONAL (only needed if use_storage=True)
    REQUIRES_FILE_STORAGE = False

    # Toolkit type for observability
    TOOLKIT_TYPE: str = "mcp"

    def __init__(
        self,
        server_name: str,
        server_type: str,
        command: Optional[str] = None,
        args: Optional[List[str]] = None,
        env: Optional[Dict[str, str]] = None,
        url: Optional[str] = None,
        headers: Optional[Dict[str, str]] = None,
        transport_type: Optional[str] = None,
        tool_timeout: Optional[float] = None,
        use_storage: bool = False,
        storage_threshold_kb: int = 100,
        enabled: bool = True,
        include_tools: Optional[List[str]] = None,
        exclude_tools: Optional[List[str]] = None,
        file_storage: Optional[FileStorage] = None,
        **config,
    ):
        """Initialize MCP toolkit.

        Args:
            server_name: Unique identifier for this MCP server
            server_type: "stdio" (subprocess) or "http" (network)
            command: Command to spawn stdio server (e.g., "python")
            args: Arguments for stdio server (e.g., ["server.py"])
            env: Environment variables for stdio server
            url: URL for HTTP server (e.g., "http://localhost:3000/mcp")
            headers: HTTP headers (e.g., {"Authorization": "Bearer ..."})
            transport_type: HTTP transport type - "sse" or "streamable" (None = auto-detect)
            tool_timeout: Timeout in seconds for tool execution (None = 300s default)
            use_storage: Enable storage wrapper for big data protection (default: False)
            storage_threshold_kb: Size threshold in KB for storage (default: 100)
            enabled: Whether this toolkit is enabled
            include_tools: Whitelist of tools to enable (None = all)
            exclude_tools: Blacklist of tools to exclude
            file_storage: FileStorage instance (required if use_storage=True)
            **config: Additional config

        Raises:
            ValueError: If parameters are invalid or inconsistent
        """
        # Validate required parameters
        if not server_name:
            raise ValueError("server_name is required")
        if server_type not in ("stdio", "http"):
            raise ValueError(f"server_type must be 'stdio' or 'http', got: {server_type}")

        if server_type == "stdio":
            if not command:
                raise ValueError("command is required for stdio server_type")
        elif server_type == "http":
            if not url:
                raise ValueError("url is required for http server_type")

        # BUG FIX #6: Validate transport_type parameter
        if transport_type is not None and transport_type not in ("sse", "streamable"):
            raise ValueError(f"transport_type must be 'sse', 'streamable', or None (auto-detect), got: {transport_type}")

        # Validate storage configuration
        if use_storage and not file_storage:
            raise ValueError(
                f"MCPToolkit '{server_name}': use_storage=True requires file_storage. "
                "Provide file_storage instance or set use_storage=False."
            )

        # Warn if threshold set but storage disabled
        if not use_storage and storage_threshold_kb != 100:
            logger.debug(
                f"MCPToolkit '{server_name}': storage_threshold_kb={storage_threshold_kb} "
                f"ignored because use_storage=False"
            )

        # Store MCP server config
        self._server_name = server_name
        self._server_type = server_type
        self._command = command
        self._args = args or []
        self._env = env
        self._url = url
        self._headers = headers
        self._transport_type = transport_type  # BUG FIX #6: Store explicit transport type
        self._tool_timeout = tool_timeout if tool_timeout is not None else 300.0  # BUG FIX #10: 5min default

        # Store storage config
        self._use_storage = use_storage
        self._storage_threshold_kb = storage_threshold_kb if use_storage else None

        # MCP connection state (initialized in _initialize_tools)
        self._context_manager = None
        self._context = None
        self._session = None
        self._mcp_tools: Dict[str, Any] = {}  # tool_name -> DSPy Tool object

        # Enable wrapping only if use_storage is True
        self._enable_wrapping = use_storage

        # BUG FIX: NEW #1 - Track initialization state
        # Manager checks this flag to prevent double initialization
        self._initialized = False

        # Pass storage threshold to BaseToolkit if storage enabled
        if use_storage and "storage_threshold_kb" not in config:
            config["storage_threshold_kb"] = storage_threshold_kb

        # Call parent (will call _setup_dependencies and _initialize_tools)
        super().__init__(
            enabled=enabled,
            include_tools=include_tools,
            exclude_tools=exclude_tools,
            file_storage=file_storage if use_storage else None,
            **config,
        )

    @property
    def class_name(self) -> str:
        """Return server-specific name instead of generic MCPToolkit.

        This allows MLflow/observability to distinguish between different MCP servers.
        Example: mcp_exa, mcp_coingecko, etc.
        """
        return f"mcp_{self._server_name}"

    @property
    def server_name(self) -> str:
        """Expose MCP server name for observability callbacks."""
        return self._server_name

    def _setup_dependencies(self) -> None:
        """Validate MCP dependencies are installed.

        Raises:
            ImportError: If dspy[mcp] dependencies not installed
        """
        if not MCP_AVAILABLE:
            raise ImportError(
                "MCP dependencies missing. "
                "Install with: pip install 'roma-dspy[mcp]' or uv add --optional mcp 'mcp>=1.0.0'"
            )

        try:
            import dspy  # noqa: F401
        except ImportError as e:
            raise ImportError(
                f"DSPy dependency missing: {e}. "
                "Install with: pip install 'roma-dspy[core]'"
            ) from e

    def _initialize_tools(self) -> None:
        """Initialize MCP connection synchronously.

        Uses asyncio.run() to run async initialization from sync context.
        This is called by BaseToolkit.__init__() during toolkit creation.

        Raises:
            RuntimeError: If called from async context
            Exception: If MCP server connection fails
        """
        # Check if already in async context
        try:
            loop = asyncio.get_running_loop()
            # Already in async context - can't use asyncio.run()
            # Toolkit will be manually initialized with await toolkit.initialize()
            logger.debug(
                f"MCPToolkit '{self._server_name}' created in async context, "
                "skipping auto-initialization (will be initialized explicitly)"
            )
            return
        except RuntimeError:
            # Not in async context - safe to proceed with asyncio.run()
            pass

        # Run async initialization
        try:
            asyncio.run(self._async_initialize())

            wrap_status = "with storage" if self._enable_wrapping else "without storage"
            threshold_info = f" (threshold: {self._storage_threshold_kb}KB)" if self._enable_wrapping else ""
            logger.info(
                f"Initialized MCP server '{self._server_name}' {wrap_status}{threshold_info} "
                f"({len(self._mcp_tools)} tools)"
            )

            # BUG FIX: NEW #1 - Mark as successfully initialized
            self._initialized = True

        except Exception as e:
            self.log_error(f"Failed to initialize MCP server '{self._server_name}': {e}")
            raise

    async def initialize(self) -> None:
        """Initialize MCP connection from async context.

        This method allows MCPToolkit to be initialized from async code,
        such as pytest async fixtures. Must be called explicitly when
        toolkit is created in async context.

        Example:
            ```python
            # In async fixture
            toolkit = MCPToolkit(...)  # Deferred init
            await toolkit.initialize()  # Explicit async init
            ```

        Raises:
            Exception: If MCP server connection fails
        """
        # BUG FIX: NEW #1 - Comprehensive initialization guard
        # Check flag first (most reliable indicator)
        if self._initialized:
            logger.debug(f"MCPToolkit '{self._server_name}' already initialized")
            return

        # Fallback: check connection state (handles edge cases where flag might be out of sync)
        if self._session is not None or self._context is not None:
            logger.debug(
                f"MCPToolkit '{self._server_name}' already connected, setting flag"
            )
            self._initialized = True
            return

        try:
            await self._async_initialize()

            wrap_status = "with storage" if self._enable_wrapping else "without storage"
            threshold_info = f" (threshold: {self._storage_threshold_kb}KB)" if self._enable_wrapping else ""
            logger.info(
                f"Initialized MCP server '{self._server_name}' {wrap_status}{threshold_info} "
                f"({len(self._mcp_tools)} tools)"
            )

            # BUG FIX: NEW #1 - Mark as successfully initialized
            self._initialized = True

        except Exception as e:
            self.log_error(f"Failed to initialize MCP server '{self._server_name}': {e}")
            raise

    async def _async_initialize(self) -> None:
        """Async initialization: connect to MCP server and discover tools.

        Uses FastMCP client (v2) if available, falls back to official MCP SDK.
        FastMCP client fixes stdio transport issues in the official SDK.

        Steps:
        1. Create transport based on server type
        2. Connect client to server
        3. List tools from server
        4. Create wrapped callables for each tool
        5. Optionally wrap with storage checker

        Raises:
            Exception: If any step fails (connection, handshake, tool list, etc.)
        """
        import dspy

        try:
            if USING_FASTMCP:
                # Use FastMCP client (fixes stdio bugs)
                await self._initialize_with_fastmcp()
            else:
                # Use official MCP SDK (has stdio bugs)
                await self._initialize_with_mcp_sdk()

        except Exception as e:
            # Clean up partial state on failure
            await self._cleanup_on_error(e)
            raise

    async def _initialize_with_fastmcp(self) -> None:
        """Initialize using FastMCP client (v2 by jlowin).

        This version fixes stdio transport issues in the official MCP SDK.
        See: https://github.com/modelcontextprotocol/python-sdk/issues/395
        """
        import dspy

        # Step 1: Create transport based on server type
        if self._server_type == "stdio":
            # Use generic StdioTransport which accepts command and args separately
            # This allows us to pass commands like "uv run python server.py"
            transport = StdioTransport(
                command=self._command,
                args=self._args,
                env=self._env,
            )
        elif self._server_type == "http":
            # BUG FIX #6: Use explicit transport_type if provided, otherwise auto-detect
            if self._transport_type == "sse":
                # Explicit SSE request
                transport = SSETransport(
                    url=self._url,
                    headers=self._headers,
                )
            elif self._transport_type == "streamable":
                # Explicit StreamableHTTP request
                transport = StreamableHttpTransport(
                    url=self._url,
                    headers=self._headers,
                )
            else:
                # Auto-detect: check URL path for "/sse" endpoint (not just substring)
                # StreamableHttpTransport is the newer default
                if "://" in self._url and "/sse" in self._url:
                    transport = SSETransport(
                        url=self._url,
                        headers=self._headers,
                    )
                else:
                    # Default to StreamableHttpTransport (newer, more reliable)
                    transport = StreamableHttpTransport(
                        url=self._url,
                        headers=self._headers,
                    )

        # Step 2: Connect client (context manager handles lifecycle)
        self._context_manager = Client(transport)
        self._context = await self._context_manager.__aenter__()

        # FastMCP Client is the session
        client = self._context

        # Step 3: List tools from server
        tools = await client.list_tools()

        # Step 4: Convert each tool to DSPy Tool with full schema extraction
        for tool in tools:
            # Convert MCP tool to DSPy Tool (preserves schema metadata)
            dspy_tool = _convert_mcp_tool_to_dspy(client=client, tool=tool)

            # Get the underlying async function
            original_func = dspy_tool.func

            # Wrap with storage if enabled
            if self._enable_wrapping:
                wrapped_func = self._wrap_with_storage(
                    tool=original_func,
                    tool_name=dspy_tool.name,
                )
            else:
                wrapped_func = original_func

            # Wrap with metrics tracking
            wrapped_func = track_tool_invocation(
                tool_name=dspy_tool.name,
                toolkit_class=self.__class__.__name__
            )(wrapped_func)

            # Replace Tool's func with wrapped version (bypass Pydantic restrictions)
            object.__setattr__(dspy_tool, 'func', wrapped_func)

            # Add ROMA metadata to function for observability callback
            wrapped_func._mcp_server_name = self._server_name
            wrapped_func._roma_toolkit_type = "mcp"
            wrapped_func._roma_toolkit_name = f"mcp_{self._server_name}"

            # Store Tool object (preserves args, arg_types, arg_desc)
            self._mcp_tools[dspy_tool.name] = dspy_tool

        logger.debug(
            f"Converted {len(self._mcp_tools)} FastMCP tools to DSPy Tools with full schema"
        )

    async def _initialize_with_mcp_sdk(self) -> None:
        """Initialize using official MCP SDK client.

        Note: This has known stdio transport bugs. Use FastMCP instead if available.
        See: https://github.com/modelcontextprotocol/python-sdk/issues/395
        """
        import dspy

        # Step 1: Create context manager based on server type
        if self._server_type == "stdio":
            params = StdioServerParameters(
                command=self._command,
                args=self._args,
                env=self._env,
            )
            self._context_manager = stdio_client(params)

        elif self._server_type == "http":
            self._context_manager = streamablehttp_client(
                url=self._url,
                headers=self._headers,
            )

        # Step 2: Enter context (spawns process or connects)
        self._context = await self._context_manager.__aenter__()

        # HTTP returns (read, write, get_session_id), stdio returns (read, write)
        if self._server_type == "http":
            read, write, _get_session_id = self._context
        else:
            read, write = self._context

        # Step 3 & 4: Create and initialize session
        self._session = ClientSession(read, write)
        await self._session.initialize()

        # Step 5: List tools from server
        tools_list = await self._session.list_tools()

        # Step 6: Convert and wrap each tool
        for mcp_tool in tools_list.tools:
            # Convert to DSPy Tool (official SDK compatible - no FastMCP issues)
            dspy_tool = dspy.Tool.from_mcp_tool(self._session, mcp_tool)

            # Get the underlying async function
            original_func = dspy_tool.func

            # Wrap with storage if enabled
            if self._enable_wrapping:
                wrapped_func = self._wrap_with_storage(
                    tool=original_func,
                    tool_name=dspy_tool.name,
                )
            else:
                wrapped_func = original_func

            # Wrap with metrics tracking
            wrapped_func = track_tool_invocation(
                tool_name=dspy_tool.name,
                toolkit_class=self.__class__.__name__
            )(wrapped_func)

            # Replace Tool's func with wrapped version
            object.__setattr__(dspy_tool, 'func', wrapped_func)

            # Add ROMA metadata to function for observability callback
            wrapped_func._mcp_server_name = self._server_name
            wrapped_func._roma_toolkit_type = "mcp"
            wrapped_func._roma_toolkit_name = f"mcp_{self._server_name}"

            # Store Tool object (preserves args, arg_types, arg_desc)
            self._mcp_tools[dspy_tool.name] = dspy_tool

        logger.debug(
            f"Converted {len(self._mcp_tools)} MCP SDK tools to DSPy Tools with full schema"
        )

    def _wrap_with_storage(
        self,
        tool: Callable,
        tool_name: str,
    ) -> Callable:
        """Wrap tool with smart storage handling.

        Strategy:
        1. Execute tool (get raw result from MCP server)
        2. Check size via self._data_storage.should_store(result)
        3. If big (> threshold): store to parquet, return file path string
        4. If small (< threshold): return raw result unchanged

        This maintains DSPy compatibility:
        - Small results: raw data (string/dict/list) - unchanged
        - Big results: file path string - "Data stored at /path..."

        Args:
            tool: DSPy tool callable (dspy_tool.acall)
            tool_name: Name of the tool

        Returns:
            Wrapped async function with storage handling
        """

        @functools.wraps(tool)
        async def wrapper(**kwargs):
            try:
                # Log the tool call for debugging
                logger.debug(
                    f"MCP tool call: {tool_name} with args: {kwargs}"
                )

                try:
                    result = await asyncio.wait_for(
                        tool(**kwargs),
                        timeout=self._tool_timeout
                    )

                    # Log successful execution
                    logger.debug(
                        f"MCP tool {tool_name} succeeded, result size: "
                        f"{len(str(result)) if result else 0} chars"
                    )

                except (asyncio.TimeoutError, TimeoutError):
                    # Python 3.11+ raises TimeoutError, earlier versions raise asyncio.TimeoutError
                    raise MCPToolTimeoutError(
                        f"{tool_name} timed out after {self._tool_timeout}s"
                    )

                # Check if should store (based on threshold)
                if self._data_storage and self._data_storage.should_store(result):
                    # BUG FIX #3: Parse JSON string if needed (MCP tools return JSON strings)
                    # Handle non-JSON text gracefully instead of silently failing
                    data_to_store = result
                    if isinstance(result, str):
                        try:
                            import json
                            data_to_store = json.loads(result)
                        except (json.JSONDecodeError, ValueError) as e:
                            # Non-JSON text - log warning and return without storage
                            self.log_warning(
                                f"Tool {tool_name} returned non-JSON text ({len(result)} chars). "
                                f"Skipping Parquet storage. Parse error: {str(e)[:100]}"
                            )
                            # Return raw text to LLM - don't attempt storage
                            return result

                    # Store to parquet (data_to_store is now dict/list, not string)
                    file_path, size_kb = await self._data_storage.store_parquet(
                        data=data_to_store,
                        data_type=tool_name.replace("_", "-"),
                        prefix=f"{self._server_name}_{tool_name}",
                    )

                    # Return file path as string (DSPy compatible)
                    # LM will see this message in context
                    return (
                        f"Data stored at {file_path} ({size_kb:.1f}KB). "
                        f"Use file operations to analyze this data."
                    )
                else:
                    # Return raw result (unchanged)
                    return result

            except MCPToolTimeoutError:
                # BUG FIX #10: Re-raise timeout errors without wrapping
                raise
            except MCPToolError:
                # Re-raise MCP errors without wrapping (already formatted)
                raise
            except Exception as e:
                # BUG FIX #7: Raise exception instead of returning error string
                # Returning error strings can trigger storage if they're large
                # Better to propagate exceptions for proper error handling
                self.log_error(f"MCP tool {tool_name} failed: {e}")
                # Limit error message size to prevent storage triggers
                error_msg = str(e)[:500]
                raise MCPToolError(f"{tool_name} execution failed: {error_msg}") from e

        # Preserve function metadata
        wrapper.__name__ = tool_name
        return wrapper

    async def _cleanup_on_error(self, error: Exception) -> None:
        """Clean up MCP connection on initialization failure.

        Ensures context manager is properly exited even if initialization
        fails partway through. Prevents zombie processes.

        Args:
            error: Exception that caused initialization to fail
        """
        if self._context_manager and self._context:
            try:
                await self._context_manager.__aexit__(
                    type(error), error, error.__traceback__
                )
            except Exception as cleanup_error:
                self.log_warning(
                    f"Cleanup failed for {self._server_name}: {cleanup_error}"
                )
            finally:
                # Reset state
                self._context_manager = None
                self._context = None
                self._session = None
                self._mcp_tools = {}

    def _validate_tool_selection(self) -> None:
        """Skip validation during __init__ - tools not available until after initialize().

        MCP tools are discovered dynamically when connecting to the server.
        Validation happens during get_enabled_tools() instead via include/exclude filters.

        This override prevents BaseToolkit from validating include_tools against
        an empty set before the MCP server has connected.
        """
        # Skip validation - tools will be filtered in get_enabled_tools()
        pass

    def get_available_tool_names(self) -> Set[str]:
        """Get names of all available MCP tools.

        Returns:
            Set of tool names discovered from MCP server
        """
        return set(self._mcp_tools.keys())

    def get_enabled_tools(self) -> Dict[str, Any]:
        """Get enabled tools with include/exclude filters applied.

        Returns DSPy Tool objects (not raw callables). Tool objects are callable
        via __call__ and .acall, and preserve full schema metadata (args, arg_types, arg_desc).
        Tools are already wrapped with storage (if enabled) and metrics tracking.

        Returns:
            Dict mapping tool names to DSPy Tool objects with metrics tracking
        """
        if not self.enabled:
            return {}

        # Get available tool names
        available = set(self._mcp_tools.keys())

        # Apply include filter
        if self.include_tools:
            enabled = set(self.include_tools) & available
        else:
            enabled = available

        # Apply exclude filter
        if self.exclude_tools:
            enabled = enabled - set(self.exclude_tools)

        # Return Tool objects (callable and have full schema)
        return {name: self._mcp_tools[name] for name in enabled}

    async def cleanup(self) -> None:
        """Clean up MCP connection and resources.

        Should be called by ToolkitManager.cleanup_execution() when
        execution completes. Ensures MCP server process is terminated.
        """
        if self._context_manager and self._context:
            try:
                await self._context_manager.__aexit__(None, None, None)
                logger.info(f"Disconnected from MCP server: {self._server_name}")
            except Exception as e:
                self.log_warning(f"Cleanup error for {self._server_name}: {e}")
            finally:
                # Reset state
                self._context_manager = None
                self._context = None
                self._session = None
                self._mcp_tools = {}

                # BUG FIX: NEW #1 - Reset initialization flag to allow re-initialization
                self._initialized = False


# Export
__all__ = ["MCPToolkit"]