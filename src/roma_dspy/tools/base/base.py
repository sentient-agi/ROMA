"""Base toolkit class for ROMA-DSPy toolkits."""

from __future__ import annotations

import inspect
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional, Set

from loguru import logger

from roma_dspy.tools.metrics.decorators import track_tool_invocation

if TYPE_CHECKING:
    from roma_dspy.core.storage import FileStorage
    from roma_dspy.tools.utils.storage import DataStorage


class BaseToolkit(ABC):
    """
    Abstract base class for all ROMA-DSPy toolkits.

    Toolkits are collections of related tools that can be added to agents.
    They follow the Agno toolkit pattern with DSPy integration.

    Key features:
    - Class-based tools that can maintain state
    - Selective tool inclusion/exclusion
    - Async support when possible
    - Rich metadata for agent reasoning
    - Configuration-time validation
    """

    # Metadata: Set to True if toolkit requires FileStorage (e.g., FileToolkit)
    # ToolkitManager checks this to ensure FileStorage is provided
    REQUIRES_FILE_STORAGE: bool = False

    # Toolkit type for observability ("builtin" or "mcp")
    # Override in subclasses like MCPToolkit
    TOOLKIT_TYPE: str = "builtin"

    def __init__(
        self,
        enabled: bool = True,
        include_tools: Optional[List[str]] = None,
        exclude_tools: Optional[List[str]] = None,
        file_storage: Optional["FileStorage"] = None,
        **config,
    ):
        """
        Initialize toolkit with configuration.

        Args:
            enabled: Whether this toolkit is enabled
            include_tools: Specific tools to include (None = all available)
            exclude_tools: Tools to exclude from available tools
            file_storage: Optional FileStorage for large data persistence
            **config: Toolkit-specific configuration (may include storage_threshold_kb)
        """
        self.enabled = enabled
        self.include_tools = include_tools or []
        self.exclude_tools = exclude_tools or []
        self.config = config

        self._tools: Dict[str, Callable] = {}

        # Store raw file_storage for toolkits that need direct access (e.g., FileToolkit)
        self._file_storage: Optional["FileStorage"] = file_storage

        # Optional storage initialization
        self._data_storage: Optional["DataStorage"] = None
        if file_storage:
            from roma_dspy.tools.utils.storage import DataStorage

            toolkit_name = self.__class__.__name__.replace("Toolkit", "").lower()
            # Get storage threshold from config, default to 1000KB (1MB)
            storage_threshold_kb = config.get("storage_threshold_kb", 1000)
            self._data_storage = DataStorage(
                file_storage=file_storage,
                toolkit_name=toolkit_name,
                threshold_kb=storage_threshold_kb,
            )

        if self.enabled:
            try:
                self._setup_dependencies()
                self._initialize_tools()
                self._register_all_tools()
                self._validate_tool_selection()
            except Exception as e:
                self.log_error(f"Failed to initialize toolkit {self.__class__.__name__}: {e}")
                raise

    @abstractmethod
    def _setup_dependencies(self) -> None:
        """
        Setup any external dependencies required by this toolkit.

        Should raise appropriate exceptions if dependencies cannot be satisfied.
        This is called during toolkit initialization.
        """
        pass

    @abstractmethod
    def _initialize_tools(self) -> None:
        """
        Initialize toolkit-specific configuration and setup.

        This method should set up the toolkit state but not register tools.
        Tool registration is handled automatically by _register_all_tools().
        """
        pass

    def get_available_tool_names(self) -> Set[str]:
        """
        Get set of all tool names that this toolkit can provide.

        Automatically discovers all public methods (not starting with _) as available tools,
        excluding abstract methods, properties, and BaseToolkit methods.
        Also respects conditional availability based on toolkit configuration.

        Returns:
            Set of tool names that can be enabled/disabled
        """
        tool_names = set()

        # Get all public methods from the class
        for name, method in inspect.getmembers(self, predicate=inspect.ismethod):
            # Skip private/protected methods
            if name.startswith('_'):
                continue

            # Skip BaseToolkit methods (these are infrastructure, not tools)
            if hasattr(BaseToolkit, name):
                continue

            # Skip abstract methods
            if getattr(method, '__isabstractmethod__', False):
                continue

            # Skip properties and other non-callable attributes
            if not callable(method):
                continue

            # Check if tool is conditionally available
            if self._is_tool_available(name):
                tool_names.add(name)

        return tool_names

    def _is_tool_available(self, tool_name: str) -> bool:
        """
        Check if a tool should be available based on configuration.

        Override this method in subclasses to implement conditional tool availability.
        By default, all discovered public methods are available.

        Args:
            tool_name: Name of the tool to check

        Returns:
            True if the tool should be available, False otherwise
        """
        return True

    def _validate_tool_selection(self) -> None:
        """Validate include/exclude tool selection against available tools."""
        available = self.get_available_tool_names()

        # Validate include_tools
        if self.include_tools:
            invalid_includes = set(self.include_tools) - available
            if invalid_includes:
                raise ValueError(
                    f"Invalid tools in include_tools: {invalid_includes}. "
                    f"Available tools: {available}"
                )

        # Validate exclude_tools
        if self.exclude_tools:
            invalid_excludes = set(self.exclude_tools) - available
            if invalid_excludes:
                raise ValueError(
                    f"Invalid tools in exclude_tools: {invalid_excludes}. "
                    f"Available tools: {available}"
                )

    def _register_all_tools(self) -> None:
        """
        Automatically register all available tools based on available tool names.

        This method inspects the toolkit instance for methods matching available tool names
        and registers them as callable tools. DSPy will use the method docstrings for
        agent reasoning.

        Tools are automatically wrapped with invocation tracking to capture:
        - Call duration and timing
        - Input/output sizes
        - Success/failure rates
        - Error details
        """
        available_tools = self.get_available_tool_names()
        toolkit_class = self.__class__.__name__

        for tool_name in available_tools:
            if hasattr(self, tool_name):
                tool_method = getattr(self, tool_name)
                if callable(tool_method):
                    # Wrap tool with invocation tracking
                    wrapped_tool = track_tool_invocation(
                        tool_name=tool_name,
                        toolkit_class=toolkit_class
                    )(tool_method)

                    self._tools[tool_name] = wrapped_tool
                    self.log_debug(f"Registered tool: {tool_name} (with metrics tracking)")
                else:
                    self.log_warning(f"Tool '{tool_name}' is not callable")
            else:
                self.log_warning(f"Tool method '{tool_name}' not found in {self.__class__.__name__}")

    def _register_tool(self, name: str, func: Callable, description: str = "",
                      parameters: Optional[Dict[str, Any]] = None,
                      examples: Optional[List[str]] = None) -> None:
        """
        Manually register a tool function (deprecated - use _register_all_tools instead).

        Args:
            name: Tool name
            func: Tool function (sync or async callable)
            description: Tool description for agent reasoning
            parameters: Parameter descriptions
            examples: Usage examples
        """
        # Store the callable directly (DSPy accepts callables)
        self._tools[name] = func

    def get_enabled_tools(self) -> Dict[str, Callable]:
        """
        Get tools that should be enabled based on include/exclude configuration.

        Returns:
            Dictionary of enabled tool name -> callable function
        """
        if not self.enabled:
            return {}

        available = self.get_available_tool_names()

        # Determine which tools to include
        if self.include_tools:
            # Only include specified tools
            enabled = set(self.include_tools) & available
        else:
            # Include all available tools
            enabled = available

        # Remove excluded tools
        if self.exclude_tools:
            enabled = enabled - set(self.exclude_tools)

        # Return only enabled tools
        return {name: func for name, func in self._tools.items() if name in enabled}

    def get_tool_metadata(self, tool_name: str) -> Optional[Dict[str, Any]]:
        """
        Get metadata for a specific tool from its docstring and method signature.

        Args:
            tool_name: Name of the tool

        Returns:
            Tool metadata dictionary or None if tool doesn't exist
        """
        if tool_name not in self._tools:
            return None

        tool_method = self._tools[tool_name]

        # Get the actual function object for bound methods
        # Bound methods wrap the actual function in __func__
        method = tool_method.__func__ if hasattr(tool_method, '__func__') else tool_method

        # Use proper async detection via inspect module
        is_async = inspect.iscoroutinefunction(method)

        return {
            "name": tool_name,
            "description": tool_method.__doc__ or "",
            "async_supported": is_async,
        }

    def get_all_metadata(self) -> Dict[str, Dict[str, Any]]:
        """
        Get metadata for all enabled tools in this toolkit.

        Returns:
            Dictionary mapping tool names to their metadata
        """
        enabled_tools = self.get_enabled_tools()
        return {
            name: self.get_tool_metadata(name)
            for name in enabled_tools.keys()
        }

    # Logging utilities following Agno patterns
    def log_debug(self, message: str) -> None:
        """Log debug message."""
        logger.debug(f"[{self.__class__.__name__}] {message}")

    def log_error(self, message: str) -> None:
        """Log error message."""
        logger.error(f"[{self.__class__.__name__}] {message}")

    def log_warning(self, message: str) -> None:
        """Log warning message."""
        logger.warning(f"[{self.__class__.__name__}] {message}")

    # Response building helpers
    async def _build_success_response(
        self,
        data: Any,
        storage_data_type: Optional[str] = None,
        storage_prefix: Optional[str] = None,
        tool_name: Optional[str] = None,
        **metadata,
    ) -> dict:
        """Build standardized success response with automatic storage.

        If storage is enabled and data exceeds threshold, automatically stores
        data to Parquet and returns file_path instead of inline data.

        Storage Path: artifacts/{toolkit_name}/{data_type}/{filename}
        Example: artifacts/coingecko/market_charts/btc_usd_30d_20250122_143022_a1b2c3d4.parquet

        Args:
            data: Response data
            storage_data_type: Data type for storage folder (e.g., "market_charts", "klines")
                             Used to organize files for LLM browsability
            storage_prefix: Filename prefix if stored (e.g., "btc_usd_30d")
            tool_name: Name of the tool method that generated this response
            **metadata: Additional response metadata

        Returns:
            Standardized response dict with success=True and either:
            - data (inline) if size < threshold
            - file_path (str) if size >= threshold, with message for LLM

        Example:
            ```python
            return await self._build_success_response(
                data=api_response,
                storage_data_type="market_charts",  # Creates: artifacts/coingecko/market_charts/
                storage_prefix=f"{coin_id}_{vs_currency}_{days}d",  # Prefix: btc_usd_30d_
                tool_name="get_coin_market_chart",
                coin_id=coin_id,
                data_points=len(api_response.get("prices", [])),
            )
            # If large: Returns file_path for LLM to use with FileToolkit or E2B
            ```
        """
        # Get toolkit metadata
        toolkit_name = self.__class__.__name__
        toolkit_metadata = {
            "toolkit": toolkit_name,
        }
        if tool_name:
            toolkit_metadata["tool"] = tool_name

        # Add execution_id if storage is enabled
        if self._data_storage:
            toolkit_metadata["execution_id"] = self._data_storage.file_storage.execution_id

        response = {
            "success": True,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **toolkit_metadata,
            **metadata,
        }

        # Auto-store if enabled + threshold exceeded
        if (
            self._data_storage
            and storage_data_type
            and storage_prefix
            and self._data_storage.should_store(data)
        ):
            path, size_kb = await self._data_storage.store_parquet(
                data=data,
                data_type=storage_data_type,
                prefix=storage_prefix,
            )
            response["file_path"] = str(path)
            response["stored"] = True
            response["size_kb"] = size_kb
            response["message"] = (
                f"Response data ({size_kb:.1f}KB) exceeds threshold and has been "
                f"saved to: {path}. Use this file path to access the data."
            )
        else:
            response["data"] = data

        return response

    def _build_error_response(self, error: Exception, tool_name: Optional[str] = None, **context) -> dict:
        """Build standardized error response.

        Args:
            error: Exception that occurred
            tool_name: Name of the tool method that encountered the error
            **context: Additional error context

        Returns:
            Standardized error response dict with success=False

        Example:
            ```python
            except (APIError, ValueError) as e:
                return self._build_error_response(
                    e, tool_name="get_coin_price", coin_id=coin_name_or_id
                )
            ```
        """
        # Get toolkit metadata
        toolkit_name = self.__class__.__name__
        toolkit_metadata = {
            "toolkit": toolkit_name,
        }
        if tool_name:
            toolkit_metadata["tool"] = tool_name

        # Add execution_id if storage is enabled
        if self._data_storage:
            toolkit_metadata["execution_id"] = self._data_storage.file_storage.execution_id

        return {
            "success": False,
            "error": str(error),
            "error_type": error.__class__.__name__,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **toolkit_metadata,
            **context,
        }

    def __repr__(self) -> str:
        enabled_count = len(self.get_enabled_tools())
        total_count = len(self.get_available_tool_names())
        return f"{self.__class__.__name__}(enabled={self.enabled}, tools={enabled_count}/{total_count})"