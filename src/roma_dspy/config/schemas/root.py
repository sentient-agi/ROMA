"""Root configuration schema for ROMA-DSPy."""

import os
from pydantic.dataclasses import dataclass
from pydantic import field_validator, model_validator, TypeAdapter
import warnings
from typing import Optional, Dict, Any

from roma_dspy.config.schemas.base import RuntimeConfig
from roma_dspy.config.schemas.agents import AgentsConfig
from roma_dspy.config.schemas.resilience import ResilienceConfig
from roma_dspy.config.schemas.agent_mapping import AgentMappingConfig
from roma_dspy.config.schemas.storage import StorageConfig
from roma_dspy.config.schemas.observability import ObservabilityConfig
from roma_dspy.config.schemas.logging import LoggingConfig


@dataclass
class ROMAConfig:
    """Complete ROMA-DSPy configuration."""

    # Project metadata
    project: str = "roma-dspy"
    version: str = "0.1.0"
    environment: str = "development"
    metadata: Optional[Dict[str, Any]] = None  # Runtime metadata (profile_name, etc.)

    # Core configurations
    agents: Optional[AgentsConfig] = None
    agent_mapping: Optional[AgentMappingConfig] = None  # Task-aware agent mapping
    resilience: Optional[ResilienceConfig] = None
    runtime: Optional[RuntimeConfig] = None
    storage: Optional[StorageConfig] = None  # Storage configuration
    observability: Optional[ObservabilityConfig] = None  # Observability configuration
    logging: Optional[LoggingConfig] = None  # Logging configuration

    def __post_init__(self):
        """Initialize nested configs with defaults if not provided."""
        if self.agents is None:
            self.agents = AgentsConfig()

        # NEW: If agent_mapping not provided, create default from agents
        if self.agent_mapping is None:
            self.agent_mapping = AgentMappingConfig(
                default_atomizer=self.agents.atomizer,
                default_planner=self.agents.planner,
                default_executor=self.agents.executor,
                default_aggregator=self.agents.aggregator,
                default_verifier=self.agents.verifier
            )
        else:
            # If agent_mapping provided but defaults are None, populate from agents
            if self.agent_mapping.default_atomizer is None:
                self.agent_mapping.default_atomizer = self.agents.atomizer
            if self.agent_mapping.default_planner is None:
                self.agent_mapping.default_planner = self.agents.planner
            if self.agent_mapping.default_executor is None:
                self.agent_mapping.default_executor = self.agents.executor
            if self.agent_mapping.default_aggregator is None:
                self.agent_mapping.default_aggregator = self.agents.aggregator
            if self.agent_mapping.default_verifier is None:
                self.agent_mapping.default_verifier = self.agents.verifier

        if self.resilience is None:
            self.resilience = ResilienceConfig()
        if self.runtime is None:
            self.runtime = RuntimeConfig()
        if self.storage is None:
            # Get base_path from environment or use default
            base_path = os.getenv("STORAGE_BASE_PATH", "~/.tmp/sentient")
            self.storage = StorageConfig(base_path=base_path)
        if self.observability is None:
            self.observability = ObservabilityConfig()
        if self.logging is None:
            self.logging = LoggingConfig()

    @field_validator("environment")
    @classmethod
    def validate_environment(cls, v: str) -> str:
        """Validate environment is one of the allowed values."""
        allowed_environments = {"development", "testing", "production"}
        if v not in allowed_environments:
            raise ValueError(f"Environment must be one of {allowed_environments}, got: {v}")
        return v

    @model_validator(mode="after")
    def validate_global_consistency(self):
        """Validate global configuration consistency."""
        # Check model consistency across agents
        models = [
            self.agents.atomizer.llm.model,
            self.agents.planner.llm.model,
            self.agents.executor.llm.model,
            self.agents.aggregator.llm.model,
            self.agents.verifier.llm.model
        ]

        # Group models by actual provider (accounting for proxies like OpenRouter)
        openrouter_models = [m for m in models if m.startswith("openrouter/")]
        openai_models = [m for m in models if not m.startswith("openrouter/") and "gpt" in m.lower()]
        anthropic_models = [m for m in models if not m.startswith("openrouter/") and "claude" in m.lower()]
        other_models = [
            m for m in models
            if not m.startswith("openrouter/")
            and "gpt" not in m.lower()
            and "claude" not in m.lower()
        ]

        # Warn about mixed providers (not an error, just a warning)
        provider_count = sum([
            1 if openrouter_models else 0,
            1 if openai_models else 0,
            1 if anthropic_models else 0,
            1 if other_models else 0
        ])

        if provider_count > 1:
            warnings.warn(
                "Mixed model providers detected. Ensure API keys are configured correctly. "
                f"OpenRouter models: {openrouter_models}, OpenAI models: {openai_models}, "
                f"Anthropic models: {anthropic_models}, Other models: {other_models}",
                UserWarning
            )

        # Validate timeout consistency
        agent_timeouts = [
            self.agents.atomizer.llm.timeout,
            self.agents.planner.llm.timeout,
            self.agents.executor.llm.timeout,
            self.agents.aggregator.llm.timeout,
            self.agents.verifier.llm.timeout
        ]

        max_agent_timeout = max(agent_timeouts)
        if self.runtime.timeout < max_agent_timeout:
            raise ValueError(
                f"Runtime timeout ({self.runtime.timeout}s) is less than maximum "
                f"agent timeout ({max_agent_timeout}s). This may cause premature timeouts."
            )

        return self

    def to_dict(self) -> Dict[str, Any]:
        """
        Serialize configuration to JSON-compatible dictionary.

        Uses Pydantic v2's TypeAdapter for proper serialization of nested
        dataclasses, handling all complex types recursively. Converts all
        values to JSON-compatible types (Path -> str, etc.).

        Returns:
            Dict[str, Any]: JSON-serializable dictionary

        Example:
            >>> config = ConfigManager().load_config("crypto_agent")
            >>> config_dict = config.to_dict()
            >>> # Can now be used with json.dumps, PostgreSQL JSONB, etc.
        """
        adapter = TypeAdapter(ROMAConfig)
        return adapter.dump_python(self, mode='json')