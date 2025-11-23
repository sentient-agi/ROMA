"""Tests for the configuration system."""

import pytest
import tempfile
from pathlib import Path
from omegaconf import OmegaConf
import os

from roma_dspy.config import (
    load_config,
    ConfigManager,
    ROMAConfig,
    AgentConfig,
    AgentsConfig,
    LLMConfig,
    RuntimeConfig,
    ResilienceConfig,
)


class TestLLMConfig:
    """Test LLMConfig validation."""

    def test_default_values(self):
        """Test default LLM configuration values."""
        config = LLMConfig()
        assert config.model == "gpt-4o-mini"
        assert config.temperature == 0.7
        assert config.max_tokens == 2000
        assert config.timeout == 30
        assert config.api_key is None
        assert config.base_url is None

    def test_valid_values(self):
        """Test valid LLM configuration values."""
        config = LLMConfig(
            model="gpt-4o",
            temperature=0.5,
            max_tokens=1000,
            timeout=60,
            api_key="test-key",
            base_url="https://api.openai.com",
        )
        assert config.model == "gpt-4o"
        assert config.temperature == 0.5
        assert config.max_tokens == 1000
        assert config.timeout == 60
        assert config.api_key == "test-key"
        assert config.base_url == "https://api.openai.com"

    def test_temperature_validation(self):
        """Test temperature validation."""
        # Valid range
        LLMConfig(temperature=0.0)
        LLMConfig(temperature=1.0)
        LLMConfig(temperature=2.0)

        # Invalid range
        with pytest.raises(ValueError):
            LLMConfig(temperature=-0.1)
        with pytest.raises(ValueError):
            LLMConfig(temperature=2.1)

    def test_max_tokens_validation(self):
        """Test max_tokens validation."""
        # Valid values
        LLMConfig(max_tokens=1)
        LLMConfig(max_tokens=100000)

        # Invalid values
        with pytest.raises(ValueError):
            LLMConfig(max_tokens=0)
        with pytest.raises(ValueError):
            LLMConfig(max_tokens=100001)

    def test_empty_model_validation(self):
        """Test empty model validation."""
        with pytest.raises(ValueError, match="Model name cannot be empty"):
            LLMConfig(model="")
        with pytest.raises(ValueError, match="Model name cannot be empty"):
            LLMConfig(model="   ")


class TestAgentConfig:
    """Test AgentConfig validation."""

    def test_default_values(self):
        """Test default agent configuration values."""
        config = AgentConfig()
        assert isinstance(config.llm, LLMConfig)
        assert config.prediction_strategy == "chain_of_thought"
        assert config.toolkits == []
        assert config.enabled is True
        assert config.agent_config == {}
        assert config.strategy_config == {}

    def test_valid_prediction_strategies(self):
        """Test valid prediction strategies."""
        valid_strategies = ["chain_of_thought", "react", "code_act", "predict"]
        for strategy in valid_strategies:
            config = AgentConfig(prediction_strategy=strategy)
            assert config.prediction_strategy == strategy

    def test_invalid_prediction_strategy(self):
        """Test invalid prediction strategy."""
        with pytest.raises(ValueError, match="Invalid prediction strategy"):
            AgentConfig(prediction_strategy="invalid_strategy")

    def test_valid_tools(self):
        """Test valid toolkits configuration."""
        from roma_dspy.config.schemas.toolkit import ToolkitConfig

        toolkit = ToolkitConfig(class_name="CalculatorToolkit", enabled=True)
        config = AgentConfig(toolkits=[toolkit])
        assert len(config.toolkits) == 1
        assert config.toolkits[0].class_name == "CalculatorToolkit"

    def test_invalid_tools(self):
        """Test invalid toolkits configuration."""
        from roma_dspy.config.schemas.toolkit import ToolkitConfig

        # This test now validates at toolkit manager level, not config level
        # Empty class name should fail
        with pytest.raises(ValueError):
            ToolkitConfig(class_name="")

    def test_tool_strategy_compatibility(self):
        """Test that toolkits work with compatible strategies."""
        from roma_dspy.config.schemas.toolkit import ToolkitConfig

        toolkit = ToolkitConfig(class_name="CalculatorToolkit", enabled=True)

        # Should work with react
        AgentConfig(prediction_strategy="react", toolkits=[toolkit])

        # Should work with code_act
        AgentConfig(prediction_strategy="code_act", toolkits=[toolkit])


