"""
Context models for ROMA-DSPy agent execution.

This module defines Pydantic models for building execution context that is passed to
all DSPy agents. Each model has extensive Field documentation to make the system
self-documenting and maintainable.

The context system follows a hierarchical structure:
1. FundamentalContext: Shared by all agents
2. Agent-specific contexts: Additional context for specific agent types

All models provide `to_xml()` methods for serialization to XML format optimized for LLM comprehension.
"""

from pydantic import BaseModel, Field
from datetime import datetime
from typing import List, Optional
from pathlib import Path

from roma_dspy.types.artifact_models import ArtifactReference


# ==================== Fundamental Context Components ====================


class TemporalContext(BaseModel):
    """
    Temporal information for date-aware and time-sensitive reasoning.

    This context helps agents understand the current time frame for tasks like:
    - Analyzing time-series data
    - Making time-relative decisions (e.g., "recent", "last month")
    - Scheduling or temporal planning
    - Date-sensitive retrieval or filtering

    Example use cases:
    - "Analyze Bitcoin price trends in the last 7 days" (needs current_date)
    - "What's the current year's best performing tokens?" (needs current_year)
    - "Schedule task execution for next week" (needs current_timestamp)
    """

    current_date: str = Field(
        ...,
        description="Current date in YYYY-MM-DD format for date-aware operations",
        examples=["2025-10-05"]
    )
    current_year: int = Field(
        ...,
        description="Current year for year-relative comparisons and filtering",
        examples=[2025]
    )
    current_timestamp: str = Field(
        ...,
        description="ISO 8601 timestamp with timezone for precise temporal operations",
        examples=["2025-10-05T14:30:22.123456+00:00"]
    )

    def to_xml(self) -> str:
        """Serialize to XML format for LLM consumption."""
        return f"""<temporal>
  <current_date>{self.current_date}</current_date>
  <current_year>{self.current_year}</current_year>
  <current_timestamp>{self.current_timestamp}</current_timestamp>
</temporal>"""


