import uuid
import json
import os
from datetime import datetime
from typing import Dict, List, Optional, Any, Callable, TYPE_CHECKING
from dataclasses import dataclass, asdict
from pathlib import Path
import threading
from loguru import logger

from .project_context import set_project_context

if TYPE_CHECKING:
    from sentientresearchagent.config import SentientConfig
    from sentientresearchagent.hierarchical_agent_framework.agents.registry import AgentRegistry
    from sentientresearchagent.hierarchical_agent_framework.agent_blueprints import AgentBlueprint

@dataclass
class ProjectMetadata:
    """Metadata for a project/chat session"""
    id: str
    title: str
    description: str
    created_at: datetime
    updated_at: datetime
    status: str  # 'active', 'completed', 'failed', 'paused', 'running'
    goal: str
    max_steps: int
    node_count: int = 0
    completion_percentage: float = 0.0
    error: Optional[str] = None  # Store error message if execution fails
    
    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        # Convert datetime objects to ISO strings
        data['created_at'] = self.created_at.isoformat()
        data['updated_at'] = self.updated_at.isoformat()
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ProjectMetadata':
        # Convert ISO strings back to datetime objects
        data['created_at'] = datetime.fromisoformat(data['created_at'])
        data['updated_at'] = datetime.fromisoformat(data['updated_at'])
        return cls(**data)

