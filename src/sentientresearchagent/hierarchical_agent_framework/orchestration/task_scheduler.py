"""
TaskScheduler - Determines which nodes are ready for execution.

Responsibilities:
- Track node dependencies
- Determine execution readiness
- Manage execution order
- Handle parallel execution constraints
"""

from typing import List, Set, Dict, Optional, TYPE_CHECKING, Tuple
from loguru import logger
from collections import defaultdict, deque

from sentientresearchagent.hierarchical_agent_framework.node.task_node import TaskNode, TaskStatus
from sentientresearchagent.hierarchical_agent_framework.types import is_terminal_status

if TYPE_CHECKING:
    from sentientresearchagent.hierarchical_agent_framework.graph.task_graph import TaskGraph
    from sentientresearchagent.hierarchical_agent_framework.graph.state_manager import StateManager


class TaskScheduler:
    """
    Schedules tasks for execution based on dependencies and readiness.
    
    This class encapsulates all logic for determining which nodes should
    be executed next, respecting dependencies and parallel execution limits.
    """
    
    def __init__(self, task_graph: "TaskGraph", state_manager: "StateManager"):
        """
        Initialize the TaskScheduler.
        
        Args:
            task_graph: The task graph containing all nodes
            state_manager: Manages node state transitions
        """
        self.task_graph = task_graph
        self.state_manager = state_manager
        
        # Cache for performance
        self._dependency_cache: Dict[str, Set[str]] = {}
        self._last_cache_update = 0
        
        # Dependency graph and topological order
        self._dependency_graph: Dict[str, Set[str]] = {}
        self._reverse_dependencies: Dict[str, Set[str]] = {}  # Who depends on this node
        self._topological_order: List[str] = []
        self._graph_version = 0
        
        logger.info("TaskScheduler initialized")
    
    async def get_ready_nodes(self, max_nodes: Optional[int] = None) -> List[TaskNode]:
        """
        Get nodes that are ready for execution.
        
        A node is ready if:
        - It's in READY status
        - All its dependencies are satisfied
        - Its parent (if any) is in an appropriate state
        
        Args:
            max_nodes: Maximum number of nodes to return (for controlling parallelism)
            
        Returns:
            List of nodes ready for execution
        """
        ready_nodes = []
        
        # Get all nodes in READY or AGGREGATING status
        all_nodes = self.task_graph.get_all_nodes()
        potential_ready = [
            node for node in all_nodes
            if node.status in [TaskStatus.READY, TaskStatus.AGGREGATING, TaskStatus.NEEDS_REPLAN]
        ]
        
        # Check each potential node
        for node in potential_ready:
            if await self._is_node_executable(node):
                ready_nodes.append(node)
                
                # Check if we've reached the limit
                if max_nodes and len(ready_nodes) >= max_nodes:
                    break
        
        # Sort by priority (layer, then creation time)
        ready_nodes.sort(key=lambda n: (n.layer, n.timestamp_created))
        
        if potential_ready:
            logger.info(f"TaskScheduler: Checked {len(potential_ready)} potential nodes "
                       f"(READY: {sum(1 for n in potential_ready if n.status == TaskStatus.READY)}, "
                       f"AGGREGATING: {sum(1 for n in potential_ready if n.status == TaskStatus.AGGREGATING)}), "
                       f"found {len(ready_nodes)} executable")
            
            # Log why nodes were rejected - more detail
            if len(ready_nodes) == 0 and len(potential_ready) > 0:
                logger.warning(f"Found {len(potential_ready)} potential nodes but NONE are executable!")
                for node in potential_ready[:3]:  # Log first 3 for debugging
                    is_exec = await self._is_node_executable(node)
                    logger.info(f"  Node {node.task_id}: status={node.status}, "
                               f"parent={node.parent_node_id}, executable={is_exec}")
        else:
            logger.info(f"TaskScheduler: No nodes in READY or AGGREGATING status")
        
        return ready_nodes
    
    async def get_active_nodes(self) -> List[TaskNode]:
        """
        Get all nodes that are currently active (not in terminal state).
        
        Returns:
            List of active nodes
        """
        all_nodes = self.task_graph.get_all_nodes()
        active_nodes = [
            node for node in all_nodes 
            if not is_terminal_status(node.status)
        ]
        
        return active_nodes
    
    async def get_pending_nodes(self) -> List[TaskNode]:
        """
        Get nodes that are pending execution.
        
        Returns:
            List of pending nodes with their blocking reasons
        """
        all_nodes = self.task_graph.get_all_nodes()
        pending_nodes = []
        
        for node in all_nodes:
            if node.status == TaskStatus.PENDING:
                # Analyze why the node is pending
                blocking_reason = await self._get_blocking_reason(node)
                node.aux_data["blocking_reason"] = blocking_reason
                pending_nodes.append(node)
        
        return pending_nodes
    
    async def update_node_readiness(self) -> int:
        """
        Update the readiness status of all nodes.
        
        This method transitions PENDING nodes to READY when their
        dependencies are satisfied.
        
        Returns:
            Number of nodes transitioned to READY
        """
        transitioned = 0
        all_nodes = self.task_graph.get_all_nodes()
        
        for node in all_nodes:
            if node.status == TaskStatus.PENDING:
                if await self._can_transition_to_ready(node):
                    # Transition the node to READY
                    old_status = node.status
                    node.update_status(TaskStatus.READY, validate_transition=True)
                    
                    # Update in knowledge store if we have one
                    # Note: TaskScheduler doesn't have direct access to knowledge store
                    # This should be handled by the caller
                    
                    transitioned += 1
                    logger.info(f"Node {node.task_id} transitioned from PENDING to READY")
        
        if transitioned > 0:
            logger.info(f"TaskScheduler: {transitioned} nodes transitioned to READY")
        
        return transitioned
    
    async def _is_node_executable(self, node: TaskNode) -> bool:
        """
        Check if a node is truly ready for execution.
        
        Args:
            node: Node to check
            
        Returns:
            True if node can be executed now
        """
        # Node must be in READY, AGGREGATING, or NEEDS_REPLAN status
        if node.status not in [TaskStatus.READY, TaskStatus.AGGREGATING, TaskStatus.NEEDS_REPLAN]:
            logger.debug(f"Node {node.task_id} not executable: wrong status {node.status}")
            return False

        # AGGREGATING nodes are always executable (they've already checked children)
        if node.status == TaskStatus.AGGREGATING:
            logger.debug(f"Node {node.task_id} is AGGREGATING - executable")
            return True

        # NEEDS_REPLAN nodes should be processed immediately to unblock the graph
        if node.status == TaskStatus.NEEDS_REPLAN:
            logger.debug(f"Node {node.task_id} is flagged for replanning - executable")
            return True
        
        # Check parent readiness
        parent_ready = await self._is_parent_ready(node)
        if not parent_ready:
            if node.parent_node_id:
                parent = self.task_graph.get_node(node.parent_node_id)
                parent_status = parent.status if parent else "NOT_FOUND"
                logger.info(f"Node {node.task_id} not executable: parent {node.parent_node_id} status={parent_status} "
                           f"(needs RUNNING or PLAN_DONE)")
            else:
                logger.info(f"Node {node.task_id} not executable: parent not ready (no parent_id)")
            return False
        
        # Check dependencies
        deps_satisfied = await self._are_dependencies_satisfied(node)
        if not deps_satisfied:
            logger.debug(f"Node {node.task_id} not executable: dependencies not satisfied")
            return False
        
        logger.debug(f"Node {node.task_id} is executable!")
        return True
    
    async def _is_parent_ready(self, node: TaskNode) -> bool:
        """
        Check if a node's parent is in an appropriate state.
        
        Args:
            node: Node to check
            
        Returns:
            True if parent is ready or node has no parent
        """
        if not node.parent_node_id:
            return True
        
        parent = self.task_graph.get_node(node.parent_node_id)
        if not parent:
            logger.warning(f"Node {node.task_id} has invalid parent {node.parent_node_id}")
            return False
        
        # Parent must be RUNNING, PLAN_DONE, DONE, or AGGREGATING for child to execute
        # FIXED: Allow children to execute even if parent is DONE or AGGREGATING
        parent_ok = parent.status in [TaskStatus.RUNNING, TaskStatus.PLAN_DONE, TaskStatus.DONE, TaskStatus.AGGREGATING]
        if not parent_ok:
            logger.debug(f"Parent {parent.task_id} not ready for child execution: status={parent.status}, "
                        f"expected RUNNING or PLAN_DONE")
        return parent_ok
    
    async def _are_dependencies_satisfied(self, node: TaskNode) -> bool:
        """
        Check if all node dependencies are satisfied.
        
        Args:
            node: Node to check
            
        Returns:
            True if all dependencies are satisfied
        """
        # Get node dependencies
        dependencies = await self._get_node_dependencies(node)
        
        # Log dependencies for debugging
        if dependencies:
            logger.debug(f"Node {node.task_id} has dependencies: {dependencies}")
        
        # Check each dependency
        for dep_id in dependencies:
            dep_node = self.task_graph.get_node(dep_id)
            if not dep_node:
                logger.warning(f"Node {node.task_id} has invalid dependency {dep_id}")
                continue
            
            # Dependency must be in terminal success state
            if dep_node.status != TaskStatus.DONE:
                logger.debug(f"Node {node.task_id} waiting for dependency {dep_id} (status: {dep_node.status})")
                return False
        
        # All dependencies satisfied
        if dependencies:
            logger.info(f"All dependencies satisfied for node {node.task_id}")
        
        return True
    
    async def _get_node_dependencies(self, node: TaskNode) -> Set[str]:
        """
        Get all dependencies for a node.
        
        Args:
            node: Node to get dependencies for
            
        Returns:
            Set of dependency node IDs
        """
        # Check cache first
        if node.task_id in self._dependency_cache:
            return self._dependency_cache[node.task_id]
        
        dependencies = set()
        
        # Method 1: Check aux_data for depends_on_indices (more reliable for newly created nodes)
        depends_on_indices = node.aux_data.get('depends_on_indices', []) if node.aux_data is not None else []
        if depends_on_indices and node.parent_node_id:
            # Get sibling nodes to resolve indices to IDs
            parent = self.task_graph.get_node(node.parent_node_id)
            if parent and parent.planned_sub_task_ids:
                for dep_idx in depends_on_indices:
                    if 0 <= dep_idx < len(parent.planned_sub_task_ids):
                        dep_id = parent.planned_sub_task_ids[dep_idx]
                        dependencies.add(dep_id)
                        logger.debug(f"Found dependency {dep_id} for node {node.task_id} from aux_data")
        
        # Method 2: Find the graph containing this node and check graph edges
        container_graph_id = None
        for graph_id, graph in self.task_graph.graphs.items():
            if node.task_id in graph.nodes:
                container_graph_id = graph_id
                break
        
        if container_graph_id:
            # Get predecessors in the graph
            predecessors = self.task_graph.get_node_predecessors(
                container_graph_id, 
                node.task_id
            )
            for pred in predecessors:
                dependencies.add(pred.task_id)
                logger.debug(f"Found dependency {pred.task_id} for node {node.task_id} from graph")
        
        # Cache the result
        self._dependency_cache[node.task_id] = dependencies
        
        return dependencies
    
    async def _can_transition_to_ready(self, node: TaskNode) -> bool:
        """
        Check if a PENDING node can transition to READY.
        
        Args:
            node: Node to check
            
        Returns:
            True if node can transition to READY
        """
        # Must be PENDING
        if node.status != TaskStatus.PENDING:
            return False
        
        # Check parent conditions
        if node.parent_node_id:
            parent = self.task_graph.get_node(node.parent_node_id)
            if not parent:
                return False
            
            # Parent must be in appropriate state
            if parent.status not in [TaskStatus.RUNNING, TaskStatus.PLAN_DONE, TaskStatus.DONE, TaskStatus.AGGREGATING]:
                return False
        
        # Check dependencies
        return await self._are_dependencies_satisfied(node)
    
    async def _get_blocking_reason(self, node: TaskNode) -> str:
        """
        Get the reason why a node is blocked from execution.
        
        Args:
            node: Node to analyze
            
        Returns:
            Human-readable blocking reason
        """
        reasons = []
        
        # Check parent status
        if node.parent_node_id:
            parent = self.task_graph.get_node(node.parent_node_id)
            if parent:
                if parent.status not in [TaskStatus.RUNNING, TaskStatus.PLAN_DONE, TaskStatus.DONE, TaskStatus.AGGREGATING]:
                    reasons.append(f"Parent {parent.task_id} is in {parent.status} state")
            else:
                reasons.append(f"Parent {node.parent_node_id} not found")
        
        # Check dependencies
        dependencies = await self._get_node_dependencies(node)
        incomplete_deps = []
        
        for dep_id in dependencies:
            dep_node = self.task_graph.get_node(dep_id)
            if dep_node and dep_node.status != TaskStatus.DONE:
                incomplete_deps.append(f"{dep_id} ({dep_node.status})")
        
        if incomplete_deps:
            reasons.append(f"Waiting for dependencies: {', '.join(incomplete_deps)}")
        
        return "; ".join(reasons) if reasons else "Unknown"
    
    def clear_dependency_cache(self):
        """Clear the dependency cache (call when graph structure changes)."""
        self._dependency_cache.clear()
        logger.debug("TaskScheduler: Dependency cache cleared")
    
    def get_execution_metrics(self) -> Dict[str, int]:
        """
        Get metrics about the current execution state.
        
        Returns:
            Dictionary with execution metrics
        """
        all_nodes = self.task_graph.get_all_nodes()
        
        metrics = {
            "total_nodes": len(all_nodes),
            "pending": sum(1 for n in all_nodes if n.status == TaskStatus.PENDING),
            "ready": sum(1 for n in all_nodes if n.status == TaskStatus.READY),
            "running": sum(1 for n in all_nodes if n.status == TaskStatus.RUNNING),
            "completed": sum(1 for n in all_nodes if n.status == TaskStatus.DONE),
            "failed": sum(1 for n in all_nodes if n.status == TaskStatus.FAILED),
            "plan_done": sum(1 for n in all_nodes if n.status == TaskStatus.PLAN_DONE),
            "aggregating": sum(1 for n in all_nodes if n.status == TaskStatus.AGGREGATING),
            "needs_replan": sum(1 for n in all_nodes if n.status == TaskStatus.NEEDS_REPLAN),
        }
        
        return metrics
    
    async def build_dependency_graph(self) -> None:
        """
        Build the complete dependency graph for all nodes.
        This enables efficient topological sorting and dependency checking.
        """
        self._dependency_graph.clear()
        self._reverse_dependencies.clear()
        
        all_nodes = self.task_graph.get_all_nodes()
        
        # Build forward and reverse dependency maps
        for node in all_nodes:
            node_id = node.task_id
            dependencies = await self._get_node_dependencies(node)
            
            self._dependency_graph[node_id] = dependencies
            
            # Build reverse dependencies
            if node_id not in self._reverse_dependencies:
                self._reverse_dependencies[node_id] = set()
                
            for dep_id in dependencies:
                if dep_id not in self._reverse_dependencies:
                    self._reverse_dependencies[dep_id] = set()
                self._reverse_dependencies[dep_id].add(node_id)
        
        # Compute topological order
        self._topological_order = self._compute_topological_order()
        self._graph_version += 1
        
        logger.info(f"Built dependency graph with {len(all_nodes)} nodes, "
                   f"computed topological order: {len(self._topological_order)} nodes")
    
    def _compute_topological_order(self) -> List[str]:
        """
        Compute topological ordering of nodes using Kahn's algorithm.
        
        Returns:
            List of node IDs in topological order
        """
        # Create in-degree count for all nodes
        in_degree = defaultdict(int)
        all_nodes = set()
        
        # Build in-degree count
        for node_id, deps in self._dependency_graph.items():
            all_nodes.add(node_id)
            for dep in deps:
                all_nodes.add(dep)
                in_degree[node_id] += 1  # node_id depends on dep
        
        # Initialize all nodes with 0 in-degree if not already counted
        for node in all_nodes:
            if node not in in_degree:
                in_degree[node] = 0
        
        # Find all nodes with no dependencies (in-degree 0)
        queue = deque([node_id for node_id in all_nodes if in_degree[node_id] == 0])
        result = []
        processed = set()
        
        while queue:
            # Process nodes level by level for better parallelism
            level_size = len(queue)
            level_nodes = []
            
            for _ in range(level_size):
                node_id = queue.popleft()
                if node_id in processed:
                    continue
                    
                processed.add(node_id)
                level_nodes.append(node_id)
                
                # Reduce in-degree for nodes that depend on this one
                if node_id in self._reverse_dependencies:
                    for dependent in self._reverse_dependencies[node_id]:
                        in_degree[dependent] -= 1
                        if in_degree[dependent] == 0 and dependent not in processed:
                            queue.append(dependent)
            
            # Add nodes from the same level (can be processed in parallel)
            result.extend(sorted(level_nodes))  # Sort for deterministic order
        
        # Check for cycles - but don't fail, just log
        if len(result) != len(all_nodes):
            unprocessed = all_nodes - processed
            logger.warning(f"Dependency graph may contain cycles or isolated nodes. "
                         f"Processed {len(result)}/{len(all_nodes)} nodes. "
                         f"Unprocessed: {unprocessed}")
            # Add unprocessed nodes at the end (they might be isolated or in cycles)
            result.extend(sorted(unprocessed))
        
        return result
    
    async def get_ready_nodes_optimized(self, max_nodes: Optional[int] = None) -> List[TaskNode]:
        """
        Get ready nodes using pre-computed dependency information.
        This is more efficient than checking dependencies for each node.
        
        Args:
            max_nodes: Maximum number of nodes to return
            
        Returns:
            List of nodes ready for execution, sorted by topological order
        """
        ready_nodes = []
        completed_nodes = set()
        
        # First pass: identify completed nodes
        all_nodes = self.task_graph.get_all_nodes()
        for node in all_nodes:
            if node.status == TaskStatus.DONE:
                completed_nodes.add(node.task_id)
        
        # Second pass: find ready nodes using topological order
        for node_id in self._topological_order:
            if max_nodes and len(ready_nodes) >= max_nodes:
                break
                
            node = self.task_graph.get_node(node_id)
            if not node:
                continue
                
            # Skip if not in READY or AGGREGATING status
            if node.status not in [TaskStatus.READY, TaskStatus.AGGREGATING, TaskStatus.NEEDS_REPLAN]:
                continue

            # AGGREGATING nodes are always ready
            if node.status == TaskStatus.AGGREGATING:
                ready_nodes.append(node)
                continue

            if node.status == TaskStatus.NEEDS_REPLAN:
                ready_nodes.append(node)
                continue
            
            # Check if all dependencies are satisfied
            dependencies = self._dependency_graph.get(node_id, set())
            if dependencies.issubset(completed_nodes):
                # Check parent readiness
                if await self._is_parent_ready(node):
                    ready_nodes.append(node)
        
        logger.info(f"Found {len(ready_nodes)} ready nodes using optimized algorithm")
        return ready_nodes
