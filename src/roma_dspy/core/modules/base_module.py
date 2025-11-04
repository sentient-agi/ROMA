"""Shared base class for ROMA-DSPy DSPy modules."""

from __future__ import annotations

import dspy
import inspect
import threading
import time
from typing import Union, Any, Optional, Dict, Mapping, Sequence, Mapping as TMapping, List, TYPE_CHECKING

from loguru import logger

from roma_dspy.types.prediction_strategy import PredictionStrategy
from roma_dspy.types.adapter_type import AdapterType
from roma_dspy.resilience import with_module_resilience
from roma_dspy.tools.base.manager import ToolkitManager

if TYPE_CHECKING:
    from roma_dspy.config.schemas.agents import AgentConfig
    from roma_dspy.config.schemas.toolkit import ToolkitConfig


class BaseModule(dspy.Module):
    """
    Common functionality for ROMA DSPy modules:
    - Per-instance LM configuration via dspy.context (thread/async-safe).
    - Accept an existing dspy.LM or build one from (model + config).
    - Build a predictor from a PredictionStrategy for a given signature.
    - Sync and async entrypoints (forward / aforward) with optional tools, context and per-call kwargs.
    """

    # Class-level declarations (override in subclasses)
    MANDATORY_TOOLKIT_NAMES: List[str] = []

    # Default adapter configuration for legacy mode (override in subclasses if needed)
    # Example: Set JSON adapter for a specific agent: DEFAULT_ADAPTER_TYPE = AdapterType.JSON
    DEFAULT_ADAPTER_TYPE: AdapterType = AdapterType.CHAT
    DEFAULT_USE_NATIVE_FUNCTION_CALLING: bool = False

    # Class-level counter for instance IDs (thread-safe)
    _instance_counter = 0
    _instance_counter_lock = threading.Lock()

    def __call__(self, *args, **kwargs):
        """Delegate to forward method for compatibility with runtime calls."""
        return self.forward(*args, **kwargs)

    def __init__(
        self,
        *,
        signature: Any,
        config: Optional["AgentConfig"] = None,
        prediction_strategy: Union[PredictionStrategy, str] = PredictionStrategy.CHAIN_OF_THOUGHT,
        lm: Optional[dspy.LM] = None,
        model: Optional[str] = None,
        model_config: Optional[Mapping[str, Any]] = None,
        tools: Optional[Union[Sequence[Any], TMapping[str, Any]]] = None,
        config_demos: Optional[List[Any]] = None,
        context_defaults: Optional[Dict[str, Any]] = None,
        **strategy_kwargs: Any,
    ) -> None:
        super().__init__()

        # Assign unique instance ID for debugging (thread-safe)
        with BaseModule._instance_counter_lock:
            BaseModule._instance_counter += 1
            self._instance_id = BaseModule._instance_counter

        # Lock for lazy predictor initialization (thread-safe)
        self._lazy_init_lock = threading.Lock()

        self.signature = signature

        # Store config demos (for few-shot prompting)
        self._config_demos: List[Any] = list(config_demos or [])

        # If config is provided, use it to set up the module
        if config is not None:
            self._init_from_config(config, strategy_kwargs)
        else:
            self._init_from_parameters(
                prediction_strategy, lm, model, model_config, tools, context_defaults, strategy_kwargs
            )

    def _init_from_config(self, config: "AgentConfig", strategy_kwargs: Dict[str, Any]) -> None:
        """Initialize module from AgentConfig."""
        # Use config values
        prediction_strategy = PredictionStrategy.from_string(config.prediction_strategy)

        # Store toolkit configs for execution-scoped initialization
        self._toolkit_configs = getattr(config, 'toolkits', [])
        self._tools: Dict[str, Any] = {}  # Will be populated per-execution

        # Build LM from config
        llm_config = config.llm
        lm_kwargs = {
            "temperature": llm_config.temperature,
            "max_tokens": llm_config.max_tokens,
            "timeout": llm_config.timeout,
            "num_retries": llm_config.num_retries,
            "cache": llm_config.cache,
        }
        if llm_config.api_key:
            lm_kwargs["api_key"] = llm_config.api_key
        if llm_config.base_url:
            lm_kwargs["base_url"] = llm_config.base_url
        if llm_config.rollout_id is not None:
            lm_kwargs["rollout_id"] = llm_config.rollout_id
        if llm_config.extra_body:
            lm_kwargs["extra_body"] = llm_config.extra_body

        # Create adapter from config
        adapter = llm_config.adapter_type.create_adapter(
            use_native_function_calling=llm_config.use_native_function_calling
        )
        logger.debug(
            f"Created {llm_config.adapter_type.value.upper()}Adapter with "
            f"native_function_calling={llm_config.use_native_function_calling}"
        )

        self._lm = dspy.LM(llm_config.model, **lm_kwargs)
        self._adapter = adapter  # Store for per-call configuration

        # Build predictor
        build_kwargs = dict(strategy_kwargs)

        # Only pass strategy-specific parameters to the prediction strategy
        build_kwargs.update(config.strategy_config)

        # For ReAct/CodeAct strategies with toolkit configs, defer predictor creation
        # These strategies need tools at construction time (for Literal type in signature)
        # But toolkit-based tools are only available at execution time (need ExecutionContext)
        # Solution: Build predictor lazily on first aforward() call
        if (prediction_strategy in (PredictionStrategy.REACT, PredictionStrategy.CODE_ACT)
            and len(self._toolkit_configs) > 0):
            # Store config for lazy initialization
            self._lazy_init_needed = True
            self._prediction_strategy = prediction_strategy
            self._build_kwargs = build_kwargs
            self._predictor = None
        else:
            # Build predictor immediately for non-tool strategies or legacy tool mode
            if prediction_strategy in (PredictionStrategy.REACT, PredictionStrategy.CODE_ACT):
                # DSPy ReAct expects tools as a list, not dict
                # When iterating "for t in tools", dict gives keys (strings), not values (callables)
                # Convert dict values to list for predictor initialization
                tools_dict = self._tools or {}
                build_kwargs.setdefault("tools", list(tools_dict.values()) if tools_dict else [])

            # Build predictor (adapter will be set at runtime via context)
            self._predictor = prediction_strategy.build(self.signature, **build_kwargs)

            self._lazy_init_needed = False
            self._prediction_strategy = None
            self._build_kwargs = None

        # Store agent-specific configuration for use by agent logic
        self._agent_config = config.agent_config

        # Context defaults
        self._context_defaults: Dict[str, Any] = {}

    def _init_from_parameters(
        self,
        prediction_strategy: Union[PredictionStrategy, str],
        lm: Optional[dspy.LM],
        model: Optional[str],
        model_config: Optional[Mapping[str, Any]],
        tools: Optional[Union[Sequence[Any], TMapping[str, Any]]],
        context_defaults: Optional[Dict[str, Any]],
        strategy_kwargs: Dict[str, Any]
    ) -> None:
        """Initialize module from individual parameters (legacy mode)."""
        if isinstance(prediction_strategy, str):
            prediction_strategy = PredictionStrategy.from_string(prediction_strategy)

        self._toolkit_configs = []  # No toolkit configs in legacy mode
        self._tools: Dict[str, Any] = self._normalize_tools(tools)

        build_kwargs = dict(strategy_kwargs)
        if prediction_strategy in (PredictionStrategy.REACT, PredictionStrategy.CODE_ACT) and self._tools:
            # DSPy ReAct expects tools as a list, not dict
            # When iterating "for t in tools", dict gives keys (strings), not values (callables)
            # Convert dict values to list for predictor initialization
            build_kwargs.setdefault("tools", list(self._tools.values()))

        # Build predictor (adapter will be set at runtime via context)
        self._predictor = prediction_strategy.build(self.signature, **build_kwargs)

        # Patch finish tool for ReAct/CodeAct strategies (prevents LLM from passing output params)
        if prediction_strategy in (PredictionStrategy.REACT, PredictionStrategy.CODE_ACT):
            self._patch_finish_tool()

        # Initialize lazy init state (used in _update_predictor_tools)
        self._lazy_init_needed = False
        self._prediction_strategy = None
        self._build_kwargs = None

        if lm is not None and model is not None:
            logger.warning(
                "Both 'lm' and 'model' parameters provided to BaseModule. "
                "Using 'lm' instance and ignoring 'model' parameter."
            )

        if lm is None:
            if model is None:
                raise ValueError(
                    "Either provide an existing lm=dspy.LM(...) or a model='provider/model' to build one."
                )
            lm_kwargs = dict(model_config or {})
            lm = dspy.LM(model, **lm_kwargs)

        self._lm: dspy.LM = lm
        self._context_defaults: Dict[str, Any] = dict(context_defaults or {})
        self._agent_config: Dict[str, Any] = {}  # No agent config in legacy mode

        # Set default adapter for legacy mode (uses class-level configuration)
        # When using config mode, adapter is set in _init_from_config from llm_config.adapter_type
        self._adapter = self.DEFAULT_ADAPTER_TYPE.create_adapter(
            use_native_function_calling=self.DEFAULT_USE_NATIVE_FUNCTION_CALLING
        )
        logger.debug(
            f"Legacy mode: Created {self.DEFAULT_ADAPTER_TYPE.value.upper()}Adapter with "
            f"native_function_calling={self.DEFAULT_USE_NATIVE_FUNCTION_CALLING}"
        )

    # ---------- Public API ----------

    def forward(
        self,
        goal: str,
        *,
        context: Optional[str] = None,
        tools: Optional[Union[Sequence[Any], TMapping[str, Any]]] = None,
        demos: Optional[List[Any]] = None,
        config: Optional[Dict[str, Any]] = None,
        dspy_context: Optional[Dict[str, Any]] = None,
        call_params: Optional[Dict[str, Any]] = None,
        **call_kwargs: Any,
    ):
        """
        Synchronous forward pass.

        Note: For toolkit-based modules, sync forward will have empty tools.
        Use async version for full toolkit support:
            result = await module.aforward(goal, **kwargs)

        Args:
            goal: The main task input (matches signature field name).
            context: XML string passed to signature's context field (agent instructions).
            tools: Optional tools (dspy.Tool objects) to use for this call.
            demos: Optional few-shot demos (dspy.Example objects) to use for this call.
                   These are merged with config demos (config demos first, then runtime demos).
                   Pass None or omit to use only config demos. Pass [] to use config demos only.
                   Note: Currently no way to clear config demos at runtime.
            config: Optional per-call LM overrides.
            dspy_context: Dict passed into dspy.context(...) for this call (DSPy runtime config like callbacks).
            call_params: Extra kwargs to pass to predictor call (strategy-specific).
            **call_kwargs: Additional kwargs merged into call_params for convenience.
        """
        # Sync forward: toolkit-based modules have empty tools (graceful degradation)
        runtime_tools = self._merge_tools(self._tools, tools)

        # Prepare demos (merge config + runtime demos)
        merged_demos = self._prepare_demos(demos)

        # Build context kwargs (merge defaults and per-call), ensure an LM is set
        ctx = dict(self._context_defaults)
        if dspy_context:
            ctx.update(dspy_context)
        ctx.setdefault("lm", self._lm)
        # Add adapter to context if available (always override to ensure correct adapter is used)
        if hasattr(self, "_adapter") and self._adapter is not None:
            ctx["adapter"] = self._adapter
            logger.debug(
                f"Setting adapter in context: {type(self._adapter).__name__} "
                f"(native_fc={getattr(self._adapter, 'use_native_function_calling', 'N/A')})"
            )

        # Prepare predictor-call kwargs (merge call_params + call_kwargs)
        extra = dict(call_params or {})
        if call_kwargs:
            extra.update(call_kwargs)
        if config is not None:
            extra["config"] = config
        if runtime_tools:
            extra["tools"] = runtime_tools
        if merged_demos:
            extra["demos"] = merged_demos
        if context is not None:
            extra["context"] = context

        # Filter extras to what the predictor's forward accepts (avoid TypeError)
        target_method = getattr(self._predictor, "forward", None)
        filtered = self._filter_kwargs(target_method, extra)

        # Debug: Log context contents before passing to DSPy
        logger.debug(f"DSPy context keys: {list(ctx.keys())}, adapter={type(ctx.get('adapter')).__name__ if 'adapter' in ctx else 'None'}")

        with dspy.context(**ctx):
            return self._execute_predictor(goal, filtered)

    async def aforward(
        self,
        goal: str,
        *,
        context: Optional[str] = None,
        tools: Optional[Union[Sequence[Any], TMapping[str, Any]]] = None,
        demos: Optional[List[Any]] = None,
        config: Optional[Dict[str, Any]] = None,
        dspy_context: Optional[Dict[str, Any]] = None,
        call_params: Optional[Dict[str, Any]] = None,
        **call_kwargs: Any,
    ):
        """
        Async version of forward(...). Uses acall(...) when available, filtering kwargs
        based on aforward(...) if present, otherwise forward(...).

        Args:
            goal: The main task input (matches signature field name).
            context: XML string passed to signature's context field (agent instructions).
            tools: Optional tools (dspy.Tool objects) to use for this call.
            demos: Optional few-shot demos (dspy.Example objects) to use for this call.
                   These are merged with config demos (config demos first, then runtime demos).
                   Pass None or omit to use only config demos. Pass [] to use config demos only.
                   Note: Currently no way to clear config demos at runtime.
            config: Optional per-call LM overrides.
            dspy_context: Dict passed into dspy.context(...) for this call (DSPy runtime config like callbacks).
            call_params: Extra kwargs to pass to predictor call (strategy-specific).
            **call_kwargs: Additional kwargs merged into call_params for convenience.
        """
        # Get execution-scoped tools from ExecutionContext
        execution_tools = await self._get_execution_tools()
        runtime_tools = self._merge_tools(execution_tools, tools)

        # Update predictor's internal tools (for ReAct/CodeAct that don't accept tools as parameters)
        self._update_predictor_tools(runtime_tools)

        # Prepare demos (merge config + runtime demos)
        merged_demos = self._prepare_demos(demos)

        ctx = dict(self._context_defaults)
        if dspy_context:
            ctx.update(dspy_context)
        ctx.setdefault("lm", self._lm)
        # Add adapter to context if available (always override to ensure correct adapter is used)
        if hasattr(self, "_adapter") and self._adapter is not None:
            ctx["adapter"] = self._adapter
            logger.debug(
                f"Setting adapter in context: {type(self._adapter).__name__} "
                f"(native_fc={getattr(self._adapter, 'use_native_function_calling', 'N/A')})"
            )

        extra = dict(call_params or {})
        if call_kwargs:
            extra.update(call_kwargs)
        if config is not None:
            extra["config"] = config
        if runtime_tools:
            extra["tools"] = runtime_tools
        if merged_demos:
            extra["demos"] = merged_demos
        if context is not None:
            extra["context"] = context

        # Choose method to derive accepted kwargs
        method_for_filter = getattr(self._predictor, "aforward", None) or getattr(self._predictor, "forward", None)
        filtered = self._filter_kwargs(method_for_filter, extra)

        with dspy.context(**ctx):
            return await self._execute_predictor_async(goal, filtered, method_for_filter)
    
    def get_model_config(self, *, redact_secrets: bool = True) -> Dict[str, Any]:
        """
        Return LM configuration from the underlying BaseLM/dspy.LM instance.
        Fields: model, model_type, cache, kwargs (e.g., temperature, max_tokens, provider-specific args).
        """
        lm = self._lm
        cfg: Dict[str, Any] = {}

        model = getattr(lm, "model", None)
        if model is not None:
            cfg["model"] = model

        model_type = getattr(lm, "model_type", None)
        if model_type is not None:
            cfg["model_type"] = model_type

        cache = getattr(lm, "cache", None)
        if cache is not None:
            cfg["cache"] = cache

        kwargs = getattr(lm, "kwargs", None)
        if isinstance(kwargs, dict):
            safe_kwargs = dict(kwargs)
            if redact_secrets:
                for k in list(safe_kwargs.keys()):
                    if any(s in k.lower() for s in ("key", "token", "secret", "password")):
                        safe_kwargs[k] = "****"
            cfg["kwargs"] = safe_kwargs
        else:
            cfg["kwargs"] = {}

        return cfg

    # ---------- Conveniences ----------

    @property
    def lm(self) -> dspy.LM:
        return self._lm

    def replace_lm(self, lm: dspy.LM) -> "BaseModule":
        self._lm = lm
        return self

    @property
    def tools(self) -> Dict[str, Any]:
        return dict(self._tools)

    @property
    def agent_config(self) -> Dict[str, Any]:
        """Get agent-specific configuration parameters."""
        return getattr(self, '_agent_config', {})

    def set_tools(self, tools: Optional[Union[Sequence[Any], TMapping[str, Any]]]) -> "BaseModule":
        self._tools = self._normalize_tools(tools)
        return self

    def add_tools(self, *tools: Any) -> "BaseModule":
        for t in tools:
            tool_name = getattr(t, '__name__', f'tool_{len(self._tools)}')
            if tool_name not in self._tools:
                self._tools[tool_name] = t
        return self

    def clear_tools(self) -> "BaseModule":
        self._tools.clear()
        return self

    # ---------- Internals ----------

    @staticmethod
    def _normalize_tools(tools: Optional[Union[Sequence[Any], TMapping[str, Any]]]) -> Dict[str, Any]:
        """Normalize tools to dict format to preserve tool names."""
        if tools is None:
            return {}
        if isinstance(tools, dict):
            return dict(tools)
        if isinstance(tools, (list, tuple)):
            # Convert list to dict using function names as keys
            result = {}
            for idx, tool in enumerate(tools):
                tool_name = getattr(tool, '__name__', f'tool_{idx}')
                result[tool_name] = tool
            return result
        raise TypeError("tools must be a sequence of dspy.Tool or a mapping name->dspy.Tool")

    def _get_mandatory_toolkit_configs(self) -> List["ToolkitConfig"]:
        """
        Get mandatory toolkits from class declaration.

        Returns:
            List of ToolkitConfig objects for mandatory toolkits
        """
        from roma_dspy.config.schemas.toolkit import ToolkitConfig

        return [
            ToolkitConfig(class_name=name, enabled=True, mandatory=True)
            for name in self.__class__.MANDATORY_TOOLKIT_NAMES
        ]

    async def _get_execution_tools(self) -> Dict[str, Any]:
        """
        Get tools for current execution from ExecutionContext.

        This method retrieves toolkit-based tools from the ToolkitManager
        using the execution-scoped FileStorage from ExecutionContext.

        If no ExecutionContext is set (e.g., in tests or legacy mode),
        falls back to empty dict.

        Returns:
            Dict of tool name -> tool function
        """
        # Import here to avoid circular dependency
        from roma_dspy.core.context import ExecutionContext

        # Get mandatory toolkits from class declaration
        mandatory_configs = self._get_mandatory_toolkit_configs()

        # Merge with user configs (mandatory first, then user toolkits)
        all_configs = mandatory_configs + list(self._toolkit_configs or [])

        # If we have toolkit configs, get tools from ToolkitManager
        if all_configs:
            ctx = ExecutionContext.get()
            if ctx:
                manager = ToolkitManager.get_instance()
                tools_dict = await manager.get_tools_for_execution(
                    execution_id=ctx.execution_id,
                    file_storage=ctx.file_storage,
                    toolkit_configs=all_configs,
                    # No longer need agent_type parameter - toolkits already merged!
                )
                # get_tools_for_execution now returns a dict directly
                return tools_dict

        # Fallback to existing tools (for legacy mode or when no context)
        return dict(self._tools)

    @staticmethod
    def _merge_tools(default_tools: Dict[str, Any], runtime_tools: Optional[Union[Sequence[Any], TMapping[str, Any]]]) -> Dict[str, Any]:
        """Merge default and runtime tools as dicts."""
        if runtime_tools is None:
            return dict(default_tools)
        merged = dict(default_tools)
        to_add = BaseModule._normalize_tools(runtime_tools)
        merged.update(to_add)
        return merged

    def _prepare_demos(self, runtime_demos: Optional[List[Any]] = None) -> List[Any]:
        """
        Merge config demos and runtime demos.

        Config demos are provided at module initialization (from YAML config),
        runtime demos are provided at forward() call time.

        Merging strategy: config demos first, then runtime demos (concatenation).

        Args:
            runtime_demos: Optional demos provided at runtime via forward() method

        Returns:
            List of dspy.Example objects (config + runtime)
        """
        if runtime_demos is None:
            return list(self._config_demos)
        # Concatenate: config demos + runtime demos
        return list(self._config_demos) + list(runtime_demos)

    def _update_predictor_tools(self, runtime_tools: Dict[str, Any]) -> None:
        """
        Update predictor's internal tools dynamically.

        Handles two cases:
        1. Lazy initialization: If predictor was deferred (ReAct/CodeAct with toolkits),
           build it now with runtime tools
        2. Dynamic update: If predictor already exists, update its internal tools dict

        Args:
            runtime_tools: Dict of tool name -> tool function to update predictor with
        """
        if not runtime_tools:
            return

        # Case 1: Lazy initialization - build predictor with tools (thread-safe with double-checked locking)
        if self._lazy_init_needed and self._predictor is None:
            with self._lazy_init_lock:
                # Double-check: another thread might have initialized while we waited for the lock
                if self._lazy_init_needed and self._predictor is None:
                    build_kwargs = dict(self._build_kwargs)
                    # DSPy ReAct/CodeAct expect tools as a list of callables, not a dict
                    # Pass list of tool functions (values), not dict keys
                    build_kwargs["tools"] = list(runtime_tools.values())

                    # Build predictor (adapter will be set at runtime via context in forward/aforward)
                    self._predictor = self._prediction_strategy.build(self.signature, **build_kwargs)

                    logger.debug(
                        f"Initialized {self._prediction_strategy.value} predictor with {len(runtime_tools)} custom tools + finish tool"
                    )
                    # Patch finish tool to accept kwargs (prevents LLM from passing output params)
                    self._patch_finish_tool()
                    # Clear lazy init state
                    self._lazy_init_needed = False
                    self._prediction_strategy = None
                    self._build_kwargs = None
            return

        # Case 2: Dynamic update - update existing predictor's tools
        if not hasattr(self._predictor, 'tools'):
            return

        from dspy.adapters.types.tool import Tool

        # Convert our dict of tools to DSPy Tool objects
        predictor_tools = {}
        for name, func in runtime_tools.items():
            if not isinstance(func, Tool):
                predictor_tools[name] = Tool(func)
            else:
                predictor_tools[name] = func

        # Preserve any existing predictor-specific tools (like ReAct's 'finish' tool)
        preserved_count = 0
        if isinstance(self._predictor.tools, dict):
            for name, tool in self._predictor.tools.items():
                if name not in predictor_tools:
                    predictor_tools[name] = tool
                    preserved_count += 1

        if preserved_count > 0:
            logger.debug(f"Preserved {preserved_count} built-in tools (e.g., finish)")

        self._predictor.tools = predictor_tools

        # Patch finish tool to accept kwargs
        self._patch_finish_tool()

    def _patch_finish_tool(self) -> None:
        """
        Patch the finish tool to accept arbitrary keyword arguments.

        DSPy's ReAct creates a finish tool with lambda: "Completed." (no parameters),
        but LLMs sometimes misinterpret the finish tool description and try to pass
        output field values as arguments, e.g. finish(output="result").

        Root cause: The finish tool description says "signals that all information for
        producing the outputs, i.e. `output`, are now available". LLMs interpret this
        as needing to pass the output value to finish().

        Setting has_kwargs=True alone doesn't work - we must replace the lambda function
        with one that actually accepts **kwargs.

        See: https://github.com/stanfordnlp/dspy/issues/7909
        """
        if not hasattr(self._predictor, 'tools') or not isinstance(self._predictor.tools, dict):
            return

        finish_tool = self._predictor.tools.get('finish')
        if finish_tool is None:
            return

        # Replace the finish tool's function with one that accepts and ignores **kwargs
        if hasattr(finish_tool, 'func'):
            finish_tool.func = lambda **kwargs: "Completed."

            # Re-parse to update has_kwargs automatically (DSPy 3.0+)
            if hasattr(finish_tool, '_parse_function'):
                finish_tool._parse_function(
                    finish_tool.func,
                    finish_tool.arg_desc if hasattr(finish_tool, 'arg_desc') else None
                )
                logger.debug(
                    f"Patched finish tool to accept **kwargs (has_kwargs={finish_tool.has_kwargs})"
                )
            else:
                # Fallback for older DSPy versions
                if hasattr(finish_tool, 'has_kwargs'):
                    finish_tool.has_kwargs = True
                logger.debug("Patched finish tool func and set has_kwargs=True")
        else:
            logger.debug("Finish tool doesn't have func attribute (unexpected)")

    @staticmethod
    def _get_allowed_kwargs(func: Optional[Any]) -> Optional[set]:
        if func is None:
            return None
        try:
            sig = inspect.signature(func)
        except (TypeError, ValueError):
            return None
        has_var_kw = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values())
        if has_var_kw:
            return None  # accepts any kwargs
        allowed = set(
            name
            for name, p in sig.parameters.items()
            if name != "self" and p.kind in (inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY)
        )
        return allowed

    @staticmethod
    def _filter_kwargs(func: Optional[Any], kwargs: Dict[str, Any]) -> Dict[str, Any]:
        allowed = BaseModule._get_allowed_kwargs(func)
        if allowed is None:
            return dict(kwargs)
        return {k: v for k, v in kwargs.items() if k in allowed}

    # ---------- Resilient Predictor Execution ----------

    @with_module_resilience(module_name="base_predictor")
    def _execute_predictor(self, goal: str, filtered: Dict[str, Any]):
        """Execute predictor with resilience protection."""
        return self._predictor(goal=goal, **filtered)

    @with_module_resilience(module_name="base_predictor")
    async def _execute_predictor_async(self, goal: str, filtered: Dict[str, Any], method_for_filter: Optional[Any]):
        """Execute predictor asynchronously with resilience protection."""
        acall = getattr(self._predictor, "acall", None)
        if acall is not None and method_for_filter is not None and hasattr(self._predictor, "aforward"):
            return await self._predictor.acall(goal=goal, **filtered)
        # Fallback to sync if async not available
        return self._predictor(goal=goal, **filtered)

    @classmethod
    def with_settings_resilience(
        cls,
        *,
        signature: Any,
        prediction_strategy: Union[PredictionStrategy, str] = PredictionStrategy.CHAIN_OF_THOUGHT,
        **kwargs
    ):
        """Create BaseModule with resilience configuration from global settings."""
        # Settings are now available through the resilience decorators
        # The decorators will use the global circuit breaker and retry policies
        return cls(
            signature=signature,
            prediction_strategy=prediction_strategy,
            **kwargs
        )
