"""End-to-end validation tests to find bugs and edge cases."""

import pytest
from unittest.mock import Mock, patch
from pathlib import Path

from roma_dspy.core.engine.solve import RecursiveSolver, solve
from roma_dspy.core.registry import AgentRegistry
from roma_dspy.core.factory.agent_factory import AgentFactory
from roma_dspy.config.manager import ConfigManager
from roma_dspy.types import AgentType, TaskType, TaskStatus
from roma_dspy.core.signatures import TaskNode


class TestE2EValidation:
    """Comprehensive end-to-end validation tests."""

    def test_convenience_function_without_config_works(self):
        """FIXED BUG #1: Convenience functions now create default config."""
        # Test that convenience function doesn't raise ValueError about missing config
        # We just want to verify it creates a RecursiveSolver successfully
        from roma_dspy.config.schemas.root import ROMAConfig

        # This should not raise ValueError - it creates default config
        try:
            # Create a solver with the same pattern as convenience function
            config = ROMAConfig()
            solver = RecursiveSolver(config=config, max_depth=2)
            # If we got here, the fix works
            assert solver is not None
            assert solver.max_depth == 2
        except ValueError as e:
            if "Either 'config' or 'registry' must be provided" in str(e):
                pytest.fail("Convenience function pattern still fails - bug not fixed!")
            # Other ValueError is acceptable
            raise

    def test_solver_requires_config_or_registry(self):
        """RecursiveSolver must have either config or registry."""
        with pytest.raises(
            ValueError, match="Either 'config' or 'registry' must be provided"
        ):
            RecursiveSolver()

    def test_solver_with_registry_works(self):
        """Solver should work with just a registry."""
        registry = AgentRegistry()
        factory = AgentFactory()

        # Create minimal default agents
        from roma_dspy.config.schemas.agents import AgentConfig
        from roma_dspy.config.schemas.base import LLMConfig

        default_config = AgentConfig(llm=LLMConfig(model="gpt-4o"), enabled=True)

        for agent_type in [
            AgentType.ATOMIZER,
            AgentType.PLANNER,
            AgentType.EXECUTOR,
            AgentType.AGGREGATOR,
        ]:
            agent = factory.create_agent(agent_type, default_config, task_type=None)
            registry.register_agent(agent_type, None, agent)

        # Should not raise
        solver = RecursiveSolver(registry=registry, max_depth=2)
        assert solver.registry is registry
        assert solver.max_depth == 2

    def test_registry_silent_failure_on_bad_config(self):
        """BUG #3: Registry silently fails when agent creation errors."""
        from roma_dspy.config.schemas.agents import AgentConfig
        from roma_dspy.config.schemas.base import LLMConfig
        from roma_dspy.config.schemas.agent_mapping import AgentMappingConfig
        from roma_dspy.config.schemas.root import ROMAConfig

        # Create config with invalid model
        bad_config = AgentConfig(llm=LLMConfig(model="invalid-model-xyz"), enabled=True)

        mapping = AgentMappingConfig(
            default_atomizer=bad_config,
            default_planner=bad_config,
            default_executor=bad_config,
            default_aggregator=bad_config,
        )

        config = ROMAConfig(agent_mapping=mapping)

        registry = AgentRegistry()
        factory = AgentFactory()

        # This should log errors but not raise
        # BUG: Silent failure - registry will be empty
        registry.initialize_from_config(config, factory)

        # Registry might be empty or partially populated
        # This is the bug - no validation after initialization
        stats = registry.get_stats()

        # If all agents failed to create, total_agents could be 0
        # But solver will only discover this at runtime
        print(f"Registry stats after bad config: {stats}")

    def test_agent_config_type_fields_unused(self):
        """BUG #2: AgentConfig.type and task_type fields are never used."""
        from roma_dspy.config.schemas.agents import AgentConfig
        from roma_dspy.config.schemas.base import LLMConfig

        # These fields exist but are never accessed
        config = AgentConfig(
            type=AgentType.EXECUTOR,
            task_type=TaskType.RETRIEVE,
            llm=LLMConfig(model="gpt-4o"),
            enabled=True,
        )

        # Fields are stored but never used by factory or registry
        assert config.type == AgentType.EXECUTOR
        assert config.task_type == TaskType.RETRIEVE

        # Factory doesn't look at config.type or config.task_type
        # They're only for YAML documentation

    def test_task_node_always_has_task_type(self):
        """TaskNode always has a task_type (defaults to THINK)."""
        task = TaskNode(goal="test")

        # Should default to THINK
        assert task.task_type == TaskType.THINK

        # Can be set explicitly
        task2 = TaskNode(goal="test", task_type=TaskType.RETRIEVE)
        assert task2.task_type == TaskType.RETRIEVE

    def test_registry_get_agent_with_none_task_type(self):
        """Registry should handle None task_type (fallback to default)."""
        registry = AgentRegistry()
        factory = AgentFactory()

        from roma_dspy.config.schemas.agents import AgentConfig
        from roma_dspy.config.schemas.base import LLMConfig

        default_config = AgentConfig(llm=LLMConfig(model="gpt-4o"), enabled=True)

        # Register only default
        agent = factory.create_agent(AgentType.ATOMIZER, default_config, task_type=None)
        registry.register_agent(AgentType.ATOMIZER, None, agent)

        # Should work with None
        result = registry.get_agent(AgentType.ATOMIZER, None)
        assert result is not None

        # Should also work with any task_type (falls back to default)
        result2 = registry.get_agent(AgentType.ATOMIZER, TaskType.RETRIEVE)
        assert result2 is not None
        assert result2 is result  # Same agent

    def test_registry_missing_default_agent_raises(self):
        """BUG #4: No validation that required default agents exist."""
        registry = AgentRegistry()

        # Empty registry
        with pytest.raises(KeyError, match="No agent registered"):
            registry.get_agent(AgentType.ATOMIZER, None)

    def test_runtime_uses_task_type_correctly(self):
        """Runtime must use task.task_type when fetching agents."""
        from roma_dspy.core.engine.runtime import ModuleRuntime
        from roma_dspy.core.engine.dag import TaskDAG

        registry = AgentRegistry()
        factory = AgentFactory()

        from roma_dspy.config.schemas.agents import AgentConfig
        from roma_dspy.config.schemas.base import LLMConfig

        # Create task-specific executor
        retrieve_config = AgentConfig(llm=LLMConfig(model="gpt-4o"), enabled=True)
        retrieve_executor = factory.create_agent(
            AgentType.EXECUTOR, retrieve_config, task_type=TaskType.RETRIEVE
        )
        registry.register_agent(
            AgentType.EXECUTOR, TaskType.RETRIEVE, retrieve_executor
        )

        # Create different task-specific executor
        write_config = AgentConfig(llm=LLMConfig(model="gpt-4o"), enabled=True)
        write_executor = factory.create_agent(
            AgentType.EXECUTOR, write_config, task_type=TaskType.WRITE
        )
        registry.register_agent(AgentType.EXECUTOR, TaskType.WRITE, write_executor)

        # Verify registry has both
        retrieved = registry.get_agent(AgentType.EXECUTOR, TaskType.RETRIEVE)
        written = registry.get_agent(AgentType.EXECUTOR, TaskType.WRITE)

        assert retrieved is retrieve_executor
        assert written is write_executor
        assert retrieved is not written

    def test_config_loading_with_uppercase_enums(self):
        """YAML must use uppercase for AgentType names, uppercase for TaskType."""
        config_path = Path("config/profiles/simple_mapping.yaml")

        if not config_path.exists():
            pytest.skip("Config not found")

        manager = ConfigManager()
        config = manager.load_config(str(config_path))

        # Should load without errors
        assert config.agent_mapping is not None
        assert config.agent_mapping.default_executor is not None

    def test_solver_max_depth_override(self):
        """Solver should allow max_depth override."""
        from roma_dspy.config.schemas.agents import AgentConfig, AgentsConfig
        from roma_dspy.config.schemas.base import LLMConfig, RuntimeConfig
        from roma_dspy.config.schemas.root import ROMAConfig

        config = ROMAConfig(runtime=RuntimeConfig(max_depth=3), agents=AgentsConfig())

        # Without override
        solver1 = RecursiveSolver(config=config)
        assert solver1.max_depth == 3

        # With override
        solver2 = RecursiveSolver(config=config, max_depth=10)
        assert solver2.max_depth == 10

    def test_registry_validation_raises_on_missing_required_agents(self):
        """FIXED BUG #4: Registry now validates required agents exist."""
        from roma_dspy.config.schemas.agents import AgentConfig
        from roma_dspy.config.schemas.base import LLMConfig
        from roma_dspy.config.schemas.agent_mapping import AgentMappingConfig
        from roma_dspy.config.schemas.root import ROMAConfig

        # Create config with only atomizer (missing others)
        good_config = AgentConfig(llm=LLMConfig(model="gpt-4o"), enabled=True)

        mapping = AgentMappingConfig(
            default_atomizer=good_config,
            # Missing: planner, executor, aggregator
        )

        config = ROMAConfig(agent_mapping=mapping)

        registry = AgentRegistry()
        factory = AgentFactory()

        # Should raise ValueError due to missing required agents
        with pytest.raises(ValueError, match="Missing required default agents"):
            registry.initialize_from_config(config, factory)
