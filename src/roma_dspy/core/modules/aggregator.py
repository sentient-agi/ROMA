"""Aggregator module for result synthesis."""

from __future__ import annotations

import dspy
from typing import Union, Any, Optional, Dict, Mapping, Sequence, Mapping as TMapping

from roma_dspy.core.modules.base_module import BaseModule
from roma_dspy.core.signatures.base_models.subtask import SubTask
from roma_dspy.core.signatures.signatures import AggregatorSignature
from roma_dspy.types import PredictionStrategy


class Aggregator(BaseModule):
    """Aggregates results from subtasks."""

    DEFAULT_SIGNATURE = AggregatorSignature
    MANDATORY_TOOLKIT_NAMES = ["ArtifactToolkit"]

    def __init__(
        self,
        prediction_strategy: Union[PredictionStrategy, str] = PredictionStrategy.CHAIN_OF_THOUGHT,
        *,
        signature: Any = None,
        config: Optional[Any] = None,
        lm: Optional[dspy.LM] = None,
        model: Optional[str] = None,
        model_config: Optional[Mapping[str, Any]] = None,
        tools: Optional[Union[Sequence[Any], TMapping[str, Any]]] = None,
        **strategy_kwargs: Any,
    ) -> None:
        super().__init__(
            signature=signature if signature is not None else self.DEFAULT_SIGNATURE,
            config=config,
            prediction_strategy=prediction_strategy,
            lm=lm,
            model=model,
            model_config=model_config,
            tools=tools,
            **strategy_kwargs,
        )

    def forward(
        self,
        original_goal: str,
        subtasks_results: Sequence[SubTask],
        *,
        context: Optional[str] = None,
        tools: Optional[Union[Sequence[Any], TMapping[str, Any]]] = None,
        config: Optional[Dict[str, Any]] = None,
        dspy_context: Optional[Dict[str, Any]] = None,
        call_params: Optional[Dict[str, Any]] = None,
        **call_kwargs: Any,
    ):
        """
        Args:
            original_goal: Original task goal.
            subtasks_results: List of subtask results to aggregate.
            context: XML string passed to signature's context field (agent instructions).
            tools: Optional tools for this call.
            config: Optional per-call LM overrides.
            dspy_context: Dict passed into dspy.context(...) for this call (DSPy runtime config like callbacks).
            call_params: Extra kwargs to pass to predictor call.
            **call_kwargs: Additional kwargs merged into call_params.
        """
        runtime_tools = self._merge_tools(self._tools, tools)

        ctx = dict(self._context_defaults)
        if dspy_context:
            ctx.update(dspy_context)
        ctx.setdefault("lm", self._lm)

        extra = dict(call_params or {})
        if call_kwargs:
            extra.update(call_kwargs)
        if config is not None:
            extra["config"] = config
        if runtime_tools:
            extra["tools"] = runtime_tools
        if context is not None:
            extra["context"] = context

        target_method = getattr(self._predictor, "forward", None)
        filtered = self._filter_kwargs(target_method, extra)

        with dspy.context(**ctx):
            return self._predictor(
                original_goal=original_goal,
                subtasks_results=list(subtasks_results),
                **filtered,
            )

    async def aforward(
        self,
        original_goal: str,
        subtasks_results: Sequence[SubTask],
        *,
        context: Optional[str] = None,
        tools: Optional[Union[Sequence[Any], TMapping[str, Any]]] = None,
        config: Optional[Dict[str, Any]] = None,
        dspy_context: Optional[Dict[str, Any]] = None,
        call_params: Optional[Dict[str, Any]] = None,
        **call_kwargs: Any,
    ):
        """Aggregate results - returns raw DSPy Prediction with get_lm_usage()."""
        # BUG FIX: Get execution-scoped tools from ExecutionContext (for toolkit-based agents)
        execution_tools = await self._get_execution_tools()
        runtime_tools = self._merge_tools(execution_tools, tools)

        # Update predictor's internal tools (for ReAct/CodeAct that don't accept tools as parameters)
        self._update_predictor_tools(runtime_tools)

        ctx = dict(self._context_defaults)
        if dspy_context:
            ctx.update(dspy_context)
        ctx.setdefault("lm", self._lm)

        extra = dict(call_params or {})
        if call_kwargs:
            extra.update(call_kwargs)
        if config is not None:
            extra["config"] = config
        if runtime_tools:
            extra["tools"] = runtime_tools
        if context is not None:
            extra["context"] = context

        method_for_filter = getattr(self._predictor, "aforward", None) or getattr(self._predictor, "forward", None)
        filtered = self._filter_kwargs(method_for_filter, extra)

        # Return raw DSPy prediction (has get_lm_usage() method)
        with dspy.context(**ctx):
            acall = getattr(self._predictor, "acall", None)
            payload = dict(original_goal=original_goal, subtasks_results=list(subtasks_results))
            if acall is not None and hasattr(self._predictor, "aforward"):
                return await acall(**payload, **filtered)
            if acall is not None:
                return await acall(**payload, **filtered)
            return self._predictor(**payload, **filtered)

    @classmethod
    def from_provider(
        cls,
        prediction_strategy: Union[PredictionStrategy, str] = PredictionStrategy.CHAIN_OF_THOUGHT,
        *,
        model: str,
        tools: Optional[Union[Sequence[Any], TMapping[str, Any]]] = None,
        **model_config: Any,
    ) -> "Aggregator":
        return cls(
            prediction_strategy,
            model=model,
            model_config=model_config or None,
            tools=tools,
        )
