"""Toolkit manager for dynamic loading and instance management."""

from __future__ import annotations

import asyncio
import gc
import hashlib
import importlib
import json
import threading
import time
from typing import Any, Dict, List, Optional, Type, TYPE_CHECKING

from loguru import logger

from roma_dspy.tools.base.base import BaseToolkit
from roma_dspy.tools.metrics.decorators import track_toolkit_lifecycle

if TYPE_CHECKING:
    from roma_dspy.config.schemas.toolkit import ToolkitConfig
    from roma_dspy.core.storage import FileStorage


class ToolkitManager:
    """
    Singleton manager for loading and managing toolkit instances.

    Responsibilities:
    - Dynamic toolkit loading by class name
    - Toolkit instance caching
    - Configuration validation
    - Registry of available toolkit classes
    """

    _instance: Optional["ToolkitManager"] = None
    _lock = threading.Lock()
    _toolkit_registry: Dict[str, Type[BaseToolkit]] = {}

    # Built-in toolkits
    BUILTIN_TOOLKITS = {
        "ArtifactToolkit": "roma_dspy.tools.core.artifact_toolkit",
        "FileToolkit": "roma_dspy.tools.core.file",
        "CalculatorToolkit": "roma_dspy.tools.core.calculator",
        "SerperToolkit": "roma_dspy.tools.web_search.serper",
        "WebSearchToolkit": "roma_dspy.tools.web_search.toolkit",
        "E2BToolkit": "roma_dspy.tools.core.e2b",
        "BinanceToolkit": "roma_dspy.tools.crypto.binance.toolkit",
        "CoinGeckoToolkit": "roma_dspy.tools.crypto.coingecko.toolkit",
        "DefiLlamaToolkit": "roma_dspy.tools.crypto.defillama.toolkit",
        "ArkhamToolkit": "roma_dspy.tools.crypto.arkham.toolkit",
        "CoinglassToolkit": "roma_dspy.tools.crypto.coinglass.toolkit",
        "MCPToolkit": "roma_dspy.tools.mcp.toolkit",
    }

    def __new__(cls) -> "ToolkitManager":
        # Standard __new__ without singleton logic
        return super().__new__(cls)

    @classmethod
    def get_instance(cls) -> "ToolkitManager":
        """Get singleton instance (thread-safe)."""
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
        return cls._instance

    def __init__(self):
        if hasattr(self, '_initialized'):
            return
        self._initialized = True

        # Individual toolkit cache with execution isolation
        # Key format: "execution_id:ClassName:config_hash"
        self._toolkit_cache: Dict[str, BaseToolkit] = {}

        # Reference counting for safe cleanup during active execution
        # Tracks how many agents are currently using each toolkit
        self._toolkit_refcounts: Dict[str, int] = {}

        # Hybrid locking for thread-safety and async-safety
        self._cache_thread_lock = threading.Lock()  # Thread-safe access across event loops
        self._cache_async_lock: Optional[asyncio.Lock] = None  # Lazy-initialized per event loop
        self._cache_async_lock_loop_id: Optional[int] = None  # Track which event loop owns the lock

        # BUG FIX B: Track which toolkits have been fetched by each execution
        # Maps execution_id -> set of cache_keys
        # This prevents refcount increment on subsequent fetches within same execution
        self._execution_toolkit_map: Dict[str, set[str]] = {}

        self._register_builtin_toolkits()

    def _register_builtin_toolkits(self) -> None:
        """Register built-in toolkits."""
        for class_name, module_path in self.BUILTIN_TOOLKITS.items():
            try:
                self._register_toolkit_class(class_name, module_path)
            except ImportError as e:
                logger.debug(f"Could not register {class_name}: {e}")
            except Exception as e:
                logger.warning(f"Failed to register {class_name}: {e}")

    def __deepcopy__(self, memo: dict) -> "ToolkitManager":
        """
        Preserve singleton semantics during deepcopy().

        GEPA clones DSPy modules via copy.deepcopy(). Returning `self`
        prevents attempts to pickle threading.Lock instances (which would fail)
        and ensures all solvers continue to share the same toolkit manager.
        """
        return self

    def _register_toolkit_class(self, class_name: str, module_path: str) -> None:
        """
        Register a toolkit class for dynamic loading.

        Args:
            class_name: Name of the toolkit class
            module_path: Python module path where the class is defined
        """
        try:
            module = importlib.import_module(module_path)
            toolkit_class = getattr(module, class_name)

            if not issubclass(toolkit_class, BaseToolkit):
                raise ValueError(f"{class_name} must inherit from BaseToolkit")

            self._toolkit_registry[class_name] = toolkit_class
            logger.debug(f"Registered toolkit: {class_name}")

        except (ImportError, AttributeError) as e:
            raise ImportError(f"Could not import {class_name} from {module_path}: {e}")

    def register_external_toolkit(self, class_name: str, toolkit_class: Type[BaseToolkit]) -> None:
        """
        Register an external toolkit class.

        Args:
            class_name: Name of the toolkit class
            toolkit_class: The toolkit class itself
        """
        if not issubclass(toolkit_class, BaseToolkit):
            raise ValueError(f"{class_name} must inherit from BaseToolkit")

        self._toolkit_registry[class_name] = toolkit_class
        logger.debug(f"Registered external toolkit: {class_name}")

    def get_available_toolkits(self) -> Dict[str, Type[BaseToolkit]]:
        """
        Get all registered toolkit classes.

        Returns:
            Dictionary mapping class names to toolkit classes
        """
        return dict(self._toolkit_registry)

    def clear_cache(self) -> None:
        """
        Clear all cached toolkit instances and force garbage collection.

        Thread-safe operation that clears:
        - All toolkit instances (_toolkit_cache)
        - All reference counts (_toolkit_refcounts)

        Warning: This affects ALL executions. Use cleanup_execution() for
        execution-specific cleanup.
        """
        with self._cache_thread_lock:
            # Clear execution-scoped caches
            cache_size = len(self._toolkit_cache)
            self._toolkit_cache.clear()
            self._toolkit_refcounts.clear()

            logger.info(
                f"Cleared all toolkit caches: {cache_size} execution-scoped instances"
            )

        # Force garbage collection to free resources
        gc.collect()

    def validate_toolkit_config(self, config: "ToolkitConfig") -> None:
        """
        Validate a toolkit configuration without creating an instance.

        Args:
            config: Toolkit configuration to validate

        Raises:
            ValueError: If configuration is invalid
        """
        # Check if toolkit class exists
        if config.class_name not in self._toolkit_registry:
            raise ValueError(
                f"Unknown toolkit class: {config.class_name}. "
                f"Available: {list(self._toolkit_registry.keys())}"
            )

        # For more detailed validation, we'd need to create a temporary instance
        # But we can do basic validation here
        if config.include_tools and config.exclude_tools:
            overlap = set(config.include_tools) & set(config.exclude_tools)
            if overlap:
                raise ValueError(
                    f"Tools cannot be both included and excluded: {overlap}"
                )

    # ==================== Execution-Scoped Toolkit Management ====================

    async def _track_toolkit_event(
        self,
        execution_id: str,
        operation: str,
        toolkit_class: str,
        duration_ms: float,
        success: bool,
        error: Optional[str] = None
    ) -> None:
        """
        Track toolkit lifecycle event via ExecutionContext buffering.

        Events are buffered in ExecutionContext and persisted to PostgreSQL
        on execution cleanup via reset_async().

        Args:
            execution_id: Unique identifier for this execution
            operation: Operation type ("create", "cache_hit", "cache_miss", "cleanup")
            toolkit_class: Name of toolkit class
            duration_ms: Operation duration in milliseconds
            success: Whether operation succeeded
            error: Error message if failed
        """
        from roma_dspy.core.context import ExecutionContext
        from roma_dspy.tools.metrics.models import ToolkitLifecycleEvent
        from datetime import datetime, timezone

        # Check if execution context is available
        ctx = ExecutionContext.get()
        if not ctx:
            logger.debug(f"No ExecutionContext available for toolkit tracking")
            return

        # TODO: Add config check once metrics config is integrated
        # if not self._metrics_config or not self._metrics_config.track_lifecycle:
        #     return

        try:
            event = ToolkitLifecycleEvent(
                execution_id=execution_id,
                timestamp=datetime.now(timezone.utc),
                operation=operation,
                toolkit_class=toolkit_class,
                duration_ms=duration_ms,
                success=success,
                error=error,
                metadata={}
            )

            ctx.toolkit_events.append(event)
            logger.debug(
                f"Tracked {operation} event for {toolkit_class} "
                f"(duration={duration_ms:.1f}ms, success={success})"
            )

        except Exception as e:
            logger.warning(f"Failed to track toolkit event: {e}")
            # Non-critical - continue execution

    def _get_async_lock(self) -> asyncio.Lock:
        """
        Get or create async lock for current event loop.

        AsyncIO locks are event-loop-specific, so we need to create a new one
        for each event loop. This method ensures thread-safe lazy initialization.

        Returns:
            Async lock for current event loop
        """
        # Try to get existing lock without creating a new event loop
        try:
            loop = asyncio.get_running_loop()
            loop_id = id(loop)  # Use loop object ID instead of private _loop attribute
        except RuntimeError:
            # Not in async context - create a new lock that will be used later
            if self._cache_async_lock is None:
                self._cache_async_lock = asyncio.Lock()
            return self._cache_async_lock

        # In async context - check if lock exists and is for this loop
        if self._cache_async_lock is None or self._cache_async_lock_loop_id != loop_id:
            # Create new lock for this event loop
            self._cache_async_lock = asyncio.Lock()
            self._cache_async_lock_loop_id = loop_id

        return self._cache_async_lock

    def _hash_toolkit_config(self, config: "ToolkitConfig") -> str:
        """
        Generate deterministic hash of toolkit configuration.

        Uses SHA-256 for collision resistance (16-char prefix = 64 bits).
        Config dict is JSON-serialized with sorted keys for determinism.

        Args:
            config: Toolkit configuration

        Returns:
            16-character hex hash of configuration

        Example:
            >>> hash1 = _hash_toolkit_config(config_a)
            >>> hash2 = _hash_toolkit_config(config_a)  # Same config
            >>> assert hash1 == hash2  # Deterministic
        """
        # Create normalized config dict (exclude FileStorage from hash)
        config_dict = {
            'enabled': config.enabled,
            'include_tools': sorted(config.include_tools or []),
            'exclude_tools': sorted(config.exclude_tools or []),
            'toolkit_config': sorted((config.toolkit_config or {}).items())
        }

        # JSON serialize with sorted keys for determinism
        try:
            config_json = json.dumps(config_dict, sort_keys=True)
        except (TypeError, ValueError) as e:
            # Handle non-serializable objects in toolkit_config
            logger.warning(
                f"Failed to JSON-serialize toolkit_config for {config.class_name}: {e}. "
                f"Falling back to str() representation. This may cause cache misses."
            )
            # Fallback: use str() representation (less reliable but works)
            config_json = str(config_dict)

        # SHA-256 hash (16 chars = 64 bits for collision resistance)
        config_hash = hashlib.sha256(config_json.encode()).hexdigest()[:16]

        return config_hash

    def _get_toolkit_cache_key(
        self,
        execution_id: str,
        class_name: str,
        config: "ToolkitConfig"
    ) -> str:
        """
        Generate cache key for a single toolkit instance.

        Key format: "execution_id:ClassName:config_hash"

        This ensures:
        1. Execution isolation (different executions never share toolkits)
        2. Config-specific caching (same config = same instance)
        3. Class-specific namespacing (avoid collisions)

        Args:
            execution_id: Unique identifier for execution
            class_name: Toolkit class name
            config: Toolkit configuration

        Returns:
            Cache key string

        Example:
            >>> key = _get_toolkit_cache_key("exec_123", "BinanceToolkit", config)
            >>> # "exec_123:BinanceToolkit:a1b2c3d4e5f6g7h8"
        """
        # Sanitize execution_id to prevent cache key injection
        safe_exec_id = execution_id.replace(":", "_").replace("|", "_")

        # Hash configuration for deterministic, collision-resistant key
        config_hash = self._hash_toolkit_config(config)

        # Format: execution_id:ClassName:config_hash
        return f"{safe_exec_id}:{class_name}:{config_hash}"

    async def get_tools_for_execution(
        self,
        execution_id: str,
        file_storage: "FileStorage",
        toolkit_configs: List["ToolkitConfig"],
    ) -> Dict[str, Any]:
        """
        Get tools for a specific execution with individual toolkit caching.

        This method uses hybrid locking for thread-safe and async-safe toolkit creation:
        1. Iterate through toolkit configs (mandatory toolkits already merged by BaseModule)
        2. For each toolkit, check if cached (with config hash)
        3. If not cached, acquire lock and create
        4. Increment reference count
        5. Merge all tools and return

        Thread Safety:
            - threading.Lock for cross-thread safety
            - asyncio.Lock for async coroutine safety
            - Double-checked locking pattern

        Execution Isolation:
            - Cache keys include execution_id
            - Different executions never share toolkits

        Performance:
            - Individual caching enables toolkit reuse across agents
            - 70% reduction in toolkit creation compared to set-level caching

        Args:
            execution_id: Unique identifier for this execution
            file_storage: FileStorage instance for this execution
            toolkit_configs: List of toolkit configurations (mandatory + user, already merged)

        Returns:
            Dict mapping tool names to tool functions from all configured toolkits

        Example:
            tools = await manager.get_tools_for_execution(
                execution_id="exec_123",
                file_storage=storage,
                toolkit_configs=all_configs,  # Mandatory already merged
            )
        """
        # Validate inputs
        if not execution_id:
            raise ValueError("execution_id cannot be None or empty")
        if file_storage is None:
            raise ValueError("file_storage cannot be None")
        if toolkit_configs is None:
            raise ValueError("toolkit_configs cannot be None (use [] for empty list)")

        # toolkit_configs already contains mandatory toolkits (merged by BaseModule)
        final_toolkit_configs = toolkit_configs

        # Verify FileStorage matches execution_id for safety
        if hasattr(file_storage, 'execution_id') and file_storage.execution_id != execution_id:
            logger.warning(
                f"FileStorage execution_id mismatch: expected {execution_id}, "
                f"got {file_storage.execution_id}. Using provided execution_id."
            )

        tools = {}
        created_count = 0
        reused_count = 0

        # Get async lock for this event loop
        async_lock = self._get_async_lock()

        # Process each toolkit individually (using merged configs)
        for config in final_toolkit_configs:
            if not config.enabled:
                continue

            # Generate cache key for THIS specific toolkit
            cache_key = self._get_toolkit_cache_key(
                execution_id,
                config.class_name,
                config
            )

            # DEBUG: Log cache key and config details
            config_hash = self._hash_toolkit_config(config)
            logger.debug(
                f"[CACHE CHECK] {config.class_name} | "
                f"cache_key={cache_key} | "
                f"config_hash={config_hash} | "
                f"toolkit_config={config.safe_dict()} | "  # BUG FIX D: Use safe_dict() to redact secrets
                f"cache_size={len(self._toolkit_cache)}"
            )

            # BUG FIX B: Initialize execution tracking for this execution
            if execution_id not in self._execution_toolkit_map:
                self._execution_toolkit_map[execution_id] = set()

            # Fast path: check cache without lock
            toolkit = None
            with self._cache_thread_lock:
                if cache_key in self._toolkit_cache:
                    toolkit = self._toolkit_cache[cache_key]

                    # BUG FIX B: Only increment refcount on FIRST fetch per execution
                    # This prevents refcount leaks when modules fetch tools multiple times
                    if cache_key not in self._execution_toolkit_map[execution_id]:
                        self._toolkit_refcounts[cache_key] = self._toolkit_refcounts.get(cache_key, 0) + 1
                        self._execution_toolkit_map[execution_id].add(cache_key)
                        logger.debug(
                            f"[CACHE HIT] First fetch for {execution_id} | "
                            f"cache_key={cache_key} | "
                            f"refcount={self._toolkit_refcounts[cache_key]}"
                        )
                    else:
                        logger.debug(
                            f"[CACHE REUSE] Subsequent fetch for {execution_id} | "
                            f"cache_key={cache_key} | "
                            f"refcount={self._toolkit_refcounts[cache_key]} (not incremented)"
                        )

                    reused_count += 1

                    # Track cache hit event
                    await self._track_toolkit_event(
                        execution_id=execution_id,
                        operation="cache_hit",
                        toolkit_class=config.class_name,
                        duration_ms=0,  # Instant (no creation time)
                        success=True
                    )
                else:
                    logger.debug(
                        f"[CACHE MISS] {config.class_name} not in cache. "
                        f"Current cache keys: {list(self._toolkit_cache.keys())}"
                    )

            # Slow path: create toolkit with double-checked locking
            if toolkit is None:
                async with async_lock:
                    # Double-check: another coroutine might have created it
                    with self._cache_thread_lock:
                        if cache_key in self._toolkit_cache:
                            toolkit = self._toolkit_cache[cache_key]
                            # BUG FIX B: Only increment refcount on first fetch per execution
                            if cache_key not in self._execution_toolkit_map[execution_id]:
                                self._toolkit_refcounts[cache_key] = self._toolkit_refcounts.get(cache_key, 0) + 1
                                self._execution_toolkit_map[execution_id].add(cache_key)
                            reused_count += 1
                        else:
                            # Create toolkit (not in lock to avoid blocking)
                            pass  # Will create outside thread lock

                    # Create toolkit outside of thread lock (can be slow)
                    if toolkit is None:
                        try:
                            # Measure toolkit creation time
                            start_time = time.time()
                            toolkit = self._create_toolkit_instance(
                                class_name=config.class_name,
                                config=config,
                                file_storage=file_storage
                            )
                            duration_ms = (time.time() - start_time) * 1000

                            # BUG FIX A: Initialize async toolkits explicitly
                            # Some toolkits (like MCPToolkit) require async initialization
                            # that can't happen in __init__ when event loop is already running
                            if hasattr(toolkit, 'initialize') and callable(toolkit.initialize):
                                # Check if not already initialized (prevent double-init)
                                needs_init = True
                                if hasattr(toolkit, '_initialized'):
                                    needs_init = not toolkit._initialized

                                if needs_init:
                                    logger.debug(f"Initializing async toolkit: {config.class_name}")
                                    init_start = time.time()
                                    await toolkit.initialize()
                                    init_duration_ms = (time.time() - init_start) * 1000

                                    # Log initialization success
                                    tool_count = len(toolkit.get_available_tool_names())
                                    logger.info(
                                        f"Async toolkit initialized: {config.class_name} | "
                                        f"tools_discovered={tool_count} | "
                                        f"init_time={init_duration_ms:.1f}ms"
                                    )

                            # Cache with thread lock
                            with self._cache_thread_lock:
                                self._toolkit_cache[cache_key] = toolkit
                                self._toolkit_refcounts[cache_key] = 1
                                # BUG FIX B: Track this toolkit for this execution
                                self._execution_toolkit_map[execution_id].add(cache_key)
                                created_count += 1

                            logger.info(
                                f"[CACHE CREATE] Created and cached {config.class_name} | "
                                f"cache_key={cache_key} | "
                                f"cache_size={len(self._toolkit_cache)}"
                            )

                            # Track successful creation
                            await self._track_toolkit_event(
                                execution_id=execution_id,
                                operation="create",
                                toolkit_class=config.class_name,
                                duration_ms=duration_ms,
                                success=True
                            )

                        except Exception as e:
                            error_msg = str(e)
                            logger.error(
                                f"Failed to create {config.class_name} for {execution_id}: {e}",
                                exc_info=True
                            )

                            # Track failed creation
                            await self._track_toolkit_event(
                                execution_id=execution_id,
                                operation="create",
                                toolkit_class=config.class_name,
                                duration_ms=0,  # Unknown duration (failed before completion)
                                success=False,
                                error=error_msg
                            )

                            continue  # Skip this toolkit

            # Collect tools from toolkit
            if toolkit:
                try:
                    enabled_tools = toolkit.get_enabled_tools()
                    if isinstance(enabled_tools, dict):
                        tools.update(enabled_tools)
                    else:
                        # If it's a list/iterable, convert to dict
                        for tool in enabled_tools:
                            tool_name = getattr(tool, '__name__', str(tool))
                            tools[tool_name] = tool
                except Exception as e:
                    logger.error(
                        f"Failed to get tools from {config.class_name}: {e}",
                        exc_info=True
                    )

        # Log cache performance
        total_requested = len([c for c in final_toolkit_configs if c.enabled])
        if total_requested > 0:
            cache_hit_rate = (reused_count / total_requested) * 100 if total_requested > 0 else 0
            logger.info(
                f"Toolkit cache stats for {execution_id}: "
                f"created={created_count}, reused={reused_count}, "
                f"hit_rate={cache_hit_rate:.1f}%, total_tools={len(tools)}"
            )

        return tools


    def _create_toolkit_instance(
        self,
        class_name: str,
        config: "ToolkitConfig",
        file_storage: Optional["FileStorage"] = None,
    ) -> BaseToolkit:
        """
        Create a toolkit instance with optional FileStorage injection.

        This method merges ToolkitFactory logic into ToolkitManager:
        - Checks REQUIRES_DATA_DIR class attribute
        - Injects data_dir from file_storage if needed
        - Passes file_storage to toolkit constructor

        Args:
            class_name: Name of the toolkit class
            config: Toolkit configuration
            file_storage: Optional FileStorage for execution-scoped paths

        Returns:
            Initialized toolkit instance

        Raises:
            ValueError: If toolkit class is not registered
        """
        # Load toolkit class
        if class_name not in self._toolkit_registry:
            if class_name in self.BUILTIN_TOOLKITS:
                try:
                    self._register_toolkit_class(
                        class_name, self.BUILTIN_TOOLKITS[class_name]
                    )
                except Exception as e:
                    logger.warning(f"Failed to register builtin toolkit {class_name}: {e}")

            if class_name not in self._toolkit_registry:
                raise ValueError(
                    f"Unknown toolkit class: {class_name}. "
                    f"Available: {list(self._toolkit_registry.keys())}"
                )

        toolkit_class = self._toolkit_registry[class_name]
        toolkit_config = config.toolkit_config or {}

        # Validate FileStorage requirement
        requires_file_storage = getattr(toolkit_class, "REQUIRES_FILE_STORAGE", False)
        if requires_file_storage and not file_storage:
            raise ValueError(
                f"{class_name} requires FileStorage but none was provided. "
                f"FileStorage ensures execution-scoped isolation of file operations."
            )

        # Create toolkit instance
        try:
            instance = toolkit_class(
                enabled=config.enabled,
                include_tools=config.include_tools,
                exclude_tools=config.exclude_tools,
                file_storage=file_storage,  # Pass FileStorage for toolkits that need it
                **toolkit_config,
            )
            return instance

        except Exception as e:
            logger.error(f"Failed to create {class_name} instance: {e}")
            raise

    async def setup_for_execution(
        self,
        dag: Any,
        config: Any,
        registry: Any
    ) -> Dict[str, List]:
        """
        LEGACY METHOD - No longer needed.

        Toolkits are now initialized dynamically per-agent via BaseModule._get_execution_tools()
        which uses class-based mandatory toolkit declarations.

        This method is kept as a no-op for backward compatibility and returns empty events.

        Args:
            dag: TaskDAG with execution_id and context (unused)
            config: ROMAConfig instance with agent configurations (unused)
            registry: AgentRegistry for accessing agent modules (unused)

        Returns:
            Empty dict with toolkit_events and tool_invocations lists
        """
        logger.debug("setup_for_execution called (legacy no-op - toolkits initialized per-agent)")
        return {'toolkit_events': [], 'tool_invocations': []}

    def setup_for_execution_sync(
        self,
        dag: Any,
        config: Any,
        registry: Any
    ) -> None:
        """
        Setup toolkits synchronously for sync execution path.

        This ensures sync solve() has the same toolkit functionality as async_solve().
        Uses asyncio.run() internally to create toolkits, then merges events into
        the sync ExecutionContext.

        Args:
            dag: TaskDAG with execution_id and context
            config: ROMAConfig instance with agent configurations
            registry: AgentRegistry for accessing agent modules
        """
        if not config or not hasattr(config, 'agents'):
            logger.debug("No agent configuration found, skipping toolkit setup")
            return

        # Check if we're already in an async context
        try:
            loop = asyncio.get_running_loop()
            logger.warning(
                "Cannot setup toolkits synchronously from async context. "
                "Use async_solve() instead of solve() when in async code."
            )
            return
        except RuntimeError:
            # Not in async context, safe to use asyncio.run()
            pass

        # Setup toolkits for all agents that need them (returns collected events)
        collected_events = asyncio.run(self.setup_for_execution(dag, config, registry))

        # Merge events from async context into sync context
        # This is necessary because asyncio.run() creates a new event loop with
        # a copy of ContextVars - modifications in the async context don't propagate back
        from roma_dspy.core.context import ExecutionContext
        ctx = ExecutionContext.get()
        if ctx and collected_events:
            ctx.toolkit_events.extend(collected_events.get('toolkit_events', []))
            ctx.tool_invocations.extend(collected_events.get('tool_invocations', []))

            if collected_events.get('toolkit_events') or collected_events.get('tool_invocations'):
                logger.debug(
                    f"Merged {len(collected_events.get('toolkit_events', []))} lifecycle events "
                    f"and {len(collected_events.get('tool_invocations', []))} tool invocations "
                    f"from async context into sync context"
                )

    @track_toolkit_lifecycle("cleanup")
    async def cleanup_execution(self, execution_id: str) -> None:
        """
        Clean up toolkits and resources for a completed execution.

        Uses reference counting for safe cleanup:
        1. Find all toolkits for this execution
        2. Call cleanup() on toolkits that will be removed
        3. Decrement reference counts
        4. Remove toolkits with refcount == 0
        5. Warn if refcount > 0 (still in use by other agents)

        Thread Safety:
            - Uses threading.Lock for atomic operations
            - Releases lock before async toolkit.cleanup() calls
            - Safe to call during active execution

        Execution Isolation:
            - Only cleans up toolkits for specified execution_id
            - Never affects other executions

        Args:
            execution_id: Unique identifier for the execution to clean up

        Example:
            await manager.cleanup_execution("exec_123")
        """
        # Sanitize execution_id for consistent key matching
        safe_exec_id = execution_id.replace(":", "_").replace("|", "_")

        removed_count = 0
        retained_count = 0

        # BUG FIX B: Use execution tracking map to get cache keys
        # This ensures we only clean up toolkits that were actually fetched
        keys_for_execution = self._execution_toolkit_map.get(execution_id, set())

        if not keys_for_execution:
            logger.debug(f"No toolkits to clean up for execution {execution_id}")
            # Clean up tracking map even if no toolkits
            self._execution_toolkit_map.pop(execution_id, None)
            return

        # Step 1: Collect toolkits to cleanup (in lock)
        toolkits_to_cleanup = []
        with self._cache_thread_lock:

            for cache_key in keys_for_execution:
                refcount = self._toolkit_refcounts.get(cache_key, 0)

                if refcount <= 1:
                    # Last reference - will be removed, check if needs cleanup
                    toolkit = self._toolkit_cache.get(cache_key)
                    if toolkit and hasattr(toolkit, 'cleanup'):
                        toolkits_to_cleanup.append((cache_key, toolkit))

        # Step 2: Cleanup toolkits (outside lock - async operations)
        for cache_key, toolkit in toolkits_to_cleanup:
            try:
                await toolkit.cleanup()
                logger.debug(f"Cleaned up toolkit: {cache_key}")
            except Exception as e:
                logger.warning(f"Toolkit cleanup error for {cache_key}: {e}")

        # Step 3: Remove from cache (back in lock)
        with self._cache_thread_lock:
            for cache_key in keys_for_execution:
                # Decrement reference count
                refcount = self._toolkit_refcounts.get(cache_key, 0)

                if refcount <= 1:
                    # Last reference - remove
                    del self._toolkit_cache[cache_key]
                    self._toolkit_refcounts.pop(cache_key, None)
                    removed_count += 1
                    logger.debug(f"Removed toolkit from cache: {cache_key}")
                else:
                    # Still in use by other agents - decrement and keep
                    self._toolkit_refcounts[cache_key] = refcount - 1
                    retained_count += 1
                    logger.debug(
                        f"Retained toolkit {cache_key} "
                        f"(refcount: {refcount} -> {refcount-1})"
                    )

        # BUG FIX B: Remove execution tracking (prevent memory leak)
        self._execution_toolkit_map.pop(execution_id, None)

        # Log cleanup summary
        if removed_count > 0 or retained_count > 0:
            logger.info(
                f"Cleaned up execution {execution_id}: "
                f"removed={removed_count}, retained={retained_count} "
                f"(cache size: {len(self._toolkit_cache)})"
            )

        # Force garbage collection to free resources
        if removed_count > 0:
            gc.collect()
