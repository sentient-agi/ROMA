"""
ReadyNodeHandler - Handles nodes in READY status.

This handler determines whether a node needs atomization,
planning, or direct execution, and dispatches to the appropriate handler.
"""

from typing import Any, Optional
from loguru import logger

from sentientresearchagent.hierarchical_agent_framework.node.task_node import TaskNode, TaskStatus, NodeType
from sentientresearchagent.hierarchical_agent_framework.orchestration import TransitionEvent
from .base_handler import BaseNodeHandler, HandlerContext
from .plan_handler import PlanHandler
from .execute_handler import ExecuteHandler


class ReadyNodeHandler(BaseNodeHandler):
    """
    Handles nodes in READY status.
    
    This handler:
    - Checks if node needs atomization
    - Determines if node should be planned or executed
    - Dispatches to appropriate sub-handler
    """
    
    def __init__(self):
        super().__init__("ReadyNodeHandler")
        
        # Initialize sub-handlers
        self.plan_handler = PlanHandler()
        self.execute_handler = ExecuteHandler()
    
    def _validate_node_state(self, node: TaskNode) -> bool:
        """Validate node is in READY state."""
        return node.status == TaskStatus.READY
    
    def _get_stage_name(self) -> str:
        """Get tracing stage name."""
        return "node_dispatch"
    
    async def _process(self, node: TaskNode, context: HandlerContext) -> Any:
        """
        Determine how to handle the READY node.
        
        Args:
            node: Node to process
            context: Handler context
            
        Returns:
            Result from sub-handler
        """
        # Don't transition to RUNNING here - let sub-handlers do it
        # to avoid duplicate transitions
        
        # Check max recursion depth
        max_recursion_depth = context.config.get("execution", {}).get("max_recursion_depth", 5)
        
        # If node is at max recursion depth, force execution (skip atomizer)
        if node.layer >= max_recursion_depth:
            logger.info(
                f"Node {node.task_id} at layer {node.layer} reached "
                f"max recursion depth {max_recursion_depth} - forcing execution (skipping atomizer)"
            )
            node.node_type = NodeType.EXECUTE
            return await self._dispatch_to_execute(node, context)
        
        # Check if this is a root node that should be forced to plan
        is_root_node = self._is_root_node(node)
        force_root_planning = context.config.get("execution", {}).get("force_root_node_planning", True)
        
        if is_root_node and force_root_planning:
            logger.info(
                f"Root node {node.task_id} with force_root_node_planning=True "
                "- skipping atomization and forcing PLAN"
            )
            node.node_type = NodeType.PLAN
            return await self._dispatch_to_plan(node, context)
        
        # Run atomization to determine node type
        atomizer_result = await self._atomize_node(node, context)
        
        if atomizer_result is None:
            raise ValueError("Atomizer returned None - cannot determine node type")
        
        # Update node type based on atomizer decision
        node.node_type = atomizer_result
        logger.info(f"Atomizer determined node {node.task_id} type: {atomizer_result}")
        
        # Dispatch to appropriate handler
        if node.node_type == NodeType.PLAN:
            return await self._dispatch_to_plan(node, context)
        elif node.node_type == NodeType.EXECUTE:
            return await self._dispatch_to_execute(node, context)
        else:
            raise ValueError(f"Unexpected node type: {node.node_type}")
    
    def _is_root_node(self, node: TaskNode) -> bool:
        """Check if this is a root node."""
        return (
            node.task_id == "root" or
            node.layer == 0 or
            node.parent_node_id is None
        )
    
    async def _atomize_node(self, node: TaskNode, context: HandlerContext) -> Optional[NodeType]:
        """
        Run atomization to determine if node needs planning or execution.
        
        Args:
            node: Node to atomize
            context: Handler context
            
        Returns:
            NodeType.PLAN or NodeType.EXECUTE
        """
        # Check if atomization should be skipped entirely
        skip_atomization = context.config.get('skip_atomization', False)
        logger.info(f"🐛 DEBUG: skip_atomization = {skip_atomization}, config type = {type(context.config)}")
        
        if skip_atomization:
            logger.info(f"🚫 ATOMIZATION SKIPPED: Node {node.task_id} - skip_atomization is enabled")
            
            # Use hierarchy/depth-based rules instead
            max_recursion_depth = context.config.get('max_planning_layer', 5)
            if node.layer >= max_recursion_depth:
                logger.info(f"🎯 DEPTH RULE APPLIED: Node {node.task_id} at layer {node.layer} >= max_depth {max_recursion_depth} - forcing EXECUTE")
                return NodeType.EXECUTE
            else:
                logger.info(f"🎯 DEPTH RULE APPLIED: Node {node.task_id} at layer {node.layer} < max_depth {max_recursion_depth} - defaulting to PLAN")
                return NodeType.PLAN
        
        # This would use an AtomizerService in real implementation
        # For now, simulate the atomization
        
        logger.info(f"Running atomization for node {node.task_id}")
        
        # Get atomizer agent
        atomizer = await self._get_agent_for_node(node, context, "atomize")
        if not atomizer:
            logger.warning(f"No atomizer available - defaulting to EXECUTE")
            return NodeType.EXECUTE
        
        # Build atomization context
        atomizer_context = await self._build_context_for_node(
            node,
            context,
            context_type="atomization"
        )
        
        # Run atomizer
        try:
            result = await atomizer.process(node, atomizer_context, context.trace_manager)
            
            if result and hasattr(result, 'is_atomic'):
                if result.is_atomic:
                    logger.info(f"Node {node.task_id} determined to be atomic")
                    return NodeType.EXECUTE
                else:
                    logger.info(f"Node {node.task_id} requires planning")
                    return NodeType.PLAN
            else:
                logger.warning(f"Invalid atomizer result - defaulting to EXECUTE")
                return NodeType.EXECUTE
                
        except Exception as e:
            import traceback
            error_traceback = traceback.format_exc()

            logger.error(
                f"Atomization failed for {node.task_id}\n"
                f"Error Type: {type(e).__name__}\n"
                f"Error Message: {str(e)}\n"
                f"Traceback:\n{error_traceback}"
            )

            # Store error in aux_data for debugging
            if node.aux_data is None:
                node.aux_data = {}
            node.aux_data.setdefault("atomization_errors", []).append({
                "error_type": type(e).__name__,
                "error_message": str(e),
                "traceback": error_traceback
            })

            # Default to execution on atomizer failure
            return NodeType.EXECUTE
    
    async def _dispatch_to_plan(self, node: TaskNode, context: HandlerContext) -> Any:
        """
        Dispatch node to plan handler.
        
        Args:
            node: Node to plan
            context: Handler context
            
        Returns:
            Planning result
        """
        logger.info(f"Dispatching node {node.task_id} to PlanHandler")
        
        # Reset status for sub-handler
        node.status = TaskStatus.READY
        
        # Delegate to plan handler
        return await self.plan_handler.handle(node, context)
    
    async def _dispatch_to_execute(self, node: TaskNode, context: HandlerContext) -> Any:
        """
        Dispatch node to execute handler.
        
        Args:
            node: Node to execute
            context: Handler context
            
        Returns:
            Execution result
        """
        logger.info(f"Dispatching node {node.task_id} to ExecuteHandler")
        
        # Reset status for sub-handler
        node.status = TaskStatus.READY
        
        # Clear any aggregator configuration if present
        if node.agent_name and 'aggregator' in node.agent_name.lower():
            logger.info(f"Clearing aggregator configuration from node {node.task_id}")
            node.agent_name = None
        
        # Delegate to execute handler
        return await self.execute_handler.handle(node, context)
    
    async def _post_process(self, node: TaskNode, context: HandlerContext, result: Any):
        """
        Post-process is handled by sub-handlers.
        Only update metrics here.
        """
        # Don't call parent post-process as sub-handlers handle it
        pass