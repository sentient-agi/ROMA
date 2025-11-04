"""
Context Manager for building execution context for ROMA-DSPy agents.

The ContextManager is responsible for:
1. Building Pydantic context models from runtime state
2. Composing fundamental + agent-specific context
3. Serializing to XML strings for DSPy signatures
4. Injecting artifacts into context based on injection mode

It follows the Single Responsibility Principle: one job is context orchestration.
"""

from datetime import datetime, UTC
from typing import List, Optional, TYPE_CHECKING
from roma_dspy.core.context.models import (
    TemporalContext,
    FileSystemContext,
    RecursionContext,
    ToolsContext,
    ToolInfo,
    FundamentalContext,
    ExecutorSpecificContext,
    PlannerSpecificContext,
    AggregatorSpecificContext,
    DependencyResult,
    ParentResult,
    SiblingResult,
)
from roma_dspy.core.artifacts.query_service import ArtifactQueryService
from roma_dspy.core.context.execution_context import ExecutionContext
from roma_dspy.types import TaskStatus
from roma_dspy.types.artifact_injection import ArtifactInjectionMode

if TYPE_CHECKING:
    from ..engine.runtime import ModuleRuntime
    from ..engine.dag import TaskDAG
    from ..signatures.base_models.task_node import TaskNode
    from ..storage import FileStorage


