"""Tests for the toolkit system."""

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from roma_dspy.config.schemas.toolkit import ToolkitConfig
from roma_dspy.tools.base.base import BaseToolkit
from roma_dspy.tools.core.calculator import CalculatorToolkit
from roma_dspy.tools.core.file import FileToolkit
from roma_dspy.tools.base.manager import ToolkitManager
from roma_dspy.tools.web_search.serper import SerperToolkit


class MockToolkit(BaseToolkit):
    """Mock toolkit for testing."""

    def _setup_dependencies(self):
        pass

    def _initialize_tools(self):
        self.test_value = self.config.get("test_value", 42)

    def mock_tool(self, input_text: str) -> str:
        """A mock tool for testing."""
        return f"Mock result: {input_text}"

    def conditional_tool(self, data: str) -> str:
        """A conditionally available tool."""
        return f"Conditional: {data}"

    def _is_tool_available(self, tool_name: str) -> bool:
        if tool_name == "conditional_tool":
            return self.config.get("enable_conditional", False)
        return True


class TestBaseToolkit:
    """Test BaseToolkit functionality."""

    def test_toolkit_initialization(self):
        """Test basic toolkit initialization."""
        toolkit = MockToolkit(enabled=True, include_tools=["mock_tool"], test_value=123)

        assert toolkit.enabled is True
        assert toolkit.include_tools == ["mock_tool"]
        assert toolkit.test_value == 123

    def test_auto_tool_discovery(self):
        """Test automatic tool discovery."""
        toolkit = MockToolkit()
        available_tools = toolkit.get_available_tool_names()

        assert "mock_tool" in available_tools
        # conditional_tool is not available by default (requires enable_conditional=True)
        assert "conditional_tool" not in available_tools
        # Should not include private methods or BaseToolkit methods
        assert "_setup_dependencies" not in available_tools
        assert "get_enabled_tools" not in available_tools

    def test_conditional_tool_availability(self):
        """Test conditional tool availability."""
        # Without enabling conditional tool
        toolkit1 = MockToolkit()
        tools1 = toolkit1.get_available_tool_names()
        assert "conditional_tool" not in tools1

        # With conditional tool enabled
        toolkit2 = MockToolkit(enable_conditional=True)
        tools2 = toolkit2.get_available_tool_names()
        assert "conditional_tool" in tools2

    def test_include_exclude_patterns(self):
        """Test include/exclude tool patterns."""
        toolkit = MockToolkit(
            enable_conditional=True,
            include_tools=["mock_tool"],
            exclude_tools=["conditional_tool"],
        )

        enabled_tools = toolkit.get_enabled_tools()
        assert "mock_tool" in enabled_tools
        assert "conditional_tool" not in enabled_tools

    def test_tool_validation(self):
        """Test tool selection validation."""
        with pytest.raises(ValueError, match="Invalid tools in include_tools"):
            MockToolkit(include_tools=["nonexistent_tool"])

        with pytest.raises(ValueError, match="Invalid tools in exclude_tools"):
            MockToolkit(exclude_tools=["nonexistent_tool"])

    def test_tool_execution(self):
        """Test that registered tools are callable."""
        toolkit = MockToolkit()
        enabled_tools = toolkit.get_enabled_tools()

        mock_tool = enabled_tools["mock_tool"]
        result = mock_tool("test input")
        assert result == "Mock result: test input"

    def test_disabled_toolkit(self):
        """Test disabled toolkit behavior."""
        toolkit = MockToolkit(enabled=False)
        enabled_tools = toolkit.get_enabled_tools()
        assert len(enabled_tools) == 0

    def test_tool_metadata(self):
        """Test tool metadata extraction from docstrings."""
        toolkit = MockToolkit()
        metadata = toolkit.get_tool_metadata("mock_tool")

        assert metadata["name"] == "mock_tool"
        assert "A mock tool for testing" in metadata["description"]

    def test_logging_methods(self):
        """Test logging utility methods."""
        toolkit = MockToolkit()

        # These shouldn't raise exceptions
        toolkit.log_debug("Debug message")
        toolkit.log_error("Error message")
        toolkit.log_warning("Warning message")


