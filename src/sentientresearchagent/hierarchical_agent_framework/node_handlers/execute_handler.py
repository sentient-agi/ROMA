"""
ExecuteHandler - Handles nodes that need execution.

This simplified handler focuses solely on execution logic,
delegating common functionality to BaseNodeHandler.
"""

from typing import Any
from loguru import logger

from sentientresearchagent.hierarchical_agent_framework.node.task_node import TaskNode, TaskStatus, NodeType
from .base_handler import BaseNodeHandler, HandlerContext


class ExecuteHandler(BaseNodeHandler):
    """
    Handles nodes that need to be executed.
    
    This handler is responsible for:
    - Getting an executor agent
    - Building execution context
    - Executing the task
    - Processing results
    - Handling HITL review
    """
    
    def __init__(self):
        super().__init__("ExecuteHandler")
    
    def _validate_node_state(self, node: TaskNode) -> bool:
        """Validate node is ready for execution."""
        # Node should be READY and of EXECUTE type
        return (
            node.status == TaskStatus.READY and
            node.node_type == NodeType.EXECUTE
        )
    
    def _get_stage_name(self) -> str:
        """Get tracing stage name."""
        return "execution"
    
    async def _process(self, node: TaskNode, context: HandlerContext) -> Any:
        """
        Main execution logic.
        
        Args:
            node: Node to execute
            context: Handler context
            
        Returns:
            Execution result
        """
        # Build execution context
        execution_context = await self._build_context_for_node(
            node, 
            context, 
            context_type="execution"
        )
        
        # Store input for tracing
        node.input_payload_dict = execution_context.model_dump()
        
        # HITL review before execution (check config first)
        hitl_before_execute = context.config.get("execution", {}).get("hitl_before_execute", False)
        if hitl_before_execute:
            review_result = await self._review_execution(node, execution_context, context)
            
            if review_result["status"] != "approved":
                raise ValueError(f"Execution not approved: {review_result['status']}")
        
        # Get executor agent
        executor = await self._get_agent_for_node(node, context, "execute")
        if not executor:
            raise ValueError(f"No executor available for node {node.task_id}")
        
        # Execute task
        logger.info(f"Executing task for node {node.task_id} with {node.task_type} executor")
        result = await executor.process(node, execution_context, context.trace_manager)
        
        # Process result based on type
        result = await self._process_result(node, result, context)
        
        return result
    
    async def _review_execution(
        self, 
        node: TaskNode, 
        execution_context: Any, 
        context: HandlerContext
    ) -> dict:
        """Review execution with HITL if enabled."""
        if context.hitl_service:
            return await context.hitl_service.review_execution(
                node=node,
                execution_context=execution_context
            )
        else:
            # No HITL service available - auto-approve
            return {"status": "approved"}
    
    async def _process_result(
        self, 
        node: TaskNode, 
        result: Any, 
        context: HandlerContext
    ) -> Any:
        """
        Process execution result based on type.
        
        Args:
            node: Executed node
            result: Raw result from executor
            context: Handler context
            
        Returns:
            Processed result
        """
        if result is None:
            logger.warning(f"Executor returned None for node {node.task_id}")
            return None
        
        # Extract meaningful information based on result type
        if hasattr(result, 'output_text_with_citations'):
            # Search result
            logger.info(f"Processing search results for {node.task_id}")
            node.output_type_description = "search_results"
            
        elif hasattr(result, 'reasoning_steps'):
            # Reasoning result
            logger.info(f"Processing reasoning output for {node.task_id}")
            node.output_type_description = "reasoning_output"
            
        elif isinstance(result, str):
            # Text result
            logger.info(f"Processing text output for {node.task_id}")
            node.output_type_description = "text_output"
            
        else:
            # Generic structured output
            logger.info(f"Processing {type(result).__name__} output for {node.task_id}")
            node.output_type_description = f"{type(result).__name__}_output"
        
        return result
    
    async def _post_process(
        self, 
        node: TaskNode, 
        context: HandlerContext, 
        result: Any
    ):
        """Post-process execution result."""
        # Handle the result
        await self._handle_agent_result(
            node,
            result,
            context,
            success_status=TaskStatus.DONE
        )
        
        # Store execution metadata
        if node.aux_data is not None:
            if hasattr(executor := node.aux_data.get('executor'), 'get_model_info'):
                node.aux_data['execution_details'] = {
                    'model_info': executor.get_model_info(),
                    'execution_time': node.timestamp_updated
                }
        
        # Call parent post-process
        await super()._post_process(node, context, result)