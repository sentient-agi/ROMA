"""
RecoveryManager - Manages error recovery strategies.

Responsibilities:
- Define recovery strategies for different error types
- Handle node retry logic
- Manage timeout recovery
- Provide deadlock recovery strategies
"""

from typing import Dict, Optional, Type, List, Any, TYPE_CHECKING
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
import time
import asyncio
from loguru import logger

from sentientresearchagent.hierarchical_agent_framework.node.task_node import TaskNode, TaskStatus
from sentientresearchagent.exceptions import (
    AgentTimeoutError, 
    AgentRateLimitError, 
    AgentExecutionError,
    TaskTimeoutError
)

if TYPE_CHECKING:
    from sentientresearchagent.config import SentientConfig
    from sentientresearchagent.hierarchical_agent_framework.graph.task_graph import TaskGraph
    from sentientresearchagent.hierarchical_agent_framework.graph.state_manager import StateManager


class RecoveryAction(Enum):
    """Types of recovery actions."""
    RETRY = "retry"
    REPLAN = "replan"
    FAIL = "fail"
    FORCE_COMPLETE = "force_complete"
    RESET_STATE = "reset_state"
    SKIP = "skip"


@dataclass
class RecoveryResult:
    """Result of a recovery attempt."""
    recovered: bool
    action: str
    details: Optional[Dict[str, Any]] = None


class RecoveryStrategy(ABC):
    """Base class for recovery strategies."""
    
    @abstractmethod
    async def can_recover(self, node: TaskNode, error: Exception) -> bool:
        """Check if this strategy can recover from the error."""
        pass
    
    @abstractmethod
    async def recover(self, node: TaskNode, error: Exception) -> RecoveryResult:
        """Attempt to recover from the error."""
        pass


class RetryStrategy(RecoveryStrategy):
    """Simple retry strategy with exponential backoff."""
    
    def __init__(self, max_retries: int = 3, base_delay: float = 1.0):
        self.max_retries = max_retries
        self.base_delay = base_delay
    
    async def can_recover(self, node: TaskNode, error: Exception) -> bool:
        """Check if we can retry this node."""
        # Check retry count
        retry_count = node.aux_data.get("retry_count", 0)
        if retry_count >= self.max_retries:
            return False
        
        # Check error type - only retry certain errors
        retryable_errors = (
            AgentTimeoutError,
            AgentRateLimitError,
            ConnectionError,
            TimeoutError
        )
        
        return isinstance(error, retryable_errors)
    
    async def recover(self, node: TaskNode, error: Exception) -> RecoveryResult:
        """Retry the node with exponential backoff."""
        retry_count = node.aux_data.get("retry_count", 0)
        
        # Calculate delay
        delay = self.base_delay * (2 ** retry_count)
        
        logger.info(f"Retrying node {node.task_id} after {delay}s (attempt {retry_count + 1}/{self.max_retries})")
        
        # Wait with backoff
        await asyncio.sleep(delay)
        
        # Update retry count
        node.aux_data["retry_count"] = retry_count + 1
        node.aux_data.setdefault("retry_history", []).append({
            "timestamp": time.time(),
            "error": str(error),
            "attempt": retry_count + 1
        })
        
        # Reset to READY for retry
        node.update_status(TaskStatus.READY)
        
        return RecoveryResult(
            recovered=True,
            action=f"Retry attempt {retry_count + 1} after {delay}s delay",
            details={"retry_count": retry_count + 1, "delay": delay}
        )


