"""
System Manager V2 - Using refactored components

This is an updated SystemManager that uses the new modular components.
You can swap this in when ready for production use.
"""

from typing import Dict, Any, Optional, List, TYPE_CHECKING
from loguru import logger

from ..config import SentientConfig, auto_load_config
from .cache.cache_manager import init_cache_manager
from .error_handler import ErrorHandler, set_error_handler

# Core components
from ..hierarchical_agent_framework.graph.task_graph import TaskGraph
from ..hierarchical_agent_framework.context.knowledge_store import KnowledgeStore
from ..hierarchical_agent_framework.graph.state_manager import StateManager

# New orchestration components
from ..hierarchical_agent_framework.orchestration import (
    ExecutionOrchestrator,
    TaskScheduler,
    DeadlockDetector,
    RecoveryManager,
    StateTransitionManager
)

# New services
from ..hierarchical_agent_framework.services import (
    HITLService,
    HITLConfig,
    AgentSelector,
    ContextBuilderService,
    ContextConfig
)

# Existing components we still need
from ..hierarchical_agent_framework.agents.registry import AgentRegistry
from ..hierarchical_agent_framework.tracing.manager import TraceManager
from ..hierarchical_agent_framework.agent_configs.profile_loader import ProfileLoader
from ..framework_entry import create_node_processor_config_from_main_config

# Optimized components
from ..hierarchical_agent_framework.context.optimized_knowledge_store import OptimizedKnowledgeStore
from ..hierarchical_agent_framework.context.cached_context_builder import CachedContextBuilder
from ..hierarchical_agent_framework.traces.batched_trace_manager import BatchedTraceManager
from ..hierarchical_agent_framework.services.node_update_manager import NodeUpdateManager

# Import WebSocket HITL utils with error handling
try:
    from ..hierarchical_agent_framework.utils.websocket_hitl_utils import (
        set_socketio_instance, 
        set_hitl_timeout, 
        is_websocket_hitl_ready,
        get_websocket_hitl_status
    )
    WEBSOCKET_HITL_AVAILABLE = True
except ImportError as e:
    logger.warning(f"WebSocket HITL functions not available: {e}")
    WEBSOCKET_HITL_AVAILABLE = False
    
    # Define fallback functions
    def set_socketio_instance(socketio):
        logger.warning("WebSocket HITL not available - using fallback")
    
    def set_hitl_timeout(timeout_seconds: float):
        logger.warning("WebSocket HITL not available - using fallback")
    
    def is_websocket_hitl_ready() -> bool:
        return False
    
    def get_websocket_hitl_status() -> Dict[str, Any]:
        return {
            "ready": False,
            "socketio_available": False,
            "connected_clients": 0,
            "pending_requests": 0,
            "timeout_seconds": 1800.0,
            "error": "WebSocket HITL functions not available"
        }

if TYPE_CHECKING:
    from ..framework_entry import SimpleSentientAgent
    from ..hierarchical_agent_framework.node.node_processor import NodeProcessor