class TestAgentsConfig:
    """Test AgentsConfig validation."""

    def test_default_values(self):
        """Test default agents configuration."""
        config = AgentsConfig()

        # Check all agents exist
        assert isinstance(config.atomizer, AgentConfig)
        assert isinstance(config.planner, AgentConfig)
        assert isinstance(config.executor, AgentConfig)
        assert isinstance(config.aggregator, AgentConfig)
        assert isinstance(config.verifier, AgentConfig)

        # Check executor configuration (now uses chain_of_thought without toolkits)
        assert config.executor.toolkits == []
        assert config.executor.prediction_strategy == "chain_of_thought"

    def test_tool_strategy_compatibility_validation(self):
        """Test cross-agent toolkit/strategy validation."""
        from roma_dspy.config.schemas.toolkit import ToolkitConfig

        toolkit = ToolkitConfig(class_name="CalculatorToolkit", enabled=True)

        # Should pass with compatible strategy
        config = AgentsConfig(
            executor=AgentConfig(prediction_strategy="react", toolkits=[toolkit])
        )
        assert len(config.executor.toolkits) == 1

        # Chain of thought with toolkits is now allowed (toolkits just won't be used)
        # No validation error should be raised
        config2 = AgentsConfig(
            executor=AgentConfig(
                prediction_strategy="chain_of_thought", toolkits=[toolkit]
            )
        )
        assert len(config2.executor.toolkits) == 1


class TestROMAConfig:
    """Test ROMAConfig validation."""

    def test_default_values(self):
        """Test default ROMA configuration."""
        config = ROMAConfig()
        assert config.project == "roma-dspy"
        assert config.version == "0.1.0"
        assert config.environment == "development"
        assert isinstance(config.agents, AgentsConfig)
        assert isinstance(config.resilience, ResilienceConfig)
        assert isinstance(config.runtime, RuntimeConfig)

    def test_timeout_consistency_validation(self):
        """Test that runtime timeout is consistent with agent timeouts."""
        # Should pass with compatible timeouts
        config = ROMAConfig(
            runtime=RuntimeConfig(timeout=60),
            agents=AgentsConfig(executor=AgentConfig(llm=LLMConfig(timeout=30))),
        )
        # Should not raise during validation

        # Should fail with incompatible timeouts
        with pytest.raises(
            ValueError, match="Runtime timeout.*is less than maximum agent timeout"
        ):
            ROMAConfig(
                runtime=RuntimeConfig(timeout=10),
                agents=AgentsConfig(executor=AgentConfig(llm=LLMConfig(timeout=30))),
            )


class TestConfigManager:
    """Test ConfigManager functionality."""

    def test_load_config_defaults_only(self):
        """Test loading config with defaults only."""
        manager = ConfigManager()
        config = manager.load_config()

        assert isinstance(config, ROMAConfig)
        assert config.project == "roma-dspy"

    def test_load_config_with_yaml(self):
        """Test loading config with YAML file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("""
project: test-project
environment: testing
agents:
  executor:
    llm:
      temperature: 0.9
