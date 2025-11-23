"""Tests for AgentRegistry storage and lookup."""

import pytest
from roma_dspy.types import AgentType, TaskType


class TestAgentRegistryBasics:
    """Test basic registry operations."""

    def test_registry_initialization(self):
        """Initialize empty registry."""
        from roma_dspy.core.registry.agent_registry import AgentRegistry

        registry = AgentRegistry()

        assert len(registry._registry) == 0
        assert registry.get_stats()["total_agents"] == 0

    def test_register_agent(self):
        """Register single agent."""
        from roma_dspy.core.registry.agent_registry import AgentRegistry
        from roma_dspy.core.factory.agent_factory import AgentFactory
        from roma_dspy.config.schemas.agents import AgentConfig
        from roma_dspy.config.schemas.base import LLMConfig

        registry = AgentRegistry()
        factory = AgentFactory()

        config = AgentConfig(llm=LLMConfig(model="gpt-4o"))
        agent = factory.create_agent(AgentType.ATOMIZER, config)

        registry.register_agent(AgentType.ATOMIZER, None, agent)

        assert len(registry._registry) == 1
        assert registry.has_agent(AgentType.ATOMIZER)

    def test_register_multiple_agents(self):
        """Register multiple agents for different types."""
        from roma_dspy.core.registry.agent_registry import AgentRegistry
        from roma_dspy.core.factory.agent_factory import AgentFactory
        from roma_dspy.config.schemas.agents import AgentConfig
        from roma_dspy.config.schemas.base import LLMConfig

        registry = AgentRegistry()
        factory = AgentFactory()

        config = AgentConfig(llm=LLMConfig(model="gpt-4o"))

        atomizer = factory.create_agent(AgentType.ATOMIZER, config)
        executor = factory.create_agent(AgentType.EXECUTOR, config)

        registry.register_agent(AgentType.ATOMIZER, None, atomizer)
        registry.register_agent(AgentType.EXECUTOR, TaskType.RETRIEVE, executor)

        assert len(registry._registry) == 2
        assert registry.has_agent(AgentType.ATOMIZER)
        assert registry.has_agent(AgentType.EXECUTOR, TaskType.RETRIEVE)


