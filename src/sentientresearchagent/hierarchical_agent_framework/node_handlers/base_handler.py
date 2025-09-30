"""
BaseNodeHandler - Base class for all node handlers.

Provides common functionality and enforces a consistent interface
for all node handlers, reducing code duplication and complexity.
"""

from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, TYPE_CHECKING
from dataclasses import dataclass
from loguru import logger

from sentientresearchagent.hierarchical_agent_framework.node.task_node import TaskNode, TaskStatus
from sentientresearchagent.hierarchical_agent_framework.context.agent_io_models import (
    AgentTaskInput, PlanOutput, AtomizerOutput
)

if TYPE_CHECKING:
    from sentientresearchagent.hierarchical_agent_framework.context.knowledge_store import KnowledgeStore
    from sentientresearchagent.hierarchical_agent_framework.agents.registry import AgentRegistry
    from sentientresearchagent.hierarchical_agent_framework.orchestration import StateTransitionManager
    from sentientresearchagent.hierarchical_agent_framework.services.agent_selector import AgentSelector
    from sentientresearchagent.hierarchical_agent_framework.services.context_builder import ContextBuilderService
    from sentientresearchagent.hierarchical_agent_framework.services.hitl_service import HITLService
    from sentientresearchagent.hierarchical_agent_framework.tracing.manager import TraceManager
    from sentientresearchagent.hierarchical_agent_framework.graph.task_graph import TaskGraph


@dataclass
class HandlerContext:
    """Context object containing all services a handler might need."""
    knowledge_store: "KnowledgeStore"
    agent_registry: "AgentRegistry"
    state_manager: "StateTransitionManager"
    agent_selector: "AgentSelector"
    context_builder: "ContextBuilderService"
    hitl_service: "HITLService"
    trace_manager: "TraceManager"
    config: Dict[str, Any]
    task_graph: Optional["TaskGraph"] = None
    update_callback: Optional[callable] = None


