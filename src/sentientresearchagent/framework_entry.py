"""
Unified entry point for the Sentient Research Agent framework.
This provides a single, easy-to-use API that integrates all system components
with proper configuration management.
"""

from typing import Dict, Any, List, Optional, Union, Iterator, TYPE_CHECKING
from pathlib import Path
from datetime import datetime
import uuid
import asyncio
import nest_asyncio
from asyncio import Lock

from loguru import logger

from .exceptions import SentientError

# MODIFIED: SystemManager import is now ONLY under TYPE_CHECKING at the top level
# from .server.services.system_manager import SystemManager # MOVED

if TYPE_CHECKING:
    from .config import SentientConfig
    from .hierarchical_agent_framework.node.node_configs import NodeProcessorConfig
    from .core.system_manager import SystemManager # This is fine for type hints
    # ADD ExecutionEngine and other problematic imports here for type hinting
    from .hierarchical_agent_framework.graph.execution_engine import ExecutionEngine
    from .hierarchical_agent_framework.node.node_processor import NodeProcessor
    from .hierarchical_agent_framework.graph.task_graph import TaskGraph
    from .hierarchical_agent_framework.graph.state_manager import StateManager
    from .hierarchical_agent_framework.context.knowledge_store import KnowledgeStore
    from .hierarchical_agent_framework.node.hitl_coordinator import HITLCoordinator
    # ADD TaskNode here for type hinting
    from .hierarchical_agent_framework.node.task_node import TaskNode

try:
    # Reduce top-level imports that might cause cycles.
    # Only import things that are truly needed at module load time for definitions.
    # Components like ExecutionEngine, NodeProcessor will be imported locally in methods or type-hinted.
    
    # Configuration system is fine
    from .config import load_config, SentientConfig, find_config_file

    FRAMEWORK_AVAILABLE = True
    
except ImportError as e:
    logger.error(f"Framework components not available at module level: {e}") # Clarify error source
    FRAMEWORK_AVAILABLE = False
    
    class SentientConfig: # type: ignore
        pass
    class NodeProcessorConfig: # type: ignore
        pass
    # Add other dummy classes if their top-level import was removed and they are used in class signatures outside TYPE_CHECKING


def load_unified_config(config_path: Optional[Union[str, Path]] = None) -> "SentientConfig":
    """
    Load configuration with unified approach.
    
    Args:
        config_path: Optional explicit path to config file
        
    Returns:
        SentientConfig instance
    """
    if not FRAMEWORK_AVAILABLE:
        raise ImportError("Framework components not available. Please install missing dependencies.")
    
    if config_path:
        config_path = Path(config_path)
        if not config_path.exists():
            raise FileNotFoundError(f"Configuration file not found: {config_path}")
        logger.info(f"Loading configuration from: {config_path}")
        config = load_config(config_file=config_path, use_env=True)
    else:
        # Auto-discover configuration
        found_config = find_config_file()
        if found_config:
            config = load_config(config_file=found_config, use_env=True)
        else:
            logger.info("Loading configuration from environment variables and defaults")
            config = load_config(use_env=True)
    
    return config


def create_node_processor_config_from_main_config(main_config: "SentientConfig") -> "NodeProcessorConfig":
    """
    Create NodeProcessorConfig from the centralized main configuration.
    """
    if not FRAMEWORK_AVAILABLE:
        raise ImportError("Framework components not available. Please install missing dependencies.")
    
    from .hierarchical_agent_framework.node.node_configs import NodeProcessorConfig
    
    node_config = NodeProcessorConfig()
    
    # THE CORRECT FIX: Set the master HITL switch on the NodeProcessorConfig
    node_config.enable_hitl = main_config.execution.enable_hitl
    
    # Set max_planning_layer from max_recursion_depth
    node_config.max_planning_layer = getattr(main_config.execution, 'max_recursion_depth', 5)
    
    # Set skip_atomization from main config
    node_config.skip_atomization = getattr(main_config.execution, 'skip_atomization', False)
    logger.info(f"🐛 NodeProcessorConfig: skip_atomization = {node_config.skip_atomization}, max_planning_layer = {node_config.max_planning_layer}")
    
    # Map centralized config to NodeProcessorConfig
    if main_config.execution.enable_hitl:
        if main_config.execution.hitl_root_plan_only:
            # Root plan only mode - only enable plan generation for root nodes
            node_config.enable_hitl_after_plan_generation = True  # Will be filtered by layer in HITLCoordinator
            node_config.enable_hitl_after_modified_plan = True    # Keep enabled for modification loop
            node_config.enable_hitl_after_atomizer = False
            node_config.enable_hitl_before_execute = False
            logger.debug("HITL configured for root plan only (with modification reviews)")
        else:
            # All-nodes HITL mode - use all configured checkpoints
            node_config.enable_hitl_after_plan_generation = main_config.execution.hitl_after_plan_generation
            node_config.enable_hitl_after_modified_plan = main_config.execution.hitl_after_modified_plan
            node_config.enable_hitl_after_atomizer = main_config.execution.hitl_after_atomizer
            node_config.enable_hitl_before_execute = main_config.execution.hitl_before_execute
            logger.debug("HITL configured for all enabled checkpoints (all-nodes mode)")
    else:
        # If master HITL is disabled, disable all checkpoints
        node_config.enable_hitl_after_plan_generation = False
        node_config.enable_hitl_after_modified_plan = False
        node_config.enable_hitl_after_atomizer = False
        node_config.enable_hitl_before_execute = False
        logger.debug("HITL disabled - all checkpoints off")
    
    # Store the root_plan_only flag for HITLCoordinator to use
    node_config.hitl_root_plan_only = getattr(main_config.execution, 'hitl_root_plan_only', False)
    
    # NEW: Store the force_root_node_planning flag
    node_config.force_root_node_planning = getattr(main_config.execution, 'force_root_node_planning', True)
    
    # NEW: Store the skip_atomization flag
    node_config.skip_atomization = getattr(main_config.execution, 'skip_atomization', False)
    
    logger.debug(f"NodeProcessorConfig created: max_planning_layer={node_config.max_planning_layer}, "
                f"plan_gen={node_config.enable_hitl_after_plan_generation}, "
                f"modified_plan={node_config.enable_hitl_after_modified_plan}, "
                f"atomizer={node_config.enable_hitl_after_atomizer}, "
                f"before_exec={node_config.enable_hitl_before_execute}, "
                f"root_only={getattr(node_config, 'hitl_root_plan_only', False)}, "
                f"force_root_planning={getattr(node_config, 'force_root_node_planning', True)}, "
                f"skip_atomization={getattr(node_config, 'skip_atomization', False)}")
    
    return node_config


