"""Tests for enhanced configuration schemas and security validation."""

import pytest
import tempfile
import os
from pathlib import Path
from pydantic import ValidationError

from roma_dspy.config.schemas.root import ROMAConfig
from roma_dspy.config.schemas.agents import AgentConfig, AgentsConfig
from roma_dspy.config.schemas.base import LLMConfig, RuntimeConfig
from roma_dspy.config.schemas.resilience import ResilienceConfig
from roma_dspy.config.schemas.toolkit import ToolkitConfig
from roma_dspy.config.manager import ConfigManager
from roma_dspy.tools.base.manager import ToolkitManager


class TestEnhancedRuntimeConfig:
    """Test enhanced RuntimeConfig with new fields."""

    def test_default_values(self):
        """Test default runtime configuration values."""
        config = RuntimeConfig()
        assert config.max_concurrency == 5
        assert config.timeout == 30
        assert config.verbose is False
        assert config.cache_dir == ".cache/dspy"
        assert config.max_depth == 5
        assert config.enable_logging is False
        assert config.log_level == "INFO"

    def test_max_depth_validation(self):
        """Test max_depth validation."""
        # Valid range
        RuntimeConfig(max_depth=1)
        RuntimeConfig(max_depth=20)

        # Invalid range
        with pytest.raises(ValidationError):
            RuntimeConfig(max_depth=0)
        with pytest.raises(ValidationError):
            RuntimeConfig(max_depth=21)

    def test_log_level_validation(self):
        """Test log_level validation."""
        # Valid levels
        for level in ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]:
            config = RuntimeConfig(log_level=level)
            assert config.log_level == level

        # Case insensitive
        config = RuntimeConfig(log_level="debug")
        assert config.log_level == "DEBUG"

        # Invalid level
        with pytest.raises(ValidationError):
            RuntimeConfig(log_level="INVALID")


class TestEnhancedResilienceConfig:
    """Test enhanced ResilienceConfig with checkpoint support."""

    def test_default_initialization(self):
        """Test default initialization creates checkpoint config."""
        config = ResilienceConfig()
        assert config.retry_strategy == "exponential_backoff"
        assert config.max_retries == 3
        assert config.failure_threshold == 5
        assert config.checkpoint is not None

    def test_retry_config(self):
        """Test retry configuration."""
        config = ResilienceConfig(
            retry_strategy="fixed_delay", max_retries=5, base_delay=2.0
        )
        assert config.retry_strategy == "fixed_delay"
        assert config.max_retries == 5
        assert config.base_delay == 2.0

    def test_retry_strategy_validation(self):
        """Test retry strategy validation."""
        # Valid strategies
        for strategy in ["exponential_backoff", "fixed_delay", "linear_backoff"]:
            ResilienceConfig(retry_strategy=strategy)

        # Invalid strategy
        with pytest.raises(ValidationError):
            ResilienceConfig(retry_strategy="invalid_strategy")

    def test_circuit_breaker_validation(self):
        """Test circuit breaker validation."""
        # Valid values
        ResilienceConfig(failure_threshold=1, recovery_timeout=1.0, success_threshold=1)
        ResilienceConfig(
            failure_threshold=100, recovery_timeout=3600.0, success_threshold=20
        )

        # Invalid values
        with pytest.raises(ValidationError):
            ResilienceConfig(failure_threshold=0)
        with pytest.raises(ValidationError):
            ResilienceConfig(recovery_timeout=0.5)
        with pytest.raises(ValidationError):
            ResilienceConfig(success_threshold=0)


