"""Test cases reproducing toolkit injection bugs."""

import pytest
from unittest.mock import Mock, MagicMock, patch
from roma_dspy.tools.base.manager import ToolkitManager
from roma_dspy.tools.base.base import BaseToolkit
from roma_dspy.core.modules.base_module import BaseModule
from roma_dspy.core.engine.runtime import ModuleRuntime
from roma_dspy.core.registry import AgentRegistry
from roma_dspy.types import AgentType
from roma_dspy.config.schemas.toolkit import ToolkitConfig


class MockToolkitA(BaseToolkit):
    """Mock toolkit A with get_price tool."""

    def _setup_dependencies(self) -> None:
        """No dependencies needed for mock."""
        pass

    def _initialize_tools(self) -> None:
        """Initialize mock toolkit A."""
        pass

    def get_price(self):
        """Get price from source A"""
        return 100.0


class MockToolkitB(BaseToolkit):
    """Mock toolkit B with get_price tool (name collision)."""

    def _setup_dependencies(self) -> None:
        """No dependencies needed for mock."""
        pass

    def _initialize_tools(self) -> None:
        """Initialize mock toolkit B."""
        pass

    def get_price(self):
        """Get price from source B"""
        return 200.0


class TestToolkitInjectionBugs:
    """Test cases for toolkit injection crashes and tool name collisions."""

    @pytest.fixture
    def toolkit_manager(self):
        """Create a fresh ToolkitManager instance."""
        manager = ToolkitManager()
        # Clear any existing registrations
        manager._toolkit_registry.clear()
        manager._execution_cache.clear()
        # Register our mock toolkits
        manager.register_external_toolkit("MockToolkitA", MockToolkitA)
        manager.register_external_toolkit("MockToolkitB", MockToolkitB)
        return manager

    @pytest.fixture
    def mock_file_storage(self):
        """Create a mock FileStorage."""
        storage = Mock()
        storage.get_artifacts_path.return_value = "/tmp/artifacts"
        return storage

    @pytest.fixture
    def mock_agent(self):
        """Create a mock agent (BaseModule instance)."""
        agent = Mock(spec=BaseModule)
        agent._tools = {}  # This expects a dict
        return agent

    def test_bug1_toolkit_injection_type_mismatch(
        self, toolkit_manager, mock_file_storage, mock_agent
    ):
        """
        BUG 1: ToolkitManager assigns a list to agent._tools, but BaseModule expects a dict.

        This test demonstrates the TypeError that occurs when BaseModule.tools property
        tries to convert a list of functions to a dict.
        """
        # Setup toolkit configs
        configs = [
            ToolkitConfig(class_name="MockToolkitA", enabled=True, toolkit_config={})
        ]

        # Get tools for execution (returns a list)
        import asyncio

        tools_list = asyncio.run(
            toolkit_manager.get_tools_for_execution(
                execution_id="test_exec_1",
                file_storage=mock_file_storage,
                toolkit_configs=configs,
            )
        )

        # Verify we get a list of tools
        assert isinstance(tools_list, list), (
            "get_tools_for_execution should return a list"
        )
        assert len(tools_list) == 1, "Should have one tool from MockToolkitA"

        # Now simulate what happens in ToolkitManager.setup_for_execution (line 567)
        mock_agent._tools = tools_list  # Assigning list to _tools

        # Create a real BaseModule to test the property
        from roma_dspy.core.signatures import AtomizerSignature

        real_module = BaseModule(
            signature=AtomizerSignature,
            model="gpt-4",
            prediction_strategy="chain_of_thought",
        )
        real_module._tools = tools_list  # Simulate the injection

        # This should raise TypeError when dict() tries to convert the list
        with pytest.raises(TypeError) as exc_info:
            _ = real_module.tools  # This calls dict(self._tools)

        assert (
            "cannot convert dictionary update sequence element"
            in str(exc_info.value).lower()
        )

    def test_bug2_tool_name_collisions(self, toolkit_manager, mock_file_storage):
        """
        BUG 2: Tool name collisions when multiple toolkits have the same function names.

        When _get_tools_from_cache returns only values and BaseModule._get_execution_tools
        rebuilds the dict using tool.__name__, tools with the same name overwrite each other.
        """
        # Setup configs for both toolkits
        configs = [
            ToolkitConfig(class_name="MockToolkitA", enabled=True, toolkit_config={}),
            ToolkitConfig(class_name="MockToolkitB", enabled=True, toolkit_config={}),
        ]

        # Get tools for execution
        import asyncio

        tools_list = asyncio.run(
            toolkit_manager.get_tools_for_execution(
                execution_id="test_exec_2",
                file_storage=mock_file_storage,
                toolkit_configs=configs,
            )
        )

        # We should get 2 tools (one from each toolkit)
        assert len(tools_list) == 2, "Should have tools from both toolkits"

        # Now simulate what BaseModule._get_execution_tools does (lines 362-366)
        tools_dict = {}
        for tool in tools_list:
            tool_name = getattr(tool, "__name__", str(tool))
            tools_dict[tool_name] = tool

        # Both tools have the same __name__ ('get_price'), so one overwrites the other
        assert len(tools_dict) == 1, "Name collision causes one tool to be lost"
        assert "get_price" in tools_dict

        # We can't tell which toolkit's get_price survived - one is silently dropped!
        # This is the bug - we've lost one of the tools due to name collision

    def test_module_runtime_crash_with_list_tools(self, mock_agent):
        """
        Test that ModuleRuntime._get_tools_data crashes when agent._tools is a list.

        This simulates what happens after ToolkitManager incorrectly assigns a list.
        """
        # Create ModuleRuntime
        registry = Mock(spec=AgentRegistry)
        runtime = ModuleRuntime(registry)

        # Setup agent with list instead of dict (simulating the bug)
        def mock_tool():
            """Mock tool function"""
            pass

        mock_agent._tools = [mock_tool]  # List instead of dict

        # Make the tools property raise TypeError (as it would with a real BaseModule)
        mock_agent.tools = property(lambda self: dict(self._tools))

        # This should crash when trying to iterate tools_dict.items()
        with pytest.raises(TypeError):
            _ = runtime._get_tools_data(mock_agent)

    def test_proposed_fix_normalize_tools(self):
        """
        Test that BaseModule._normalize_tools correctly handles list input.

        This demonstrates the fix: using _normalize_tools before assignment.
        """

        # Test that _normalize_tools converts list to dict correctly
        def tool1():
            """Tool 1"""
            pass

        def tool2():
            """Tool 2"""
            pass

        tools_list = [tool1, tool2]
        normalized = BaseModule._normalize_tools(tools_list)

        assert isinstance(normalized, dict)
        assert "tool1" in normalized
        assert "tool2" in normalized
        assert normalized["tool1"] is tool1
        assert normalized["tool2"] is tool2

    def test_proposed_fix_preserve_tool_names(self, toolkit_manager, mock_file_storage):
        """
        Test proposed fix: preserve original tool names from get_enabled_tools.

        Instead of discarding names and using __name__, keep the original mapping.
        """
        # Setup configs for both toolkits
        configs = [
            ToolkitConfig(class_name="MockToolkitA", enabled=True, toolkit_config={}),
            ToolkitConfig(class_name="MockToolkitB", enabled=True, toolkit_config={}),
        ]

        # Proposed fix: modify _get_tools_from_cache to return dict
        def fixed_get_tools_from_cache(cache_key: str) -> dict:
            """Fixed version that preserves tool names."""
            toolkits = toolkit_manager._execution_cache[cache_key].values()
            tools = {}
            for toolkit in toolkits:
                enabled_tools = toolkit.get_enabled_tools()
                if isinstance(enabled_tools, dict):
                    # Keep the original names instead of discarding them
                    tools.update(enabled_tools)
                else:
                    # Fallback for non-dict (shouldn't happen with BaseToolkit)
                    for idx, tool in enumerate(enabled_tools):
                        tool_name = getattr(tool, "__name__", f"tool_{idx}")
                        tools[tool_name] = tool
            return tools

        # First, populate the cache
        import asyncio

        asyncio.run(
            toolkit_manager.get_tools_for_execution(
                execution_id="test_exec_3",
                file_storage=mock_file_storage,
                toolkit_configs=configs,
            )
        )

        # Get cache key
        cache_key = toolkit_manager._get_execution_cache_key("test_exec_3", configs)

        # Use the fixed version
        tools_dict = fixed_get_tools_from_cache(cache_key)

        # Now both tools should be preserved with unique names
        assert isinstance(tools_dict, dict)
        assert "get_price" in tools_dict  # Only one will remain due to collision
        assert len(tools_dict) == 2, "Both tools preserved with unique names"

        # The fixed version should have both tools preserved
        # Let's verify the expected behavior after the fix
