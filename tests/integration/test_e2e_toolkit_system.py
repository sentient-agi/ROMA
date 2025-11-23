"""End-to-end integration tests for the complete toolkit system."""

import json
import os
import tempfile
import yaml
from pathlib import Path
from unittest.mock import Mock, patch
from typing import Dict, Any

import pytest

from roma_dspy.config.manager import ConfigManager
from roma_dspy.core.modules.base_module import BaseModule
from roma_dspy.core.signatures.signatures import ExecutorSignature
from roma_dspy.tools import register_toolkit, CalculatorToolkit, SerperToolkit


class TestE2EToolkitSystem:
    """End-to-end tests for the complete toolkit system."""

    def setup_method(self):
        """Set up test environment."""
        self.temp_dir = tempfile.mkdtemp()
        self.config_dir = Path(self.temp_dir) / "configs"
        self.config_dir.mkdir()

        # Register external toolkits
        register_toolkit(CalculatorToolkit)

    def teardown_method(self):
        """Clean up test environment."""
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _create_config_file(self, config_data: Dict[str, Any], filename: str) -> Path:
        """Create a YAML config file and return its path."""
        config_path = self.config_dir / filename
        with open(config_path, "w") as f:
            yaml.dump(config_data, f, default_flow_style=False)
        return config_path

    def test_file_toolkit_e2e_workflow(self):
        """Test complete workflow with FileToolkit from YAML config to tool execution."""

        # 1. Create YAML configuration
        config_data = {
            "project": "file-toolkit-test",
            "environment": "development",
            "agents": {
                "executor": {
                    "llm": {"model": "openai/gpt-3.5-turbo", "temperature": 0.3},
                    "prediction_strategy": "react",
                    "toolkits": [
                        {
                            "class_name": "FileToolkit",
                            "enabled": True,
                            "toolkit_config": {
                                "base_directory": self.temp_dir,
                                "enable_delete": True,
                                "max_file_size": 1048576,  # 1MB
                            },
                        }
                    ],
                }
            },
        }

        config_path = self._create_config_file(config_data, "file_toolkit.yaml")

        # 2. Load configuration
        config = ConfigManager().load_config(config_path)

        # Verify config loaded correctly
        assert config.project == "file-toolkit-test"
        assert len(config.agents.executor.toolkits) == 1
        assert config.agents.executor.toolkits[0].class_name == "FileToolkit"

        # 3. Create BaseModule with toolkit configuration
        with (
            patch("dspy.LM") as mock_lm_class,
            patch(
                "src.roma_dspy.types.prediction_strategy.PredictionStrategy.build"
            ) as mock_build,
        ):
            mock_lm = Mock()
            mock_lm_class.return_value = mock_lm
            mock_predictor = Mock()
            mock_build.return_value = mock_predictor

            module = BaseModule(
                signature=ExecutorSignature, config=config.agents.executor
            )

            # 4. Verify tools were loaded
            assert len(module._tools) > 0

            # Find file toolkit tools
            tool_functions = {tool.__name__: tool for tool in module._tools}

            # Should have file operations
            file_tools = [
                name
                for name in tool_functions.keys()
                if "file" in name.lower()
                or name
                in [
                    "save_file",
                    "read_file",
                    "list_files",
                    "search_files",
                    "create_directory",
                    "delete_file",
                ]
            ]
            assert len(file_tools) > 0

            # 5. Test actual tool execution
            save_file_tool = None
            read_file_tool = None

            for tool in module._tools:
                if hasattr(tool, "__name__"):
                    if "save_file" in tool.__name__:
                        save_file_tool = tool
                    elif "read_file" in tool.__name__:
                        read_file_tool = tool

            # Test file save and read workflow
            if save_file_tool and read_file_tool:
                # Save a file
                save_result = save_file_tool(
                    "test_file.txt", "Hello, ROMA-DSPy!", overwrite=True
                )
                save_data = json.loads(save_result)
                assert save_data["success"] is True

                # Read the file back
                read_result = read_file_tool("test_file.txt")
                read_data = json.loads(read_result)
                assert read_data["success"] is True
                assert read_data["content"] == "Hello, ROMA-DSPy!"

    def test_calculator_toolkit_e2e_workflow(self):
        """Test complete workflow with CalculatorToolkit."""

        # 1. Create YAML configuration
        config_data = {
            "project": "calculator-test",
            "environment": "development",
            "agents": {
                "executor": {
                    "llm": {"model": "openai/gpt-4", "temperature": 0.1},
                    "prediction_strategy": "react",
                    "toolkits": [
                        {
                            "class_name": "CalculatorToolkit",
                            "enabled": True,
                            "exclude_tools": ["factorial"],  # Exclude for testing
                            "toolkit_config": {"precision": 4},
                        }
                    ],
                }
            },
        }

        config_path = self._create_config_file(config_data, "calculator_toolkit.yaml")

        # 2. Load and verify configuration
        config = ConfigManager().load_config(config_path)
        calculator_config = config.agents.executor.toolkits[0]

        assert calculator_config.class_name == "CalculatorToolkit"
        assert "factorial" in calculator_config.exclude_tools
        assert calculator_config.toolkit_config["precision"] == 4

        # 3. Create BaseModule and test tool execution
        with (
            patch("dspy.LM") as mock_lm_class,
            patch(
                "src.roma_dspy.types.prediction_strategy.PredictionStrategy.build"
            ) as mock_build,
        ):
            mock_lm = Mock()
            mock_lm_class.return_value = mock_lm
            mock_predictor = Mock()
            mock_build.return_value = mock_predictor

            module = BaseModule(
                signature=ExecutorSignature, config=config.agents.executor
            )

            # Find calculator tools
            add_tool = None
            factorial_tool = None

            for tool in module._tools:
                if hasattr(tool, "__name__"):
                    if "add" in tool.__name__:
                        add_tool = tool
                    elif "factorial" in tool.__name__:
                        factorial_tool = tool

            # Should have add but not factorial (excluded)
            assert add_tool is not None
            assert factorial_tool is None

            # Test calculation
            if add_tool:
                result = add_tool(5.5, 3.3)
                data = json.loads(result)
                assert data["success"] is True
                assert data["result"] == 8.8  # Should be rounded to 4 decimal places

    @patch.dict(os.environ, {"SERPER_API_KEY": "test_api_key"})
    def test_multi_toolkit_e2e_workflow(self):
        """Test workflow with multiple toolkits in one agent."""

        # 1. Create comprehensive configuration
        config_data = {
            "project": "multi-toolkit-test",
            "environment": "production",
            "agents": {
                "executor": {
                    "llm": {"model": "openai/gpt-4", "temperature": 0.5},
                    "prediction_strategy": "react",
                    "toolkits": [
                        {
                            "class_name": "FileToolkit",
                            "enabled": True,
                            "include_tools": ["save_file", "read_file"],
                            "toolkit_config": {"base_directory": self.temp_dir},
                        },
                        {
                            "class_name": "CalculatorToolkit",
                            "enabled": True,
                            "include_tools": ["add", "multiply"],
                            "toolkit_config": {"precision": 2},
                        },
                    ],
                }
            },
            "runtime": {"timeout": 180},
        }

        config_path = self._create_config_file(config_data, "multi_toolkit.yaml")

        # 2. Load configuration and verify structure
        config = ConfigManager().load_config(config_path)

        assert len(config.agents.executor.toolkits) == 2
        assert config.runtime.timeout == 180

        # 3. Create BaseModule with multiple toolkits
        with (
            patch("dspy.LM") as mock_lm_class,
            patch(
                "src.roma_dspy.types.prediction_strategy.PredictionStrategy.build"
            ) as mock_build,
        ):
            mock_lm = Mock()
            mock_lm_class.return_value = mock_lm
            mock_predictor = Mock()
            mock_build.return_value = mock_predictor

            module = BaseModule(
                signature=ExecutorSignature, config=config.agents.executor
            )

            # 4. Verify tools from both toolkits are present
            tool_names = [
                getattr(tool, "__name__", "unknown") for tool in module._tools
            ]

            # Should have tools from both toolkits (but only included ones)
            file_tool_found = any(
                "save_file" in name or "read_file" in name for name in tool_names
            )
            calc_tool_found = any(
                "add" in name or "multiply" in name for name in tool_names
            )

            assert file_tool_found, f"File tools not found in: {tool_names}"
            assert calc_tool_found, f"Calculator tools not found in: {tool_names}"

            # Should NOT have excluded tools
            excluded_tools_found = any(
                "list_files" in name or "subtract" in name or "divide" in name
                for name in tool_names
            )
            assert not excluded_tools_found, f"Excluded tools found in: {tool_names}"

    def test_invalid_configuration_handling(self):
        """Test system handles invalid configurations gracefully."""

        # Configuration with invalid toolkit
        config_data = {
            "project": "invalid-config-test",
            "agents": {
                "executor": {
                    "llm": {"model": "openai/gpt-3.5-turbo"},
                    "prediction_strategy": "react",
                    "toolkits": [{"class_name": "NonExistentToolkit", "enabled": True}],
                }
            },
        }

        config_path = self._create_config_file(config_data, "invalid_toolkit.yaml")

        # Should raise validation error during config load
        with pytest.raises((ValueError, KeyError)):
            ConfigManager().load_config(config_path)

    def test_toolkit_error_resilience(self):
        """Test system resilience when toolkit initialization fails."""

        config_data = {
            "project": "resilience-test",
            "agents": {
                "executor": {
                    "llm": {"model": "openai/gpt-3.5-turbo"},
                    "prediction_strategy": "react",
                    "toolkits": [
                        {
                            "class_name": "FileToolkit",
                            "enabled": True,
                            "toolkit_config": {
                                "base_directory": "/non/existent/path/that/cannot/be/created"
                            },
                        }
                    ],
                }
            },
        }

        config_path = self._create_config_file(config_data, "error_resilience.yaml")
        config = ConfigManager().load_config(config_path)

        # BaseModule should handle toolkit initialization errors gracefully
        with (
            patch("dspy.LM") as mock_lm_class,
            patch(
                "src.roma_dspy.types.prediction_strategy.PredictionStrategy.build"
            ) as mock_build,
        ):
            mock_lm = Mock()
            mock_lm_class.return_value = mock_lm
            mock_predictor = Mock()
            mock_build.return_value = mock_predictor

            # Should not raise exception, but may have no tools
            module = BaseModule(
                signature=ExecutorSignature, config=config.agents.executor
            )

            # Module should exist even if toolkit failed to initialize
            assert module is not None
            # Tools list may be empty due to initialization failure
            assert isinstance(module._tools, list)

    def test_yaml_config_roundtrip(self):
        """Test that configurations can be loaded, modified, and saved correctly."""

        # 1. Create initial configuration
        original_config = {
            "project": "roundtrip-test",
            "agents": {
                "executor": {
                    "llm": {"model": "openai/gpt-3.5-turbo"},
                    "prediction_strategy": "react",
                    "toolkits": [
                        {
                            "class_name": "FileToolkit",
                            "enabled": True,
                            "toolkit_config": {"base_directory": "/tmp"},
                        }
                    ],
                }
            },
        }

        config_path = self._create_config_file(original_config, "roundtrip.yaml")

        # 2. Load configuration
        loaded_config = ConfigManager().load_config(config_path)

        # 3. Verify loaded configuration matches original
        assert loaded_config.project == "roundtrip-test"
        assert loaded_config.agents.executor.prediction_strategy == "react"
        assert len(loaded_config.agents.executor.toolkits) == 1

        toolkit_config = loaded_config.agents.executor.toolkits[0]
        assert toolkit_config.class_name == "FileToolkit"
        assert toolkit_config.enabled is True
        assert toolkit_config.toolkit_config["base_directory"] == "/tmp"

        # 4. Test that the loaded config can be used successfully
        with (
            patch("dspy.LM") as mock_lm_class,
            patch(
                "src.roma_dspy.types.prediction_strategy.PredictionStrategy.build"
            ) as mock_build,
        ):
            mock_lm = Mock()
            mock_lm_class.return_value = mock_lm
            mock_predictor = Mock()
            mock_build.return_value = mock_predictor

            # Should create module successfully
            module = BaseModule(
                signature=ExecutorSignature, config=loaded_config.agents.executor
            )

            assert module is not None
            assert hasattr(module, "_tools")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
