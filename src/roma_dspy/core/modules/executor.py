"""Executor module for task execution and tool routing."""

from __future__ import annotations

import dspy
from typing import Union, Any, Optional, Dict, Mapping, Sequence, Mapping as TMapping, List

from roma_dspy.core.signatures.signatures import ExecutorSignature
from roma_dspy.types import PredictionStrategy
from roma_dspy.core.modules.base_module import BaseModule


class Executor(BaseModule):
    """Executes atomic tasks and routes to tools."""

    DEFAULT_SIGNATURE = ExecutorSignature
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

    # Executor now inherits forward() and aforward() from BaseModule
    # No overrides needed - parameter names and logic are identical!

    @classmethod
    def from_provider(
        cls,
        prediction_strategy: Union[PredictionStrategy, str] = PredictionStrategy.CHAIN_OF_THOUGHT,
        *,
        model: str,
        tools: Optional[Union[Sequence[Any], TMapping[str, Any]]] = None,
        **model_config: Any,
    ) -> "Executor":
        return cls(
            prediction_strategy,
            model=model,
            model_config=model_config or None,
            tools=tools,
        )