class ReplanStrategy(RecoveryStrategy):
    """Strategy to force replanning when execution fails."""
    
    def __init__(self, max_replan_attempts: int = 2):
        self.max_replan_attempts = max_replan_attempts
    
    async def can_recover(self, node: TaskNode, error: Exception) -> bool:
        """Check if we can replan this node."""
        # Check replan attempts
        if node.replan_attempts >= self.max_replan_attempts:
            return False
        
        # Replan for execution errors
        if isinstance(error, AgentExecutionError):
            return True
        
        # Replan if error message suggests planning issue
        error_msg = str(error).lower()
        replan_indicators = [
            "invalid plan",
            "cannot execute",
            "missing dependency",
            "prerequisite",
            "not ready"
        ]
        
        return any(indicator in error_msg for indicator in replan_indicators)
    
    async def recover(self, node: TaskNode, error: Exception) -> RecoveryResult:
        """Force the node to replan."""
        logger.info(f"Forcing replan for node {node.task_id} due to error: {error}")
        
        # Set replan reason
        node.replan_reason = f"Recovery from error: {str(error)[:100]}"
        node.update_status(TaskStatus.NEEDS_REPLAN)
        
        return RecoveryResult(
            recovered=True,
            action=f"Forced replan (attempt {node.replan_attempts + 1})",
            details={"reason": node.replan_reason}
        )


class TimeoutRecoveryStrategy(RecoveryStrategy):
    """Strategy for recovering from timeout conditions."""
    
    def __init__(self, config: "SentientConfig"):
        self.config = config
        self.node_start_times: Dict[str, float] = {}
    
    async def can_recover(self, node: TaskNode, error: Exception) -> bool:
        """Check if this is a recoverable timeout."""
        return isinstance(error, (TaskTimeoutError, TimeoutError))
    
    async def recover(self, node: TaskNode, error: Exception) -> RecoveryResult:
        """Recover from timeout by resetting or replanning."""
        logger.warning(f"Timeout recovery for node {node.task_id}")
        
        # Check if node has been stuck too long
        node_key = f"{node.task_id}_{node.status.name}"
        start_time = self.node_start_times.get(node_key, time.time())
        stuck_duration = time.time() - start_time
        
        # Decide recovery action based on duration
        if stuck_duration > self.config.execution.max_stuck_duration:
            # Too long - fail the node
            node.update_status(
                TaskStatus.FAILED,
                error_msg=f"Timeout after {stuck_duration:.0f}s"
            )
            return RecoveryResult(
                recovered=False,
                action="Failed due to excessive timeout",
                details={"duration": stuck_duration}
            )
        else:
            # Try replanning
            node.replan_reason = f"Timeout recovery after {stuck_duration:.0f}s"
            node.update_status(TaskStatus.NEEDS_REPLAN)
            return RecoveryResult(
                recovered=True,
                action="Forced replan due to timeout",
                details={"duration": stuck_duration}
            )