class TestToolkitConfigValidation:
    """Test ToolkitConfig validation and security."""

    def test_valid_toolkit_config(self):
        """Test valid toolkit configuration."""
        config = ToolkitConfig(
            class_name="FileToolkit",
            enabled=True,
            include_tools=["read_file", "write_file"],
            exclude_tools=["delete_file"],
            toolkit_config={"base_directory": "/tmp", "enable_delete": False},
        )
        assert config.class_name == "FileToolkit"
        assert config.enabled is True
        assert "read_file" in config.include_tools
        assert "delete_file" in config.exclude_tools

    def test_empty_class_name_validation(self):
        """Test empty class name validation."""
        with pytest.raises(ValidationError):
            ToolkitConfig(class_name="")
        with pytest.raises(ValidationError):
            ToolkitConfig(class_name="   ")

    def test_toolkit_manager_validation(self):
        """Test toolkit validation through manager."""
        manager = ToolkitManager.get_instance()

        # Valid builtin toolkit
        config = ToolkitConfig(class_name="FileToolkit", enabled=True)
        # Should not raise
        manager.validate_toolkit_config(config)

        # Unknown toolkit
        invalid_config = ToolkitConfig(class_name="UnknownToolkit", enabled=True)
        with pytest.raises(ValueError, match="Unknown toolkit class"):
            manager.validate_toolkit_config(invalid_config)

    def test_tool_overlap_validation(self):
        """Test that tools cannot be both included and excluded."""
        with pytest.raises(
            ValidationError, match="Tools cannot be both included and excluded"
        ):
            ToolkitConfig(
                class_name="FileToolkit",
                include_tools=["read_file", "write_file"],
                exclude_tools=["read_file"],  # Overlap!
            )


class TestAgentConfigValidation:
    """Test AgentConfig validation with toolkits."""

    def test_default_agent_config(self):
        """Test default agent configuration."""
        config = AgentConfig()
        assert isinstance(config.llm, LLMConfig)
        assert config.prediction_strategy == "chain_of_thought"
        assert config.toolkits == []
        assert config.enabled is True
        assert config.agent_config == {}
        assert config.strategy_config == {}

    def test_agent_with_toolkit(self):
        """Test agent configuration with toolkit."""
        config = AgentConfig(
            prediction_strategy="react",
            toolkits=[ToolkitConfig(class_name="FileToolkit", enabled=True)],
        )
        assert config.prediction_strategy == "react"
        assert len(config.toolkits) == 1
        assert config.toolkits[0].class_name == "FileToolkit"

    def test_prediction_strategy_validation(self):
        """Test prediction strategy validation."""
        # Valid strategies
        for strategy in ["chain_of_thought", "react", "code_act", "predict"]:
            AgentConfig(prediction_strategy=strategy)

        # Invalid strategy
        with pytest.raises(ValidationError):
            AgentConfig(prediction_strategy="invalid_strategy")


class TestSecurityValidation:
    """Test security-related configuration validation."""

    def test_file_toolkit_security_config(self):
        """Test FileToolkit security configuration."""
        # Safe configuration
        safe_config = ToolkitConfig(
            class_name="FileToolkit",
            enabled=True,
            toolkit_config={
                "base_directory": "/tmp/safe_workspace",
                "enable_delete": False,
                "max_file_size": 1048576,  # 1MB
            },
        )
        # Should not raise

        # Configuration with security considerations
        prod_config = ToolkitConfig(
            class_name="FileToolkit",
            enabled=True,
            exclude_tools=["delete_file"],  # Exclude dangerous operations
            toolkit_config={
                "base_directory": "/home/user/workspace",
                "enable_delete": False,
                "max_file_size": 5242880,  # 5MB
            },
        )
        # Should not raise

    def test_toolkit_enable_disable_security(self):
        """Test toolkit enable/disable for security."""
        # Disabled toolkit should not be used
        disabled_config = ToolkitConfig(
            class_name="FileToolkit",
            enabled=False,
            toolkit_config={
                "base_directory": "/"
            },  # Even dangerous config is OK when disabled
        )
        # Should not raise since it's disabled

    def test_agent_config_security_defaults(self):
        """Test that agent config defaults are secure."""
        config = AgentsConfig()

        # Executor should have safe defaults
        assert config.executor.prediction_strategy == "chain_of_thought"  # Safe default
        assert config.executor.toolkits == []  # No tools by default

        # All agents should have reasonable LLM configs
        for agent_name in ["atomizer", "planner", "executor", "aggregator", "verifier"]:
            agent = getattr(config, agent_name)
            assert agent.llm.timeout <= 60  # Reasonable timeout
            assert 0.0 <= agent.llm.temperature <= 1.0  # Reasonable temperature range


