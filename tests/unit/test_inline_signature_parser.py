"""Tests for DSPy inline signature parsing."""

import pytest
import dspy


class TestInlineSignatureParser:
    """Test inline signature string parsing."""

    def test_parse_simple_signature(self):
        """Parse basic 'input -> output' format."""
        from roma_dspy.core.factory.agent_factory import AgentFactory

        sig = AgentFactory._parse_inline_signature("goal -> output")

        assert issubclass(sig, dspy.Signature)
        # Verify fields exist in model_fields
        assert "goal" in sig.model_fields
        assert "output" in sig.model_fields

    def test_parse_typed_signature(self):
        """Parse signature with type annotations."""
        from roma_dspy.core.factory.agent_factory import AgentFactory

        sig = AgentFactory._parse_inline_signature(
            "goal: str -> is_atomic: bool, node_type: str"
        )

        assert issubclass(sig, dspy.Signature)
        assert "goal" in sig.model_fields
        assert "is_atomic" in sig.model_fields
        assert "node_type" in sig.model_fields

    def test_parse_signature_with_instructions(self):
        """Parse signature with custom instructions."""
        from roma_dspy.core.factory.agent_factory import AgentFactory

        sig = AgentFactory._parse_inline_signature(
            "goal -> output", instructions="Custom instructions for this signature"
        )

        assert issubclass(sig, dspy.Signature)
        assert sig.__doc__ == "Custom instructions for this signature"

    def test_parse_complex_signature(self):
        """Parse signature with multiple inputs and outputs."""
        from roma_dspy.core.factory.agent_factory import AgentFactory

        sig = AgentFactory._parse_inline_signature(
            "goal: str, context: str -> output: str, sources: list[str], confidence: float"
        )

        assert issubclass(sig, dspy.Signature)
        assert "goal" in sig.model_fields
        assert "context" in sig.model_fields
        assert "output" in sig.model_fields
        assert "sources" in sig.model_fields
        assert "confidence" in sig.model_fields

    def test_parse_invalid_signature_no_arrow(self):
        """Fail on signature without arrow."""
        from roma_dspy.core.factory.agent_factory import AgentFactory

        with pytest.raises(ValueError, match="Must contain '->'"):
            AgentFactory._parse_inline_signature("goal output")

    def test_parse_empty_signature(self):
        """Fail on empty signature."""
        from roma_dspy.core.factory.agent_factory import AgentFactory

        with pytest.raises(ValueError):
            AgentFactory._parse_inline_signature("")

    def test_parse_none_signature(self):
        """Fail on None signature."""
        from roma_dspy.core.factory.agent_factory import AgentFactory

        with pytest.raises((ValueError, TypeError, AttributeError)):
            AgentFactory._parse_inline_signature(None)


class TestSignatureFallback:
    """Test signature fallback mechanism."""

    def test_fallback_on_invalid_signature(self):
        """Use default signature when custom is invalid."""
        from roma_dspy.core.factory.agent_factory import AgentFactory
        from roma_dspy.config.schemas.agents import AgentConfig
        from roma_dspy.config.schemas.base import LLMConfig
        from roma_dspy.types import AgentType
        from roma_dspy.core.signatures import AtomizerSignature

        config = AgentConfig(
            llm=LLMConfig(model="gpt-4o"),
            signature="invalid without arrow",  # Malformed
        )

        factory = AgentFactory()
        signature = factory._resolve_signature(AgentType.ATOMIZER, config, None)

        # Should fall back to default
        assert signature == AtomizerSignature

    def test_fallback_on_empty_signature(self):
        """Use default signature when custom is empty."""
        from roma_dspy.core.factory.agent_factory import AgentFactory
        from roma_dspy.config.schemas.agents import AgentConfig
        from roma_dspy.config.schemas.base import LLMConfig
        from roma_dspy.types import AgentType
        from roma_dspy.core.signatures import ExecutorSignature

        config = AgentConfig(
            llm=LLMConfig(model="gpt-4o"),
            signature="",  # Empty
        )

        factory = AgentFactory()
        signature = factory._resolve_signature(AgentType.EXECUTOR, config, None)

        # Should fall back to default
        assert signature == ExecutorSignature

    def test_fallback_on_none_signature(self):
        """Use default signature when custom is None."""
        from roma_dspy.core.factory.agent_factory import AgentFactory
        from roma_dspy.config.schemas.agents import AgentConfig
        from roma_dspy.config.schemas.base import LLMConfig
        from roma_dspy.types import AgentType
        from roma_dspy.core.signatures import PlannerSignature

        config = AgentConfig(llm=LLMConfig(model="gpt-4o"), signature=None)

        factory = AgentFactory()
        signature = factory._resolve_signature(AgentType.PLANNER, config, None)

        # Should use default
        assert signature == PlannerSignature

    def test_use_custom_valid_signature(self):
        """Use custom signature when valid."""
        from roma_dspy.core.factory.agent_factory import AgentFactory
        from roma_dspy.config.schemas.agents import AgentConfig
        from roma_dspy.config.schemas.base import LLMConfig
        from roma_dspy.types import AgentType
        from roma_dspy.core.signatures import ExecutorSignature

        config = AgentConfig(
            llm=LLMConfig(model="gpt-4o"),
            signature="goal: str -> result: str, confidence: float",
        )

        factory = AgentFactory()
        signature = factory._resolve_signature(AgentType.EXECUTOR, config, None)

        # Should NOT be default
        assert signature != ExecutorSignature
        # Should be a valid dspy.Signature
        assert issubclass(signature, dspy.Signature)