class TestFileToolkit:
    """Test FileToolkit functionality."""

    def setup_method(self):
        """Set up test environment."""
        self.temp_dir = tempfile.mkdtemp()
        self.toolkit = FileToolkit(base_directory=self.temp_dir)

    def teardown_method(self):
        """Clean up test environment."""
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_file_toolkit_tools(self):
        """Test FileToolkit has expected tools."""
        tools = self.toolkit.get_available_tool_names()
        expected_tools = {
            "save_file",
            "read_file",
            "list_files",
            "search_files",
            "create_directory",
        }
        assert expected_tools.issubset(tools)

    def test_delete_tool_availability(self):
        """Test delete_file tool conditional availability."""
        # With delete enabled (default)
        toolkit1 = FileToolkit(base_directory=self.temp_dir, enable_delete=True)
        tools1 = toolkit1.get_available_tool_names()
        assert "delete_file" in tools1

        # With delete disabled
        toolkit2 = FileToolkit(base_directory=self.temp_dir, enable_delete=False)
        tools2 = toolkit2.get_available_tool_names()
        assert "delete_file" not in tools2

    def test_save_and_read_file(self):
        """Test file save and read operations."""
        content = "Hello, world!"
        file_path = "test.txt"

        # Save file
        save_result = self.toolkit.save_file(file_path, content)
        save_data = json.loads(save_result)
        assert save_data["success"] is True

        # Read file
        read_result = self.toolkit.read_file(file_path)
        read_data = json.loads(read_result)
        assert read_data["success"] is True
        assert read_data["content"] == content

    def test_overwrite_protection(self):
        """Test file overwrite protection."""
        file_path = "test.txt"
        self.toolkit.save_file(file_path, "Original content")

        # Should fail without overwrite=True
        result = self.toolkit.save_file(file_path, "New content")
        data = json.loads(result)
        assert data["success"] is False
        assert "already exists" in data["error"]

        # Should succeed with overwrite=True
        result = self.toolkit.save_file(file_path, "New content", overwrite=True)
        data = json.loads(result)
        assert data["success"] is True

    def test_list_files(self):
        """Test directory listing."""
        # Create test files
        (Path(self.temp_dir) / "file1.txt").write_text("content1")
        (Path(self.temp_dir) / "file2.txt").write_text("content2")
        (Path(self.temp_dir) / "subdir").mkdir()

        result = self.toolkit.list_files()
        data = json.loads(result)
        assert data["success"] is True
        assert data["count"] == 3

        file_names = [item["name"] for item in data["items"]]
        assert "file1.txt" in file_names
        assert "file2.txt" in file_names
        assert "subdir" in file_names

    def test_create_directory(self):
        """Test directory creation."""
        dir_path = "nested/directory/structure"

        result = self.toolkit.create_directory(dir_path)
        data = json.loads(result)
        assert data["success"] is True

        # Verify directory was created
        full_path = Path(self.temp_dir) / dir_path
        assert full_path.exists() and full_path.is_dir()

    def test_path_security(self):
        """Test path traversal protection."""
        with pytest.raises(ValueError, match="path traversal detected"):
            self.toolkit._get_full_path("../../../etc/passwd")


class TestCalculatorToolkit:
    """Test CalculatorToolkit functionality."""

    def setup_method(self):
        """Set up test environment."""
        self.toolkit = CalculatorToolkit(precision=2)

    def test_calculator_tools(self):
        """Test CalculatorToolkit has expected tools."""
        tools = self.toolkit.get_available_tool_names()
        expected_tools = {
            "add",
            "subtract",
            "multiply",
            "divide",
            "exponentiate",
            "factorial",
            "is_prime",
            "square_root",
        }
        assert expected_tools == tools

    def test_basic_arithmetic(self):
        """Test basic arithmetic operations."""
        # Addition
        result = self.toolkit.add(5, 3)
        data = json.loads(result)
        assert data["success"] is True
        assert data["result"] == 8

        # Subtraction
        result = self.toolkit.subtract(10, 4)
        data = json.loads(result)
        assert data["success"] is True
        assert data["result"] == 6

        # Multiplication
        result = self.toolkit.multiply(6, 7)
        data = json.loads(result)
        assert data["success"] is True
        assert data["result"] == 42

        # Division
        result = self.toolkit.divide(15, 3)
        data = json.loads(result)
        assert data["success"] is True
        assert data["result"] == 5

    def test_division_by_zero(self):
        """Test division by zero protection."""
        result = self.toolkit.divide(10, 0)
        data = json.loads(result)
        assert data["success"] is False
        assert "Division by zero" in data["error"]

    def test_factorial(self):
        """Test factorial calculation."""
        result = self.toolkit.factorial(5)
        data = json.loads(result)
        assert data["success"] is True
        assert data["result"] == 120

        # Test negative input
        result = self.toolkit.factorial(-1)
        data = json.loads(result)
        assert data["success"] is False
        assert "negative numbers" in data["error"]

    def test_prime_check(self):
        """Test prime number checking."""
        # Prime number
        result = self.toolkit.is_prime(7)
        data = json.loads(result)
        assert data["success"] is True
        assert data["result"] is True

        # Non-prime number
        result = self.toolkit.is_prime(12)
        data = json.loads(result)
        assert data["success"] is True
        assert data["result"] is False

    def test_square_root(self):
        """Test square root calculation."""
        result = self.toolkit.square_root(16)
        data = json.loads(result)
        assert data["success"] is True
        assert data["result"] == 4

        # Test negative input
        result = self.toolkit.square_root(-4)
        data = json.loads(result)
        assert data["success"] is False
        assert "negative numbers" in data["error"]