class ProjectManager:
    """Manages multiple projects/chat sessions"""
    
    def __init__(self, projects_dir: Optional[str] = None):
        if projects_dir:
            self.projects_dir = Path(projects_dir)
        else:
            # Use centralized runtime paths
            from ..config.paths import RuntimePaths
            paths = RuntimePaths.get_default()
            self.projects_dir = paths.projects_dir
        self.projects_dir.mkdir(exist_ok=True, parents=True)
        self.projects: Dict[str, ProjectMetadata] = {}
        self.current_project_id: Optional[str] = None
        self._lock = threading.Lock()
        self._load_projects()
    
    def _load_projects(self):
        """Load existing projects from disk"""
        try:
            projects_file = self.projects_dir / "projects.json"
            if projects_file.exists():
                with open(projects_file, 'r') as f:
                    data = json.load(f)
                    for project_data in data.get('projects', []):
                        project = ProjectMetadata.from_dict(project_data)
                        self.projects[project.id] = project
                    self.current_project_id = data.get('current_project_id')
                logger.info(f"Loaded {len(self.projects)} existing projects")
        except Exception as e:
            logger.error(f"Failed to load projects: {e}")
    
    def _save_projects(self):
        """Save projects metadata to disk"""
        try:
            projects_file = self.projects_dir / "projects.json"
            data = {
                'projects': [project.to_dict() for project in self.projects.values()],
                'current_project_id': self.current_project_id
            }
            with open(projects_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save projects: {e}")
    
    def create_project(self, goal: str, max_steps: int = 250) -> ProjectMetadata:
        """Create a new project with universal folder structure"""
        with self._lock:
            project_id = str(uuid.uuid4())
            
            # Create project structure using centralized manager
            from .project_structure import ProjectStructure
            project_dirs = ProjectStructure.create_project_structure(project_id)
            
            toolkits_dir = project_dirs['toolkits_dir']
            results_dir = project_dirs['results_dir']
            
            # Set thread-local project context
            set_project_context(project_id)
            
            # Generate a smart title from the goal
            title = self._generate_title(goal)
            
            project = ProjectMetadata(
                id=project_id,
                title=title,
                description=goal[:200] + "..." if len(goal) > 200 else goal,
                created_at=datetime.now(),
                updated_at=datetime.now(),
                status='active',
                goal=goal,
                max_steps=max_steps
            )
            
            self.projects[project_id] = project
            self.current_project_id = project_id
            self._save_projects()
            
            logger.info(f"Created new project: {project_id} - {title}")
            logger.info(f"Project structure: {project_dirs['project_root']}")
            return project
    
    def _generate_title(self, goal: str) -> str:
        """Generate a smart title from the project goal"""
        # Simple title generation - could be enhanced with AI
        words = goal.split()[:8]  # Take first 8 words
        title = " ".join(words)
        if len(goal.split()) > 8:
            title += "..."
        return title.title()
    
    def get_project(self, project_id: str) -> Optional[ProjectMetadata]:
        """Get a specific project"""
        return self.projects.get(project_id)
    
    def get_all_projects(self) -> List[ProjectMetadata]:
        """Get all projects sorted by updated_at desc"""
        return sorted(
            self.projects.values(),
            key=lambda p: p.updated_at,
            reverse=True
        )
    
    def update_project(self, project_id: str, **updates) -> Optional[ProjectMetadata]:
        """Update project metadata"""
        with self._lock:
            if project_id not in self.projects:
                return None
            
            project = self.projects[project_id]
            for key, value in updates.items():
                if hasattr(project, key):
                    setattr(project, key, value)
            
            project.updated_at = datetime.now()
            self._save_projects()
            return project
    
    def delete_project(self, project_id: str) -> bool:
        """Delete a project"""
        with self._lock:
            if project_id not in self.projects:
                return False
            
            # Remove project directory
            project_dir = self.projects_dir / project_id
            if project_dir.exists():
                import shutil
                shutil.rmtree(project_dir)
            
            # Remove from memory and update current if needed
            del self.projects[project_id]
            if self.current_project_id == project_id:
                self.current_project_id = None
            
            self._save_projects()
            logger.info(f"Deleted project: {project_id}")
            return True
    
    def set_current_project(self, project_id: str) -> bool:
        """Set the current active project"""
        if project_id not in self.projects:
            return False
        
        self.current_project_id = project_id
        self._save_projects()
        return True
    
    def get_current_project(self) -> Optional[ProjectMetadata]:
        """Get the current active project"""
        if self.current_project_id:
            return self.projects.get(self.current_project_id)
        return None
    
    def get_current_project_id(self) -> Optional[str]:
        """Get the current active project ID"""
        return self.current_project_id
    
    def switch_project(self, project_id: str) -> bool:
        """Switch to a different project (alias for set_current_project)"""
        return self.set_current_project(project_id)
    
    def save_project_state(self, project_id: str, task_graph_data: Dict[str, Any]):
        """Save the current task graph state for a project"""
        try:
            project_dir = self.projects_dir / project_id
            project_dir.mkdir(exist_ok=True)
            
            state_file = project_dir / "graph_state.json"
            with open(state_file, 'w') as f:
                json.dump(task_graph_data, f, indent=2, default=str)  # default=str to handle datetime objects
                
            # Update project stats
            node_count = len(task_graph_data.get('all_nodes', {}))
            self.update_project(project_id, node_count=node_count)
            
        except Exception as e:
            logger.error(f"Failed to save project state for {project_id}: {e}")
    
    def load_project_state(self, project_id: str) -> Optional[Dict[str, Any]]:
        """Load the task graph state for a project"""
        try:
            project_dir = self.projects_dir / project_id
            state_file = project_dir / "graph_state.json"
            
            if state_file.exists():
                with open(state_file, 'r') as f:
                    return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load project state for {project_id}: {e}")
        
        return None

class ProjectExecutionContext:
    """
    Encapsulates all execution components for a specific project.
    
    This class solves the project isolation issue by ensuring each project
    has its own independent execution environment including:
    - TaskGraph
    - KnowledgeStore  
    - StateManager
    - ExecutionEngine
    - NodeProcessor
    - HITLCoordinator
    
    This prevents cross-project contamination and allows seamless switching.
    """
    
    def __init__(
        self,
        project_id: str,
        config: "SentientConfig",
        agent_registry: "AgentRegistry",
        agent_blueprint: Optional["AgentBlueprint"] = None,
        update_callback: Optional[Callable] = None
    ):
        """
        Initialize project execution context.
        
        Args:
            project_id: Unique project identifier
            config: Configuration for this project
            agent_registry: Agent registry instance
            agent_blueprint: Agent blueprint for this project
            update_callback: Optional callback for updates
        """
        self.project_id = project_id
        self.config = config
        self.agent_registry = agent_registry
        self.agent_blueprint = agent_blueprint
        self.update_callback = update_callback
        
        # Initialize project-specific components
        self._initialize_components()
        
        logger.info(f"✅ ProjectExecutionContext initialized for project {project_id}")
    
    def _initialize_components(self):
        """Initialize all project-specific execution components."""
        from sentientresearchagent.hierarchical_agent_framework.graph.task_graph import TaskGraph
        from sentientresearchagent.hierarchical_agent_framework.graph.state_manager import StateManager
        from sentientresearchagent.hierarchical_agent_framework.graph.execution_engine import ExecutionEngine
        from sentientresearchagent.hierarchical_agent_framework.node.node_processor import NodeProcessor
        from sentientresearchagent.hierarchical_agent_framework.node.hitl_coordinator import HITLCoordinator
        from sentientresearchagent.hierarchical_agent_framework.context.knowledge_store import KnowledgeStore
        from sentientresearchagent.hierarchical_agent_framework.tracing.manager import TraceManager
        from sentientresearchagent.framework_entry import create_node_processor_config_from_main_config
        
        # Create project-specific components
        self.task_graph = TaskGraph()
        self.knowledge_store = KnowledgeStore()
        self.state_manager = StateManager(self.task_graph)
        
        # Create project-specific trace manager
        self.trace_manager = TraceManager(project_id=self.project_id)
        
        # Create node processor config
        self.node_processor_config = create_node_processor_config_from_main_config(self.config)
        
        # Create HITL coordinator
        self.hitl_coordinator = HITLCoordinator(config=self.node_processor_config)
        
        # Create node processor
        self.node_processor = NodeProcessor(
            task_graph=self.task_graph,
            knowledge_store=self.knowledge_store,
            agent_registry=self.agent_registry,
            trace_manager=self.trace_manager,
            config=self.config,
            node_processor_config=self.node_processor_config,
            agent_blueprint=self.agent_blueprint,
            update_callback=self.update_callback
        )
        
        # Create execution engine (v2 signature)
        self.execution_engine = ExecutionEngine(
            task_graph=self.task_graph,
            state_manager=self.state_manager,
            knowledge_store=self.knowledge_store,
            node_processor=self.node_processor,
            agent_registry=self.node_processor.agent_registry,  # Get from node_processor
            config=self.config,
            checkpoint_manager=None,  # Optional
            websocket_handler=None   # Will be set later if needed
        )
        
        # Ensure project-scoped broadcasting where supported
        if hasattr(self.execution_engine, "update_manager"):
            try:
                self.execution_engine.update_manager.set_project_scope(project_id=self.project_id)
            except Exception as scope_error:
                logger.warning(f"Failed to configure update manager scope for project {self.project_id}: {scope_error}")
    
    def get_components(self) -> Dict[str, Any]:
        """
        Get all components as a dictionary.
        
        Returns:
            Dictionary containing all execution components
        """
        return {
            'task_graph': self.task_graph,
            'knowledge_store': self.knowledge_store,
            'state_manager': self.state_manager,
            'execution_engine': self.execution_engine,
            'node_processor': self.node_processor,
            'hitl_coordinator': self.hitl_coordinator,
            'trace_manager': self.trace_manager,
            'update_callback': self.update_callback,
            'config': self.config,
            'node_processor_config': self.node_processor_config
        }
    
    def load_state(self, project_state: Dict[str, Any]) -> bool:
        """
        Load project state into this execution context.
        
        Args:
            project_state: Serialized project state
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Clear existing state
            self.task_graph.nodes.clear()
            self.task_graph.graphs.clear()
            self.task_graph.root_graph_id = None
            self.task_graph.overall_project_goal = None
            self.knowledge_store.clear()
            
            if 'all_nodes' in project_state:
                # Load nodes by deserializing dictionaries back to TaskNode objects
                from sentientresearchagent.hierarchical_agent_framework.node.task_node import TaskNode
                
                for node_id, node_data in project_state['all_nodes'].items():
                    try:
                        # Convert datetime strings back to datetime objects if needed
                        self._deserialize_node_timestamps(node_data)
                        self._deserialize_node_enums(node_data)
                        
                        # Create TaskNode object from dictionary
                        task_node = TaskNode(**node_data)
                        self.task_graph.nodes[node_id] = task_node
                        
                        # Also add to knowledge store
                        self.knowledge_store.add_or_update_record_from_node(task_node)
                    except Exception as e:
                        logger.warning(f"Failed to deserialize node {node_id}: {e}")
                        continue
            
            # Properly reconstruct graphs
            if 'graphs' in project_state:
                self._reconstruct_graphs(project_state['graphs'])
            
            if 'overall_project_goal' in project_state:
                self.task_graph.overall_project_goal = project_state['overall_project_goal']
                
            if 'root_graph_id' in project_state:
                self.task_graph.root_graph_id = project_state['root_graph_id']
            
            logger.info(f"✅ Loaded state for project {self.project_id}: {len(self.task_graph.nodes)} nodes")
            return True
            
        except Exception as e:
            logger.error(f"Failed to load state for project {self.project_id}: {e}")
            return False
    
    def save_state(self) -> Dict[str, Any]:
        """
        Save current state to a serializable dictionary.
        
        Returns:
            Serialized project state
        """
        try:
            if hasattr(self.task_graph, 'to_visualization_dict'):
                return self.task_graph.to_visualization_dict()
            else:
                # Fallback serialization
                from sentientresearchagent.hierarchical_agent_framework.graph.graph_serializer import GraphSerializer
                serializer = GraphSerializer(self.task_graph)
                return serializer.to_visualization_dict()
        except Exception as e:
            logger.error(f"Failed to save state for project {self.project_id}: {e}")
            return {}
    
    def _deserialize_node_timestamps(self, node_data: Dict[str, Any]):
        """Convert timestamp strings back to datetime objects."""
        timestamp_fields = ['timestamp_created', 'timestamp_updated', 'timestamp_completed']
        for field in timestamp_fields:
            if field in node_data and isinstance(node_data[field], str):
                try:
                    node_data[field] = datetime.fromisoformat(node_data[field])
                except ValueError:
                    # If parsing fails, set to None
                    node_data[field] = None
    
    def _deserialize_node_enums(self, node_data: Dict[str, Any]):
        """Convert enum strings back to enum objects."""
        from sentientresearchagent.hierarchical_agent_framework.types import TaskStatus, TaskType, NodeType
        
        # Convert status string to enum
        if 'status' in node_data and isinstance(node_data['status'], str):
            try:
                node_data['status'] = TaskStatus[node_data['status'].upper()]
            except KeyError:
                node_data['status'] = TaskStatus.PENDING
        
        # Convert task_type string to enum
        if 'task_type' in node_data and isinstance(node_data['task_type'], str):
            try:
                node_data['task_type'] = TaskType[node_data['task_type'].upper()]
            except KeyError:
                node_data['task_type'] = TaskType.THINK
        
        # Convert node_type string to enum
        if 'node_type' in node_data and isinstance(node_data['node_type'], str):
            try:
                node_data['node_type'] = NodeType[node_data['node_type'].upper()]
            except KeyError:
                node_data['node_type'] = None
    
    def _reconstruct_graphs(self, graphs_data: Dict[str, Any]):
        """Reconstruct graph structure from serialized data."""
        try:
            for graph_id, graph_data in graphs_data.items():
                if isinstance(graph_data, dict) and 'node_ids' in graph_data:
                    # Reconstruct the graph with proper node references
                    node_ids = graph_data['node_ids']
                    valid_node_ids = [nid for nid in node_ids if nid in self.task_graph.nodes]
                    
                    if valid_node_ids:
                        self.task_graph.graphs[graph_id] = {
                            'node_ids': valid_node_ids,
                            'metadata': graph_data.get('metadata', {})
                        }
        except Exception as e:
            logger.warning(f"Failed to reconstruct graphs for project {self.project_id}: {e}")
    
    def cleanup(self):
        """Clean up resources when context is no longer needed."""
        try:
            # Clear all data structures
            if hasattr(self, 'task_graph'):
                self.task_graph.nodes.clear()
                self.task_graph.graphs.clear()
            
            if hasattr(self, 'knowledge_store'):
                self.knowledge_store.clear()
            
            logger.debug(f"🧹 Cleaned up ProjectExecutionContext for project {self.project_id}")
        except Exception as e:
            logger.warning(f"Error during cleanup for project {self.project_id}: {e}") 