class SystemManagerV2:
    """
    Updated system manager using the refactored modular components.
    """
    
    def __init__(self, config: Optional[SentientConfig] = None):
        """Initialize with refactored components."""
        self.config = config or auto_load_config()
        self._initialized = False  # Initialize as False until setup is complete
        logger.info("📋 SystemManagerV2: Initializing with refactored components")
        
        # Core components
        self.task_graph = TaskGraph()
        
        # Use optimized knowledge store if enabled
        optimization_level = getattr(self.config.execution, 'optimization_level', 'balanced')
        if optimization_level == 'aggressive':
            self.knowledge_store = OptimizedKnowledgeStore(
                cache_size=1000,
                cache_ttl_ms=5000,
                write_buffer_size=getattr(self.config.execution, 'knowledge_store_batch_size', 10)
            )
        else:
            self.knowledge_store = KnowledgeStore()
        
        self.state_manager = StateManager(self.task_graph)
        self.agent_registry = AgentRegistry()
        
        # Use batched trace manager for better performance
        execution_strategy = getattr(self.config.execution, 'execution_strategy', 'standard')
        self.trace_manager = BatchedTraceManager(
            project_id="sentient_v2",
            enable_batching=execution_strategy != 'realtime',
            trace_lightweight=execution_strategy == 'realtime'
        )
        
        # New orchestration components
        self.state_transition_manager = StateTransitionManager(
            self.task_graph,
            self.knowledge_store
        )
        self.task_scheduler = TaskScheduler(self.task_graph, self.state_manager)
        self.deadlock_detector = DeadlockDetector(self.task_graph, self.state_manager, config=self.config)
        self.recovery_manager = RecoveryManager(self.config)
        
        # New services
        hitl_config = HITLConfig.from_config(self.config)
        self.hitl_service = HITLService(hitl_config)
        self.agent_selector: Optional[AgentSelector] = None  # Set when profile loaded
        
        # Use cached context builder for better performance
        if optimization_level in ['balanced', 'aggressive']:
            self.context_builder = CachedContextBuilder(
                self.knowledge_store,
                cache_size=100,
                cache_ttl_ms=30000
            )
        else:
            self.context_builder = ContextBuilderService(ContextConfig())
        
        # Initialize node update manager
        self.node_update_manager = NodeUpdateManager.from_config(self.config.execution)
        
        # Node processor (still using old one for compatibility)
        self.node_processor: Optional["NodeProcessor"] = None
        
        # Execution orchestrator (replaces ExecutionEngine)
        self.execution_orchestrator: Optional[ExecutionOrchestrator] = None
        
        # Other components
        self.cache_manager = init_cache_manager(self.config.cache)
        self.error_handler = ErrorHandler(self.config)
        set_error_handler(self.error_handler)
        
        # Load YAML agents into the registry
        from ..hierarchical_agent_framework.agent_configs.registry_integration import integrate_yaml_agents
        try:
            integration_results = integrate_yaml_agents(self.agent_registry)
            logger.info(f"✅ YAML agents integrated: {integration_results['registered_action_keys']} action keys, {integration_results['registered_named_keys']} named agents")
        except Exception as e:
            logger.error(f"❌ Failed to integrate YAML agents: {e}")
            raise
        
        self._current_profile: Optional[str] = None
        self._current_blueprint = None
        
        # Mark initialization as complete
        self._initialized = True
        logger.success("✅ SystemManagerV2 initialized with refactored components")
    
    def initialize_with_profile(self, profile_name: str):
        """Initialize system with a specific agent profile."""
        logger.info(f"🎯 Initializing with profile: {profile_name}")
        
        # Load profile
        profile_loader = ProfileLoader()
        profile = profile_loader.load_profile(profile_name)
        
        if not profile:
            raise ValueError(f"Profile '{profile_name}' not found")
        
        # Get blueprint using the profile loaded
        blueprint = profile  # ProfileLoader.load_profile already returns the blueprint object
        
        if blueprint:
            self._current_blueprint = blueprint
            # Update agent selector with blueprint
            self.agent_selector = AgentSelector(blueprint)
            logger.info(f"✅ Loaded blueprint: {blueprint.name}")
        else:
            # Use default agent selector
            self.agent_selector = AgentSelector()
            logger.warning(f"Blueprint for profile '{profile_name}' not found, using defaults")
        
        # Create node processor with blueprint
        from ..hierarchical_agent_framework.node.node_processor import NodeProcessor
        node_processor_config = create_node_processor_config_from_main_config(self.config)
        
        self.node_processor = NodeProcessor(
            task_graph=self.task_graph,
            knowledge_store=self.knowledge_store,
            agent_registry=self.agent_registry,
            trace_manager=self.trace_manager,
            config=node_processor_config,
            node_processor_config=node_processor_config,
            agent_blueprint=self._current_blueprint,
            update_manager=self.node_update_manager,
            context_builder=self.context_builder
        )
        
        # Create execution orchestrator
        self.execution_orchestrator = ExecutionOrchestrator(
            task_graph=self.task_graph,
            state_manager=self.state_manager,
            knowledge_store=self.knowledge_store,
            node_processor=self.node_processor,
            config=self.config,
            task_scheduler=self.task_scheduler,
            deadlock_detector=self.deadlock_detector,
            recovery_manager=self.recovery_manager
        )
        
        self._current_profile = profile_name
        logger.success(f"✅ Profile '{profile_name}' loaded and system initialized")
    
    def get_simple_agent(self) -> "SimpleSentientAgent":
        """Get a simple agent instance using the new components."""
        from ..framework_entry import SimpleSentientAgent
        
        if not self._current_profile:
            self.initialize_with_profile("deep_research_agent")
        
        # Create wrapper that uses our orchestrator
        agent = SimpleSentientAgent(system_manager=self)
        
        # Override the execution engine with our orchestrator
        # This requires a small adapter
        agent.execution_engine = self._create_execution_engine_adapter()
        
        return agent
    
    def _create_execution_engine_adapter(self):
        """Create an adapter to make ExecutionOrchestrator compatible with old interface."""
        class ExecutionEngineAdapter:
            def __init__(self, orchestrator: ExecutionOrchestrator):
                self.orchestrator = orchestrator
            
            async def run_project_flow(self, root_goal: str, max_steps: int = 250):
                """Adapt to old interface."""
                return await self.orchestrator.execute(
                    root_goal=root_goal,
                    max_steps=max_steps
                )
        
        return ExecutionEngineAdapter(self.execution_orchestrator)
    
    def get_system_info(self) -> Dict[str, Any]:
        """Get comprehensive system information."""
        return {
            "config": {
                "hitl_enabled": self.config.execution.enable_hitl,
                "max_steps": self.config.execution.max_execution_steps,
                "profile": self._current_profile
            },
            "components": {
                "orchestrator": "ExecutionOrchestrator (refactored)",
                "scheduler": self.task_scheduler.get_execution_metrics(),
                "hitl": self.hitl_service.get_metrics(),
                "agent_selector": self.agent_selector.get_metrics() if self.agent_selector else {},
                "context_builder": self.context_builder.get_metrics()
            },
            "state": {
                "nodes": len(self.task_graph.get_all_nodes()),
                "graphs": len(self.task_graph.graphs),
                "state_stats": self.state_transition_manager.get_state_statistics()
            }
        }
    
    def get_current_profile(self) -> Optional[str]:
        """Get the currently active profile name."""
        return self._current_profile
    
    def close(self):
        """Clean shutdown of all components."""
        logger.info("🔄 Shutting down SystemManagerV2...")
        
        # Cleanup components
        if self.cache_manager:
            self.cache_manager.close()
        
        logger.info("✅ SystemManagerV2 shutdown complete")
    
    def setup_websocket_hitl(self, socketio):
        """
        Setup WebSocket HITL integration.
        
        Args:
            socketio: SocketIO instance to use for HITL
        """
        if not WEBSOCKET_HITL_AVAILABLE:
            logger.warning("⚠️ WebSocket HITL functions not available - skipping setup")
            return
            
        # Enable WebSocket HITL
        import os
        os.environ['SENTIENT_USE_WEBSOCKET_HITL'] = 'true'
        
        # Set server connection info for cross-process communication
        os.environ['SENTIENT_SERVER_HOST'] = 'localhost'
        os.environ['SENTIENT_SERVER_PORT'] = '5000'
        
        # Set up WebSocket HITL instance
        set_socketio_instance(socketio)
        set_hitl_timeout(self.config.execution.hitl_timeout_seconds)
        
        logger.info(f"✅ WebSocket HITL initialized with {self.config.execution.hitl_timeout_seconds}s timeout")
        logger.info(f"🔗 HTTP fallback configured for localhost:5000")
        
        # Also setup optimized broadcast service for the execution orchestrator
        if self.execution_orchestrator and hasattr(self.execution_orchestrator, 'update_manager'):
            from ..server.services.optimized_broadcast_service import OptimizedBroadcastService
            broadcast_service = OptimizedBroadcastService(
                socketio=socketio,
                batch_size=self.config.execution.ws_batch_size,
                batch_timeout_ms=self.config.execution.ws_batch_timeout_ms,
                enable_compression=self.config.execution.enable_ws_compression,
                enable_diff_updates=self.config.execution.enable_diff_updates
            )
            # Set the websocket handler on the update manager
            self.execution_orchestrator.update_manager.websocket_handler = broadcast_service
            logger.info("✅ Optimized broadcast service configured for NodeUpdateManager")
    
    def is_websocket_hitl_ready(self) -> bool:
        """Check if WebSocket HITL is ready for use"""
        if not WEBSOCKET_HITL_AVAILABLE:
            return False
        return is_websocket_hitl_ready()
    
    def get_websocket_hitl_status(self) -> Dict[str, Any]:
        """Get detailed WebSocket HITL status"""
        if not WEBSOCKET_HITL_AVAILABLE:
            return {
                "ready": False,
                "socketio_available": False,
                "connected_clients": 0,
                "pending_requests": 0,
                "timeout_seconds": 1800.0,
                "error": "WebSocket HITL functions not available"
            }
        return get_websocket_hitl_status()
    
    def get_available_profiles(self) -> List[str]:
        """Get list of available agent profiles."""
        try:
            loader = ProfileLoader()
            return loader.list_available_profiles()
        except Exception as e:
            logger.error(f"Failed to get available profiles: {e}")
            return []
    
    def get_profile_details(self, profile_name: str) -> Dict[str, Any]:
        """
        Get detailed information about a specific profile.
        
        Args:
            profile_name: Name of the profile to get details for
            
        Returns:
            Dictionary containing profile details
        """
        try:
            loader = ProfileLoader()
            blueprint = loader.load_profile(profile_name)
            
            if not blueprint:
                return {
                    "name": profile_name,
                    "error": "Profile not found",
                    "is_valid": False
                }
            
            return {
                "name": blueprint.name,
                "description": blueprint.description,
                "root_planner": blueprint.root_planner_adapter_name,
                "planner_mappings": {str(k): v for k, v in blueprint.planner_adapter_names.items()},
                "executor_mappings": {str(k): v for k, v in blueprint.executor_adapter_names.items()},
                "atomizer": blueprint.atomizer_adapter_name,
                "aggregator": blueprint.aggregator_adapter_name,
                "plan_modifier": blueprint.plan_modifier_adapter_name,
                "default_planner": blueprint.default_planner_adapter_name,
                "default_executor": blueprint.default_executor_adapter_name,
                "recommended_for": ["Research Projects", "Data Analysis", "Report Writing"],
                "is_valid": True
            }
        except Exception as e:
            logger.error(f"Failed to get profile details for {profile_name}: {e}")
            return {
                "name": profile_name,
                "error": str(e),
                "is_valid": False,
                "recommended_for": []
            }
    
    def get_profiles_with_current(self) -> Dict[str, Any]:
        """Get profiles list with current profile marked."""
        try:
            profiles = []
            available_profile_names = self.get_available_profiles()
            current_profile = self.get_current_profile()
            
            if not current_profile and available_profile_names:
                # Prioritize general_agent for data analysis tasks
                if "general_agent" in available_profile_names:
                    current_profile = "general_agent"
                elif "deep_research_agent" in available_profile_names:
                    current_profile = "deep_research_agent"
                else:
                    current_profile = available_profile_names[0]
                self._current_profile = current_profile
                logger.info(f"🎯 Auto-selected profile: {current_profile}")
            
            for profile_name in available_profile_names:
                profile_details = self.get_profile_details(profile_name)
                profile_details['is_current'] = (profile_name == current_profile)
                profiles.append(profile_details)
            
            return {
                "current_profile": current_profile,
                "profiles": profiles,
                "total_count": len(profiles)
            }
        except Exception as e:
            logger.error(f"Failed to get profiles with current: {e}")
            return {
                "current_profile": None,
                "profiles": [],
                "total_count": 0
            }
    
    def switch_profile(self, profile_name: str) -> Dict[str, Any]:
        """
        Switch to a different agent profile.
        
        Args:
            profile_name: Name of the profile to switch to
            
        Returns:
            Dictionary containing switch results and new system info
        """
        try:
            logger.info(f"🔄 Switching to profile: {profile_name}")
            
            # Clear current state
            if self.task_graph:
                self.task_graph.nodes.clear()
                self.task_graph.graphs.clear()
                self.task_graph.root_graph_id = None
                self.task_graph.overall_project_goal = None
            
            # Re-initialize with new profile
            self.initialize_with_profile(profile_name)
            
            logger.success(f"✅ Successfully switched to profile: {profile_name}")
            
            return {
                "success": True,
                "profile": profile_name,
                "message": f"Successfully switched to {profile_name}",
                "system_info": self.get_system_info(),
                "profile_details": self.get_profile_details(profile_name)
            }
            
        except Exception as e:
            logger.error(f"❌ Failed to switch profile to {profile_name}: {e}")
            return {
                "success": False,
                "error": str(e),
                "profile": profile_name
            }