class FileSystemContext(BaseModel):
    """
    File system paths and storage information for file operations.

    This context provides agents with complete knowledge of where to store and retrieve files
    within the execution-scoped storage system. All paths are scoped to the execution_id
    to ensure isolation between different executions.

    Example use cases:
    - "Save analysis results to a file" → artifacts_path
    - "Load previously cached data" → base_directory
    - "Generate report and write to outputs/" → reports_path or outputs_path
    - "Create temporary processing files" → temp_path
    - "Save plots from analysis" → plots_path

    Path hierarchy:
        {base_path}/executions/{execution_id}/
        ├── artifacts/      # General artifacts
        ├── temp/           # Temporary files
        ├── results/        # Execution results
        │   ├── plots/      # Plot outputs
        │   └── reports/    # Report outputs
        ├── outputs/        # Agent outputs
        └── logs/           # Execution logs
    """

    execution_id: str = Field(
        ...,
        description="Unique identifier for this execution run, used for storage isolation",
        examples=["20251005_143022_abc12345"]
    )
    base_directory: str = Field(
        ...,
        description="Root directory for all execution-scoped files ({base_path}/executions/{execution_id})",
        examples=["/opt/sentient/executions/20251005_143022_abc12345"]
    )
    artifacts_path: str = Field(
        ...,
        description="Path for general artifacts (Parquet files, CSV exports, etc.)",
        examples=["/opt/sentient/executions/20251005_143022_abc12345/artifacts"]
    )
    temp_path: str = Field(
        ...,
        description="Path for temporary files (auto-cleaned after execution)",
        examples=["/opt/sentient/executions/20251005_143022_abc12345/temp"]
    )
    results_path: str = Field(
        ...,
        description="Path for execution results",
        examples=["/opt/sentient/executions/20251005_143022_abc12345/results"]
    )
    plots_path: str = Field(
        ...,
        description="Path for plot outputs (charts, visualizations)",
        examples=["/opt/sentient/executions/20251005_143022_abc12345/results/plots"]
    )
    reports_path: str = Field(
        ...,
        description="Path for report outputs (analysis summaries, findings)",
        examples=["/opt/sentient/executions/20251005_143022_abc12345/results/reports"]
    )
    outputs_path: str = Field(
        ...,
        description="Path for general agent outputs",
        examples=["/opt/sentient/executions/20251005_143022_abc12345/outputs"]
    )
    logs_path: str = Field(
        ...,
        description="Path for execution logs",
        examples=["/opt/sentient/executions/20251005_143022_abc12345/logs"]
    )

    @classmethod
    def from_file_storage(cls, file_storage: "FileStorage") -> "FileSystemContext":
        """Create FileSystemContext from FileStorage instance.

        Args:
            file_storage: FileStorage instance for this execution

        Returns:
            FileSystemContext with all paths populated
        """
        return cls(
            execution_id=file_storage.execution_id,
            base_directory=str(file_storage.root),
            artifacts_path=str(file_storage.get_artifacts_path()),
            temp_path=str(file_storage.get_temp_path()),
            results_path=str(file_storage.get_results_path()),
            plots_path=str(file_storage.get_plots_path()),
            reports_path=str(file_storage.get_reports_path()),
            outputs_path=str(file_storage.get_outputs_path()),
            logs_path=str(file_storage.get_logs_path()),
        )

    def to_xml(self) -> str:
        """Serialize to XML format with all paths for agent use."""
        return f"""<file_system execution_id="{self.execution_id}">
  <base_directory>{self.base_directory}</base_directory>
  <paths>
    <artifacts>{self.artifacts_path}</artifacts>
    <temp>{self.temp_path}</temp>
    <results>{self.results_path}</results>
    <plots>{self.plots_path}</plots>
    <reports>{self.reports_path}</reports>
    <outputs>{self.outputs_path}</outputs>
    <logs>{self.logs_path}</logs>
  </paths>
  <usage_notes>
    <note>CRITICAL: ALWAYS save generated files (CSV, Parquet, plots, reports) to the provided paths above. DO NOT use /tmp/ or other temporary directories.</note>
    <note>All paths are absolute and ready to use in generated code</note>
    <note>Paths are automatically created and isolated by execution_id</note>
    <note>Use artifacts_path for storing large data files (Parquet, CSV)</note>
    <note>Use temp_path for intermediate processing files</note>
    <note>Use plots_path for visualization outputs</note>
    <note>Use reports_path for analysis reports</note>
    <note>E2B Sandbox: All files are already available at these paths - no download or file transfer operations needed. Directly access files using provided paths.</note>
  </usage_notes>
</file_system>"""


class RecursionContext(BaseModel):
    """
    Recursion depth tracking for task decomposition control.

    This context helps agents understand their position in the task decomposition hierarchy
    and whether they should continue decomposing or execute directly. Critical for preventing
    infinite recursion and ensuring tasks bottom out.

    Example use cases:
    - Atomizer deciding whether task is atomic or needs decomposition
    - Planner understanding decomposition limits
    - Agents adjusting complexity based on remaining depth

    at_limit=True signals that task MUST be executed directly, no further decomposition.
    """

    current_depth: int = Field(
        ...,
        description="Current recursion depth (0 = root task)",
        examples=[0, 1, 2],
        ge=0
    )
    max_depth: int = Field(
        ...,
        description="Maximum allowed recursion depth before forced execution",
        examples=[2, 3, 5],
        gt=0
    )
    at_limit: bool = Field(
        ...,
        description="True if at max depth - task MUST be executed directly, no decomposition"
    )

    def to_xml(self) -> str:
        """Serialize to XML format with clear limit semantics."""
        return f"""<recursion>
  <current_depth>{self.current_depth}</current_depth>
  <max_depth>{self.max_depth}</max_depth>
  <at_limit>{str(self.at_limit).lower()}</at_limit>
</recursion>"""