class SentientAgent:
    """
    Unified entry point for the Sentient Research Agent framework.
    This class consumes a pre-configured SystemManager instance.
    """
    
    def __init__(self, system_manager: "SystemManager"):
        if not FRAMEWORK_AVAILABLE: # This check might now be less reliable if imports are deferred
            # Consider re-checking FRAMEWORK_AVAILABLE after attempting local imports if critical
            raise ImportError("Framework components not available. Please check installation.")

        self.system_manager: "SystemManager" = system_manager
        self.config: "SentientConfig" = self.system_manager.config
        
        # Access components from system_manager. These should be concrete instances.
        # No need for local imports here if SystemManager guarantees they are initialized.
        self.task_graph = self.system_manager.task_graph
        self.knowledge_store = self.system_manager.knowledge_store
        self.state_manager = self.system_manager.state_manager
        self.hitl_coordinator = getattr(self.system_manager, 'hitl_coordinator', None) or getattr(self.system_manager, 'hitl_service', None)
        self.node_processor = self.system_manager.node_processor
        self.execution_engine = getattr(self.system_manager, 'execution_engine', None) or getattr(self.system_manager, 'execution_orchestrator', None)
        self.cache_manager = getattr(self.system_manager, 'cache_manager', None)
        self.error_handler = getattr(self.system_manager, 'error_handler', None)
        
        # THE FIX: Add a lock to the agent instance to serialize executions
        self._execution_lock = Lock()
        
        if not all([
            self.config, self.task_graph, self.knowledge_store, self.state_manager, 
            self.hitl_coordinator, self.node_processor, self.execution_engine, 
            self.cache_manager, self.error_handler
        ]):
            logger.error("SentientAgent initialized with an incomplete SystemManager. Some core components are missing.")
            # This indicates an issue with SystemManager's initialization.
            # SystemManager should guarantee these are set after its __init__ and initialize_with_profile.

        current_profile = self.system_manager.get_current_profile()
        # Ensure config is available for logging HITL status
        hitl_status_log = 'unknown (config not fully loaded)'
        if self.config and hasattr(self.config, 'execution'):
            hitl_status_log = 'enabled' if self.config.execution.enable_hitl else 'disabled'

        logger.info(f"SentientAgent initialized. SystemManager active profile: {current_profile}. HITL from config: {hitl_status_log}")
    
    @classmethod
    def create(
        cls, 
        config_path: Optional[Union[str, Path]] = None,
        enable_hitl_override: Optional[bool] = None,
        hitl_root_plan_only_override: Optional[bool] = None,
        default_profile_name: str = "deep_research_agent",
        **config_kwargs
    ) -> "SentientAgent":
        if not FRAMEWORK_AVAILABLE:
            raise ImportError("Framework components not available. Please check installation.")
        
        # MODIFIED: Import SystemManager locally within the factory method
        from .core.system_manager import SystemManagerV2 as ConcreteSystemManager

        config = load_unified_config(config_path)
        
        # Apply config_overrides if provided
        if 'config_overrides' in config_kwargs:
            overrides = config_kwargs.pop('config_overrides')
            if isinstance(overrides, dict):
                for section, values in overrides.items():
                    if hasattr(config, section) and isinstance(values, dict):
                        for key, value in values.items():
                            if hasattr(getattr(config, section), key):
                                setattr(getattr(config, section), key, value)
                                logger.debug(f"Applied config override: {section}.{key} = {value}")
        
        # Apply any remaining config_kwargs and HITL overrides
        if enable_hitl_override is not None:
            config.execution.enable_hitl = enable_hitl_override
        if hitl_root_plan_only_override is not None:
            config.execution.hitl_root_plan_only = hitl_root_plan_only_override
        
        system_manager = ConcreteSystemManager(config=config) # Use locally imported SystemManager
        
        if not system_manager.get_current_profile():
            system_manager.initialize_with_profile(default_profile_name)
            profile_name = default_profile_name
        else:
            active_profile = system_manager.get_current_profile()
            system_manager.initialize_with_profile(active_profile)
            profile_name = active_profile

        # Check if this is LightweightSentientAgent which requires profile_name
        if cls.__name__ == 'LightweightSentientAgent':
            return cls(profile_name=profile_name, system_manager=system_manager)
        else:
            return cls(system_manager=system_manager)
    
    def execute(self, goal: str, **options) -> Dict[str, Any]:
        """
        Execute a goal using the sophisticated agent system.
        
        Args:
            goal: The high-level goal to achieve
            **options: Additional options:
                - max_steps: Maximum execution steps (overrides config)
                - enable_hitl: Enable HITL for this execution only
                - hitl_root_plan_only: Only review root node's plan for this execution
                - save_state: Whether to save execution state (default: True)
        
        Returns:
            Dictionary with execution results including:
            - execution_id: Unique identifier for this execution
            - goal: The original goal
            - status: 'completed', 'failed', or 'partial'
            - final_output: The main result
            - execution_time: Time taken in seconds
            - node_count: Number of nodes created
            - hitl_enabled: Whether HITL was enabled
            - hitl_root_plan_only: Whether only root plan was reviewed
        """
        start_time = datetime.now()
        execution_id = f"exec_{uuid.uuid4().hex[:8]}"
        execution_result = None
        
        try:
            logger.info(f"[{execution_id}] Starting execution: {goal[:100]}...")
            
            # Get options
            max_steps = options.get('max_steps', self.config.execution.max_execution_steps)
            enable_hitl_override = options.get('enable_hitl')
            hitl_root_plan_only_override = options.get('hitl_root_plan_only')
            save_state = options.get('save_state', True)
            
            # Temporarily override HITL if specified
            original_hitl_setting = self.config.execution.enable_hitl
            original_root_plan_only_setting = getattr(self.config.execution, 'hitl_root_plan_only', False)
            original_node_config = None
            
            config_changed = False
            
            if enable_hitl_override is not None:
                self.config.execution.enable_hitl = enable_hitl_override
                config_changed = True
            
            # NEW: Handle root plan only override
            if hitl_root_plan_only_override is not None:
                self.config.execution.hitl_root_plan_only = hitl_root_plan_only_override
                # If enabling root plan only, ensure HITL is enabled
                if hitl_root_plan_only_override and not self.config.execution.enable_hitl:
                    self.config.execution.enable_hitl = True
                    logger.info(f"[{execution_id}] Automatically enabled HITL because hitl_root_plan_only=True")
                config_changed = True
            
            if config_changed:
                # Recreate NodeProcessorConfig with new HITL settings
                original_node_config = self.node_processor.node_processor_config
                new_node_config = create_node_processor_config_from_main_config(self.config)
                
                # THE FIX: Also update the SystemManager's internal config reference.
                self.system_manager.config = self.config

                # Update both the node processor AND the HITL coordinator
                self.node_processor.node_processor_config = new_node_config
                self.hitl_coordinator.config = new_node_config
                
                logger.info(f"[{execution_id}] HITL settings overridden - "
                           f"enabled: {self.config.execution.enable_hitl}, "
                           f"root_only: {getattr(self.config.execution, 'hitl_root_plan_only', False)}")
            
            try:
                # Run the async execution - JUPYTER SAFE
                execution_result = _run_async_safely(self._run_async_execution(goal, max_steps))
                
                # Extract results
                final_output = self._extract_final_result()
                execution_time = (datetime.now() - start_time).total_seconds()
                node_count = len(self.task_graph.nodes)
                
                result = {
                    'execution_id': execution_id,
                    'goal': goal,
                    'status': 'completed',
                    'final_output': final_output,
                    'execution_time': execution_time,
                    'node_count': node_count,
                    'hitl_enabled': self.config.execution.enable_hitl,
                    'hitl_root_plan_only': getattr(self.config.execution, 'hitl_root_plan_only', False),
                    'config_source': 'config_file' if find_config_file() else 'defaults',
                    'framework_result': execution_result,
                    'environment': 'jupyter' if _is_jupyter_environment() else 'python'
                }
                
                # Save state if requested
                if save_state:
                    self._save_execution_state(execution_id, result)
                
                logger.info(f"[{execution_id}] Execution completed: {node_count} nodes, {execution_time:.2f}s")
                return result
                
            finally:
                # Restore original HITL settings AND NodeProcessorConfig
                if config_changed:
                    self.config.execution.enable_hitl = original_hitl_setting
                    self.config.execution.hitl_root_plan_only = original_root_plan_only_setting
                    if original_node_config:
                        self.node_processor.node_processor_config = original_node_config
                        self.hitl_coordinator.config = original_node_config
                        logger.debug(f"[{execution_id}] Restored original HITL configuration")
        
        except Exception as e:
            execution_time = (datetime.now() - start_time).total_seconds()
            logger.error(f"[{execution_id}] Execution failed: {e}")
            
            return {
                'execution_id': execution_id,
                'goal': goal,
                'status': 'failed',
                'error': str(e),
                'execution_time': execution_time,
                'node_count': len(self.task_graph.nodes),
                'hitl_enabled': self.config.execution.enable_hitl,
                'hitl_root_plan_only': getattr(self.config.execution, 'hitl_root_plan_only', False),
                'framework_result': execution_result,
                'environment': 'jupyter' if _is_jupyter_environment() else 'python'
            }
    
    async def _run_async_execution(self, goal: str, max_steps: int):
        """Run the async execution flow"""
        # THE FIX: Use a lock to ensure only one execution runs at a time, preventing state corruption.
        async with self._execution_lock:
            # Clear previous state right before execution, inside the lock
            logger.debug("Execution lock acquired. Clearing previous task graph state.")
            self.task_graph.nodes.clear()
            self.task_graph.graphs.clear()
            self.task_graph.root_graph_id = None
            self.task_graph.overall_project_goal = None
            # Also clear the knowledge store to prevent context from leaking between runs
            if hasattr(self.knowledge_store, 'clear_all_records'):
                 self.knowledge_store.clear_all_records()
            
            # ExecutionEngine is obtained from self.system_manager.execution_engine
            if not self.execution_engine:
                logger.error("ExecutionEngine not available on SystemManager for _run_async_execution")
                # This would be a critical error in SystemManager's initialization
                raise SentientError("ExecutionEngine not initialized properly.")
                
            return await self._invoke_execution_engine(goal, max_steps)
    
    def stream_execution(self, goal: str, **options) -> Iterator[Dict[str, Any]]:
        """
        Stream execution progress in real-time.
        
        Args:
            goal: The high-level goal to achieve
            **options: Same as execute() method
            
        Yields:
            Progress updates with status, message, and current state
        """
        execution_id = f"stream_{uuid.uuid4().hex[:8]}"
        
        try:
            yield {
                'execution_id': execution_id,
                'status': 'initializing',
                'message': f'Starting: {goal[:50]}...',
                'progress': 0,
                'hitl_enabled': self.config.execution.enable_hitl,
                'environment': 'jupyter' if _is_jupyter_environment() else 'python'
            }
            
            # Get options
            max_steps = options.get('max_steps', self.config.execution.max_execution_steps)
            enable_hitl_override = options.get('enable_hitl')
            
            # Temporarily override HITL if specified
            original_hitl_setting = self.config.execution.enable_hitl
            original_node_config = None
            
            if enable_hitl_override is not None:
                self.config.execution.enable_hitl = enable_hitl_override
                original_node_config = self.node_processor.node_processor_config
                new_node_config = create_node_processor_config_from_main_config(self.config)
                self.node_processor.node_processor_config = new_node_config
                self.hitl_coordinator.config = new_node_config
            
            try:
                yield {
                    'execution_id': execution_id,
                    'status': 'planning', 
                    'message': 'Initializing sophisticated planning agents',
                    'progress': 10,
                    'hitl_enabled': self.config.execution.enable_hitl
                }
                
                # Run execution with periodic updates - JUPYTER SAFE
                result = _run_async_safely(self._run_async_execution(goal, max_steps))
                
                yield {
                    'execution_id': execution_id,
                    'status': 'completed',
                    'message': 'Execution completed successfully',
                    'progress': 100,
                    'final_output': self._extract_final_result(),
                    'node_count': len(self.task_graph.nodes),
                    'hitl_enabled': self.config.execution.enable_hitl
                }
                
            finally:
                # Restore original HITL setting
                if enable_hitl_override is not None:
                    self.config.execution.enable_hitl = original_hitl_setting
                    if original_node_config:
                        self.node_processor.node_processor_config = original_node_config
                        self.hitl_coordinator.config = original_node_config
            
        except Exception as e:
            yield {
                'execution_id': execution_id,
                'status': 'failed',
                'message': f'Execution failed: {str(e)}',
                'error': str(e),
                'hitl_enabled': self.config.execution.enable_hitl,
                'environment': 'jupyter' if _is_jupyter_environment() else 'python'
            }
    
    def _extract_final_result(self) -> str:
        """Extract final result from the task graph."""
        try:
            # Get the root node from the task graph
            if self.task_graph.root_graph_id:
                root_nodes = self.task_graph.get_nodes_in_graph(self.task_graph.root_graph_id)
                if root_nodes:
                    root_node = root_nodes[0]  # Get the first (root) node
                    if root_node and root_node.result:
                        return str(root_node.result)
                    elif root_node and root_node.output_summary:
                        return root_node.output_summary
            
            return "Task completed using sophisticated agent framework"
        except Exception as e:
            logger.warning(f"Could not extract final result: {e}")
            return "Execution completed (result extraction pending)"
    
    def _save_execution_state(self, execution_id: str, result: Dict[str, Any]):
        """Save execution state for later analysis."""
        try:
            state_dir = Path(".agent_executions")
            state_dir.mkdir(exist_ok=True)
            
            state_file = state_dir / f"{execution_id}.json"
            
            # Add task graph state to result
            if hasattr(self.task_graph, 'to_visualization_dict'):
                result['task_graph_state'] = self.task_graph.to_visualization_dict()
            
            import json
            with open(state_file, 'w') as f:
                json.dump(result, f, indent=2, default=str)
            
            logger.debug(f"Execution state saved to {state_file}")
        except Exception as e:
            logger.warning(f"Failed to save execution state: {e}")
    
    def get_system_info(self) -> Dict[str, Any]:
        """Get comprehensive system information from the SystemManager."""
        if not self.system_manager: # Should not happen with new __init__
            return {"error": "SystemManager not available"}
        return self.system_manager.get_system_info()

    def validate_configuration(self) -> Dict[str, Any]:
        """Validate current configuration (obtained from SystemManager) and return results."""
        if not self.config: # Should not happen
             return {"valid": False, "issues": ["Configuration not loaded"], "warnings": []}
        return validate_config(self.config) # validate_config is from config_utils

    def close(self):
        """
        Cleanly shuts down the agent and its underlying components, releasing resources.
        This should be called when the agent is no longer needed.
        """
        logger.info("Shutting down SentientAgent and its components...")
        if self.system_manager:
            self.system_manager.close()
        logger.info("SentientAgent shutdown complete.")

    async def __aenter__(self):
        """Asynchronous context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Asynchronous context manager exit."""
        self.close()