class TestConfigManagerEnhancements:
    """Test ConfigManager with enhanced schemas."""

    def test_load_config_with_enhanced_schemas(self):
        """Test loading config with enhanced schemas."""
        manager = ConfigManager()
        config = manager.load_config()

        # Check enhanced fields are present
        assert hasattr(config.runtime, "max_depth")
        assert hasattr(config.runtime, "enable_logging")
        assert hasattr(config.runtime, "log_level")
        assert hasattr(config.resilience, "retry_strategy")
        assert hasattr(config.resilience, "failure_threshold")

    def test_load_config_with_path_and_string(self):
        """Test ConfigManager accepts both Path and string inputs."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("""
project: test-enhanced
runtime:
  max_depth: 7
  enable_logging: true
  log_level: DEBUG
resilience:
  retry_strategy: exponential_backoff
  max_retries: 5
""")
            config_path = f.name

        try:
            manager = ConfigManager()

            # Test with string path
            config1 = manager.load_config(config_path=config_path)
            assert config1.project == "test-enhanced"
            assert config1.runtime.max_depth == 7
            assert config1.runtime.enable_logging is True
            assert config1.runtime.log_level == "DEBUG"
            assert config1.resilience.max_retries == 5

            # Test with Path object
            config2 = manager.load_config(config_path=Path(config_path))
            assert config2.project == "test-enhanced"
            assert config2.runtime.max_depth == 7

        finally:
            os.unlink(config_path)

    def test_profile_with_enhanced_schemas(self):
        """Test profile loading with enhanced schemas."""
        with tempfile.TemporaryDirectory() as temp_dir:
            config_dir = Path(temp_dir)
            profiles_dir = config_dir / "profiles"
            profiles_dir.mkdir()

            # Create enhanced profile
            profile_file = profiles_dir / "enhanced.yaml"
            profile_file.write_text("""
agents:
  executor:
    prediction_strategy: react
    toolkits:
      - class_name: FileToolkit
        enabled: true
        toolkit_config:
          base_directory: "/tmp"
          enable_delete: false
runtime:
  max_depth: 8
  enable_logging: true
  log_level: DEBUG
resilience:
  retry_strategy: exponential_backoff
  max_retries: 4
  failure_threshold: 3
""")

            manager = ConfigManager(config_dir=config_dir)
            config = manager.load_config(profile="enhanced")

            # Verify enhanced fields
            assert config.agents.executor.prediction_strategy == "react"
            assert len(config.agents.executor.toolkits) == 1
            assert config.agents.executor.toolkits[0].class_name == "FileToolkit"
            assert config.runtime.max_depth == 8
            assert config.runtime.enable_logging is True
            assert config.runtime.log_level == "DEBUG"
            assert config.resilience.max_retries == 4
            assert config.resilience.failure_threshold == 3


class TestEndToEndValidation:
    """Test end-to-end configuration validation."""

    def test_complete_config_validation(self):
        """Test complete configuration validation."""
        config = ROMAConfig(
            project="test-e2e",
            environment="testing",
            agents=AgentsConfig(
                executor=AgentConfig(
                    llm=LLMConfig(model="gpt-4", temperature=0.5),
                    prediction_strategy="react",
                    toolkits=[
                        ToolkitConfig(
                            class_name="FileToolkit",
                            enabled=True,
                            exclude_tools=["delete_file"],
                            toolkit_config={
                                "base_directory": "/tmp/test",
                                "enable_delete": False,
                                "max_file_size": 1048576,
                            },
                        )
                    ],
                )
            ),
            runtime=RuntimeConfig(
                max_depth=6, enable_logging=True, log_level="INFO", timeout=120
            ),
            resilience=ResilienceConfig(
                retry_strategy="exponential_backoff", max_retries=3, failure_threshold=5
            ),
        )

        # Should validate successfully
        assert config.project == "test-e2e"
        assert config.agents.executor.prediction_strategy == "react"
        assert config.runtime.max_depth == 6
        assert config.resilience.retry_strategy == "exponential_backoff"

    def test_invalid_config_combinations(self):
        """Test invalid configuration combinations."""
        # Agent with tools but incompatible strategy
        with pytest.raises(ValidationError):
            AgentsConfig(
                executor=AgentConfig(
                    prediction_strategy="chain_of_thought",  # Doesn't support tools
                    toolkits=[ToolkitConfig(class_name="FileToolkit", enabled=True)],
                )
            )
