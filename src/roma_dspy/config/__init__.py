"""Configuration system for ROMA-DSPy using OmegaConf and Pydantic."""

from pathlib import Path
from typing import Optional, List

from .schemas.root import ROMAConfig
from .schemas.agents import AgentConfig, AgentsConfig
from .schemas.base import LLMConfig, RuntimeConfig
from .schemas.resilience import ResilienceConfig
from .manager import ConfigManager


def load_config(
    config_path: Optional[str] = None,
    profile: Optional[str] = None,
    overrides: Optional[List[str]] = None,
    env_prefix: str = "ROMA_",
) -> ROMAConfig:
    """
    Convenience function to load configuration.

    Args:
        config_path: Path to YAML configuration file
        profile: Profile name to apply
        overrides: List of configuration overrides (e.g., ["agents.executor.llm.temperature=0.9"])
        env_prefix: Prefix for environment variables (default: "ROMA_")

    Returns:
        Validated ROMAConfig instance

    Examples:
        # Use all defaults
        config = load_config()

        # With profile
        config = load_config(profile="lightweight")

        # With overrides
        config = load_config(
            profile="tool_enabled",
            overrides=["agents.executor.llm.temperature=0.9"]
        )

        # Environment variables (ROMA_AGENTS__EXECUTOR__LLM__MODEL=gpt-4o)
        config = load_config()
    """
    manager = ConfigManager()
    return manager.load_config(
        Path(config_path) if config_path else None, profile, overrides, env_prefix
    )


__all__ = [
    # Main configuration classes
    "ROMAConfig",
    "AgentConfig",
    "AgentsConfig",
    "LLMConfig",
    "RuntimeConfig",
    "ResilienceConfig",
    # Configuration management
    "ConfigManager",
    "load_config",
]
