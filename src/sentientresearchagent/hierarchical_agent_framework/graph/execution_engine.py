"""
ExecutionEngine v2 - Backward-compatible wrapper around the new orchestration components.

This provides the same API as the original ExecutionEngine but delegates to the new
modular architecture (ExecutionOrchestrator, TaskScheduler, etc.).
"""

from typing import Optional, Dict, Any, TYPE_CHECKING
from loguru import logger
import uuid

from sentientresearchagent.hierarchical_agent_framework.node.task_node import TaskType
from sentientresearchagent.hierarchical_agent_framework.orchestration.execution_orchestrator import ExecutionOrchestrator
from sentientresearchagent.hierarchical_agent_framework.orchestration.task_scheduler import TaskScheduler
from sentientresearchagent.hierarchical_agent_framework.orchestration.deadlock_detector import DeadlockDetector
from sentientresearchagent.hierarchical_agent_framework.orchestration.recovery_manager import RecoveryManager
from sentientresearchagent.hierarchical_agent_framework.orchestration.state_transition_manager import StateTransitionManager
from sentientresearchagent.hierarchical_agent_framework.services import HITLService, HITLConfig
from sentientresearchagent.hierarchical_agent_framework.node_handlers import ReadyNodeHandler, HandlerContext
from sentientresearchagent.hierarchical_agent_framework.services import AgentSelector, ContextBuilderService
from sentientresearchagent.hierarchical_agent_framework.graph.project_initializer import ProjectInitializer

if TYPE_CHECKING:
    from sentientresearchagent.hierarchical_agent_framework.graph.task_graph import TaskGraph
    from sentientresearchagent.hierarchical_agent_framework.graph.state_manager import StateManager
    from sentientresearchagent.hierarchical_agent_framework.context.knowledge_store import KnowledgeStore
    from sentientresearchagent.hierarchical_agent_framework.node.node_processor import NodeProcessor
    from sentientresearchagent.config import SentientConfig
    from sentientresearchagent.hierarchical_agent_framework.persistence.checkpoint_manager import CheckpointManager
    from sentientresearchagent.hierarchical_agent_framework.agent_configs.agent_registry import AgentRegistry