# SimpleSentientAgent alias is maintained for backward compatibility.
# SystemManager.get_simple_agent() uses this.
SimpleSentientAgent = SentientAgent


class ProfiledSentientAgent(SentientAgent): # MODIFIED: Inherits from refactored SentientAgent
    """
    Enhanced SentientAgent that ensures a specific agent profile is active.
    """
    
    def __init__(self, profile_name: str, system_manager: "SystemManager"): # MODIFIED: String literal for type hint
        """
        Initialize the ProfiledSentientAgent.
        Assumes system_manager has already been configured with the specified profile_name.
        
        Args:
            profile_name: The name of the profile this agent is configured for.
            system_manager: A SystemManager instance, expected to be configured with profile_name.
        """
        self.profile_name = profile_name 
        super().__init__(system_manager=system_manager) # Calls SentientAgent.__init__
        
        # Verification step
        if self.system_manager.get_current_profile() != self.profile_name:
            logger.warning(
                f"ProfiledSentientAgent for '{self.profile_name}' was initialized, "
                f"but its SystemManager has profile '{self.system_manager.get_current_profile()}' active. "
                f"This might indicate an issue in the instantiation flow. Re-applying profile."
            )
            # Attempt to re-apply to ensure consistency for this agent instance
            try:
                self.system_manager.initialize_with_profile(self.profile_name)
            except Exception as e:
                logger.error(f"Failed to re-apply profile '{self.profile_name}' during ProfiledSentientAgent init: {e}")
                # Agent might be in an inconsistent state.
    
    @classmethod
    def create_with_profile(
        cls, 
        profile_name: str = "deep_research_agent",
        enable_hitl_override: Optional[bool] = None,
        hitl_root_plan_only_override: Optional[bool] = None,
        config_path: Optional[Union[str, Path]] = None,
        system_manager: Optional["SystemManager"] = None,
        **config_kwargs
    ) -> "ProfiledSentientAgent":
        """
        Factory method to create a ProfiledSentientAgent with a specific profile.
        
        Args:
            profile_name: Name of the agent profile to use
            enable_hitl_override: Override HITL enable setting
            hitl_root_plan_only_override: Override HITL root plan only setting
            config_path: Path to configuration file
            system_manager: Optional existing SystemManager instance to use
            **config_kwargs: Additional configuration overrides
        """
        logger.info(f"🤖 Creating ProfiledSentientAgent with profile: {profile_name}")
        
        # If system_manager is provided, use it directly
        if system_manager is not None:
            logger.info(f"Using provided SystemManager instance")
            # Ensure the profile is initialized
            if system_manager.get_current_profile() != profile_name:
                system_manager.initialize_with_profile(profile_name)
            return cls(profile_name=profile_name, system_manager=system_manager)
        
        # Otherwise create a new one
        # MODIFIED: Import SystemManager locally
        from .core.system_manager import SystemManagerV2 as ConcreteSystemManager
        
        config = load_unified_config(config_path)
        
        # Set execution strategy for ProfiledSentientAgent
        config.execution.execution_strategy = "realtime"
        config.execution.broadcast_mode = "full"  # Real-time UI updates
        logger.info(f"ProfiledSentientAgent: Setting execution_strategy='realtime', broadcast_mode='full'")
        
        # THE FIX: Apply overrides directly to the config object *before* initializing the system manager.
        if enable_hitl_override is not None:
            config.execution.enable_hitl = enable_hitl_override
            logger.info(f"Config Override: 'enable_hitl' set to {enable_hitl_override}.")

        if hitl_root_plan_only_override is not None:
            config.execution.hitl_root_plan_only = hitl_root_plan_only_override
            logger.info(f"Config Override: 'hitl_root_plan_only' set to {hitl_root_plan_only_override}.")

        # Map max_planning_depth to the correct internal config attribute
        if 'max_planning_depth' in config_kwargs:
            depth = config_kwargs.pop('max_planning_depth')
            config.execution.max_recursion_depth = depth
            logger.info(f"Overriding execution.max_recursion_depth with value: {depth}")

        # Apply any other dynamic kwargs to the config
        # Example: max_planning_depth=2 would target config.execution.max_planning_depth
        for key, value in config_kwargs.items():
            if hasattr(config.execution, key):
                setattr(config.execution, key, value)
                logger.info(f"Config Override: 'execution.{key}' set to {value}.")
            elif hasattr(config, key):
                setattr(config, key, value)
                logger.info(f"Config Override: '{key}' set to {value}.")

        system_manager = ConcreteSystemManager(config=config)
        
        try:
            system_manager.initialize_with_profile(profile_name)
            logger.info(f"SystemManager initialized and configured with profile: {profile_name}")
        except Exception as e:
            logger.error(f"❌ Failed to initialize SystemManager with profile '{profile_name}': {e}")
            # Consider how SentientError is defined or if a more specific error is better.
            raise SentientError(f"Failed to create agent with profile {profile_name}: {e}") from e
            
        agent = cls(profile_name=profile_name, system_manager=system_manager)
        
        logger.info(f"✅ ProfiledSentientAgent created successfully with profile: {profile_name}")
        return agent

    def get_profile_info(self) -> Dict[str, Any]:
        """Get information about the agent's configured profile from SystemManager."""
        if not self.system_manager: # Should be guaranteed by __init__
            return {"error": "SystemManager not available", "profile_name": self.profile_name}
        try:
            # Ensure we request details for the profile this agent instance is meant for.
            return self.system_manager.get_profile_details(self.profile_name)
        except Exception as e:
            logger.error(f"Failed to get profile info for '{self.profile_name}' via SystemManager: {e}")
            return {"error": str(e), "profile_name": self.profile_name, "source": "ProfiledSentientAgent_fallback"}


