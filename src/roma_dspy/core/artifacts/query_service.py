"""
Artifact Query Service for retrieving artifacts based on injection modes.

This service provides centralized logic for querying artifacts from the registry
based on different injection modes (NONE, DEPENDENCIES, SUBTASK, FULL).
"""

from typing import List, Set, TYPE_CHECKING
from loguru import logger

from roma_dspy.core.artifacts.artifact_registry import ArtifactRegistry
from roma_dspy.types.artifact_models import ArtifactReference
from roma_dspy.types.artifact_injection import ArtifactInjectionMode

if TYPE_CHECKING:
    from roma_dspy.core.engine.dag import TaskDAG


class ArtifactQueryService:
    """
    Service for querying artifacts based on injection modes.

    Provides methods to retrieve artifacts from the registry based on:
    - NONE: No artifacts
    - DEPENDENCIES: Artifacts from specific dependency tasks
    - SUBTASK: Artifacts within the current subtask tree (future)
    - FULL: All artifacts in the execution

    All methods return List[ArtifactReference] for lightweight context injection.
    """

    async def get_artifacts_for_dependencies(
        self,
        registry: ArtifactRegistry,
        dependency_task_ids: List[str],
        mode: ArtifactInjectionMode,
    ) -> List[ArtifactReference]:
        """
        Get artifacts from dependency tasks based on injection mode.

        Args:
            registry: Artifact registry to query
            dependency_task_ids: List of task IDs that are dependencies
            mode: Injection mode controlling which artifacts to return

        Returns:
            List of artifact references for context injection
        """
        if mode == ArtifactInjectionMode.NONE:
            return []

        if not dependency_task_ids:
            return []

        # Deduplicate task IDs
        unique_task_ids = list(set(dependency_task_ids))

        # Query artifacts for each dependency task
        references: List[ArtifactReference] = []
        seen_artifact_ids: Set[str] = set()

        for task_id in unique_task_ids:
            artifacts = await registry.get_by_task(task_id)

            for artifact in artifacts:
                # Deduplicate by artifact ID
                artifact_id_str = str(artifact.artifact_id)
                if artifact_id_str not in seen_artifact_ids:
                    seen_artifact_ids.add(artifact_id_str)
                    ref = ArtifactReference.from_artifact(artifact)
                    references.append(ref)

        logger.debug(
            f"Retrieved {len(references)} artifacts for {len(unique_task_ids)} "
            f"dependencies (mode={mode.value})"
        )

        return references

    async def get_all_artifacts(
        self,
        registry: ArtifactRegistry,
        mode: ArtifactInjectionMode,
    ) -> List[ArtifactReference]:
        """
        Get all artifacts in the execution (FULL mode).

        Args:
            registry: Artifact registry to query
            mode: Injection mode (should be FULL)

        Returns:
            List of all artifact references
        """
        if mode == ArtifactInjectionMode.NONE:
            return []

        artifacts = await registry.get_all()

        references = [
            ArtifactReference.from_artifact(artifact)
            for artifact in artifacts
        ]

        logger.debug(
            f"Retrieved {len(references)} artifacts in FULL mode"
        )

        return references

    async def get_artifacts_for_subtask(
        self,
        registry: ArtifactRegistry,
        dag: "TaskDAG",
        current_task_id: str,
        mode: ArtifactInjectionMode,
    ) -> List[ArtifactReference]:
        """
        Get artifacts within the current subtask tree (SUBTASK mode).

        Retrieves artifacts from all tasks within the same subgraph as the current task.
        This includes the current task, its siblings, and all descendants.

        Args:
            registry: Artifact registry to query
            dag: Task DAG for navigating task hierarchy
            current_task_id: Current task ID
            mode: Injection mode (should be SUBTASK)

        Returns:
            List of artifact references within subtask tree
        """
        if mode == ArtifactInjectionMode.NONE:
            return []

        # Get current task node
        task_node = dag.find_node(current_task_id)
        if not task_node:
            logger.warning(
                f"Task {current_task_id} not found in DAG for SUBTASK mode, "
                "returning empty list"
            )
            return []

        # Collect all task IDs in the same subgraph
        task_ids_in_subtree: Set[str] = set()

        # If task has a subgraph, get all tasks within it
        if task_node.subgraph_id:
            subgraph = dag.get_subgraph(task_node.subgraph_id)
            if subgraph:
                # Get all tasks in subgraph recursively
                all_tasks = subgraph.get_all_tasks(include_subgraphs=True)
                task_ids_in_subtree.update(t.task_id for t in all_tasks)

        # Also include the current task itself
        task_ids_in_subtree.add(current_task_id)

        # If no subgraph, find parent's subgraph to include siblings
        if not task_node.subgraph_id:
            # Look for parent task
            for node in dag.get_all_tasks(include_subgraphs=True):
                if node.subgraph_id:
                    subgraph = dag.get_subgraph(node.subgraph_id)
                    if subgraph:
                        subtask_ids = [t.task_id for t in subgraph.get_all_tasks(include_subgraphs=False)]
                        if current_task_id in subtask_ids:
                            # Current task is in this subgraph, include all siblings
                            task_ids_in_subtree.update(subtask_ids)
                            break

        # Query artifacts for all tasks in subtree
        references: List[ArtifactReference] = []
        seen_artifact_ids: Set[str] = set()

        for task_id in task_ids_in_subtree:
            artifacts = await registry.get_by_task(task_id)

            for artifact in artifacts:
                # Deduplicate by artifact ID
                artifact_id_str = str(artifact.artifact_id)
                if artifact_id_str not in seen_artifact_ids:
                    seen_artifact_ids.add(artifact_id_str)
                    ref = ArtifactReference.from_artifact(artifact)
                    references.append(ref)

        logger.debug(
            f"Retrieved {len(references)} artifacts from {len(task_ids_in_subtree)} "
            f"tasks in SUBTASK mode for task {current_task_id}"
        )

        return references