class ToolInfo(BaseModel):
    """
    Information about a single available tool.

    Tools are functions or methods that agents can invoke to perform specific actions
    like API calls, computations, or data transformations.
    """

    name: str = Field(..., description="Tool name/identifier", examples=["search_web", "calculate", "get_token_price"])
    description: str = Field(..., description="What the tool does and when to use it")


class ToolsContext(BaseModel):
    """
    Available tools and capabilities for this agent.

    This context informs agents about what tools they have access to for task execution.
    Different agent configurations may have different toolkits (e.g., search tools, calculation
    tools, API tools).

    Example use cases:
    - Executor choosing which tool to use for a task
    - Agent planning tool usage strategy
    - Understanding capabilities for task feasibility assessment

    Empty tools list means the agent operates in pure reasoning mode without external tools.
    """

    tools: List[ToolInfo] = Field(
        default_factory=list,
        description="List of available tools with descriptions"
    )

    def to_xml(self) -> str:
        """Serialize to XML format with tool catalog."""
        if not self.tools:
            return "<available_tools>No tools available</available_tools>"

        xml_parts = ['<available_tools>']
        for tool in self.tools:
            xml_parts.append(f'  <tool name="{tool.name}">')
            xml_parts.append(f'    <description>{self._escape_xml(tool.description)}</description>')
            xml_parts.append(f'  </tool>')
        xml_parts.append('</available_tools>')
        return '\n'.join(xml_parts)

    @staticmethod
    def _escape_xml(text: str) -> str:
        """Escape XML special characters to prevent parsing errors."""
        return (text
            .replace('&', '&amp;')
            .replace('<', '&lt;')
            .replace('>', '&gt;')
            .replace('"', '&quot;')
            .replace("'", '&apos;'))


class FundamentalContext(BaseModel):
    """
    Fundamental context shared by all agents in an execution.

    This is the base context that every agent receives, regardless of type. It provides
    essential information about the execution environment, available capabilities, and
    the overall objective being pursued.

    Components:
    - overall_objective: The root goal this execution is trying to achieve
    - temporal: Date/time information for temporal reasoning
    - recursion: Depth tracking for decomposition control
    - tools: Available tools/capabilities
    - file_system: File storage paths (optional, only for agents that need file operations)

    This context is constructed once per agent invocation and passed as XML to the
    agent's DSPy signature.
    """

    overall_objective: str = Field(
        ...,
        description="The root goal of this execution, for alignment and context",
        examples=["Analyze Bitcoin market trends and generate investment report"]
    )
    temporal: TemporalContext = Field(
        ...,
        description="Current date/time for temporal reasoning"
    )
    recursion: RecursionContext = Field(
        ...,
        description="Recursion depth tracking for decomposition control"
    )
    # tools: ToolsContext = Field(
    #     ...,
    #     description="Available tools and capabilities"
    # )
    file_system: Optional[FileSystemContext] = Field(
        default=None,
        description="File storage context (only included for agents that perform file operations)"
    )

    def to_xml(self) -> str:
        """Serialize to hierarchical XML format optimized for LLM comprehension."""
        xml_parts = [
            '<fundamental_context>',
            f'  <overall_objective>{self._escape_xml(self.overall_objective)}</overall_objective>',
            '  ' + self.temporal.to_xml().replace('\n', '\n  '),
            '  ' + self.recursion.to_xml().replace('\n', '\n  '),
            # DISABLED: Tools now handled by DSPy natively to avoid duplication
            # '  ' + self.tools.to_xml().replace('\n', '\n  '),
        ]

        if self.file_system:
            xml_parts.append('  ' + self.file_system.to_xml().replace('\n', '\n  '))

        xml_parts.append('</fundamental_context>')
        return '\n'.join(xml_parts)

    @staticmethod
    def _escape_xml(text: str) -> str:
        """Escape XML special characters to prevent parsing errors."""
        return (text
            .replace('&', '&amp;')
            .replace('<', '&lt;')
            .replace('>', '&gt;')
            .replace('"', '&quot;')
            .replace("'", '&apos;'))