class TestSerperToolkit:
    """Test SerperToolkit functionality."""

    @patch.dict(os.environ, {"SERPER_API_KEY": "test_api_key"})
    def test_serper_initialization(self):
        """Test SerperToolkit initialization."""
        try:
            import requests
        except ImportError:
            pytest.skip("requests library not installed")

        toolkit = SerperToolkit()
        assert toolkit.api_key == "test_api_key"

    def test_missing_api_key(self):
        """Test SerperToolkit fails without API key."""
        try:
            import requests
        except ImportError:
            pytest.skip("requests library not installed")

        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError, match="SERPER_API_KEY is required"):
                SerperToolkit()

    def test_missing_requests_dependency(self):
        """Test SerperToolkit fails without requests library."""
        # Test that importing requests is handled properly
        with patch.dict(os.environ, {"SERPER_API_KEY": "test_key"}):
            with patch(
                "builtins.__import__",
                side_effect=lambda name, *args, **kwargs: (_ for _ in ()).throw(
                    ImportError("No module named 'requests'")
                )
                if name == "requests"
                else __import__(name, *args, **kwargs),
            ):
                with pytest.raises(ImportError, match="requests library is required"):
                    SerperToolkit()

    @patch.dict(os.environ, {"SERPER_API_KEY": "test_api_key"})
    def test_serper_tools(self):
        """Test SerperToolkit has expected tools."""
        try:
            import requests
        except ImportError:
            pytest.skip("requests library not installed")

        toolkit = SerperToolkit()
        tools = toolkit.get_available_tool_names()
        expected_tools = {"search", "search_news", "search_scholar", "scrape_webpage"}
        assert expected_tools == tools


class TestToolkitManager:
    """Test ToolkitManager functionality."""

    def setup_method(self):
        """Set up test environment."""
        # Clear singleton instance for clean testing
        ToolkitManager._instance = None
        ToolkitManager._toolkit_registry.clear()
        ToolkitManager._toolkit_instances.clear()

    def test_singleton_pattern(self):
        """Test ToolkitManager singleton behavior."""
        manager1 = ToolkitManager.get_instance()
        manager2 = ToolkitManager.get_instance()
        assert manager1 is manager2

    def test_builtin_toolkit_registration(self):
        """Test builtin toolkit registration."""
        manager = ToolkitManager()
        available = manager.get_available_toolkits()

        # Should have FileToolkit as builtin
        assert "FileToolkit" in available

    def test_external_toolkit_registration(self):
        """Test external toolkit registration."""
        manager = ToolkitManager()
        manager.register_external_toolkit("MockToolkit", MockToolkit)

        available = manager.get_available_toolkits()
        assert "MockToolkit" in available

    def test_toolkit_creation(self):
        """Test toolkit instance creation."""
        manager = ToolkitManager()
        manager.register_external_toolkit("MockToolkit", MockToolkit)

        config = ToolkitConfig(
            class_name="MockToolkit", enabled=True, toolkit_config={"test_value": 999}
        )

        toolkit = manager.get_toolkit("MockToolkit", config)
        assert isinstance(toolkit, MockToolkit)
        assert toolkit.test_value == 999

    def test_toolkit_caching(self):
        """Test toolkit instance caching."""
        manager = ToolkitManager()
        manager.register_external_toolkit("MockToolkit", MockToolkit)

        config = ToolkitConfig(class_name="MockToolkit")

        toolkit1 = manager.get_toolkit("MockToolkit", config)
        toolkit2 = manager.get_toolkit("MockToolkit", config)

        # Should return the same cached instance
        assert toolkit1 is toolkit2

    def test_unknown_toolkit_error(self):
        """Test error for unknown toolkit class."""
        manager = ToolkitManager()
        config = ToolkitConfig(class_name="NonexistentToolkit")

        with pytest.raises(ValueError, match="Unknown toolkit class"):
            manager.get_toolkit("NonexistentToolkit", config)

    def test_config_validation(self):
        """Test toolkit configuration validation."""
        manager = ToolkitManager()

        # Valid config should not raise
        config = ToolkitConfig(class_name="FileToolkit")
        manager.validate_toolkit_config(config)

        # Invalid class name should raise
        invalid_config = ToolkitConfig(class_name="NonexistentToolkit")
        with pytest.raises(ValueError):
            manager.validate_toolkit_config(invalid_config)


class TestToolkitConfig:
    """Test ToolkitConfig functionality."""

    def test_basic_config(self):
        """Test basic configuration creation."""
        config = ToolkitConfig(
            class_name="TestToolkit",
            enabled=False,
            include_tools=["tool1"],
            exclude_tools=["tool2"],
            toolkit_config={"param": "value"},
        )

        assert config.class_name == "TestToolkit"
        assert config.enabled is False
        assert config.include_tools == ["tool1"]
        assert config.exclude_tools == ["tool2"]
        assert config.toolkit_config == {"param": "value"}

    def test_default_values(self):
        """Test configuration default values."""
        config = ToolkitConfig(class_name="TestToolkit")

        assert config.enabled is True
        assert config.include_tools == []
        assert config.exclude_tools == []
        assert config.toolkit_config == {}


if __name__ == "__main__":
    pytest.main([__file__])