class ExecutionEngine:
    """
    Backward-compatible ExecutionEngine that delegates to the new orchestration architecture.
    
    This maintains the same API as the original ExecutionEngine while using the new
    modular components internally.
    """
    
    def __init__(
        self,
        task_graph: "TaskGraph",
        state_manager: "StateManager",
        knowledge_store: "KnowledgeStore",
        node_processor: "NodeProcessor",
        agent_registry: "AgentRegistry",
        config: "SentientConfig",
        checkpoint_manager: Optional["CheckpointManager"] = None,
        websocket_handler: Optional[Any] = None
    ):
        """
        Initialize the ExecutionEngine with v2 components.
        
        Args:
            task_graph: The task graph to execute
            state_manager: Manages state transitions
            knowledge_store: Stores execution knowledge
            node_processor: Processes individual nodes
            agent_registry: Registry of available agents
            config: System configuration
            checkpoint_manager: Manages checkpoints (optional)
            websocket_handler: Handler for WebSocket communication (optional)
        """
        self.task_graph = task_graph
        self.state_manager = state_manager
        self.knowledge_store = knowledge_store
        self.node_processor = node_processor
        self.agent_registry = agent_registry
        self.config = config
        self.checkpoint_manager = checkpoint_manager
        
        # Initialize v2 services
        self.hitl_service = HITLService(
            HITLConfig.from_config(config),
            websocket_handler=websocket_handler
        )
        
        self.agent_selector = AgentSelector(blueprint=None)  # Will use default mappings
        self.context_builder_service = ContextBuilderService()  # Uses default config
        
        # Initialize state transition manager
        self.state_transition_manager = StateTransitionManager(task_graph, knowledge_store)
        
        # Initialize v2 orchestration components
        self.task_scheduler = TaskScheduler(task_graph, state_manager)
        self.deadlock_detector = DeadlockDetector(task_graph, state_manager)
        self.recovery_manager = RecoveryManager(config)
        
        # Initialize handler context
        # Note: We need a trace manager - create a simple one or get from config
        from sentientresearchagent.hierarchical_agent_framework.tracing.manager import TraceManager
        trace_manager = TraceManager(project_id="default")
        
        # Create node processor config from main config
        from sentientresearchagent.framework_entry import create_node_processor_config_from_main_config
        node_config = create_node_processor_config_from_main_config(config) if hasattr(config, 'execution') else config
        
        self.handler_context = HandlerContext(
            knowledge_store=knowledge_store,
            agent_registry=agent_registry,
            state_manager=self.state_transition_manager,
            agent_selector=self.agent_selector,
            context_builder=self.context_builder_service,
            hitl_service=self.hitl_service,
            trace_manager=trace_manager,
            config=node_config.dict() if hasattr(node_config, 'dict') else node_config,
            update_callback=None
        )
        
        # Initialize node handler
        self.node_handler = ReadyNodeHandler()
        
        # Create orchestrator
        self.orchestrator = ExecutionOrchestrator(
            task_graph=task_graph,
            state_manager=state_manager,
            knowledge_store=knowledge_store,
            node_processor=node_processor,
            config=config,
            task_scheduler=self.task_scheduler,
            deadlock_detector=self.deadlock_detector,
            recovery_manager=self.recovery_manager,
            checkpoint_manager=checkpoint_manager
        )
        # Expose the orchestrator's update manager for external configuration
        self.update_manager = self.orchestrator.update_manager
        
        # Note: The orchestrator uses node_processor directly, not node_handler
        
        # Initialize project initializer for compatibility
        self.project_initializer = ProjectInitializer()
        
        logger.info("ExecutionEngine v2 initialized with new orchestration architecture")
    
    async def run_project_flow(
        self, 
        root_goal: str, 
        root_task_type: TaskType = TaskType.WRITE, 
        max_steps: int = 250
    ) -> Dict[str, Any]:
        """
        Complete project flow: Initializes project, then runs execution cycle.
        
        This method maintains backward compatibility with the original ExecutionEngine API.
        
        Args:
            root_goal: The root goal to achieve
            root_task_type: Type of the root task
            max_steps: Maximum execution steps
            
        Returns:
            Execution results
        """
        logger.info(f"ExecutionEngine v2: Starting project flow with root goal: '{root_goal}'")
        
        # Generate execution ID
        execution_id = str(uuid.uuid4())
        
        # Note: The orchestrator will create the root node internally
        # We don't need to create it here
        
        # Run execution using the orchestrator
        try:
            result = await self.orchestrator.execute(
                root_goal=root_goal,
                max_steps=max_steps,
                execution_id=execution_id
            )
            
            logger.info(f"ExecutionEngine v2: Project flow completed successfully")
            return result
            
        except Exception as e:
            logger.error(f"ExecutionEngine v2: Project flow failed: {e}")
            raise
    
    async def run_execution_cycle(
        self,
        max_steps: int = 250,
        execution_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Run the execution cycle.
        
        This method is provided for backward compatibility but delegates to the orchestrator.
        
        Args:
            max_steps: Maximum execution steps
            execution_id: Optional execution ID
            
        Returns:
            Execution results
        """
        if not execution_id:
            execution_id = str(uuid.uuid4())
            
        # Get root goal from the task graph
        root_node = self.task_graph.get_node("root")
        if not root_node:
            raise ValueError("No root node found in task graph")
            
        return await self.orchestrator.execute(
            root_goal=root_node.goal,
            max_steps=max_steps,
            execution_id=execution_id
        )
    
    def get_execution_stats(self) -> Dict[str, Any]:
        """Get execution statistics."""
        return self.orchestrator.get_execution_stats()
    
    def get_hitl_metrics(self) -> Dict[str, Any]:
        """Get HITL metrics."""
        return self.hitl_service.get_metrics()
