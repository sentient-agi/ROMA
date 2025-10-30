"""Unit tests for extra_body parameter in LLMConfig."""

import pytest
from roma_dspy.config.schemas.base import LLMConfig
from roma_dspy.config.schemas.agents import AgentConfig
from roma_dspy.core.modules import Atomizer


class TestExtraBodyValidation:
    """Test extra_body field validation in LLMConfig."""

    def test_extra_body_none(self):
        """Test that None is accepted for extra_body."""
        config = LLMConfig(model="gpt-4o", extra_body=None)
        assert config.extra_body is None

    def test_extra_body_basic_dict(self):
        """Test that a basic dict is accepted."""
        extra = {"plugins": ["web_search"]}
        config = LLMConfig(model="openrouter/gpt-4o", extra_body=extra)
        assert config.extra_body == extra

    def test_extra_body_complex_structure(self):
        """Test that complex nested structures are accepted."""
        extra = {
            "plugins": ["web_search"],
            "web_search_options": {
                "search_context_size": 5,
                "search_recency_filter": "week"
            },
            "models": ["gpt-4o", "gpt-4o-mini"],
            "route": "fallback"
        }
        config = LLMConfig(model="openrouter/gpt-4o", extra_body=extra)
        assert config.extra_body == extra

    def test_extra_body_sensitive_key_api_key(self):
        """Test that api_key in extra_body is rejected."""
        with pytest.raises(ValueError, match="Sensitive key 'api_key'"):
            LLMConfig(
                model="gpt-4o",
                extra_body={"api_key": "secret-key"}
            )

    def test_extra_body_sensitive_key_secret(self):
        """Test that secret in extra_body is rejected."""
        with pytest.raises(ValueError, match="Sensitive key 'my_secret'"):
            LLMConfig(
                model="gpt-4o",
                extra_body={"my_secret": "value"}
            )

    def test_extra_body_sensitive_key_token(self):
        """Test that token in extra_body is rejected."""
        with pytest.raises(ValueError, match="Sensitive key 'auth_token'"):
            LLMConfig(
                model="gpt-4o",
                extra_body={"auth_token": "value"}
            )

    def test_extra_body_sensitive_key_password(self):
        """Test that password in extra_body is rejected."""
        with pytest.raises(ValueError, match="Sensitive key 'password'"):
            LLMConfig(
                model="gpt-4o",
                extra_body={"password": "value"}
            )

    def test_extra_body_sensitive_key_credential(self):
        """Test that credential in extra_body is rejected."""
        with pytest.raises(ValueError, match="Sensitive key 'credential'"):
            LLMConfig(
                model="gpt-4o",
                extra_body={"credential": "value"}
            )

    def test_extra_body_size_limit(self):
        """Test that oversized extra_body is rejected."""
        # Create a dict that exceeds 50KB when JSON-serialized
        huge_dict = {"data": "x" * 100_000}
        with pytest.raises(ValueError, match="extra_body too large"):
            LLMConfig(model="gpt-4o", extra_body=huge_dict)

    def test_extra_body_size_within_limit(self):
        """Test that extra_body within size limit is accepted."""
        # Create a dict that's large but under 50KB
        large_dict = {"data": "x" * 10_000}
        config = LLMConfig(model="gpt-4o", extra_body=large_dict)
        assert config.extra_body == large_dict

    def test_extra_body_web_search_warning(self, caplog):
        """Test that web_search plugin triggers a warning."""
        import logging
        caplog.set_level(logging.WARNING)

        config = LLMConfig(
            model="openrouter/gpt-4o",
            extra_body={"plugins": ["web_search"]}
        )

        # Check that warning was logged
        assert any("web_search plugin enabled" in record.message.lower()
                   for record in caplog.records)

    def test_extra_body_plugin_typo_warning(self, caplog):
        """Test that 'plugin' (singular) triggers a warning."""
        import logging
        caplog.set_level(logging.WARNING)

        config = LLMConfig(
            model="openrouter/gpt-4o",
            extra_body={"plugin": "web_search"}
        )

        # Check that typo warning was logged
        assert any("did you mean 'plugins'" in record.message.lower()
                   for record in caplog.records)


class TestExtraBodyIntegration:
    """Test extra_body integration with BaseModule."""

    def test_extra_body_passed_to_lm(self):
        """Test that extra_body is passed to dspy.LM via AgentConfig."""
        extra = {"plugins": ["web_search"]}
        agent_config = AgentConfig(
            llm=LLMConfig(
                model="openrouter/anthropic/claude-sonnet-4.5",
                extra_body=extra
            ),
            prediction_strategy="chain_of_thought"
        )

        atomizer = Atomizer(config=agent_config)

        # Verify that extra_body was passed to the LM kwargs
        assert hasattr(atomizer, "_lm")
        # DSPy LM stores kwargs internally - check if extra_body is in the kwargs
        lm_kwargs = atomizer._lm.kwargs
        assert "extra_body" in lm_kwargs
        assert lm_kwargs["extra_body"] == extra

    def test_extra_body_none_not_passed(self):
        """Test that None extra_body is not added to lm_kwargs."""
        agent_config = AgentConfig(
            llm=LLMConfig(
                model="gpt-4o",
                extra_body=None
            ),
            prediction_strategy="chain_of_thought"
        )

        atomizer = Atomizer(config=agent_config)

        # Verify that extra_body is not in kwargs when None
        lm_kwargs = atomizer._lm.kwargs
        assert "extra_body" not in lm_kwargs or lm_kwargs.get("extra_body") is None

    def test_multiple_extra_body_features(self):
        """Test that multiple OpenRouter features can be combined."""
        extra = {
            "plugins": ["web_search"],
            "web_search_options": {
                "search_context_size": 3,
                "search_recency_filter": "month"
            },
            "models": [
                "anthropic/claude-sonnet-4.5",
                "openai/gpt-4o"
            ],
            "route": "fallback",
            "provider": {
                "order": ["Anthropic", "OpenAI"],
                "data_collection": "deny"
            }
        }

        config = LLMConfig(
            model="openrouter/anthropic/claude-sonnet-4.5",
            extra_body=extra
        )

        assert config.extra_body == extra