class TestAgentRegistryLookup:
    """Test agent lookup with fallback."""

    def test_get_exact_match(self):
        """Get agent with exact (agent_type, task_type) match."""
        from roma_dspy.core.registry.agent_registry import AgentRegistry
        from roma_dspy.core.factory.agent_factory import AgentFactory
        from roma_dspy.config.schemas.agents import AgentConfig
        from roma_dspy.config.schemas.base import LLMConfig

        registry = AgentRegistry()
        factory = AgentFactory()

        config = AgentConfig(llm=LLMConfig(model="gpt-4o"))
        executor = factory.create_agent(AgentType.EXECUTOR, config, TaskType.RETRIEVE)

        registry.register_agent(AgentType.EXECUTOR, TaskType.RETRIEVE, executor)

        retrieved = registry.get_agent(AgentType.EXECUTOR, TaskType.RETRIEVE)

        assert retrieved is executor

    def test_get_with_fallback(self):
        """Get default agent when task-specific not found."""
        from roma_dspy.core.registry.agent_registry import AgentRegistry
        from roma_dspy.core.factory.agent_factory import AgentFactory
        from roma_dspy.config.schemas.agents import AgentConfig
        from roma_dspy.config.schemas.base import LLMConfig

        registry = AgentRegistry()
        factory = AgentFactory()

        config = AgentConfig(llm=LLMConfig(model="gpt-4o"))
        default_executor = factory.create_agent(AgentType.EXECUTOR, config)

        # Register only default
        registry.register_agent(AgentType.EXECUTOR, None, default_executor)

        # Request task-specific, should fall back to default
        retrieved = registry.get_agent(AgentType.EXECUTOR, TaskType.WRITE)

        assert retrieved is default_executor
        assert registry.get_stats()["fallbacks"] == 1

    def test_get_prefers_exact_over_default(self):
        """Prefer task-specific over default."""
        from roma_dspy.core.registry.agent_registry import AgentRegistry
        from roma_dspy.core.factory.agent_factory import AgentFactory
        from roma_dspy.config.schemas.agents import AgentConfig
        from roma_dspy.config.schemas.base import LLMConfig

        registry = AgentRegistry()
        factory = AgentFactory()

        default_config = AgentConfig(llm=LLMConfig(model="gpt-4o-mini"))
        retrieve_config = AgentConfig(llm=LLMConfig(model="gpt-4o"))

        default_executor = factory.create_agent(AgentType.EXECUTOR, default_config)
        retrieve_executor = factory.create_agent(
            AgentType.EXECUTOR, retrieve_config, TaskType.RETRIEVE
        )

        registry.register_agent(AgentType.EXECUTOR, None, default_executor)
        registry.register_agent(
            AgentType.EXECUTOR, TaskType.RETRIEVE, retrieve_executor
        )

        # Should get task-specific
        retrieved = registry.get_agent(AgentType.EXECUTOR, TaskType.RETRIEVE)
        assert retrieved is retrieve_executor

        # Should get default for other tasks
        retrieved_write = registry.get_agent(AgentType.EXECUTOR, TaskType.WRITE)
        assert retrieved_write is default_executor

    def test_get_agent_not_found(self):
        """Raise KeyError when agent not registered."""
        from roma_dspy.core.registry.agent_registry import AgentRegistry

        registry = AgentRegistry()

        with pytest.raises(KeyError, match="No agent registered"):
            registry.get_agent(AgentType.EXECUTOR, TaskType.RETRIEVE)

    def test_has_agent_exact(self):
        """Check agent existence - exact match."""
        from roma_dspy.core.registry.agent_registry import AgentRegistry
        from roma_dspy.core.factory.agent_factory import AgentFactory
        from roma_dspy.config.schemas.agents import AgentConfig
        from roma_dspy.config.schemas.base import LLMConfig

        registry = AgentRegistry()
        factory = AgentFactory()

        config = AgentConfig(llm=LLMConfig(model="gpt-4o"))
        executor = factory.create_agent(AgentType.EXECUTOR, config, TaskType.RETRIEVE)

        registry.register_agent(AgentType.EXECUTOR, TaskType.RETRIEVE, executor)

        assert registry.has_agent(AgentType.EXECUTOR, TaskType.RETRIEVE)
        assert not registry.has_agent(AgentType.EXECUTOR, TaskType.WRITE)

    def test_has_agent_with_fallback(self):
        """Check agent existence - with default fallback."""
        from roma_dspy.core.registry.agent_registry import AgentRegistry
        from roma_dspy.core.factory.agent_factory import AgentFactory
        from roma_dspy.config.schemas.agents import AgentConfig
        from roma_dspy.config.schemas.base import LLMConfig

        registry = AgentRegistry()
        factory = AgentFactory()

        config = AgentConfig(llm=LLMConfig(model="gpt-4o"))
        executor = factory.create_agent(AgentType.EXECUTOR, config)

        registry.register_agent(AgentType.EXECUTOR, None, executor)

        # Has default, so any task_type should return True
        assert registry.has_agent(AgentType.EXECUTOR, TaskType.RETRIEVE)
        assert registry.has_agent(AgentType.EXECUTOR, TaskType.WRITE)
        assert registry.has_agent(AgentType.EXECUTOR, None)


