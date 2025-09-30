"""
DeadlockDetector - Detects and analyzes deadlock conditions in task execution.

Responsibilities:
- Detect various deadlock patterns
- Analyze root causes of deadlocks
- Provide detailed diagnostics
- Suggest recovery strategies
"""

from typing import List, Dict, Set, Optional, Tuple, TYPE_CHECKING, Any
from dataclasses import dataclass
from enum import Enum
from loguru import logger

from sentientresearchagent.hierarchical_agent_framework.node.task_node import TaskNode, TaskStatus
from sentientresearchagent.hierarchical_agent_framework.types import is_terminal_status

if TYPE_CHECKING:
    from sentientresearchagent.hierarchical_agent_framework.graph.task_graph import TaskGraph
    from sentientresearchagent.hierarchical_agent_framework.graph.state_manager import StateManager
    from sentientresearchagent.config import SentientConfig


class DeadlockPattern(Enum):
    """Types of deadlock patterns."""
    CIRCULAR_DEPENDENCY = "circular_dependency"
    PARENT_CHILD_SYNC = "parent_child_sync"
    STUCK_AGGREGATION = "stuck_aggregation"
    ORPHANED_NODES = "orphaned_nodes"
    SINGLE_NODE_HANG = "single_node_hang"
    RESOURCE_STARVATION = "resource_starvation"
    UNKNOWN = "unknown"


@dataclass
class DeadlockInfo:
    """Information about a detected deadlock."""
    is_deadlocked: bool
    pattern: DeadlockPattern
    affected_nodes: List[str]
    reason: str
    diagnostics: Dict[str, any]
    suggested_recovery: Optional[str] = None


