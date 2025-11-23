"""Registry for agent instances with task-aware lookup."""

from typing import Optional, Dict, Tuple

from loguru import logger

from roma_dspy.core.modules import BaseModule
from roma_dspy.core.factory.agent_factory import AgentFactory
from roma_dspy.config.schemas.root import ROMAConfig
from roma_dspy.config.schemas.agent_mapping import AgentMappingConfig
from roma_dspy.config.schemas.agents import AgentConfig
from roma_dspy.types import AgentType, TaskType


class AgentRegistry:
    """
    Registry for agent instances with task-aware lookup.

    Storage: {(AgentType, TaskType): BaseModule}
    Lookup: (AgentType, TaskType) with fallback to (AgentType, None)
    """

    def __init__(self):
        # (agent_type, task_type) -> module instance
        self._registry: Dict[Tuple[AgentType, Optional[TaskType]], BaseModule] = {}

        # Statistics
        self._stats = {
            "registrations": 0,
            "lookups": 0,
            "fallbacks": 0,
            "cache_hits": 0,
        }

    def initialize_from_config(
        self, config: ROMAConfig, factory: Optional[AgentFactory] = None
    ) -> None:
        """
        Build entire registry from ROMAConfig.

        Process:
        1. For each agent_type (atomizer, planner, etc.)
        2. For each task_type mapping in agent_mapping
        3. Create agent via factory and register
        4. Register defaults for fallback

        Args:
            config: ROMAConfig with agent_mapping
            factory: AgentFactory instance (creates one if None)
        """
        if factory is None:
            factory = AgentFactory()

        agent_mapping = config.agent_mapping

        # Collect all errors during registration
        all_errors = []

        # Register task-specific agents
        all_errors.extend(
            self._register_agents_for_type(
                AgentType.ATOMIZER,
                agent_mapping.atomizers,
                agent_mapping.default_atomizer,
                factory,
            )
        )

        all_errors.extend(
            self._register_agents_for_type(
                AgentType.PLANNER,
                agent_mapping.planners,
                agent_mapping.default_planner,
                factory,
            )
        )

        all_errors.extend(
            self._register_agents_for_type(
                AgentType.EXECUTOR,
                agent_mapping.executors,
                agent_mapping.default_executor,
                factory,
            )
        )

        all_errors.extend(
            self._register_agents_for_type(
                AgentType.AGGREGATOR,
                agent_mapping.aggregators,
                agent_mapping.default_aggregator,
                factory,
            )
        )

        all_errors.extend(
            self._register_agents_for_type(
                AgentType.VERIFIER,
                agent_mapping.verifiers,
                agent_mapping.default_verifier,
                factory,
            )
        )

        # Report accumulated errors
        if all_errors:
            logger.warning(
                f"Registry initialization had {len(all_errors)} errors:\n"
                + "\n".join(f"  - {e}" for e in all_errors)
            )

        logger.info(
            f"Initialized registry with {len(self._registry)} agents. "
            f"Task-specific: {self._count_task_specific()}, "
            f"Defaults: {self._count_defaults()}"
        )

        # Validate that required default agents exist
        self._validate_required_agents()

    def _register_agents_for_type(
        self,
        agent_type: AgentType,
        task_configs: Dict[str, AgentConfig],
        default_config: Optional[AgentConfig],
        factory: AgentFactory,
    ) -> list[str]:
        """Register all agents for a specific agent type.

        Returns:
            List of error messages encountered during registration
        """
        errors = []

        # Register task-specific agents
        for task_type_str, agent_config in task_configs.items():
            if not agent_config.enabled:
                continue

            try:
                task_type = TaskType.from_string(task_type_str)
                agent = factory.create_agent(agent_type, agent_config, task_type)
                self.register_agent(agent_type, task_type, agent)
            except Exception as e:
                error_msg = f"{agent_type.value}/{task_type_str}: {str(e)}"
                logger.error(f"Failed to create {error_msg}")
                errors.append(error_msg)

        # Register default agent (fallback)
        if default_config and default_config.enabled:
            try:
                agent = factory.create_agent(agent_type, default_config, task_type=None)
                self.register_agent(agent_type, None, agent)
            except Exception as e:
                error_msg = f"default {agent_type.value}: {str(e)}"
                logger.error(f"Failed to create {error_msg}")
                errors.append(error_msg)

        return errors

    def register_agent(
        self, agent_type: AgentType, task_type: Optional[TaskType], module: BaseModule
    ) -> None:
        """
        Register agent in registry.

        Args:
            agent_type: Type of agent
            task_type: Task type (None for default)
            module: Configured module instance
        """
        key = (agent_type, task_type)

        if key in self._registry:
            logger.warning(
                f"Overwriting existing agent: {agent_type.value}, "
                f"task_type={task_type.value if task_type else 'default'}"
            )

        self._registry[key] = module
        self._stats["registrations"] += 1

        # DEBUG: Log instance ID for tracking
        instance_id = getattr(module, "_instance_id", "UNKNOWN")
        logger.debug(
            f"Registered {agent_type.value} instance #{instance_id} "
            f"(task_type={task_type.value if task_type else 'default'})"
        )

    def get_agent(
        self, agent_type: AgentType, task_type: Optional[TaskType] = None
    ) -> BaseModule:
        """
        Get agent with fallback logic.

        Lookup Order:
        1. Exact match: (agent_type, task_type)
        2. Fallback: (agent_type, None)
        3. Raise KeyError if not found

        Args:
            agent_type: Type of agent needed
            task_type: Task type (None for default)

        Returns:
            Configured agent instance

        Raises:
            KeyError: If no agent found for agent_type
        """
        self._stats["lookups"] += 1

        # Try exact match first
        key = (agent_type, task_type)
        if key in self._registry:
            self._stats["cache_hits"] += 1
            instance_id = getattr(self._registry[key], "_instance_id", "UNKNOWN")
            logger.debug(
                f"Registry hit: {agent_type.value} instance #{instance_id}, "
                f"task_type={task_type.value if task_type else 'default'}"
            )
            return self._registry[key]

        # Fall back to default
        default_key = (agent_type, None)
        if default_key in self._registry:
            self._stats["fallbacks"] += 1
            instance_id = getattr(
                self._registry[default_key], "_instance_id", "UNKNOWN"
            )
            logger.debug(
                f"Registry fallback: {agent_type.value} instance #{instance_id}, "
                f"requested={task_type.value if task_type else 'None'}, "
                f"using default"
            )
            return self._registry[default_key]

        # Not found
        raise KeyError(
            f"No agent registered for {agent_type.value} "
            f"(task_type={task_type.value if task_type else 'default'}). "
            f"Available: {list(self._registry.keys())}"
        )

    def iter_agents(self):
        """
        Iterate over all registered agents.

        Yields:
            Tuples of (AgentType, Optional[TaskType], BaseModule).

        Notes:
            - Provides a read-only view of the registry; modifications should still
              go through register_agent().
            - Ordering mirrors the underlying registration order (insertion-ordered dict).
        """
        for (agent_type, task_type), module in self._registry.items():
            yield agent_type, task_type, module

    def has_agent(
        self, agent_type: AgentType, task_type: Optional[TaskType] = None
    ) -> bool:
        """Check if agent exists (with fallback check)."""
        return (agent_type, task_type) in self._registry or (
            agent_type,
            None,
        ) in self._registry

    def _count_task_specific(self) -> int:
        """Count task-specific agents (not defaults)."""
        return sum(1 for _, task_type in self._registry.keys() if task_type is not None)

    def _count_defaults(self) -> int:
        """Count default agents."""
        return sum(1 for _, task_type in self._registry.keys() if task_type is None)

    def _validate_required_agents(self) -> None:
        """Validate that required default agents exist."""
        required = [
            AgentType.ATOMIZER,
            AgentType.PLANNER,
            AgentType.EXECUTOR,
            AgentType.AGGREGATOR,
        ]
        missing = [a for a in required if not self.has_agent(a, None)]
        if missing:
            raise ValueError(
                f"Registry initialization failed. Missing required default agents: "
                f"{[a.value for a in missing]}. Check your configuration and LLM settings."
            )

    def get_stats(self) -> Dict[str, int]:
        """Get registry statistics."""
        return {
            **self._stats,
            "total_agents": len(self._registry),
            "task_specific": self._count_task_specific(),
            "defaults": self._count_defaults(),
        }

    @classmethod
    def from_modules(
        cls,
        atomizer: Optional[BaseModule] = None,
        planner: Optional[BaseModule] = None,
        executor: Optional[BaseModule] = None,
        aggregator: Optional[BaseModule] = None,
        verifier: Optional[BaseModule] = None,
    ) -> "AgentRegistry":
        """
        Create registry from individual modules (legacy support).

        Registers all modules as defaults (task_type=None).
        """
        registry = cls()

        if atomizer:
            registry.register_agent(AgentType.ATOMIZER, None, atomizer)
        if planner:
            registry.register_agent(AgentType.PLANNER, None, planner)
        if executor:
            registry.register_agent(AgentType.EXECUTOR, None, executor)
        if aggregator:
            registry.register_agent(AgentType.AGGREGATOR, None, aggregator)
        if verifier:
            registry.register_agent(AgentType.VERIFIER, None, verifier)

        return registry