class LightweightSentientAgent(SentientAgent):
    """
    Lightweight version of SentientAgent optimized for speed and server-to-server usage.
    
    This class provides the same interface as ProfiledSentientAgent but removes:
    - WebSocket broadcasting overhead
    - Real-time UI updates
    - Heavy serialization for visualization
    - Frequent state saves
    
    Ideal for FastAPI endpoints and programmatic usage where UI features aren't needed.
    """
    
    def __init__(self, profile_name: str, system_manager: "SystemManager"):
        """
        Initialize the LightweightSentientAgent.
        
        Args:
            profile_name: The name of the profile this agent is configured for.
            system_manager: A SystemManager instance, expected to be configured with profile_name.
        """
        self.profile_name = profile_name
        super().__init__(system_manager=system_manager)
        
        # Disable broadcasting and real-time updates for performance
        self._disable_broadcasting()
        
        # Verification step
        if self.system_manager.get_current_profile() != self.profile_name:
            logger.warning(
                f"LightweightSentientAgent for '{self.profile_name}' was initialized, "
                f"but its SystemManager has profile '{self.system_manager.get_current_profile()}' active. "
                f"Re-applying profile."
            )
            try:
                self.system_manager.initialize_with_profile(self.profile_name)
            except Exception as e:
                logger.error(f"Failed to re-apply profile '{self.profile_name}' during LightweightSentientAgent init: {e}")
    
    def _disable_broadcasting(self):
        """Disable broadcasting and real-time updates for performance."""
        # Override any broadcast callbacks to no-op functions
        if hasattr(self.system_manager, 'broadcast_manager'):
            self.system_manager.broadcast_manager = None
            logger.debug("Disabled broadcast manager for lightweight execution")
    
    async def execute(self, goal: str, max_steps: int = 50, save_state: bool = False, **options) -> Dict[str, Any]:
        """
        Execute a goal with lightweight processing (no UI overhead).
        
        Args:
            goal: The high-level goal to achieve
            max_steps: Maximum execution steps (reduced default for lightweight usage)
            save_state: Whether to save execution state (disabled by default for performance)
            **options: Additional execution options (enable_hitl, hitl_root_plan_only, etc.)
            
        Returns:
            Dictionary with execution results in minimal format
        """
        execution_id = str(uuid.uuid4())[:8]
        start_time = datetime.now()
        
        logger.info(f"[{execution_id}] 🚀 LightweightSentientAgent executing: '{goal[:50]}...'")
        
        try:
            # Apply configuration overrides if provided
            config_changed = False
            original_execution_config = None
            
            # List of execution config options that can be overridden
            execution_overrides = {}
            for key in ['max_concurrent_nodes', 'skip_atomization', 'max_recursion_depth', 
                       'enable_hitl', 'hitl_root_plan_only', 'force_root_node_planning']:
                if key in options:
                    execution_overrides[key] = options[key]
            
            if execution_overrides:
                config_changed = True
                # Store original config for restoration
                original_execution_config = self.config.execution.dict()
                
                # Apply execution overrides
                for key, value in execution_overrides.items():
                    if hasattr(self.config.execution, key):
                        setattr(self.config.execution, key, value)
                        logger.debug(f"[{execution_id}] Override applied: {key} = {value}")
                
                # Update system manager config
                self.system_manager.config = self.config
                
                # Update node processor config if HITL settings, max_recursion_depth, or skip_atomization changed
                if any(key.startswith('hitl') or key in ['enable_hitl', 'max_recursion_depth', 'skip_atomization'] for key in execution_overrides):
                    new_node_config = create_node_processor_config_from_main_config(self.config)
                    self.node_processor.node_processor_config = new_node_config
                    if self.hitl_coordinator:
                        self.hitl_coordinator.config = new_node_config
                    # Also update ExecutionEngine's handler context if available
                    if hasattr(self.execution_engine, 'handler_context'):
                        self.execution_engine.handler_context.config = new_node_config.dict()
                        logger.info(f"[{execution_id}] 🐛 Updated ExecutionEngine handler context config")
                    
                    # Update the orchestrator's node processor if it's different
                    if hasattr(self.execution_engine, 'node_processor') and self.execution_engine.node_processor != self.node_processor:
                        logger.warning(f"[{execution_id}] 🐛 ExecutionEngine has different NodeProcessor instance!")
                        # Update the orchestrator's node processor config
                        self.execution_engine.node_processor.node_processor_config = new_node_config
                        # Also update its handler context if it exists
                        if hasattr(self.execution_engine.node_processor, 'handler_context'):
                            self.execution_engine.node_processor.handler_context.config = new_node_config.dict()
                            logger.info(f"[{execution_id}] 🐛 Updated ExecutionEngine's NodeProcessor handler context")
                    
                    logger.info(f"[{execution_id}] 🐛 Updated NodeProcessorConfig: max_planning_layer = {new_node_config.max_planning_layer}, skip_atomization = {new_node_config.skip_atomization}")
                
                logger.info(f"[{execution_id}] Config overrides applied: {list(execution_overrides.keys())}")
            
            try:
                # Run the lightweight execution
                execution_result = await self._run_lightweight_execution(goal, max_steps)
                
                # Extract minimal results (no heavy serialization)
                final_output = self._extract_lightweight_result()
                execution_time = (datetime.now() - start_time).total_seconds()
                node_count = len(self.task_graph.nodes)
                
                result = {
                    'execution_id': execution_id,
                    'goal': goal,
                    'status': 'completed',
                    'final_result': final_output,  # Match expected key name
                    'execution_time': execution_time,
                    'execution_stats': {
                        'steps_completed': max_steps,  # Will be updated if we track actual steps
                        'total_execution_time': execution_time
                    },
                    'node_count': node_count,
                    'lightweight': True,  # Marker for lightweight execution
                    'framework_result': execution_result
                }
                
                # Only save state if explicitly requested (performance optimization)
                if save_state:
                    self._save_execution_state(execution_id, result)
                
                logger.info(f"[{execution_id}] ✅ Lightweight execution completed: {node_count} nodes, {execution_time:.2f}s")
                return result
                
            finally:
                # Restore original configuration if it was changed
                if config_changed and original_execution_config:
                    # Restore execution config from stored dict
                    for key, value in original_execution_config.items():
                        if hasattr(self.config.execution, key):
                            setattr(self.config.execution, key, value)
                    
                    # Update system manager config
                    self.system_manager.config = self.config
                    
                    # Recreate node processor config with restored settings
                    restored_node_config = create_node_processor_config_from_main_config(self.config)
                    self.node_processor.node_processor_config = restored_node_config
                    if self.hitl_coordinator:
                        self.hitl_coordinator.config = restored_node_config
                    
                    logger.debug(f"[{execution_id}] Configuration restored: max_planning_layer = {restored_node_config.max_planning_layer}")
        
        except Exception as e:
            execution_time = (datetime.now() - start_time).total_seconds()
            logger.error(f"[{execution_id}] ❌ Lightweight execution failed: {e}")
            
            return {
                'execution_id': execution_id,
                'goal': goal,
                'status': 'failed',
                'error': str(e),
                'execution_time': execution_time,
                'node_count': len(self.task_graph.nodes) if self.task_graph else 0,
                'lightweight': True,
                'framework_result': None
            }
    
    async def _run_lightweight_execution(self, goal: str, max_steps: int):
        """Run lightweight execution without UI overhead."""
        async with self._execution_lock:
            # Clear previous state
            logger.debug("Lightweight execution: Clearing previous state")
            self.task_graph.nodes.clear()
            self.task_graph.graphs.clear()
            self.task_graph.root_graph_id = None
            self.task_graph.overall_project_goal = None
            
            if hasattr(self.knowledge_store, 'clear_all_records'):
                self.knowledge_store.clear_all_records()
            
            if not self.execution_engine:
                raise SentientError("ExecutionEngine not initialized properly.")
            
            return await self._invoke_execution_engine(goal, max_steps, prefer_execute=True)
    
    async def _invoke_execution_engine(
        self,
        goal: str,
        max_steps: int,
        prefer_execute: bool = True
    ):
        """
        Invoke the underlying execution engine, supporting both legacy ExecutionEngine
        (run_project_flow) and the refactored ExecutionOrchestrator (execute).
        """
        engine = self.execution_engine
        if not engine:
            raise SentientError("Execution engine is not available.")
        
        method_order = ["execute", "run_project_flow"] if prefer_execute else ["run_project_flow", "execute"]
        attempted_methods: List[str] = []
        last_type_error: Optional[Exception] = None
        
        for method_name in method_order:
            method = getattr(engine, method_name, None)
            if not method:
                continue
            
            attempted_methods.append(method_name)
            try:
                result = method(root_goal=goal, max_steps=max_steps)
            except TypeError as exc:
                # Signature mismatch - remember and try the next option.
                last_type_error = exc
                logger.debug(f"Execution engine method '{method_name}' signature mismatch: {exc}")
                continue
            
            if asyncio.iscoroutine(result) or hasattr(result, "__await__"):
                logger.debug(f"Using execution engine method '{method_name}' for goal '{goal[:60]}...'")
                return await result
            
            # Fallback for any synchronous implementation (unexpected but guarded)
            logger.debug(f"Execution engine method '{method_name}' returned a non-awaitable result.")
            return result
        
        available = [name for name in ("execute", "run_project_flow") if hasattr(engine, name)]
        raise SentientError(
            "Execution engine does not expose a compatible async interface.",
            context={
                "engine_type": engine.__class__.__name__,
                "available_methods": available,
                "attempted_methods": attempted_methods,
                "last_type_error": str(last_type_error) if last_type_error else None
            }
        )
    
    def _extract_lightweight_result(self) -> Optional[str]:
        """Extract final result without heavy serialization."""
        try:
            # Get root node result efficiently
            if hasattr(self.task_graph, 'nodes') and self.task_graph.nodes:
                for node in self.task_graph.nodes.values():
                    if hasattr(node, 'layer') and node.layer == 0 and node.result:
                        if hasattr(node.result, 'output_text'):
                            return node.result.output_text
                        elif hasattr(node.result, 'full_result'):
                            return str(node.result.full_result)
                        else:
                            return str(node.result)
            return None
        except Exception as e:
            logger.warning(f"Failed to extract lightweight result: {e}")
            return None
    
    @classmethod
    def create_with_profile(
        cls, 
        profile_name: str = "general_agent",
        enable_hitl_override: Optional[bool] = None,
        hitl_root_plan_only_override: Optional[bool] = None, 
        config_path: Optional[Union[str, Path]] = None,
        **config_kwargs
    ) -> "LightweightSentientAgent":
        """
        Create a LightweightSentientAgent with a specific profile.
        
        Args:
            profile_name: Agent profile to use
            enable_hitl_override: Override HITL setting (typically False for lightweight usage)
            hitl_root_plan_only_override: Override root-only HITL setting
            config_path: Optional config file path
            **config_kwargs: Additional config overrides
            
        Returns:
            LightweightSentientAgent instance
        """
        logger.info(f"🏃‍♂️ Creating LightweightSentientAgent with profile: {profile_name}")
        
        # Import SystemManager locally
        from .core.system_manager import SystemManagerV2 as ConcreteSystemManager
        
        config = load_unified_config(config_path)
        
        # Set execution strategy for LightweightSentientAgent
        config.execution.execution_strategy = "deferred"
        config.execution.broadcast_mode = "none"  # No broadcasts for lightweight
        config.execution.optimization_level = "aggressive"  # Maximum optimization
        logger.info(f"LightweightSentientAgent: Setting execution_strategy='deferred', broadcast_mode='none', optimization_level='aggressive'")
        
        # Apply overrides with defaults optimized for lightweight usage
        if enable_hitl_override is not None:
            config.execution.enable_hitl = enable_hitl_override
        else:
            # Default to False for lightweight usage unless explicitly enabled
            config.execution.enable_hitl = False
            
        if hitl_root_plan_only_override is not None:
            config.execution.hitl_root_plan_only = hitl_root_plan_only_override
        
        # Apply other config overrides
        for key, value in config_kwargs.items():
            if hasattr(config.execution, key):
                setattr(config.execution, key, value)
                logger.info(f"Config Override: 'execution.{key}' set to {value}")
            elif hasattr(config, key):
                setattr(config, key, value)
                logger.info(f"Config Override: '{key}' set to {value}")
        
        # Create system manager with lightweight optimizations
        system_manager = ConcreteSystemManager(config=config)
        
        try:
            system_manager.initialize_with_profile(profile_name)
            logger.info(f"SystemManager initialized with profile: {profile_name}")
        except Exception as e:
            logger.error(f"❌ Failed to initialize SystemManager with profile '{profile_name}': {e}")
            raise SentientError(f"Failed to create lightweight agent with profile {profile_name}: {e}") from e
        
        agent = cls(profile_name=profile_name, system_manager=system_manager)
        
        logger.info(f"✅ LightweightSentientAgent created successfully with profile: {profile_name}")
        return agent


