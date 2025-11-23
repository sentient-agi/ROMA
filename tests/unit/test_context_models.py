"""Unit tests for context models."""

import pytest
from datetime import datetime, UTC
from pathlib import Path

from roma_dspy.core.context.models import (
    TemporalContext,
    FileSystemContext,
    RecursionContext,
    ToolInfo,
    ToolsContext,
    FundamentalContext,
    DependencyResult,
    ExecutorSpecificContext,
    ParentResult,
    SiblingResult,
    PlannerSpecificContext,
)


class TestTemporalContext:
    """Test TemporalContext model."""

    def test_create_temporal_context(self):
        """Test creating temporal context."""
        now = datetime.now(UTC)
        context = TemporalContext(
            current_date=now.strftime("%Y-%m-%d"),
            current_year=now.year,
            current_timestamp=now.isoformat(),
        )

        assert context.current_date == now.strftime("%Y-%m-%d")
        assert context.current_year == now.year
        assert context.current_timestamp == now.isoformat()

    def test_temporal_context_to_xml(self):
        """Test XML serialization."""
        context = TemporalContext(
            current_date="2025-10-05",
            current_year=2025,
            current_timestamp="2025-10-05T14:30:22.123456+00:00",
        )

        xml = context.to_xml()
        assert "<temporal>" in xml
        assert "<current_date>2025-10-05</current_date>" in xml
        assert "<current_year>2025</current_year>" in xml
        assert (
            "<current_timestamp>2025-10-05T14:30:22.123456+00:00</current_timestamp>"
            in xml
        )
        assert "</temporal>" in xml


class TestFileSystemContext:
    """Test FileSystemContext model."""

    def test_create_file_system_context(self):
        """Test creating file system context."""
        context = FileSystemContext(
            execution_id="test_exec_123",
            base_directory=Path("/data/executions/test_exec_123"),
        )

        assert context.execution_id == "test_exec_123"
        assert context.base_directory == Path("/data/executions/test_exec_123")

    def test_file_system_context_to_xml(self):
        """Test XML serialization with usage instructions."""
        context = FileSystemContext(
            execution_id="test_exec_123",
            base_directory=Path("/data/executions/test_exec_123"),
        )

        xml = context.to_xml()
        assert 'execution_id="test_exec_123"' in xml
        assert "<file_system" in xml
        assert "<instruction>" in xml
        assert "FileStorage methods" in xml
        assert "<base_directory>" in xml


class TestRecursionContext:
    """Test RecursionContext model."""

    def test_create_recursion_context(self):
        """Test creating recursion context."""
        context = RecursionContext(current_depth=2, max_depth=5, at_limit=False)

        assert context.current_depth == 2
        assert context.max_depth == 5
        assert context.at_limit is False

    def test_recursion_context_at_limit(self):
        """Test at_limit flag."""
        context = RecursionContext(current_depth=5, max_depth=5, at_limit=True)

        assert context.at_limit is True

    def test_recursion_context_to_xml(self):
        """Test XML serialization."""
        context = RecursionContext(current_depth=2, max_depth=5, at_limit=False)

        xml = context.to_xml()
        assert "<recursion>" in xml
        assert "<current_depth>2</current_depth>" in xml
        assert "<max_depth>5</max_depth>" in xml
        assert "<at_limit>false</at_limit>" in xml


class TestToolsContext:
    """Test ToolsContext model."""

    def test_create_empty_tools_context(self):
        """Test creating empty tools context."""
        context = ToolsContext(tools=[])

        assert context.tools == []

    def test_create_tools_context_with_tools(self):
        """Test creating tools context with tools."""
        tools = [
            ToolInfo(name="search_web", description="Search the web for information"),
            ToolInfo(name="calculate", description="Perform mathematical calculations"),
        ]
        context = ToolsContext(tools=tools)

        assert len(context.tools) == 2
        assert context.tools[0].name == "search_web"
        assert context.tools[1].name == "calculate"

    def test_tools_context_to_xml_empty(self):
        """Test XML serialization with no tools."""
        context = ToolsContext(tools=[])

        xml = context.to_xml()
        assert xml == "<available_tools>No tools available</available_tools>"

    def test_tools_context_to_xml_with_tools(self):
        """Test XML serialization with tools."""
        tools = [
            ToolInfo(name="search_web", description="Search the web"),
            ToolInfo(name="calculate", description="Do math"),
        ]
        context = ToolsContext(tools=tools)

        xml = context.to_xml()
        assert "<available_tools>" in xml
        assert '<tool name="search_web">' in xml
        assert "<description>Search the web</description>" in xml
        assert '<tool name="calculate">' in xml
        assert "<description>Do math</description>" in xml

    def test_tools_context_xml_escaping(self):
        """Test that special XML characters are escaped."""
        tools = [
            ToolInfo(name="test", description='Description with <special> & "chars"')
        ]
        context = ToolsContext(tools=tools)

        xml = context.to_xml()
        assert "&lt;special&gt;" in xml
        assert "&amp;" in xml
        assert "&quot;" in xml


