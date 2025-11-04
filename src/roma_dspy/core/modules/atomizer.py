"""Atomizer module for task decomposition."""

from __future__ import annotations

import dspy
from typing import Union, Any, Optional, Mapping, Sequence, Mapping as TMapping

from roma_dspy.core.modules.base_module import BaseModule
from roma_dspy.core.signatures.signatures import AtomizerSignature
from roma_dspy.types import PredictionStrategy


class Atomizer(BaseModule):
    """Decomposes tasks into atomic units."""

    DEFAULT_SIGNATURE = AtomizerSignature
    MANDATORY_TOOLKIT_NAMES = []

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

    @classmethod
    def from_provider(
        cls,
        prediction_strategy: Union[PredictionStrategy, str] = PredictionStrategy.CHAIN_OF_THOUGHT,
        *,
        model: str,
        tools: Optional[Union[Sequence[Any], TMapping[str, Any]]] = None,
        **model_config: Any,
    ) -> "Atomizer":
        return cls(
            prediction_strategy,
            model=model,
            model_config=model_config or None,
            tools=tools,
        )
