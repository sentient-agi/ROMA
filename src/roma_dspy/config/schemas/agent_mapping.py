"""Agent mapping configuration schema for task-aware agent selection."""

from pydantic.dataclasses import dataclass
from typing import Dict, Optional
from dataclasses import field

from roma_dspy.config.schemas.agents import AgentConfig


@dataclass
class AgentMappingConfig:
    """
    Maps (AgentType, TaskType) -> AgentConfig.

    Structure:
    - atomizers: {RETRIEVE: config, WRITE: config, ...}
    - planners: {RETRIEVE: config, WRITE: config, ...}
    - executors: {RETRIEVE: config, WRITE: config, ...}
    - aggregators: {RETRIEVE: config, default: config, ...}
    - verifiers: {RETRIEVE: config, ...}

    Default agents are used when task_type is None or not found in mapping.
    """

    # Task-specific agent configs (TaskType.value -> AgentConfig)
    atomizers: Dict[str, AgentConfig] = field(default_factory=dict)
    planners: Dict[str, AgentConfig] = field(default_factory=dict)
    executors: Dict[str, AgentConfig] = field(default_factory=dict)
    aggregators: Dict[str, AgentConfig] = field(default_factory=dict)
    verifiers: Dict[str, AgentConfig] = field(default_factory=dict)

    # Default agents (when task_type is None or not found)
    default_atomizer: Optional[AgentConfig] = None
    default_planner: Optional[AgentConfig] = None
    default_executor: Optional[AgentConfig] = None
    default_aggregator: Optional[AgentConfig] = None
    default_verifier: Optional[AgentConfig] = None
