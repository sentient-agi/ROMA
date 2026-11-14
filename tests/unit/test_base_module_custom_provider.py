"""Regression test for custom OpenAI-compatible providers (CometAPI, n1n.ai, etc.).

Covers #58 (Add CometAPI support) and #62 (Add n1n.ai API as a model provider):
LLMConfig.base_url/api_key already flow through to the underlying dspy.LM,
so any OpenAI-compatible gateway works via the `openai/` model prefix with no
new provider code. This test pins that behavior so it can't regress silently.
"""

from __future__ import annotations

import dspy

from roma_dspy.config.schemas.agents import AgentConfig
from roma_dspy.config.schemas.base import LLMConfig
from roma_dspy.core.modules.base_module import BaseModule


class _DummySignature(dspy.Signature):
    """goal -> output"""

    goal: str = dspy.InputField()
    output: str = dspy.OutputField()


def test_custom_openai_compatible_base_url_and_api_key_propagate() -> None:
    """A CometAPI-style config should build a dspy.LM with base_url + api_key set."""
    config = AgentConfig(
        llm=LLMConfig(
            model="openai/gpt-4o-mini",
            base_url="https://api.cometapi.com/v1",
            api_key="sk-cometapi-test-key",
        ),
        prediction_strategy="chain_of_thought",
    )

    module = BaseModule(signature=_DummySignature, config=config)

    assert module.lm.model == "openai/gpt-4o-mini"
    assert module.lm.kwargs.get("base_url") == "https://api.cometapi.com/v1"
    assert module.lm.kwargs.get("api_key") == "sk-cometapi-test-key"


def test_n1n_style_base_url_also_propagates() -> None:
    """Same code path, different gateway: n1n.ai works identically to CometAPI."""
    config = AgentConfig(
        llm=LLMConfig(
            model="openai/gpt-4o-mini",
            base_url="https://n1n.ai/v1",
            api_key="sk-n1n-test-key",
        ),
        prediction_strategy="chain_of_thought",
    )

    module = BaseModule(signature=_DummySignature, config=config)

    assert module.lm.kwargs.get("base_url") == "https://n1n.ai/v1"
    assert module.lm.kwargs.get("api_key") == "sk-n1n-test-key"
