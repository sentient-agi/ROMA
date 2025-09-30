import threading
import networkx as nx
from typing import Dict, List, Optional, Any, TYPE_CHECKING
from enum import Enum # Added for isinstance check

if TYPE_CHECKING:
    from sentientresearchagent.hierarchical_agent_framework.node.task_node import TaskNode
    from sentientresearchagent.hierarchical_agent_framework.context.knowledge_store import KnowledgeStore
from sentientresearchagent.hierarchical_agent_framework.context.agent_io_models import CustomSearcherOutput # <--- IMPORT IT
from pydantic import BaseModel # Make sure this import is present
from loguru import logger # Add loguru import
# GraphSerializer import moved to method level to avoid circular import

class TaskGraph:
    """Manages the hierarchical graph structure of TaskNodes."""
    def __init__(self):
        # Stores the actual graphs. Key is graph_id, value is nx.DiGraph
        # A graph_id typically corresponds to a parent TaskNode's sub_graph_id or a root_graph_id.
        self.graphs: Dict[str, nx.DiGraph] = {}
        # Flat map for quick node lookup by ID across all graphs
        self.nodes: Dict[str, "TaskNode"] = {}
        self.root_graph_id: Optional[str] = None
        self.overall_project_goal: Optional[str] = None # Store the main goal
        # Add lock for thread-safe operations
        self._lock = threading.RLock()  # RLock allows re-entrant locking

    def add_graph(self, graph_id: str, is_root: bool = False) -> nx.DiGraph:
        with self._lock:
            if graph_id in self.graphs:
                # In a resumable system, you might load an existing graph.
                # For now, let's assume fresh creation or raise error.
                raise ValueError(f"Graph ID {graph_id} already exists.")
            graph = nx.DiGraph(graph_id=graph_id) # Add graph_id attribute to the graph itself
            self.graphs[graph_id] = graph
            if is_root:
                if self.root_graph_id is not None and self.root_graph_id != graph_id:
                    raise ValueError(f"Root graph already set to {self.root_graph_id}. Cannot set {graph_id} as root.")
                self.root_graph_id = graph_id
            logger.info(f"TaskGraph: Added graph '{graph_id}'. Is root: {is_root}")
            return graph

    def get_graph(self, graph_id: str) -> Optional[nx.DiGraph]:
        return self.graphs.get(graph_id)

    def add_node_to_graph(self, graph_id: str, node: "TaskNode"):
        """Adds a TaskNode to a specific graph and the global node lookup."""
        with self._lock:
            if graph_id not in self.graphs:
                raise ValueError(f"Graph ID '{graph_id}' not found. Cannot add node '{node.task_id}'.")
            
            graph = self.get_graph(graph_id)
            # The following check is redundant due to the check above and get_graph always returning a graph if the ID exists.
            # if graph is None: # Should be caught by above, but defensive check
            #     raise ValueError(f"Graph object for ID '{graph_id}' is None.")

            if node.task_id in self.nodes:
                # This could happen if a node is part of multiple conceptual graphs,
                # but a TaskNode object should be unique.
                # Or if attempting to re-add. For now, let's enforce uniqueness of add.
                # If updating, use a different method or get_node then modify.
                raise ValueError(f"Node ID {node.task_id} already exists in the global node map.")

            self.nodes[node.task_id] = node
            # Store the TaskNode object itself as a node attribute in the graph
            graph.add_node(node.task_id, task_node_obj=node)
            logger.info(f"TaskGraph: Added node '{node.task_id}' to graph '{graph_id}'.")


    def add_edge(self, graph_id: str, u_node_id: str, v_node_id: str):
        """Adds a directed edge (dependency) between two nodes in a specific graph."""
        with self._lock:
            graph = self.get_graph(graph_id)
            if not graph:
                raise ValueError(f"Graph ID {graph_id} not found. Cannot add edge between '{u_node_id}' and '{v_node_id}'.")
            if u_node_id not in graph.nodes or v_node_id not in graph.nodes:
                raise ValueError("Nodes must exist in the specified graph to add an edge.")
            graph.add_edge(u_node_id, v_node_id)
            logger.info(f"TaskGraph: Added edge {u_node_id} -> {v_node_id} in graph '{graph_id}'.")

    def get_node(self, node_id: str) -> Optional["TaskNode"]:
        """Retrieves a TaskNode by its ID from the global lookup."""
        return self.nodes.get(node_id)

    def get_all_nodes(self) -> List["TaskNode"]:
        """Returns a list of all TaskNode objects managed."""
        with self._lock:
            return list(self.nodes.values())

    def get_node_predecessors(self, graph_id: str, node_id: str) -> List["TaskNode"]:
        """Gets all predecessor TaskNodes of a given node within a specific graph."""
        graph = self.get_graph(graph_id)
        if not graph or node_id not in graph:
            return []
        
        predecessor_node_ids = list(graph.predecessors(node_id))
        predecessors = []
        for pred_id in predecessor_node_ids:
            node = self.get_node(pred_id)
            if node:
                predecessors.append(node)
        return predecessors

    def get_node_successors(self, graph_id: str, node_id: str) -> List["TaskNode"]:
        """Gets all successor TaskNodes of a given node within a specific graph."""
        graph = self.get_graph(graph_id)
        if not graph or node_id not in graph:
            return []
        
        successor_node_ids = list(graph.successors(node_id))
        successors = []
        for succ_id in successor_node_ids:
            node = self.get_node(succ_id)
            if node:
                successors.append(node)
        return successors

    def get_nodes_in_graph(self, graph_id: str) -> List["TaskNode"]:
        """Returns all TaskNodes belonging to a specific graph."""
        with self._lock:
            graph = self.get_graph(graph_id)
            if not graph:
                return []

        node_ids_in_graph = list(graph.nodes())
        nodes = []
        for node_id in node_ids_in_graph:
            node = self.get_node(node_id) # Fetch from the global map
            if node:
                nodes.append(node)
        return nodes

    def remove_graph_and_nodes(self, graph_id: str, knowledge_store: Optional["KnowledgeStore"] = None) -> None:
        """Remove a sub-graph and all associated TaskNodes."""
        with self._lock:
            graph = self.graphs.pop(graph_id, None)
            if not graph:
                logger.warning(f"TaskGraph: Attempted to remove non-existent graph '{graph_id}'")
                return

            node_ids = list(graph.nodes())
            for node_id in node_ids:
                self.nodes.pop(node_id, None)
            logger.info(f"TaskGraph: Removed graph '{graph_id}' and {len(node_ids)} node(s)")

        if knowledge_store:
            for node_id in node_ids:
                knowledge_store.remove_record(node_id)

    def to_visualization_dict(self) -> Dict[str, Any]:
        """
        Serializes the task graph to a dictionary for frontend visualization
        using the GraphSerializer.
        """
        from sentientresearchagent.hierarchical_agent_framework.graph.graph_serializer import GraphSerializer
        serializer = GraphSerializer(self)
        return serializer.to_visualization_dict()