""")
            config_path = Path(f.name)

        try:
            manager = ConfigManager()
            config = manager.load_config(config_path=config_path)

            assert config.project == "test-project"
            assert config.environment == "testing"
            assert config.agents.executor.llm.temperature == 0.9
        finally:
            config_path.unlink()

    def test_load_config_with_overrides(self):
        """Test loading config with overrides."""
        manager = ConfigManager()
        config = manager.load_config(
            overrides=[
                "agents.executor.llm.temperature=0.5",
                "project=override-project",
            ]
        )

        assert config.project == "override-project"
        assert config.agents.executor.llm.temperature == 0.5

    def test_load_config_with_env_vars(self):
        """Test loading config with environment variables."""
        os.environ["ROMA_PROJECT"] = "env-project"
        os.environ["ROMA_AGENTS__EXECUTOR__LLM__TEMPERATURE"] = "0.3"

        try:
            manager = ConfigManager()
            config = manager.load_config()

            assert config.project == "env-project"
            assert config.agents.executor.llm.temperature == 0.3
        finally:
            # Clean up environment variables
            os.environ.pop("ROMA_PROJECT", None)
            os.environ.pop("ROMA_AGENTS__EXECUTOR__LLM__TEMPERATURE", None)

    def test_load_profile(self):
        """Test loading a profile."""
        with tempfile.TemporaryDirectory() as temp_dir:
            config_dir = Path(temp_dir)
            profiles_dir = config_dir / "profiles"
            profiles_dir.mkdir()

            # Create a test profile
            profile_file = profiles_dir / "test.yaml"
            profile_file.write_text("""
agents:
  executor:
    llm:
      temperature: 0.1
    toolkits: []
""")

            manager = ConfigManager(config_dir=config_dir)
            config = manager.load_config(profile="test")

            assert config.agents.executor.llm.temperature == 0.1
            assert config.agents.executor.toolkits == []

    def test_profile_not_found(self):
        """Test error when profile not found."""
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = ConfigManager(config_dir=Path(temp_dir))

            with pytest.raises(ValueError, match="Profile 'nonexistent' not found"):
                manager.load_config(profile="nonexistent")

    def test_invalid_yaml_file(self):
        """Test error with invalid YAML file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("invalid: yaml: content: [")
            config_path = Path(f.name)

        try:
            manager = ConfigManager()
            with pytest.raises(ValueError, match="Failed to load YAML config"):
                manager.load_config(config_path=config_path)
        finally:
            config_path.unlink()

    def test_config_caching(self):
        """Test that configs are cached."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("project: cached-project")
            config_path = Path(f.name)

        try:
            manager = ConfigManager()

            # Load twice - should use cache
            config1 = manager.load_config(config_path=config_path)
            config2 = manager.load_config(config_path=config_path)

            assert config1.project == "cached-project"
            assert config2.project == "cached-project"

            # Clear cache and verify
            manager.clear_cache()
            assert len(manager._cache) == 0
        finally:
            config_path.unlink()


class TestLoadConfigFunction:
    """Test the convenience load_config function."""

    def test_load_config_defaults(self):
        """Test load_config with defaults."""
        config = load_config()
        assert isinstance(config, ROMAConfig)
        assert config.project == "roma-dspy"

    def test_load_config_with_overrides(self):
        """Test load_config with overrides."""
        config = load_config(overrides=["project=test-project"])
        assert config.project == "test-project"

    def test_load_config_with_env_prefix(self):
        """Test load_config with custom env prefix."""
        os.environ["TEST_PROJECT"] = "env-test-project"

        try:
            config = load_config(env_prefix="TEST_")
            assert config.project == "env-test-project"
        finally:
            os.environ.pop("TEST_PROJECT", None)


class TestConfigResolutionOrder:
    """Test configuration resolution order."""

    def test_resolution_priority(self):
        """Test that later sources override earlier ones."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("project: yaml-project")
            config_path = Path(f.name)

        with tempfile.TemporaryDirectory() as temp_dir:
            config_dir = Path(temp_dir)
            profiles_dir = config_dir / "profiles"
            profiles_dir.mkdir()

            profile_file = profiles_dir / "test.yaml"
            profile_file.write_text("project: profile-project")

            os.environ["ROMA_PROJECT"] = "env-project"

            try:
                manager = ConfigManager(config_dir=config_dir)

                # Test: YAML < Profile < Override < Env
                config = manager.load_config(
                    config_path=config_path,
                    profile="test",
                    overrides=["project=override-project"],
                    # Env vars should override everything
                )

                assert config.project == "env-project"

                # Without env var, override should win
                os.environ.pop("ROMA_PROJECT")
                config = manager.load_config(
                    config_path=config_path,
                    profile="test",
                    overrides=["project=override-project"],
                )
                assert config.project == "override-project"

            finally:
                config_path.unlink()
                os.environ.pop("ROMA_PROJECT", None)