class BaseNodeHandler(ABC):
    """
    Base class for all node handlers.
    
    This class provides common functionality and ensures a consistent
    interface across all handlers.
    """
    
    def __init__(self, handler_name: str):
        """
        Initialize the base handler.
        
        Args:
            handler_name: Name of this handler for logging
        """
        self.handler_name = handler_name
        self._metrics = {
            "nodes_handled": 0,
            "successful": 0,
            "failed": 0,
            "average_duration": 0.0
        }
    
    async def handle(self, node: TaskNode, context: HandlerContext) -> bool:
        """
        Handle a node with common pre/post processing.
        
        Args:
            node: Node to handle
            context: Handler context with services
            
        Returns:
            True if handling was successful
        """
        import time
        start_time = time.time()
        
        logger.info(f"{self.handler_name}: Handling node {node.task_id} "
                   f"(status: {node.status}, goal: '{node.goal[:50]}...')")
        
        # Start tracing
        stage_name = self._get_stage_name()
        stage = context.trace_manager.start_stage(
            node_id=node.task_id,
            stage_name=stage_name,
            agent_name=node.agent_name,
            adapter_name=self.handler_name
        )
        
        try:
            # Validate node state
            if not self._validate_node_state(node):
                raise ValueError(f"Invalid node state for {self.handler_name}")
            
            # Pre-processing hook
            await self._pre_process(node, context)
            
            # Main processing
            result = await self._process(node, context)
            
            # Post-processing hook
            await self._post_process(node, context, result)
            
            # Update metrics
            self._update_metrics(True, time.time() - start_time)
            
            # Complete tracing
            context.trace_manager.complete_stage(
                node_id=node.task_id,
                stage_name=stage_name,
                output_data=self._extract_output_data(result)
            )
            
            # Trigger update callback if provided
            if context.update_callback:
                try:
                    context.update_callback()
                except Exception as e:
                    logger.warning(f"Update callback failed: {e}")
            
            logger.success(f"{self.handler_name}: Successfully handled node {node.task_id}")
            return True
            
        except Exception as e:
            import traceback
            error_traceback = traceback.format_exc()

            logger.error(
                f"{self.handler_name}: Failed to handle node {node.task_id}\n"
                f"Error Type: {type(e).__name__}\n"
                f"Error Message: {str(e)}\n"
                f"Traceback:\n{error_traceback}"
            )

            # Store detailed error info in aux_data for debugging
            if node.aux_data is None:
                node.aux_data = {}
            node.aux_data.setdefault("error_history", []).append({
                "handler": self.handler_name,
                "error_type": type(e).__name__,
                "error_message": str(e),
                "traceback": error_traceback,
                "timestamp": time.time()
            })

            # Update metrics
            self._update_metrics(False, time.time() - start_time)

            # Complete tracing with error
            context.trace_manager.complete_stage(
                node_id=node.task_id,
                stage_name=stage_name,
                error=f"{type(e).__name__}: {str(e)}"
            )

            # Update node status if needed
            if node.status not in [TaskStatus.FAILED, TaskStatus.CANCELLED]:
                await context.state_manager.transition_node(
                    node,
                    TaskStatus.FAILED,
                    reason=f"Handler error: {type(e).__name__}: {str(e)}",
                    error_msg=str(e)
                )

            return False
    
    @abstractmethod
    def _validate_node_state(self, node: TaskNode) -> bool:
        """
        Validate that the node is in an appropriate state for this handler.
        
        Args:
            node: Node to validate
            
        Returns:
            True if node state is valid
        """
        pass
    
    @abstractmethod
    async def _process(self, node: TaskNode, context: HandlerContext) -> Any:
        """
        Main processing logic for the handler.
        
        Args:
            node: Node to process
            context: Handler context
            
        Returns:
            Processing result
        """
        pass
    
    @abstractmethod
    def _get_stage_name(self) -> str:
        """Get the tracing stage name for this handler."""
        pass
    
    async def _pre_process(self, node: TaskNode, context: HandlerContext):
        """
        Pre-processing hook.
        
        Args:
            node: Node being processed
            context: Handler context
        """
        # Default: Update node to RUNNING if not already
        if node.status != TaskStatus.RUNNING:
            await context.state_manager.transition_node(
                node,
                TaskStatus.RUNNING,
                reason=f"Starting {self._get_stage_name()}"
            )
    
    async def _post_process(
        self, 
        node: TaskNode, 
        context: HandlerContext, 
        result: Any
    ):
        """
        Post-processing hook.
        
        Args:
            node: Node that was processed
            context: Handler context
            result: Result from processing
        """
        # Update knowledge store
        context.knowledge_store.add_or_update_record_from_node(node)
    
    def _extract_output_data(self, result: Any) -> Any:
        """
        Extract output data for tracing.
        
        Args:
            result: Processing result
            
        Returns:
            Data suitable for tracing
        """
        if result is None:
            return None
        
        if hasattr(result, 'model_dump'):
            return result.model_dump()
        
        if isinstance(result, (str, int, float, bool, list, dict)):
            return result
        
        return str(result)
    
    def _update_metrics(self, success: bool, duration: float):
        """Update handler metrics."""
        self._metrics["nodes_handled"] += 1
        
        if success:
            self._metrics["successful"] += 1
        else:
            self._metrics["failed"] += 1
        
        # Update average duration
        current_avg = self._metrics["average_duration"]
        total_handled = self._metrics["nodes_handled"]
        self._metrics["average_duration"] = (
            (current_avg * (total_handled - 1) + duration) / total_handled
        )
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get handler metrics."""
        return self._metrics.copy()
    
    async def _get_agent_for_node(
        self, 
        node: TaskNode, 
        context: HandlerContext,
        action_verb: str
    ) -> Optional[Any]:
        """
        Get the appropriate agent adapter for a node.
        
        Args:
            node: Node needing an agent
            context: Handler context
            action_verb: Action verb (plan, execute, aggregate, etc.)
            
        Returns:
            Agent adapter or None
        """
        # Use agent selector service
        agent_name = await context.agent_selector.select_agent(
            node=node,
            action_verb=action_verb,
            task_type=node.task_type
        )
        
        if not agent_name:
            logger.error(f"No agent found for {action_verb} on {node.task_id}")
            return None
        
        # Update node's agent name
        node.agent_name = agent_name
        
        # Get adapter from registry
        adapter = context.agent_registry.get_agent_adapter(node, action_verb)
        
        if not adapter:
            logger.error(f"No adapter found for agent {agent_name} with action {action_verb}")
            return None
        
        logger.info(f"Selected agent {agent_name} for {action_verb} on {node.task_id}")
        return adapter
    
    async def _build_context_for_node(
        self,
        node: TaskNode,
        context: HandlerContext,
        context_type: str = "default"
    ) -> AgentTaskInput:
        """
        Build context for a node using the context builder service.
        
        Args:
            node: Node needing context
            context: Handler context
            context_type: Type of context to build
            
        Returns:
            Built context
        """
        return await context.context_builder.build_context(
            node=node,
            context_type=context_type,
            knowledge_store=context.knowledge_store,
            task_graph=context.task_graph  # Now properly passed
        )
    
    async def _handle_agent_result(
        self,
        node: TaskNode,
        result: Any,
        context: HandlerContext,
        success_status: TaskStatus = TaskStatus.DONE
    ):
        """
        Handle the result from an agent.
        
        Args:
            node: Node that was processed
            result: Result from agent
            context: Handler context
            success_status: Status to set on success
        """
        if result is not None:
            # Store result
            node.result = result
            node.aux_data['full_result'] = result
            
            # Generate summary
            if hasattr(result, 'sub_tasks'):
                # Plan result
                task_count = len(result.sub_tasks) if result.sub_tasks else 0
                node.output_summary = f"Generated {task_count} sub-tasks"
            elif hasattr(result, 'output_text_with_citations'):
                # Search result
                node.output_summary = f"Search completed: {result.output_text_with_citations[:100]}..."
            elif isinstance(result, str):
                # Text result
                node.output_summary = result  # No truncation
            else:
                # Generic result
                node.output_summary = f"Completed with {type(result).__name__}"
            
            # Transition to success
            await context.state_manager.transition_node(
                node,
                success_status,
                reason=f"{self._get_stage_name()} completed",
                result=result,
                result_summary=node.output_summary
            )
        else:
            # No result - failure
            await context.state_manager.transition_node(
                node,
                TaskStatus.FAILED,
                reason="No result from agent",
                error_msg="Agent returned no result"
            )