class DeadlockDetector:
    """
    Detects and analyzes deadlock conditions in task execution.
    
    This class encapsulates all deadlock detection logic, providing
    clean separation from the execution engine.
    """
    
    def __init__(
        self,
        task_graph: "TaskGraph",
        state_manager: "StateManager",
        config: Optional["SentientConfig"] = None
    ):
        """
        Initialize the DeadlockDetector.
        
        Args:
            task_graph: The task graph to analyze
            state_manager: State manager for node states
        """
        self.task_graph = task_graph
        self.state_manager = state_manager
        self._config = config
        
        # Detection state
        self._detection_history: List[DeadlockInfo] = []
        self._pattern_detectors = {
            DeadlockPattern.CIRCULAR_DEPENDENCY: self._detect_circular_dependencies,
            DeadlockPattern.PARENT_CHILD_SYNC: self._detect_parent_child_sync_issues,
            DeadlockPattern.STUCK_AGGREGATION: self._detect_stuck_aggregation,
            DeadlockPattern.ORPHANED_NODES: self._detect_orphaned_nodes,
            DeadlockPattern.SINGLE_NODE_HANG: self._detect_single_node_hang,
            DeadlockPattern.RESOURCE_STARVATION: self._detect_resource_starvation,
        }
        
        # Determine single-node hang timeout using configuration when available
        # IMPROVED: Reduced default timeout from 120s to 60s for faster detection
        default_hang_timeout = 60.0  # Changed from 120.0
        self.single_node_hang_timeout_seconds = default_hang_timeout

        exec_config = getattr(config, "execution", None) if config else None
        if exec_config:
            # Prefer explicit configuration if provided
            configured_timeout = getattr(exec_config, "single_node_hang_timeout_seconds", None)
            if configured_timeout is not None:
                try:
                    # IMPROVED: Reduced minimum from 30s to 20s
                    self.single_node_hang_timeout_seconds = max(20.0, float(configured_timeout))
                except (TypeError, ValueError):
                    logger.warning(
                        "Invalid single_node_hang_timeout_seconds (%s); using default %.1fs",
                        configured_timeout,
                        default_hang_timeout
                    )
                    self.single_node_hang_timeout_seconds = default_hang_timeout
            else:
                # Fall back to a fraction of the overall node execution timeout, capped for responsiveness
                node_timeout = float(getattr(exec_config, "node_execution_timeout_seconds", default_hang_timeout))
                computed_timeout = node_timeout / 2.0
                # IMPROVED: Use 60s default instead of computed_timeout if it's larger
                self.single_node_hang_timeout_seconds = min(60.0, max(20.0, computed_timeout))

        logger.info(f"DeadlockDetector initialized with hang timeout: {self.single_node_hang_timeout_seconds}s")
    
    async def detect_deadlock(self) -> Dict[str, any]:
        """
        Detect if the system is in a deadlock state.
        
        Returns:
            Dictionary with deadlock information
        """
        # Get active nodes
        active_nodes = self._get_active_nodes()
        
        if not active_nodes:
            return {
                "is_deadlocked": False,
                "reason": "No active nodes"
            }
        
        # Try each pattern detector
        for pattern, detector in self._pattern_detectors.items():
            result = await detector(active_nodes)
            if result and result.is_deadlocked:
                # Record detection
                self._detection_history.append(result)
                
                # Return formatted result
                return {
                    "is_deadlocked": True,
                    "pattern": pattern.value,
                    "affected_nodes": result.affected_nodes,
                    "reason": result.reason,
                    "diagnostics": result.diagnostics,
                    "suggested_recovery": result.suggested_recovery
                }
        
        # No deadlock detected
        return {
            "is_deadlocked": False,
            "reason": "No deadlock patterns detected",
            "active_nodes": len(active_nodes)
        }
    
    async def analyze_execution_state(self) -> Dict[str, any]:
        """
        Perform comprehensive analysis of the execution state.
        
        Returns:
            Detailed analysis of current execution state
        """
        all_nodes = self.task_graph.get_all_nodes()
        active_nodes = self._get_active_nodes()
        
        # Build status counts
        status_counts = {}
        for node in active_nodes:
            status = node.status.name if isinstance(node.status, TaskStatus) else str(node.status)
            status_counts[status] = status_counts.get(status, 0) + 1
        
        # Analyze dependencies
        dependency_analysis = await self._analyze_dependencies(active_nodes)
        
        # Check state validity
        validation_errors = self._validate_execution_state(all_nodes)
        
        # Build execution graph visualization
        graph_visualization = self._build_graph_visualization(active_nodes)
        
        return {
            "total_nodes": len(all_nodes),
            "active_nodes": len(active_nodes),
            "status_distribution": status_counts,
            "dependency_chains": dependency_analysis["chains"],
            "blocked_nodes": dependency_analysis["blocked"],
            "validation_errors": validation_errors,
            "graph_visualization": graph_visualization,
            "detection_history": [
                {
                    "pattern": d.pattern.value,
                    "affected_nodes": d.affected_nodes,
                    "reason": d.reason
                }
                for d in self._detection_history[-5:]  # Last 5 detections
            ]
        }
    
    async def _detect_circular_dependencies(self, active_nodes: List[TaskNode]) -> Optional[DeadlockInfo]:
        """Detect circular dependency deadlocks."""
        visited = set()
        path = []
        
        def has_cycle(node_id: str, visiting: Set[str]) -> Optional[List[str]]:
            """DFS to detect cycles."""
            if node_id in visiting:
                # Found cycle
                cycle_start = path.index(node_id)
                return path[cycle_start:] + [node_id]
            
            if node_id in visited:
                return None
            
            visiting.add(node_id)
            path.append(node_id)
            
            node = self.task_graph.get_node(node_id)
            if node:
                # Check parent dependency
                if node.parent_node_id:
                    cycle = has_cycle(node.parent_node_id, visiting)
                    if cycle:
                        return cycle
                
                # Check graph dependencies
                container_graph = self._find_container_graph(node)
                if container_graph:
                    predecessors = self.task_graph.get_node_predecessors(container_graph, node_id)
                    for pred in predecessors:
                        cycle = has_cycle(pred.task_id, visiting)
                        if cycle:
                            return cycle
            
            path.pop()
            visiting.remove(node_id)
            visited.add(node_id)
            return None
        
        # Check each active node
        for node in active_nodes:
            if node.task_id not in visited:
                cycle = has_cycle(node.task_id, set())
                if cycle:
                    return DeadlockInfo(
                        is_deadlocked=True,
                        pattern=DeadlockPattern.CIRCULAR_DEPENDENCY,
                        affected_nodes=cycle,
                        reason=f"Circular dependency detected: {' -> '.join(cycle)}",
                        diagnostics={"cycle": cycle},
                        suggested_recovery="Break cycle by failing one of the nodes"
                    )
        
        return None
    
    async def _detect_parent_child_sync_issues(self, active_nodes: List[TaskNode]) -> Optional[DeadlockInfo]:
        """Detect parent-child synchronization issues."""
        issues = []
        
        # Group nodes by status
        nodes_by_status = {}
        for node in active_nodes:
            status = node.status
            if status not in nodes_by_status:
                nodes_by_status[status] = []
            nodes_by_status[status].append(node)
        
        # Check for RUNNING parents with PENDING children
        running_nodes = nodes_by_status.get(TaskStatus.RUNNING, [])
        pending_nodes = nodes_by_status.get(TaskStatus.PENDING, [])
        
        for parent in running_nodes:
            stuck_children = []
            for child in pending_nodes:
                if child.parent_node_id == parent.task_id:
                    # Check if child can't find its container graph
                    container_graph = self._find_container_graph(child)
                    if not container_graph:
                        stuck_children.append(child)
            
            if stuck_children:
                issues.append({
                    "parent": parent.task_id,
                    "stuck_children": [c.task_id for c in stuck_children],
                    "reason": "Children can't find container graph"
                })
        
        # Check for PLAN_DONE parents without proper sub-graph
        plan_done_nodes = nodes_by_status.get(TaskStatus.PLAN_DONE, [])
        for node in plan_done_nodes:
            if node.sub_graph_id:
                sub_nodes = self.task_graph.get_nodes_in_graph(node.sub_graph_id)
                if not sub_nodes:
                    issues.append({
                        "node": node.task_id,
                        "reason": "PLAN_DONE with empty sub-graph"
                    })
        
        if issues:
            affected_nodes = []
            for issue in issues:
                if "parent" in issue:
                    affected_nodes.append(issue["parent"])
                    affected_nodes.extend(issue.get("stuck_children", []))
                else:
                    affected_nodes.append(issue["node"])
            
            return DeadlockInfo(
                is_deadlocked=True,
                pattern=DeadlockPattern.PARENT_CHILD_SYNC,
                affected_nodes=list(set(affected_nodes)),
                reason="Parent-child synchronization failure",
                diagnostics={"issues": issues},
                suggested_recovery="Force parent to PLAN_DONE or fix sub-graph references"
            )
        
        return None
    
    async def _detect_stuck_aggregation(self, active_nodes: List[TaskNode]) -> Optional[DeadlockInfo]:
        """Detect nodes stuck waiting for aggregation."""
        stuck_nodes = []
        
        for node in active_nodes:
            if node.status == TaskStatus.PLAN_DONE and node.sub_graph_id:
                sub_nodes = self.task_graph.get_nodes_in_graph(node.sub_graph_id)
                
                # Check if all children are done but parent hasn't aggregated
                if sub_nodes:
                    all_done = all(
                        n.status in [TaskStatus.DONE, TaskStatus.FAILED] 
                        for n in sub_nodes
                    )
                    
                    if all_done:
                        # Parent should be aggregating
                        stuck_nodes.append({
                            "node": node.task_id,
                            "children_count": len(sub_nodes),
                            "reason": "All children complete but not aggregating"
                        })
                    else:
                        # Some children still active - only consider stuck if ALL children are PENDING
                        # and none are RUNNING or READY (true deadlock)
                        incomplete = [
                            n for n in sub_nodes 
                            if n.status not in [TaskStatus.DONE, TaskStatus.FAILED]
                        ]
                        
                        # Only flag as stuck if all incomplete children are truly stuck (PENDING only)
                        # and none are actively running or ready to run
                        all_stuck = all(
                            n.status == TaskStatus.PENDING for n in incomplete
                        )
                        
                        if all_stuck and len(incomplete) > 0:
                            # Additional check: are any children actually ready to transition?
                            children_can_progress = any(
                                self.state_manager.can_become_ready(n) for n in incomplete
                            )
                            
                            if not children_can_progress:
                                stuck_nodes.append({
                                    "node": node.task_id,
                                    "incomplete_children": [n.task_id for n in incomplete],
                                    "reason": f"True deadlock: {len(incomplete)} children permanently stuck in PENDING"
                                })
        
        if stuck_nodes:
            affected_nodes = [s["node"] for s in stuck_nodes]
            
            return DeadlockInfo(
                is_deadlocked=True,
                pattern=DeadlockPattern.STUCK_AGGREGATION,
                affected_nodes=affected_nodes,
                reason="Nodes stuck waiting for aggregation",
                diagnostics={"stuck_nodes": stuck_nodes},
                suggested_recovery="Force aggregation or fail incomplete children"
            )
        
        return None
    
    async def _detect_orphaned_nodes(self, active_nodes: List[TaskNode]) -> Optional[DeadlockInfo]:
        """Detect orphaned nodes with invalid parent states."""
        orphaned = []
        
        for node in active_nodes:
            if node.status == TaskStatus.PENDING and node.parent_node_id:
                parent = self.task_graph.get_node(node.parent_node_id)
                
                if not parent:
                    orphaned.append({
                        "node": node.task_id,
                        "parent": node.parent_node_id,
                        "reason": "Parent not found"
                    })
                elif parent.status not in [TaskStatus.RUNNING, TaskStatus.PLAN_DONE, TaskStatus.DONE, TaskStatus.AGGREGATING]:
                    orphaned.append({
                        "node": node.task_id,
                        "parent": node.parent_node_id,
                        "parent_status": parent.status.name,
                        "reason": "Parent in invalid state"
                    })
        
        if orphaned:
            affected_nodes = [o["node"] for o in orphaned]
            
            return DeadlockInfo(
                is_deadlocked=True,
                pattern=DeadlockPattern.ORPHANED_NODES,
                affected_nodes=affected_nodes,
                reason=f"{len(orphaned)} orphaned nodes detected",
                diagnostics={"orphaned_nodes": orphaned},
                suggested_recovery="Fix parent states or transition orphans to READY"
            )
        
        return None
    
    async def _detect_single_node_hang(self, active_nodes: List[TaskNode]) -> Optional[DeadlockInfo]:
        """Detect single node execution hang."""
        if len(active_nodes) == 1 and active_nodes[0].status == TaskStatus.RUNNING:
            node = active_nodes[0]
            
            # Check if node has been running for too long
            import time
            current_time = time.time()
            
            # Get node start time from timestamp_updated or use a reasonable default
            node_start_time = getattr(node, 'timestamp_updated', None)
            if node_start_time:
                # Convert to timestamp if it's a datetime
                if hasattr(node_start_time, 'timestamp'):
                    node_start_time = node_start_time.timestamp()
                elif isinstance(node_start_time, str):
                    # Try to parse ISO format
                    try:
                        from datetime import datetime
                        dt = datetime.fromisoformat(node_start_time.replace('Z', '+00:00'))
                        node_start_time = dt.timestamp()
                    except:
                        node_start_time = current_time
            else:
                # If no timestamp, assume it just started
                node_start_time = current_time
            
            # Calculate how long the node has been running
            running_duration = current_time - node_start_time
            
            # Only consider it hanging if it's been running beyond the configured threshold.
            if running_duration > self.single_node_hang_timeout_seconds:
                return DeadlockInfo(
                    is_deadlocked=True,
                    pattern=DeadlockPattern.SINGLE_NODE_HANG,
                    affected_nodes=[node.task_id],
                    reason=(
                        "Single node stuck in RUNNING state for "
                        f"{running_duration:.1f}s (timeout: {self.single_node_hang_timeout_seconds:.0f}s)"
                    ),
                    diagnostics={
                        "node": node.task_id,
                        "goal": node.goal,
                        "type": f"{node.task_type}/{node.node_type}",
                        "running_duration": running_duration
                    },
                    suggested_recovery="Force node to NEEDS_REPLAN or FAILED"
                )
            else:
                logger.debug(f"Single node {node.task_id} has been running for {running_duration:.1f}s (not hanging yet)")
        
        return None

    async def _detect_resource_starvation(self, active_nodes: List[TaskNode]) -> Optional[DeadlockInfo]:
        """Detect when all running nodes are stuck and no new work can be scheduled."""
        running_nodes = [node for node in active_nodes if node.status == TaskStatus.RUNNING]
        if not running_nodes:
            return None

        ready_nodes = [node for node in active_nodes if node.status == TaskStatus.READY]
        aggregating_nodes = [node for node in active_nodes if node.status == TaskStatus.AGGREGATING]

        # If the scheduler still has READY or AGGREGATING nodes to process, this isn't starvation.
        if ready_nodes or aggregating_nodes:
            return None

        import time
        current_time = time.time()
        stuck_nodes: List[Dict[str, Any]] = []

        for node in running_nodes:
            node_start_time = getattr(node, 'timestamp_updated', None)
            if node_start_time:
                if hasattr(node_start_time, 'timestamp'):
                    node_start_time = node_start_time.timestamp()
                elif isinstance(node_start_time, str):
                    try:
                        from datetime import datetime
                        dt = datetime.fromisoformat(node_start_time.replace('Z', '+00:00'))
                        node_start_time = dt.timestamp()
                    except Exception:
                        node_start_time = current_time
            else:
                node_start_time = current_time

            running_duration = current_time - node_start_time

            if running_duration > self.single_node_hang_timeout_seconds:
                stuck_nodes.append({
                    "node": node.task_id,
                    "goal": node.goal,
                    "type": f"{node.task_type}/{node.node_type}",
                    "running_duration": running_duration
                })

        # All running nodes are stuck beyond the timeout and nothing else can run – resource starvation
        if stuck_nodes and len(stuck_nodes) == len(running_nodes):
            return DeadlockInfo(
                is_deadlocked=True,
                pattern=DeadlockPattern.RESOURCE_STARVATION,
                affected_nodes=[info["node"] for info in stuck_nodes],
                reason=(
                    "All running nodes exceeded hang timeout with no READY or AGGREGATING nodes available"
                ),
                diagnostics={
                    "running_nodes": stuck_nodes,
                    "timeout_seconds": self.single_node_hang_timeout_seconds
                },
                suggested_recovery="Force running nodes to NEEDS_REPLAN to unblock execution"
            )

        return None
    
    def _get_active_nodes(self) -> List[TaskNode]:
        """Get all non-terminal nodes."""
        all_nodes = self.task_graph.get_all_nodes()
        return [
            node for node in all_nodes 
            if not is_terminal_status(node.status)
        ]
    
    def _find_container_graph(self, node: TaskNode) -> Optional[str]:
        """Find the graph containing a node."""
        for graph_id, graph in self.task_graph.graphs.items():
            if node.task_id in graph.nodes:
                return graph_id
        return None
    
    def _validate_execution_state(self, all_nodes: List[TaskNode]) -> List[str]:
        """Validate the overall execution state for inconsistencies."""
        errors = []
        
        # Check parent-child state consistency
        for node in all_nodes:
            if node.parent_node_id:
                parent = self.task_graph.get_node(node.parent_node_id)
                if parent:
                    # Validate parent-child state combinations
                    if node.status in [TaskStatus.READY, TaskStatus.RUNNING]:
                        if parent.status not in [TaskStatus.RUNNING, TaskStatus.PLAN_DONE, TaskStatus.DONE]:
                            errors.append(
                                f"Invalid state: Child {node.task_id} is {node.status.name} "
                                f"but parent {parent.task_id} is {parent.status.name}"
                            )
        
        # Check sub-graph consistency
        for node in all_nodes:
            if node.sub_graph_id:
                sub_nodes = self.task_graph.get_nodes_in_graph(node.sub_graph_id)
                if not sub_nodes and node.status == TaskStatus.PLAN_DONE:
                    errors.append(f"Node {node.task_id} is PLAN_DONE with empty sub-graph")
        
        return errors
    
    async def _analyze_dependencies(self, active_nodes: List[TaskNode]) -> Dict[str, any]:
        """Analyze dependency relationships."""
        chains = []
        blocked = []
        
        for node in active_nodes:
            if node.status == TaskStatus.PENDING:
                # Build dependency chain
                chain = self._build_dependency_chain(node)
                if chain:
                    chains.append(chain)
                
                # Check if blocked
                blocking_reason = await self._get_blocking_reason(node)
                if blocking_reason:
                    blocked.append({
                        "node": node.task_id,
                        "reason": blocking_reason
                    })
        
        return {
            "chains": chains[:10],  # Limit output
            "blocked": blocked
        }
    
    def _build_dependency_chain(self, node: TaskNode, max_depth: int = 5) -> Optional[str]:
        """Build a dependency chain string."""
        chain_parts = []
        current = node
        depth = 0
        
        while current and depth < max_depth:
            status = current.status.name if isinstance(current.status, TaskStatus) else str(current.status)
            chain_parts.append(f"{current.task_id}({status})")
            
            if current.parent_node_id:
                current = self.task_graph.get_node(current.parent_node_id)
                depth += 1
            else:
                break
        
        if len(chain_parts) > 1:
            chain_parts.reverse()
            return " -> ".join(chain_parts)
        
        return None
    
    async def _get_blocking_reason(self, node: TaskNode) -> Optional[str]:
        """Get why a node is blocked."""
        reasons = []
        
        # Check parent
        if node.parent_node_id:
            parent = self.task_graph.get_node(node.parent_node_id)
            if parent and parent.status not in [TaskStatus.RUNNING, TaskStatus.PLAN_DONE, TaskStatus.DONE]:
                reasons.append(f"Parent {parent.task_id} is {parent.status.name}")
        
        # Check dependencies
        container_graph = self._find_container_graph(node)
        if container_graph:
            predecessors = self.task_graph.get_node_predecessors(container_graph, node.task_id)
            incomplete_deps = [
                f"{p.task_id}({p.status.name})" 
                for p in predecessors 
                if p.status != TaskStatus.DONE
            ]
            if incomplete_deps:
                reasons.append(f"Waiting for: {', '.join(incomplete_deps)}")
        
        return "; ".join(reasons) if reasons else None
    
    def _build_graph_visualization(self, active_nodes: List[TaskNode]) -> List[str]:
        """Build a simple text visualization of the graph state."""
        lines = []
        
        # Group by layer
        nodes_by_layer = {}
        for node in active_nodes:
            layer = node.layer
            if layer not in nodes_by_layer:
                nodes_by_layer[layer] = []
            nodes_by_layer[layer].append(node)
        
        # Build visualization
        for layer in sorted(nodes_by_layer.keys()):
            lines.append(f"Layer {layer}:")
            for node in nodes_by_layer[layer]:
                status = node.status.name if isinstance(node.status, TaskStatus) else str(node.status)
                lines.append(f"  [{status}] {node.task_id}: {node.goal[:30]}...")
        
        return lines[:20]  # Limit output
