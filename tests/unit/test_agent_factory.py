"""Tests for AgentFactory agent creation."""

import pytest
from roma_dspy.config.schemas.agents import AgentConfig
from roma_dspy.config.schemas.base import LLMConfig
from roma_dspy.types import AgentType, TaskType


class TestAgentFactoryCreation:
    """Test agent instance creation."""

    def test_create_atomizer_default_signature(self):
        """Create atomizer with default signature."""
        from roma_dspy.core.factory.agent_factory import AgentFactory
        from roma_dspy.core.modules import Atomizer

        config = AgentConfig(llm=LLMConfig(model="gpt-4o", temperature=0.1))

        factory = AgentFactory()
        agent = factory.create_agent(AgentType.ATOMIZER, config)

        assert isinstance(agent, Atomizer)
        assert agent.signature == AgentFactory.DEFAULT_SIGNATURES[AgentType.ATOMIZER]

    def test_create_executor_custom_signature(self):
        """Create executor with custom signature."""
        from roma_dspy.core.factory.agent_factory import AgentFactory
        from roma_dspy.core.modules import Executor

        config = AgentConfig(
            llm=LLMConfig(model="gpt-4o"),
            signature="goal: str -> output: str, sources: list[str]",
        )

        factory = AgentFactory()
        agent = factory.create_agent(AgentType.EXECUTOR, config, TaskType.RETRIEVE)

        assert isinstance(agent, Executor)
        # Should have custom signature
        assert agent.signature != AgentFactory.DEFAULT_SIGNATURES[AgentType.EXECUTOR]

    def test_create_planner_with_instructions(self):
        """Create planner with signature instructions."""
        from roma_dspy.core.factory.agent_factory import AgentFactory
        from roma_dspy.core.modules import Planner

        config = AgentConfig(
            llm=LLMConfig(model="gpt-4o"),
            signature="goal -> subtasks: list[str]",
            signature_instructions="Break down complex goals into subtasks",
        )

        factory = AgentFactory()
        agent = factory.create_agent(AgentType.PLANNER, config)

        assert isinstance(agent, Planner)
        assert agent.signature.__doc__ == "Break down complex goals into subtasks"

    def test_create_aggregator(self):
        """Create aggregator agent."""
        from roma_dspy.core.factory.agent_factory import AgentFactory
        from roma_dspy.core.modules import Aggregator

        config = AgentConfig(llm=LLMConfig(model="gpt-4o", temperature=0.2))

        factory = AgentFactory()
        agent = factory.create_agent(AgentType.AGGREGATOR, config)

        assert isinstance(agent, Aggregator)

    def test_create_verifier(self):
        """Create verifier agent."""
        from roma_dspy.core.factory.agent_factory import AgentFactory
        from roma_dspy.core.modules import Verifier

        config = AgentConfig(llm=LLMConfig(model="gpt-4o", temperature=0.0))

        factory = AgentFactory()
        agent = factory.create_agent(AgentType.VERIFIER, config)

        assert isinstance(agent, Verifier)

    def test_create_agent_invalid_type(self):
        """Fail on invalid agent type."""
        from roma_dspy.core.factory.agent_factory import AgentFactory

        config = AgentConfig(llm=LLMConfig(model="gpt-4o"))

        factory = AgentFactory()

        with pytest.raises(ValueError, match="Unknown agent type"):
            factory.create_agent("INVALID_TYPE", config)

    def test_get_default_signature(self):
        """Get default signatures for all agent types."""
        from roma_dspy.core.factory.agent_factory import AgentFactory
        from roma_dspy.core.signatures import (
            AtomizerSignature,
            PlannerSignature,
            ExecutorSignature,
            AggregatorResult,
            VerifierSignature,
        )

        assert (
            AgentFactory.get_default_signature(AgentType.ATOMIZER) == AtomizerSignature
        )
        assert AgentFactory.get_default_signature(AgentType.PLANNER) == PlannerSignature
        assert (
            AgentFactory.get_default_signature(AgentType.EXECUTOR) == ExecutorSignature
        )
        assert (
            AgentFactory.get_default_signature(AgentType.AGGREGATOR) == AggregatorResult
        )
        assert (
            AgentFactory.get_default_signature(AgentType.VERIFIER) == VerifierSignature
        )