class DeadlockRecoveryStrategy:
    """Strategy for recovering from deadlocks."""
    
    def __init__(self):
        self.recovery_actions = {
            "circular_dependency": self._recover_circular_dependency,
            "parent_child_sync": self._recover_parent_child_sync,
            "stuck_aggregation": self._recover_stuck_aggregation,
            "single_node_hang": self._recover_single_node_hang,
            "orphaned_nodes": self._recover_orphaned_nodes
        }
    
    async def recover_from_deadlock(
        self, 
        deadlock_info: Dict[str, Any],
        task_graph: "TaskGraph",
        state_manager: "StateManager"
    ) -> Dict[str, Any]:
        """
        Attempt to recover from a detected deadlock.
        
        Args:
            deadlock_info: Information about the deadlock
            task_graph: The task graph
            state_manager: State manager
            
        Returns:
            Recovery result
        """
        pattern = deadlock_info.get("pattern", "unknown")
        
        # Get recovery function
        recovery_func = self.recovery_actions.get(pattern)
        if not recovery_func:
            logger.error(f"No recovery strategy for deadlock pattern: {pattern}")
            return {"recovered": False, "action": "No recovery strategy available"}
        
        # Attempt recovery
        try:
            return await recovery_func(deadlock_info, task_graph, state_manager)
        except Exception as e:
            logger.error(f"Deadlock recovery failed: {e}")
            return {"recovered": False, "action": f"Recovery failed: {str(e)}"}
    
    async def _recover_circular_dependency(
        self, 
        deadlock_info: Dict[str, Any],
        task_graph: "TaskGraph",
        state_manager: "StateManager"
    ) -> Dict[str, Any]:
        """Recover from circular dependency by breaking the cycle."""
        affected_nodes = deadlock_info.get("affected_nodes", [])
        if not affected_nodes:
            return {"recovered": False, "action": "No affected nodes found"}
        
        # Find the best node to fail (prefer higher layer nodes)
        nodes_to_check = []
        for node_id in affected_nodes:
            node = task_graph.get_node(node_id)
            if node:
                nodes_to_check.append(node)
        
        if not nodes_to_check:
            return {"recovered": False, "action": "Could not find nodes in cycle"}
        
        # Sort by layer (highest first) to fail leaf nodes
        nodes_to_check.sort(key=lambda n: n.layer, reverse=True)
        node_to_fail = nodes_to_check[0]
        
        # Fail the node to break the cycle
        logger.warning(f"Breaking circular dependency by failing node {node_to_fail.task_id}")
        node_to_fail.update_status(
            TaskStatus.FAILED,
            error_msg="Failed to break circular dependency deadlock"
        )
        
        return {
            "recovered": True,
            "action": f"Broke cycle by failing node {node_to_fail.task_id}"
        }
    
    async def _recover_parent_child_sync(
        self, 
        deadlock_info: Dict[str, Any],
        task_graph: "TaskGraph",
        state_manager: "StateManager"
    ) -> Dict[str, Any]:
        """Recover from parent-child sync issues."""
        issues = deadlock_info.get("diagnostics", {}).get("issues", [])
        
        for issue in issues:
            if "parent" in issue and "stuck_children" in issue:
                parent_id = issue["parent"]
                parent = task_graph.get_node(parent_id)
                
                if parent and parent.status == TaskStatus.RUNNING:
                    # Find the sub-graph containing children
                    children_graph_id = None
                    for child_id in issue["stuck_children"]:
                        child = task_graph.get_node(child_id)
                        if child:
                            # Find graph containing child
                            for graph_id, graph in task_graph.graphs.items():
                                if child_id in graph.nodes:
                                    children_graph_id = graph_id
                                    break
                            if children_graph_id:
                                break
                    
                    if children_graph_id:
                        # Fix the parent
                        parent.sub_graph_id = children_graph_id
                        parent.update_status(TaskStatus.PLAN_DONE)
                        
                        logger.info(f"Fixed parent-child sync: {parent_id} -> PLAN_DONE")
                        return {
                            "recovered": True,
                            "action": f"Fixed parent {parent_id} state and sub-graph reference"
                        }
        
        return {"recovered": False, "action": "Could not fix parent-child sync"}
    
    async def _recover_stuck_aggregation(
        self, 
        deadlock_info: Dict[str, Any],
        task_graph: "TaskGraph",
        state_manager: "StateManager"
    ) -> Dict[str, Any]:
        """Recover from stuck aggregation."""
        stuck_nodes = deadlock_info.get("diagnostics", {}).get("stuck_nodes", [])
        
        for stuck in stuck_nodes:
            node_id = stuck["node"]
            node = task_graph.get_node(node_id)
            
            if node and node.status == TaskStatus.PLAN_DONE:
                # Force aggregation
                logger.info(f"Forcing aggregation for stuck node {node_id}")
                node.update_status(TaskStatus.AGGREGATING)
                
                return {
                    "recovered": True,
                    "action": f"Forced aggregation for node {node_id}"
                }
        
        return {"recovered": False, "action": "No nodes could be forced to aggregate"}
    
    async def _recover_single_node_hang(
        self, 
        deadlock_info: Dict[str, Any],
        task_graph: "TaskGraph",
        state_manager: "StateManager"
    ) -> Dict[str, Any]:
        """Recover from single node hang."""
        affected_nodes = deadlock_info.get("affected_nodes", [])
        if not affected_nodes:
            return {"recovered": False, "action": "No hanging node found"}
        
        node_id = affected_nodes[0]
        node = task_graph.get_node(node_id)
        
        if node and node.status == TaskStatus.RUNNING:
            # Force replan
            logger.warning(f"Forcing replan for hanging node {node_id}")
            node.update_status(
                TaskStatus.NEEDS_REPLAN,
                error_msg="Node hanging in RUNNING state"
            )
            
            return {
                "recovered": True,
                "action": f"Forced hanging node {node_id} to NEEDS_REPLAN"
            }
        
        return {"recovered": False, "action": "Could not recover hanging node"}
    
    async def _recover_orphaned_nodes(
        self, 
        deadlock_info: Dict[str, Any],
        task_graph: "TaskGraph",
        state_manager: "StateManager"
    ) -> Dict[str, Any]:
        """Recover orphaned nodes."""
        orphaned = deadlock_info.get("diagnostics", {}).get("orphaned_nodes", [])
        recovered_count = 0
        
        for orphan_info in orphaned:
            node_id = orphan_info["node"]
            node = task_graph.get_node(node_id)
            
            if node and node.status == TaskStatus.PENDING:
                # Try to transition to READY if conditions allow
                if orphan_info["reason"] == "Parent in invalid state":
                    # Force to READY if parent is terminal
                    parent = task_graph.get_node(node.parent_node_id)
                    if parent and parent.status in [TaskStatus.DONE, TaskStatus.FAILED]:
                        logger.info(f"Forcing orphaned node {node_id} to READY")
                        node.update_status(TaskStatus.READY)
                        recovered_count += 1
        
        if recovered_count > 0:
            return {
                "recovered": True,
                "action": f"Transitioned {recovered_count} orphaned nodes to READY"
            }
        
        return {"recovered": False, "action": "Could not recover orphaned nodes"}