class TestAgentRegistryFromConfig:
    """Test registry initialization from ROMAConfig."""

    def test_initialize_from_config_minimal(self):
        """Initialize with minimal config (defaults only)."""
        from roma_dspy.core.registry.agent_registry import AgentRegistry
        from roma_dspy.config.schemas.root import ROMAConfig

        config = ROMAConfig()  # Uses default AgentsConfig

        registry = AgentRegistry()
        registry.initialize_from_config(config)

        # Should have default agents registered
        assert registry.has_agent(AgentType.ATOMIZER)
        assert registry.has_agent(AgentType.PLANNER)
        assert registry.has_agent(AgentType.EXECUTOR)
        assert registry.has_agent(AgentType.AGGREGATOR)

    def test_initialize_from_config_with_mapping(self):
        """Initialize with agent_mapping (task-specific configs)."""
        from roma_dspy.core.registry.agent_registry import AgentRegistry
        from roma_dspy.config.schemas.root import ROMAConfig
        from roma_dspy.config.schemas.agent_mapping import AgentMappingConfig
        from roma_dspy.config.schemas.agents import AgentConfig
        from roma_dspy.config.schemas.base import LLMConfig

        # Create default configs for all required agents
        default_config = AgentConfig(llm=LLMConfig(model="gpt-4o"))

        agent_mapping = AgentMappingConfig(
            executors={
                "RETRIEVE": AgentConfig(
                    llm=LLMConfig(model="gpt-4o", temperature=0.3),
                    signature="goal: str -> output: str, sources: list[str]",
                ),
                "WRITE": AgentConfig(
                    llm=LLMConfig(model="claude-3-5-sonnet-20241022", temperature=0.7)
                ),
            },
            default_executor=AgentConfig(llm=LLMConfig(model="gpt-4o-mini")),
            # Add required default agents
            default_atomizer=default_config,
            default_planner=default_config,
            default_aggregator=default_config,
        )

        config = ROMAConfig(agent_mapping=agent_mapping)

        registry = AgentRegistry()
        registry.initialize_from_config(config)

        # Should have task-specific executors
        assert registry.has_agent(AgentType.EXECUTOR, TaskType.RETRIEVE)
        assert registry.has_agent(AgentType.EXECUTOR, TaskType.WRITE)

        # Should have default fallback
        assert registry.has_agent(AgentType.EXECUTOR, TaskType.THINK)

        stats = registry.get_stats()
        assert stats["task_specific"] >= 2  # RETRIEVE and WRITE
        assert stats["defaults"] >= 1  # default_executor


class TestAgentRegistryStats:
    """Test registry statistics."""

    def test_stats_initial(self):
        """Check initial stats."""
        from roma_dspy.core.registry.agent_registry import AgentRegistry

        registry = AgentRegistry()

        stats = registry.get_stats()

        assert stats["registrations"] == 0
        assert stats["lookups"] == 0
        assert stats["fallbacks"] == 0
        assert stats["cache_hits"] == 0
        assert stats["total_agents"] == 0
        assert stats["task_specific"] == 0
        assert stats["defaults"] == 0

    def test_stats_after_operations(self):
        """Track stats after operations."""
        from roma_dspy.core.registry.agent_registry import AgentRegistry
        from roma_dspy.core.factory.agent_factory import AgentFactory
        from roma_dspy.config.schemas.agents import AgentConfig
        from roma_dspy.config.schemas.base import LLMConfig

        registry = AgentRegistry()
        factory = AgentFactory()

        config = AgentConfig(llm=LLMConfig(model="gpt-4o"))

        # Register agents
        executor_retrieve = factory.create_agent(
            AgentType.EXECUTOR, config, TaskType.RETRIEVE
        )
        executor_default = factory.create_agent(AgentType.EXECUTOR, config)

        registry.register_agent(
            AgentType.EXECUTOR, TaskType.RETRIEVE, executor_retrieve
        )
        registry.register_agent(AgentType.EXECUTOR, None, executor_default)

        # Perform lookups
        registry.get_agent(AgentType.EXECUTOR, TaskType.RETRIEVE)  # Cache hit
        registry.get_agent(AgentType.EXECUTOR, TaskType.WRITE)  # Fallback

        stats = registry.get_stats()

        assert stats["registrations"] == 2
        assert stats["lookups"] == 2
        assert stats["cache_hits"] == 1
        assert stats["fallbacks"] == 1
        assert stats["total_agents"] == 2
        assert stats["task_specific"] == 1
        assert stats["defaults"] == 1


class TestAgentRegistryFromModules:
    """Test legacy module-based initialization."""

    def test_from_modules_legacy_support(self):
        """Create registry from individual modules (backward compatibility)."""
        from roma_dspy.core.registry.agent_registry import AgentRegistry
        from roma_dspy.core.factory.agent_factory import AgentFactory
        from roma_dspy.config.schemas.agents import AgentConfig
        from roma_dspy.config.schemas.base import LLMConfig

        factory = AgentFactory()

        config = AgentConfig(llm=LLMConfig(model="gpt-4o"))

        atomizer = factory.create_agent(AgentType.ATOMIZER, config)
        executor = factory.create_agent(AgentType.EXECUTOR, config)

        registry = AgentRegistry.from_modules(atomizer=atomizer, executor=executor)

        assert registry.has_agent(AgentType.ATOMIZER)
        assert registry.has_agent(AgentType.EXECUTOR)
        assert len(registry._registry) == 2

        # All should be defaults (task_type=None)
        assert registry.get_stats()["defaults"] == 2
        assert registry.get_stats()["task_specific"] == 0