# Convenience functions - ensure they align with new create methods
def quick_research(topic: str, enable_hitl: Optional[bool] = None, profile_name: str = "deep_research_agent", **kwargs) -> str:
    """Quick research using the SentientAgent framework."""
    if not FRAMEWORK_AVAILABLE:
        raise ImportError("Framework components not available. Please check installation.")
    
    agent = SentientAgent.create(
        enable_hitl_override=enable_hitl, 
        default_profile_name=profile_name, # SentientAgent.create uses this if no profile on SM
        **kwargs
    )
    result = agent.execute(f"Research {topic} and provide a comprehensive summary")
    return result.get('final_output', 'No output generated')


def quick_analysis(data_description: str, enable_hitl: Optional[bool] = None, profile_name: str = "deep_research_agent", **kwargs) -> str:
    """Quick analysis using the SentientAgent framework."""
    if not FRAMEWORK_AVAILABLE:
        raise ImportError("Framework components not available. Please check installation.")
    
    agent = SentientAgent.create(
        enable_hitl_override=enable_hitl, 
        default_profile_name=profile_name,
        **kwargs
    )
    result = agent.execute(f"Analyze {data_description} and provide insights")
    return result.get('final_output', 'No output generated')


def quick_execute(goal: str, enable_hitl: Optional[bool] = None, profile_name: str = "deep_research_agent", **kwargs) -> str:
    """Quick execution of any goal using the SentientAgent framework."""
    if not FRAMEWORK_AVAILABLE:
        raise ImportError("Framework components not available. Please check installation.")
    
    agent = SentientAgent.create(
        enable_hitl_override=enable_hitl, 
        default_profile_name=profile_name,
        **kwargs
    )
    result = agent.execute(goal)
    return result.get('final_output', 'No output generated')