# ==================== Agent-Specific Context Components ====================


class DependencyResult(BaseModel):
    """
    Result from a dependency task that the current task builds upon.

    Dependencies represent tasks that must complete before the current task can execute.
    Their results provide input data or context that the current task uses.

    Example:
    - Task A: "Fetch Bitcoin price data" → produces price data
    - Task B: "Analyze Bitcoin trends" (depends on A) → uses price data from A
    """

    goal: str = Field(
        ...,
        description="What the dependency task was trying to achieve",
        examples=["Fetch Bitcoin price data for last 30 days"]
    )
    output: str = Field(
        ...,
        description="The result produced by the dependency task",
        examples=["Price data: $65,432.10 on 2025-10-05, ..."]
    )


class ExecutorSpecificContext(BaseModel):
    """
    Context specific to Executor agents for atomic task execution.

    Executors perform actual work (API calls, computations, tool usage). They often
    depend on results from previous tasks. This context provides those dependency results
    and any artifacts created by dependencies so the executor can build upon prior work.

    Example use case:
    - Current task: "Analyze the price data"
    - Dependency: "Fetch price data" (already completed)
    - This context provides:
      1. Text result from dependency
      2. Artifacts created by dependency (e.g., price_data.parquet)

    Empty dependency_results and available_artifacts means this is an independent task.
    """

    dependency_results: List[DependencyResult] = Field(
        default_factory=list,
        description="Results from tasks this task depends on, provided as input context"
    )
    available_artifacts: List[ArtifactReference] = Field(
        default_factory=list,
        description="Artifacts created by dependency tasks, available for use in this task"
    )

    def to_xml(self) -> str:
        """Serialize dependency results and artifacts to XML for executor consumption."""
        if not self.dependency_results and not self.available_artifacts:
            return "<executor_specific>No dependencies or artifacts</executor_specific>"

        xml_parts = ['<executor_specific>']

        # Dependency results section
        if self.dependency_results:
            xml_parts.append('  <dependency_results>')
            for dep in self.dependency_results:
                xml_parts.append('    <dependency>')
                xml_parts.append(f'      <goal>{self._escape_xml(dep.goal)}</goal>')
                xml_parts.append(f'      <output>{self._escape_xml(dep.output)}</output>')
                xml_parts.append('    </dependency>')
            xml_parts.append('  </dependency_results>')

        # Available artifacts section
        if self.available_artifacts:
            xml_parts.append('  <available_artifacts>')
            for artifact in self.available_artifacts:
                xml_parts.append(f'    {artifact.to_xml_element()}')
            xml_parts.append('  </available_artifacts>')

        xml_parts.append('</executor_specific>')
        return '\n'.join(xml_parts)

    @staticmethod
    def _escape_xml(text: str) -> str:
        """Escape XML special characters."""
        return FundamentalContext._escape_xml(text)


class ParentResult(BaseModel):
    """
    Result from the parent task in the decomposition hierarchy.

    Parent tasks are decomposed into subtasks. The parent's planning and context
    can guide how subtasks should be approached.
    """

    goal: str = Field(..., description="Parent task's goal")
    result: str = Field(..., description="Parent task's result or planning output")


class SiblingResult(BaseModel):
    """
    Result from a sibling task (another subtask of the same parent).

    Siblings are tasks at the same level of decomposition. Their results can help
    coordinate work and avoid duplication.
    """

    goal: str = Field(..., description="Sibling task's goal")
    result: str = Field(..., description="Sibling task's result")


