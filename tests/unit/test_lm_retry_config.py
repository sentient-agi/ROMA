"""Tests for DSPy LM retry configuration propagation."""

import pytest
from roma_dspy.config.schemas.base import LLMConfig
from roma_dspy.config.schemas.agents import AgentConfig
from roma_dspy.core.modules.atomizer import Atomizer


def test_llm_config_defaults():
    """Test that LLMConfig has correct DSPy retry defaults."""
    config = LLMConfig()

    assert config.num_retries == 3
    assert config.cache is True
    assert config.rollout_id is None


def test_llm_config_custom_retry():
    """Test custom retry configuration."""
    config = LLMConfig(model="gpt-4o-mini", num_retries=5, cache=False, rollout_id=42)

    assert config.num_retries == 5
    assert config.cache is False
    assert config.rollout_id == 42


def test_llm_config_retry_validation():
    """Test that num_retries validation works."""
    with pytest.raises(ValueError, match="num_retries must be between 0 and 10"):
        LLMConfig(num_retries=11)

    with pytest.raises(ValueError, match="num_retries must be between 0 and 10"):
        LLMConfig(num_retries=-1)


def test_base_module_uses_retry_config(mock_lm):
    """Test that BaseModule passes retry config to dspy.LM."""
    agent_config = AgentConfig(
        llm=LLMConfig(model="gpt-4o-mini", num_retries=4, cache=True, rollout_id=1),
        prediction_strategy="chain_of_thought",
    )

    atomizer = Atomizer(config=agent_config)

    # Verify LM was created with correct kwargs
    assert atomizer._lm.kwargs.get("num_retries") == 4
    assert atomizer._lm.kwargs.get("cache") is True
    assert atomizer._lm.kwargs.get("rollout_id") == 1


def test_base_module_defaults_when_not_specified(mock_lm):
    """Test that defaults are used when not explicitly set."""
    agent_config = AgentConfig(
        llm=LLMConfig(model="gpt-4o-mini"), prediction_strategy="chain_of_thought"
    )

    atomizer = Atomizer(config=agent_config)

    # Should use defaults from LLMConfig
    assert atomizer._lm.kwargs.get("num_retries") == 3
    assert atomizer._lm.kwargs.get("cache") is True


@pytest.fixture
def mock_lm(monkeypatch):
    """Mock dspy.LM to capture initialization kwargs."""

    class MockLM:
        def __init__(self, model, **kwargs):
            self.model = model
            self.kwargs = kwargs

    monkeypatch.setattr("dspy.LM", MockLM)
    return MockLM