def create_research_agent(enable_hitl: bool = True, **kwargs) -> ProfiledSentientAgent:
    """
    Create a research-focused agent using a specific profile (default: deep_research_agent).
    """
    # This correctly uses ProfiledSentientAgent.create_with_profile
    return ProfiledSentientAgent.create_with_profile(
        profile_name=kwargs.pop("profile_name", "deep_research_agent"), # Allow profile override
        enable_hitl_override=enable_hitl,
        **kwargs
    )


def list_available_profiles() -> List[str]:
    """
    List all available agent profiles.
    
    Returns:
        List of profile names
    """
    try:
        from .hierarchical_agent_framework.agent_configs.profile_loader import ProfileLoader
        loader = ProfileLoader()
        return loader.list_available_profiles()
    except Exception as e:
        logger.error(f"Failed to list profiles: {e}")
        return [] 

def _is_jupyter_environment() -> bool:
    """Check if we're running in a Jupyter notebook environment."""
    try:
        # Check for IPython/Jupyter
        from IPython import get_ipython
        return get_ipython() is not None
    except ImportError:
        return False

def _run_async_safely(coro):
    """Run async code safely in both Jupyter and regular Python environments."""
    if _is_jupyter_environment():
        # In Jupyter, use nest_asyncio to allow nested event loops
        try:
            import nest_asyncio
            nest_asyncio.apply()
        except ImportError:
            logger.warning("nest_asyncio not available. Install with: pip install nest_asyncio")
        
        # Try to get the current event loop
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # If loop is running, we need to use a different approach
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(asyncio.run, coro)
                    return future.result()
            else:
                return asyncio.run(coro)
        except RuntimeError:
            # No event loop, safe to use asyncio.run
            return asyncio.run(coro)
    else:
        # Regular Python environment
        return asyncio.run(coro) 