class ContextManager:
    """
    Central context manager that orchestrates context building for all agents.

    Design principles:
    - Uses Pydantic models for type safety and validation
    - Separates data (models) from building logic (this class)
    - Returns XML strings ready for DSPy signatures
    - Follows DRY: shared components built once, composed differently per agent

    Usage:
        manager = ContextManager(file_storage, overall_objective)
        context_xml = manager.build_executor_context(task, tools_data, runtime, dag)
        # Pass context_xml to executor signature
    """

    def __init__(self, file_storage: "FileStorage", overall_objective: str):
        """
        Initialize context manager.

        Args:
            file_storage: FileStorage instance for this execution (provides paths and execution_id)
            overall_objective: Root goal of execution (helps agents align with bigger picture)
        """
        self.file_storage = file_storage
        self.overall_objective = overall_objective
        self._artifact_query_service = ArtifactQueryService()

    # ==================== Component Builders (Private) ====================

    def _build_temporal(self) -> TemporalContext:
        """Build temporal context with current date/time."""
        now = datetime.now(UTC)
        return TemporalContext(
            current_date=now.strftime("%Y-%m-%d"),
            current_year=now.year,
            current_timestamp=now.isoformat()
        )

    def _build_file_system(self) -> FileSystemContext:
        """Build file system context from FileStorage instance."""
        return FileSystemContext.from_file_storage(self.file_storage)

    def _build_recursion(self, task: "TaskNode") -> RecursionContext:
        """Build recursion context from task's depth information."""
        return RecursionContext(
            current_depth=task.depth,
            max_depth=task.max_depth,
            at_limit=task.depth >= task.max_depth
        )

    def _build_tools(self, tools_data: List[dict]) -> ToolsContext:
        """Build tools context from tools data."""
        tools = [ToolInfo(name=t["name"], description=t["description"]) for t in tools_data]
        return ToolsContext(tools=tools)

    def _build_fundamental(
        self,
        task: "TaskNode",
        tools_data: List[dict],
        include_file_system: bool = False
    ) -> FundamentalContext:
        """Build fundamental context available to all agents."""
        return FundamentalContext(
            overall_objective=self.overall_objective,
            temporal=self._build_temporal(),
            recursion=self._build_recursion(task),
            tools=self._build_tools(tools_data),
            file_system=self._build_file_system() if include_file_system else None
        )

    async def _query_artifacts_for_context(
        self,
        task_ids: List[str],
        injection_mode: ArtifactInjectionMode,
        current_task_id: Optional[str] = None,
        dag: Optional["TaskDAG"] = None
    ) -> List:
        """
        Query artifacts based on injection mode.

        Centralized artifact querying logic usable by any agent type.
        This method is DRY - single source of truth for artifact queries.

        Args:
            task_ids: Task IDs to query artifacts from (dependencies, parent, siblings, etc.)
            injection_mode: Controls which artifacts to retrieve
            current_task_id: Current task ID (needed for SUBTASK mode)
            dag: Task DAG (needed for SUBTASK mode to navigate hierarchy)

        Returns:
            List of ArtifactReference objects for context injection
        """
        if injection_mode == ArtifactInjectionMode.NONE:
            return []

        registry = ExecutionContext.get_artifact_registry()
        if not registry:
            return []

        if injection_mode == ArtifactInjectionMode.DEPENDENCIES:
            if not task_ids:
                return []
            return await self._artifact_query_service.get_artifacts_for_dependencies(
                registry=registry,
                dependency_task_ids=task_ids,
                mode=injection_mode
            )
        elif injection_mode == ArtifactInjectionMode.FULL:
            return await self._artifact_query_service.get_all_artifacts(
                registry=registry,
                mode=injection_mode
            )
        elif injection_mode == ArtifactInjectionMode.SUBTASK:
            if not current_task_id or not dag:
                from loguru import logger
                logger.warning(
                    "SUBTASK mode requires current_task_id and dag parameters, "
                    "falling back to empty list"
                )
                return []
            return await self._artifact_query_service.get_artifacts_for_subtask(
                registry=registry,
                dag=dag,
                current_task_id=current_task_id,
                mode=injection_mode
            )

        return []

    async def _build_executor_specific(
        self,
        task: "TaskNode",
        runtime: "ModuleRuntime",
        dag: "TaskDAG",
        injection_mode: ArtifactInjectionMode = ArtifactInjectionMode.DEPENDENCIES
    ) -> ExecutorSpecificContext:
        """
        Build executor-specific context with dependency results and artifacts.

        Args:
            task: Current task node
            runtime: Module runtime for accessing context store
            dag: Task DAG for finding dependency tasks
            injection_mode: Controls which artifacts are injected

        Returns:
            ExecutorSpecificContext with dependency results and artifact references
        """
        dependency_results = []

        if task.dependencies:
            for dep_id in task.dependencies:
                result_str = runtime.context_store.get_result(dep_id)
                if result_str:
                    try:
                        dep_task, _ = dag.find_node(dep_id)
                        dependency_results.append(
                            DependencyResult(goal=dep_task.goal, output=result_str)
                        )
                    except ValueError:
                        pass  # Dependency not found in DAG

        # Query artifacts using centralized method
        available_artifacts = await self._query_artifacts_for_context(
            task_ids=list(task.dependencies) if task.dependencies else [],
            injection_mode=injection_mode,
            current_task_id=task.task_id,
            dag=dag
        )

        return ExecutorSpecificContext(
            dependency_results=dependency_results,
            available_artifacts=available_artifacts
        )

    async def _build_planner_specific(
        self,
        task: "TaskNode",
        runtime: "ModuleRuntime",
        dag: "TaskDAG",
        injection_mode: ArtifactInjectionMode = ArtifactInjectionMode.DEPENDENCIES
    ) -> PlannerSpecificContext:
        """
        Build planner-specific context with parent/sibling results and artifacts.

        Args:
            task: Current task node
            runtime: Module runtime for accessing context store
            dag: Task DAG for finding parent/sibling tasks
            injection_mode: Controls which artifacts are injected

        Returns:
            PlannerSpecificContext with parent/sibling results and artifact references
        """
        parent_results = []
        sibling_results = []

        # Get parent result
        if task.parent_id:
            parent_result = runtime.context_store.get_result(task.parent_id)
            if parent_result:
                # BUG FIX: Use find_node for hierarchical lookup (parent is in parent DAG, not subgraph)
                try:
                    parent_task, _ = dag.find_node(task.parent_id)
                    parent_results.append(ParentResult(goal=parent_task.goal, result=parent_result))
                except ValueError:
                    from loguru import logger
                    logger.warning(
                        f"[build_planner_context] Parent task {task.parent_id[:8]}... not found in DAG hierarchy"
                    )

        # Get sibling results
        if task.parent_id:
            # BUG FIX: Use find_node for hierarchical lookup (parent is in parent DAG, not subgraph)
            try:
                parent, _ = dag.find_node(task.parent_id)
            except ValueError:
                from loguru import logger
                logger.warning(
                    f"[build_planner_context] Parent task {task.parent_id[:8]}... not found for sibling lookup"
                )
                parent = None
            if parent and parent.subgraph_id:
                subgraph = dag.get_subgraph(parent.subgraph_id)
                for sibling in subgraph.get_all_tasks(include_subgraphs=False):
                    if sibling.task_id != task.task_id and sibling.status == TaskStatus.COMPLETED:
                        sib_result = runtime.context_store.get_result(sibling.task_id)
                        if sib_result:
                            sibling_results.append(SiblingResult(goal=sibling.goal, result=sib_result))

        # Query artifacts from parent using centralized method
        # Note: Siblings don't have task_id in SiblingResult model, so we only query parent
        task_ids = [task.parent_id] if task.parent_id else []
        available_artifacts = await self._query_artifacts_for_context(
            task_ids=task_ids,
            injection_mode=injection_mode,
            current_task_id=task.task_id,
            dag=dag
        )

        return PlannerSpecificContext(
            parent_results=parent_results,
            sibling_results=sibling_results,
            available_artifacts=available_artifacts
        )

    async def _build_aggregator_specific(
        self,
        task: "TaskNode",
        runtime: "ModuleRuntime",
        dag: "TaskDAG",
        injection_mode: ArtifactInjectionMode = ArtifactInjectionMode.DEPENDENCIES
    ) -> AggregatorSpecificContext:
        """
        Build aggregator-specific context with artifacts from subtasks.

        Args:
            task: Current task node (should have subgraph_id for subtasks)
            runtime: Module runtime (not used for aggregator, but kept for signature consistency)
            dag: Task DAG for accessing subgraph
            injection_mode: Controls which artifacts are injected (DEPENDENCIES mode queries all subtasks)

        Returns:
            AggregatorSpecificContext with artifact references from all subtasks
        """
        subtask_ids = []

        # Get all subtask IDs from the subgraph
        if task.subgraph_id:
            subgraph = dag.get_subgraph(task.subgraph_id)
            if subgraph:
                subtask_ids = [t.task_id for t in subgraph.get_all_tasks(include_subgraphs=False)]

        # Query artifacts from all subtasks using centralized method
        available_artifacts = await self._query_artifacts_for_context(
            task_ids=subtask_ids,
            injection_mode=injection_mode,
            current_task_id=task.task_id,
            dag=dag
        )

        return AggregatorSpecificContext(
            available_artifacts=available_artifacts
        )

    # ==================== Generic Builder (DRY) ====================

    def _build_context(
        self,
        task: "TaskNode",
        tools_data: List[dict],
        include_file_system: bool = False,
        specific_context: Optional[str] = None
    ) -> str:
        """
        Generic context builder - composes fundamental + agent-specific context.

        Args:
            task: Current task node
            tools_data: Available tools information
            include_file_system: Whether to include file system in fundamental context
            specific_context: Optional agent-specific context XML (or None for agents with no specific context)

        Returns:
            Complete XML context string
        """
        fundamental = self._build_fundamental(task, tools_data, include_file_system)

        parts = ["<context>", fundamental.to_xml()]
        if specific_context:
            parts.append(specific_context)
        parts.append("</context>")

        return '\n'.join(parts)

    # ==================== Public API: Agent-Specific Builders ====================
    # Executor, Planner, and Aggregator have specialized async builders (they need artifacts)
    # Other agents (Atomizer, Verifier) use build_basic_context (no artifacts needed)

    async def build_planner_context(
        self,
        task: "TaskNode",
        tools_data: List[dict],
        runtime: "ModuleRuntime",
        dag: "TaskDAG",
        injection_mode: ArtifactInjectionMode = ArtifactInjectionMode.DEPENDENCIES
    ) -> str:
        """
        Build complete context for Planner agent (fundamental + parent/siblings + artifacts).

        Args:
            task: Current task node
            tools_data: Available tools information
            runtime: Module runtime for context access
            dag: Task DAG for parent/sibling lookup
            injection_mode: Controls which artifacts are injected (default: DEPENDENCIES)

        Returns:
            Complete XML context string
        """
        specific = await self._build_planner_specific(task, runtime, dag, injection_mode)
        return self._build_context(task, tools_data, include_file_system=False, specific_context=specific.to_xml())

    async def build_executor_context(
        self,
        task: "TaskNode",
        tools_data: List[dict],
        runtime: "ModuleRuntime",
        dag: "TaskDAG",
        injection_mode: ArtifactInjectionMode = ArtifactInjectionMode.DEPENDENCIES
    ) -> str:
        """
        Build complete context for Executor agent (fundamental + file_system + dependencies + artifacts).

        Args:
            task: Current task node
            tools_data: Available tools information
            runtime: Module runtime for context access
            dag: Task DAG for dependency lookup
            injection_mode: Controls which artifacts are injected (default: DEPENDENCIES)

        Returns:
            Complete XML context string
        """
        specific = await self._build_executor_specific(task, runtime, dag, injection_mode)
        return self._build_context(task, tools_data, include_file_system=True, specific_context=specific.to_xml())

    async def build_aggregator_context(
        self,
        task: "TaskNode",
        tools_data: List[dict],
        runtime: "ModuleRuntime",
        dag: "TaskDAG",
        injection_mode: ArtifactInjectionMode = ArtifactInjectionMode.DEPENDENCIES
    ) -> str:
        """
        Build complete context for Aggregator agent (fundamental + subtask artifacts).

        Args:
            task: Current task node (should have subgraph_id)
            tools_data: Available tools information
            runtime: Module runtime for context access
            dag: Task DAG for subgraph access
            injection_mode: Controls which artifacts are injected (default: DEPENDENCIES)

        Returns:
            Complete XML context string
        """
        specific = await self._build_aggregator_specific(task, runtime, dag, injection_mode)
        return self._build_context(task, tools_data, include_file_system=False, specific_context=specific.to_xml())

    def build_basic_context(
        self,
        task: "TaskNode",
        tools_data: List[dict],
    ) -> str:
        """
        Build fundamental context for agents without specific context needs (Atomizer, Verifier).

        Args:
            task: Current task node
            tools_data: Available tools information

        Returns:
            Complete XML context string with only fundamental context
        """
        return self._build_context(task, tools_data, include_file_system=False, specific_context=None)