class TestFundamentalContext:
    """Test FundamentalContext model."""

    def test_create_fundamental_context(self):
        """Test creating fundamental context."""
        temporal = TemporalContext(
            current_date="2025-10-05",
            current_year=2025,
            current_timestamp="2025-10-05T14:30:22+00:00",
        )
        recursion = RecursionContext(current_depth=1, max_depth=3, at_limit=False)
        tools = ToolsContext(tools=[])

        context = FundamentalContext(
            overall_objective="Analyze Bitcoin trends",
            temporal=temporal,
            recursion=recursion,
            tools=tools,
        )

        assert context.overall_objective == "Analyze Bitcoin trends"
        assert context.temporal == temporal
        assert context.recursion == recursion
        assert context.tools == tools
        assert context.file_system is None

    def test_fundamental_context_with_file_system(self):
        """Test fundamental context with file system."""
        temporal = TemporalContext(
            current_date="2025-10-05",
            current_year=2025,
            current_timestamp="2025-10-05T14:30:22+00:00",
        )
        recursion = RecursionContext(current_depth=1, max_depth=3, at_limit=False)
        tools = ToolsContext(tools=[])
        file_system = FileSystemContext(
            execution_id="exec_123", base_directory=Path("/data/executions/exec_123")
        )

        context = FundamentalContext(
            overall_objective="Test task",
            temporal=temporal,
            recursion=recursion,
            tools=tools,
            file_system=file_system,
        )

        assert context.file_system is not None
        assert context.file_system.execution_id == "exec_123"

    def test_fundamental_context_to_xml(self):
        """Test XML serialization."""
        temporal = TemporalContext(
            current_date="2025-10-05",
            current_year=2025,
            current_timestamp="2025-10-05T14:30:22+00:00",
        )
        recursion = RecursionContext(current_depth=1, max_depth=3, at_limit=False)
        tools = ToolsContext(tools=[])

        context = FundamentalContext(
            overall_objective="Test objective",
            temporal=temporal,
            recursion=recursion,
            tools=tools,
        )

        xml = context.to_xml()
        assert "<fundamental_context>" in xml
        assert "<overall_objective>Test objective</overall_objective>" in xml
        assert "<temporal>" in xml
        assert "<recursion>" in xml
        assert "<available_tools>" in xml
        assert "</fundamental_context>" in xml

    def test_fundamental_context_xml_escaping(self):
        """Test XML escaping in overall_objective."""
        temporal = TemporalContext(
            current_date="2025-10-05",
            current_year=2025,
            current_timestamp="2025-10-05T14:30:22+00:00",
        )
        recursion = RecursionContext(current_depth=1, max_depth=3, at_limit=False)
        tools = ToolsContext(tools=[])

        context = FundamentalContext(
            overall_objective='Test with <special> & "chars"',
            temporal=temporal,
            recursion=recursion,
            tools=tools,
        )

        xml = context.to_xml()
        assert "&lt;special&gt;" in xml
        assert "&amp;" in xml
        assert "&quot;" in xml


class TestExecutorSpecificContext:
    """Test ExecutorSpecificContext model."""

    def test_create_empty_executor_context(self):
        """Test creating executor context with no dependencies."""
        context = ExecutorSpecificContext(dependency_results=[])

        assert context.dependency_results == []

    def test_create_executor_context_with_dependencies(self):
        """Test creating executor context with dependency results."""
        deps = [
            DependencyResult(
                goal="Fetch Bitcoin price data", output="Price data: $65,432.10"
            ),
            DependencyResult(
                goal="Fetch Ethereum price data", output="Price data: $3,245.67"
            ),
        ]
        context = ExecutorSpecificContext(dependency_results=deps)

        assert len(context.dependency_results) == 2
        assert context.dependency_results[0].goal == "Fetch Bitcoin price data"

    def test_executor_context_to_xml_empty(self):
        """Test XML serialization with no dependencies."""
        context = ExecutorSpecificContext(dependency_results=[])

        xml = context.to_xml()
        assert xml == "<executor_specific>No dependencies</executor_specific>"

    def test_executor_context_to_xml_with_dependencies(self):
        """Test XML serialization with dependencies."""
        deps = [DependencyResult(goal="Fetch data", output="Data result")]
        context = ExecutorSpecificContext(dependency_results=deps)

        xml = context.to_xml()
        assert "<executor_specific>" in xml
        assert "<dependency_results>" in xml
        assert "<dependency>" in xml
        assert "<goal>Fetch data</goal>" in xml
        assert "<output>Data result</output>" in xml


class TestPlannerSpecificContext:
    """Test PlannerSpecificContext model."""

    def test_create_empty_planner_context(self):
        """Test creating planner context with no parent/siblings."""
        context = PlannerSpecificContext(parent_results=[], sibling_results=[])

        assert context.parent_results == []
        assert context.sibling_results == []

    def test_create_planner_context_with_data(self):
        """Test creating planner context with parent and siblings."""
        parent = [ParentResult(goal="Parent goal", result="Parent result")]
        siblings = [
            SiblingResult(goal="Sibling 1", result="Result 1"),
            SiblingResult(goal="Sibling 2", result="Result 2"),
        ]

        context = PlannerSpecificContext(
            parent_results=parent, sibling_results=siblings
        )

        assert len(context.parent_results) == 1
        assert len(context.sibling_results) == 2

    def test_planner_context_to_xml(self):
        """Test XML serialization."""
        parent = [ParentResult(goal="Parent goal", result="Parent result")]
        siblings = [SiblingResult(goal="Sibling goal", result="Sibling result")]

        context = PlannerSpecificContext(
            parent_results=parent, sibling_results=siblings
        )

        xml = context.to_xml()
        assert "<planner_specific>" in xml
        assert "<parent_results>" in xml
        assert "<parent>" in xml
        assert "<goal>Parent goal</goal>" in xml
        assert "<sibling_results>" in xml
        assert "<sibling>" in xml
        assert "<goal>Sibling goal</goal>" in xml

    def test_planner_context_to_xml_empty(self):
        """Test XML serialization with empty lists."""
        context = PlannerSpecificContext(parent_results=[], sibling_results=[])

        xml = context.to_xml()
        assert "<planner_specific>" in xml
        assert "</planner_specific>" in xml
        # Empty lists should not have parent_results or sibling_results sections
        assert "<parent_results>" not in xml
        assert "<sibling_results>" not in xml
