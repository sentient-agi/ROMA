"""Integration tests for toolkit system with BaseModule."""

import tempfile
from unittest.mock import Mock, patch

import dspy
import pytest

from roma_dspy.config.schemas.agents import AgentConfig
from roma_dspy.config.schemas.base import LLMConfig
from roma_dspy.config.schemas.toolkit import ToolkitConfig
from roma_dspy.core.modules.base_module import BaseModule
from roma_dspy.core.signatures.signatures import ExecutorSignature
from roma_dspy.tools.core.calculator import CalculatorToolkit
from roma_dspy.tools.core.file import FileToolkit
from roma_dspy.tools.base.manager import ToolkitManager


class TestBaseModuleToolkitIntegration:
    """Test BaseModule integration with toolkit system."""

    def setup_method(self):
        """Set up test environment."""
        # Clear singleton instance for clean testing
        ToolkitManager._instance = None
        ToolkitManager._toolkit_registry.clear()
        ToolkitManager._toolkit_instances.clear()

        # Register external toolkits for testing
        manager = ToolkitManager.get_instance()
        manager.register_external_toolkit("CalculatorToolkit", CalculatorToolkit)

        self.temp_dir = tempfile.mkdtemp()

    def teardown_method(self):
        """Clean up test environment."""
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_basemodule_with_file_toolkit(self):
        """Test BaseModule with FileToolkit configuration."""
        file_toolkit_config = ToolkitConfig(
            class_name="FileToolkit",
            enabled=True,
            toolkit_config={"base_directory": self.temp_dir},
        )

        agent_config = AgentConfig(
            llm=LLMConfig(model="openai/gpt-3.5-turbo"),
            prediction_strategy="react",
            toolkits=[file_toolkit_config],
        )

        # Mock DSPy components
        with (
            patch("dspy.LM") as mock_lm_class,
            patch(
                "roma_dspy.types.prediction_strategy.PredictionStrategy.build"
            ) as mock_build,
        ):
            mock_lm = Mock()
            mock_lm_class.return_value = mock_lm

            mock_predictor = Mock()
            mock_build.return_value = mock_predictor

            # Create BaseModule with toolkit config
            module = BaseModule(signature=ExecutorSignature, config=agent_config)

            # Verify tools were loaded
            assert len(module._tools) > 0

            # Verify file toolkit tools are present
            tool_names = [tool.__name__ for tool in module._tools]
            expected_tools = [
                "save_file",
                "read_file",
                "list_files",
                "search_files",
                "create_directory",
            ]
            for expected in expected_tools:
                assert any(expected in name for name in tool_names)

    def test_basemodule_with_calculator_toolkit(self):
        """Test BaseModule with CalculatorToolkit configuration."""
        calc_toolkit_config = ToolkitConfig(
            class_name="CalculatorToolkit",
            enabled=True,
            exclude_tools=["factorial"],  # Exclude factorial for safety
            toolkit_config={"precision": 5},
        )

        agent_config = AgentConfig(
            llm=LLMConfig(model="openai/gpt-3.5-turbo"),
            prediction_strategy="react",
            toolkits=[calc_toolkit_config],
        )

        # Mock DSPy components
        with (
            patch("dspy.LM") as mock_lm_class,
            patch(
                "roma_dspy.types.prediction_strategy.PredictionStrategy.build"
            ) as mock_build,
        ):
            mock_lm = Mock()
            mock_lm_class.return_value = mock_lm

            mock_predictor = Mock()
            mock_build.return_value = mock_predictor

            # Create BaseModule with toolkit config
            module = BaseModule(signature=ExecutorSignature, config=agent_config)

            # Verify tools were loaded (excluding factorial)
            tool_names = [tool.__name__ for tool in module._tools]
            expected_tools = [
                "add",
                "subtract",
                "multiply",
                "divide",
                "square_root",
                "is_prime",
            ]
            for expected in expected_tools:
                assert any(expected in name for name in tool_names)

            # Verify factorial is excluded
            assert not any("factorial" in name for name in tool_names)

    def test_basemodule_with_multiple_toolkits(self):
        """Test BaseModule with multiple toolkits."""
        file_config = ToolkitConfig(
            class_name="FileToolkit",
            enabled=True,
            include_tools=["save_file", "read_file"],  # Only include specific tools
            toolkit_config={"base_directory": self.temp_dir},
        )

        calc_config = ToolkitConfig(
            class_name="CalculatorToolkit",
            enabled=True,
            include_tools=["add", "multiply"],  # Only basic operations
            toolkit_config={"precision": 3},
        )

        agent_config = AgentConfig(
            llm=LLMConfig(model="openai/gpt-3.5-turbo"),
            prediction_strategy="react",
            toolkits=[file_config, calc_config],
        )

        # Mock DSPy components
        with (
            patch("dspy.LM") as mock_lm_class,
            patch(
                "roma_dspy.types.prediction_strategy.PredictionStrategy.build"
            ) as mock_build,
        ):
            mock_lm = Mock()
            mock_lm_class.return_value = mock_lm

            mock_predictor = Mock()
            mock_build.return_value = mock_predictor

            # Create BaseModule with multiple toolkits
            module = BaseModule(signature=ExecutorSignature, config=agent_config)

            # Should have tools from both toolkits
            tool_names = [tool.__name__ for tool in module._tools]

            # File tools (only included ones)
            assert any("save_file" in name for name in tool_names)
            assert any("read_file" in name for name in tool_names)
            assert not any("list_files" in name for name in tool_names)  # Not included

            # Calculator tools (only included ones)
            assert any("add" in name for name in tool_names)
            assert any("multiply" in name for name in tool_names)
            assert not any("subtract" in name for name in tool_names)  # Not included

    def test_basemodule_toolkit_error_handling(self):
        """Test BaseModule handles toolkit initialization errors gracefully."""
        # Invalid toolkit configuration
        invalid_config = ToolkitConfig(class_name="NonexistentToolkit", enabled=True)

        agent_config = AgentConfig(
            llm=LLMConfig(model="openai/gpt-3.5-turbo"),
            prediction_strategy="chain_of_thought",  # CoT doesn't use tools
            toolkits=[invalid_config],
        )

        # Mock DSPy components
        with (
            patch("dspy.LM") as mock_lm_class,
            patch(
                "roma_dspy.types.prediction_strategy.PredictionStrategy.build"
            ) as mock_build,
        ):
            mock_lm = Mock()
            mock_lm_class.return_value = mock_lm

            mock_predictor = Mock()
            mock_build.return_value = mock_predictor

            # Should not raise exception, but should have empty tools
            module = BaseModule(signature=ExecutorSignature, config=agent_config)

            # Should have no tools due to error
            assert len(module._tools) == 0

    def test_basemodule_without_toolkits(self):
        """Test BaseModule works without any toolkits."""
        agent_config = AgentConfig(
            llm=LLMConfig(model="openai/gpt-3.5-turbo"),
            prediction_strategy="chain_of_thought",
            toolkits=[],  # Empty toolkits list
        )

        # Mock DSPy components
        with (
            patch("dspy.LM") as mock_lm_class,
            patch(
                "roma_dspy.types.prediction_strategy.PredictionStrategy.build"
            ) as mock_build,
        ):
            mock_lm = Mock()
            mock_lm_class.return_value = mock_lm

            mock_predictor = Mock()
            mock_build.return_value = mock_predictor

            # Should work without any issues
            module = BaseModule(signature=ExecutorSignature, config=agent_config)

            # Should have no tools
            assert len(module._tools) == 0

    def test_predictor_receives_tools(self):
        """Test that tools are passed to the predictor for ReAct strategy."""
        calc_config = ToolkitConfig(
            class_name="CalculatorToolkit", enabled=True, include_tools=["add"]
        )

        agent_config = AgentConfig(
            llm=LLMConfig(model="openai/gpt-3.5-turbo"),
            prediction_strategy="react",  # ReAct should receive tools
            toolkits=[calc_config],
        )

        # Mock DSPy components
        with (
            patch("dspy.LM") as mock_lm_class,
            patch(
                "roma_dspy.types.prediction_strategy.PredictionStrategy.build"
            ) as mock_build,
        ):
            mock_lm = Mock()
            mock_lm_class.return_value = mock_lm

            mock_predictor = Mock()
            mock_build.return_value = mock_predictor

            # Create BaseModule
            module = BaseModule(signature=ExecutorSignature, config=agent_config)

            # Verify build was called with tools
            mock_build.assert_called_once()
            call_args = mock_build.call_args
            assert "tools" in call_args[1]
            assert len(call_args[1]["tools"]) > 0


if __name__ == "__main__":
    pytest.main([__file__])