class PlannerSpecificContext(BaseModel):
    """
    Context specific to Planner agents for task decomposition.

    Planners break complex tasks into subtasks. They benefit from understanding:
    - Parent task context: What larger goal are we decomposing?
    - Sibling results: What work has already been done at this level?
    - Available artifacts: What data/outputs exist from parent/sibling tasks?

    This helps planners:
    - Maintain consistency with parent's intent
    - Avoid duplicating work done by siblings
    - Coordinate subtask planning across the decomposition tree
    - Understand what artifacts are available for subtasks to use

    Example use case:
    - Parent: "Analyze crypto market" decomposed into 3 subtasks
    - Subtask 1 & 2 already completed, created data artifacts
    - Subtask 3's planner sees siblings' results and artifacts to avoid duplication
    """

    parent_results: List[ParentResult] = Field(
        default_factory=list,
        description="Results from parent task(s) for context and alignment"
    )
    sibling_results: List[SiblingResult] = Field(
        default_factory=list,
        description="Results from sibling tasks for coordination and avoiding duplication"
    )
    available_artifacts: List[ArtifactReference] = Field(
        default_factory=list,
        description="Artifacts created by parent/sibling tasks, visible for planning decisions"
    )

    def to_xml(self) -> str:
        """Serialize parent, sibling context, and artifacts to XML."""
        xml_parts = ['<planner_specific>']

        # Parent results
        if self.parent_results:
            xml_parts.append('  <parent_results>')
            for parent in self.parent_results:
                xml_parts.append('    <parent>')
                xml_parts.append(f'      <goal>{self._escape_xml(parent.goal)}</goal>')
                xml_parts.append(f'      <result>{self._escape_xml(parent.result)}</result>')
                xml_parts.append('    </parent>')
            xml_parts.append('  </parent_results>')

        # Sibling results
        if self.sibling_results:
            xml_parts.append('  <sibling_results>')
            for sibling in self.sibling_results:
                xml_parts.append('    <sibling>')
                xml_parts.append(f'      <goal>{self._escape_xml(sibling.goal)}</goal>')
                xml_parts.append(f'      <result>{self._escape_xml(sibling.result)}</result>')
                xml_parts.append('    </sibling>')
            xml_parts.append('  </sibling_results>')

        # Available artifacts
        if self.available_artifacts:
            xml_parts.append('  <available_artifacts>')
            for artifact in self.available_artifacts:
                xml_parts.append(f'    {artifact.to_xml_element()}')
            xml_parts.append('  </available_artifacts>')

        xml_parts.append('</planner_specific>')
        return '\n'.join(xml_parts)

    @staticmethod
    def _escape_xml(text: str) -> str:
        """Escape XML special characters."""
        return FundamentalContext._escape_xml(text)


class AggregatorSpecificContext(BaseModel):
    """
    Context specific to Aggregator agents for synthesizing subtask results.

    Aggregators combine multiple subtask results into a cohesive output. They need to see:
    - Available artifacts: Data/outputs created by subtasks during execution

    This enables aggregators to:
    - Reference artifacts created by subtasks in their synthesis
    - Include artifact metadata in final outputs
    - Create comprehensive reports that link to generated data/plots

    Example use case:
    - Parent task: "Analyze crypto market" decomposed into 3 subtasks
    - Subtask 1: "Fetch price data" → creates price_data.parquet
    - Subtask 2: "Analyze trends" → creates trend_analysis.md
    - Subtask 3: "Generate plot" → creates price_chart.png
    - Aggregator sees all 3 artifacts to create comprehensive final report
    """

    available_artifacts: List[ArtifactReference] = Field(
        default_factory=list,
        description="Artifacts created by subtasks, available for synthesis"
    )

    def to_xml(self) -> str:
        """Serialize artifacts to XML for aggregator consumption."""
        if not self.available_artifacts:
            return "<aggregator_specific>No artifacts from subtasks</aggregator_specific>"

        xml_parts = ['<aggregator_specific>']
        xml_parts.append('  <available_artifacts>')
        for artifact in self.available_artifacts:
            xml_parts.append(f'    {artifact.to_xml_element()}')
        xml_parts.append('  </available_artifacts>')
        xml_parts.append('</aggregator_specific>')
        return '\n'.join(xml_parts)

    @staticmethod
    def _escape_xml(text: str) -> str:
        """Escape XML special characters."""
        return FundamentalContext._escape_xml(text)
