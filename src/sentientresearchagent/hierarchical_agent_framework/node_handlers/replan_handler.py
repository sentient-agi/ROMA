"""
ReplanHandler - Handles nodes that need replanning.

This handler manages the replanning process for nodes that
have failed or need modification.
"""

from typing import Any, Optional
from loguru import logger

from sentientresearchagent.hierarchical_agent_framework.node.task_node import TaskNode, TaskStatus, NodeType
from sentientresearchagent.hierarchical_agent_framework.context.agent_io_models import PlanOutput, ReplanRequestDetails
from .base_handler import BaseNodeHandler, HandlerContext


class ReplanHandler(BaseNodeHandler):
    """
    Handles nodes in NEEDS_REPLAN status.
    
    This handler:
    - Determines if replanning is viable
    - Chooses between plan modification or full replan
    - Executes the replanning
    - Handles user modifications vs system replans
    """
    
    def __init__(self):
        super().__init__("ReplanHandler")
    
    def _validate_node_state(self, node: TaskNode) -> bool:
        """Validate node is in NEEDS_REPLAN state."""
        return node.status == TaskStatus.NEEDS_REPLAN
    
    def _get_stage_name(self) -> str:
        """Get tracing stage name."""
        return "replanning"
    
    async def _process(self, node: TaskNode, context: HandlerContext) -> Optional[PlanOutput]:
        """
        Main replanning logic.
        
        Args:
            node: Node to replan
            context: Handler context
            
        Returns:
            New plan output or None if replanning failed
        """
        # Check if this is a user-requested modification
        is_user_modification = node.aux_data.get('user_modification_instructions') is not None
        
        # Check replan attempts (skip for user modifications)
        max_replan_attempts = context.config.get("max_replan_attempts", 2)
        if not is_user_modification and node.replan_attempts >= max_replan_attempts:
            logger.warning(
                f"Node {node.task_id} has reached max replan attempts "
                f"({max_replan_attempts}) - failing node"
            )
            await context.state_manager.transition_node(
                node,
                TaskStatus.FAILED,
                reason="Max replan attempts reached"
            )
            return None
        
        # Increment attempts for system replans
        if not is_user_modification:
            node.replan_attempts += 1
        
        # Ensure node type is PLAN for replanning
        node.node_type = NodeType.PLAN
        
        # Try plan modification first if available
        if await self._can_modify_plan(node, context):
            result = await self._modify_plan(node, context)
            if result:
                return result
        
        # Fall back to full replanning
        return await self._full_replan(node, context)
    
    async def _can_modify_plan(self, node: TaskNode, context: HandlerContext) -> bool:
        """
        Check if plan modification is available.
        
        Args:
            node: Node to check
            context: Handler context
            
        Returns:
            True if plan modification is possible
        """
        # Check if we have a plan modifier agent
        modifier = await self._get_agent_for_node(node, context, "modify_plan")
        
        # Check if we have the original plan and modification instructions
        has_original_plan = node.aux_data.get('original_plan_for_modification') is not None
        has_instructions = node.aux_data.get('user_modification_instructions') is not None
        
        return modifier is not None and (has_original_plan or has_instructions)
    
    async def _modify_plan(self, node: TaskNode, context: HandlerContext) -> Optional[PlanOutput]:
        """
        Modify an existing plan.
        
        Args:
            node: Node with plan to modify
            context: Handler context
            
        Returns:
            Modified plan or None if modification failed
        """
        logger.info(f"Attempting plan modification for node {node.task_id}")
        
        # Get plan modifier agent
        modifier = await self._get_agent_for_node(node, context, "modify_plan")
        if not modifier:
            logger.warning("No plan modifier available - falling back to full replan")
            return None
        
        # Build modification context
        modification_context = await self._build_modification_context(node, context)
        
        # Execute modification
        try:
            result = await modifier.process(node, modification_context, context.trace_manager)
            
            if result and hasattr(result, 'sub_tasks'):
                logger.info(f"Plan modification successful for {node.task_id}")
                return result
            else:
                logger.warning("Plan modifier returned invalid result")
                return None
                
        except Exception as e:
            logger.error(f"Plan modification failed: {e}")
            return None
    
    async def _full_replan(self, node: TaskNode, context: HandlerContext) -> Optional[PlanOutput]:
        """
        Perform full replanning.
        
        Args:
            node: Node to replan
            context: Handler context
            
        Returns:
            New plan or None if replanning failed
        """
        logger.info(f"Performing full replan for node {node.task_id}")
        
        # Get planner agent
        planner = await self._get_agent_for_node(node, context, "plan")
        if not planner:
            raise ValueError(f"No planner available for replanning node {node.task_id}")
        
        # Build replanning context
        replan_context = await self._build_replan_context(node, context)
        
        # Store input for tracing
        node.input_payload_dict = replan_context.model_dump()
        
        # Execute replanning
        result = await planner.process(node, replan_context, context.trace_manager)
        
        if not result or not hasattr(result, 'sub_tasks'):
            raise ValueError("Replanning failed - planner returned invalid output")
        
        return result
    
    async def _build_modification_context(self, node: TaskNode, context: HandlerContext) -> Any:
        """Build context for plan modification."""
        # Get base context
        base_context = await self._build_context_for_node(
            node,
            context,
            context_type="planning"
        )
        
        # Add modification-specific data
        if hasattr(base_context, 'aux_data'):
            base_context.aux_data = {
                'original_plan': node.aux_data.get('original_plan_for_modification'),
                'modification_instructions': node.aux_data.get('user_modification_instructions'),
                'replan_reason': node.replan_reason
            }
        
        return base_context
    
    async def _build_replan_context(self, node: TaskNode, context: HandlerContext) -> Any:
        """Build context for full replanning."""
        # Get base context
        base_context = await self._build_context_for_node(
            node,
            context,
            context_type="planning"
        )
        
        # Add replan details
        if node.replan_details:
            # In real implementation, would add replan_details to context
            pass
        
        # Add failure context if this is error recovery
        if node.error:
            if hasattr(base_context, 'aux_data'):
                base_context.aux_data = base_context.aux_data or {}
                base_context.aux_data['previous_error'] = node.error
                base_context.aux_data['replan_reason'] = node.replan_reason
        
        return base_context
    
    async def _post_process(self, node: TaskNode, context: HandlerContext, result: PlanOutput):
        """Post-process replanning result."""
        if result and result.sub_tasks:
            # Check if this was a user modification
            is_user_modification = node.aux_data.get('user_modification_instructions') is not None if node.aux_data else False

            review_result = {"status": "approved"}

            # HITL review if available
            if context.hitl_service:
                if is_user_modification:
                    # Review modified plan
                    review_result = await context.hitl_service.review_modified_plan(
                        node=node,
                        modified_plan=result,
                        replan_attempt=node.replan_attempts
                    )
                else:
                    # Review replanned result
                    review_result = await context.hitl_service.review_plan(
                        node=node,
                        plan_output=result,
                        planning_context=node.input_payload_dict,
                        is_replan=True
                    )

            if review_result["status"] == "request_modification":
                # Another modification requested
                modification_instructions = review_result.get('modification_instructions', '')
                if node.aux_data is None:
                    node.aux_data = {}
                node.aux_data['original_plan_for_modification'] = result
                node.aux_data['user_modification_instructions'] = modification_instructions
                node.replan_reason = f"User requested modification: {modification_instructions[:100]}..."
                
                # Stay in NEEDS_REPLAN
                logger.info(f"User requested another modification for {node.task_id}")
                return

            if review_result["status"] != "approved":
                # Not approved
                await context.state_manager.transition_node(
                    node,
                    TaskStatus.FAILED,
                    reason=f"Replan not approved: {review_result['status']}"
                )
                return

            # Clear existing sub-graph if any (handle legacy cases where sub_graph_id was unset)
            existing_sub_graph_id = node.sub_graph_id or f"subgraph_{node.task_id}"
            if getattr(context, "task_graph", None) and context.task_graph.get_graph(existing_sub_graph_id):
                logger.info(f"Clearing existing sub-graph {existing_sub_graph_id}")
                try:
                    context.task_graph.remove_graph_and_nodes(existing_sub_graph_id, context.knowledge_store)
                except AttributeError:
                    logger.warning("TaskGraph.remove_graph_and_nodes not available; skipping explicit graph removal")
            node.sub_graph_id = None
            node.planned_sub_task_ids = []

            # Create new sub-nodes (placeholder for future integration)
            # In real implementation: await context.sub_node_creator.create_sub_nodes(node, result)

            # Clear replan bookkeeping regardless of prior structure
            node.replan_details = None
            node.replan_reason = None
            if node.aux_data:
                node.aux_data.pop('original_plan_for_modification', None)
                node.aux_data.pop('user_modification_instructions', None)

            # Transition to PLAN_DONE so orchestration can pick up aggregation immediately
            await context.state_manager.transition_node(
                node,
                TaskStatus.PLAN_DONE,
                reason=f"Replanning complete after {node.replan_attempts} attempts",
                result=result,
                result_summary=f"Replanned with {len(result.sub_tasks)} sub-tasks"
            )
        else:
            # Replanning failed
            await context.state_manager.transition_node(
                node,
                TaskStatus.FAILED,
                reason="Replanning produced no valid plan"
            )
        
        # Call parent post-process
        await super()._post_process(node, context, result)