class RecoveryManager:
    """
    Manages all recovery strategies for the system.
    
    This class acts as a facade for different recovery strategies,
    selecting the appropriate strategy based on the error type.
    """
    
    def __init__(self, config: "SentientConfig"):
        """
        Initialize the RecoveryManager.
        
        Args:
            config: System configuration
        """
        self.config = config
        
        # Initialize strategies
        self.retry_strategy = RetryStrategy(
            max_retries=config.execution.max_retries,
            base_delay=getattr(config.execution, 'retry_base_delay', 1.0)
        )
        self.replan_strategy = ReplanStrategy(
            max_replan_attempts=getattr(config.execution, "max_replan_attempts", 2)
        )
        self.timeout_strategy = TimeoutRecoveryStrategy(config)
        self.deadlock_recovery = DeadlockRecoveryStrategy()
        
        # Strategy selection based on error type
        self.error_strategies: List[RecoveryStrategy] = [
            self.timeout_strategy,  # Check timeout first
            self.retry_strategy,    # Then retry
            self.replan_strategy,   # Finally replan
        ]
        
        logger.info("RecoveryManager initialized")
    
    def get_strategy_for_error(self, error: Exception) -> Optional[RecoveryStrategy]:
        """
        Get the appropriate recovery strategy for an error.
        
        Args:
            error: The exception to recover from
            
        Returns:
            Recovery strategy or None if no strategy applies
        """
        # Try each strategy in order
        for strategy in self.error_strategies:
            # Note: We would need to make this async in real implementation
            # For now, assume we can check synchronously
            if hasattr(strategy, 'can_recover'):
                # This is a simplification - in reality we'd need the node
                if isinstance(error, (TaskTimeoutError, TimeoutError)) and isinstance(strategy, TimeoutRecoveryStrategy):
                    return strategy
                elif isinstance(error, (AgentTimeoutError, AgentRateLimitError)) and isinstance(strategy, RetryStrategy):
                    return strategy
                elif isinstance(error, AgentExecutionError) and isinstance(strategy, ReplanStrategy):
                    return strategy
        
        return None
    
    def get_deadlock_recovery_strategy(self) -> DeadlockRecoveryStrategy:
        """Get the deadlock recovery strategy."""
        return self.deadlock_recovery
    
    def get_recovery_stats(self) -> Dict[str, int]:
        """Get statistics about recovery attempts."""
        # In a real implementation, we would track these
        return {
            "retry_attempts": 0,
            "replan_attempts": 0,
            "timeout_recoveries": 0,
            "deadlock_recoveries": 0
        }