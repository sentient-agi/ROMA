"""DAG layout engine for hierarchical graph visualization.

This module provides algorithms for positioning nodes in a DAG for ASCII rendering.
Uses NetworkX for graph algorithms and provides hierarchical and topological layouts.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Dict, List, Optional, Set, Tuple

import networkx as nx
from loguru import logger

from roma_dspy.tui.models import DAGEdge, DAGViewModel, TaskViewModel
from roma_dspy.types import EdgeType


class Position:
    """2D position for node placement."""

    def __init__(self, x: float, y: float):
        self.x = x
        self.y = y

    def to_grid(self, cell_width: int = 4, cell_height: int = 2) -> Tuple[int, int]:
        """Convert float position to terminal grid coordinates."""
        return (int(self.x * cell_width), int(self.y * cell_height))

    def __repr__(self) -> str:
        return f"Position({self.x}, {self.y})"


class EdgePath:
    """Path for rendering an edge between two nodes."""

    def __init__(
        self,
        from_pos: Position,
        to_pos: Position,
        edge_type: EdgeType,
        waypoints: Optional[List[Position]] = None,
    ):
        self.from_pos = from_pos
        self.to_pos = to_pos
        self.edge_type = edge_type
        self.waypoints = waypoints or []

    def get_grid_points(
        self, cell_width: int = 4, cell_height: int = 2
    ) -> List[Tuple[int, int]]:
        """Get all grid points along the path."""
        points = [self.from_pos.to_grid(cell_width, cell_height)]
        for waypoint in self.waypoints:
            points.append(waypoint.to_grid(cell_width, cell_height))
        points.append(self.to_pos.to_grid(cell_width, cell_height))
        return points


class DAGLayoutEngine:
    """
    Layout engine for DAG visualization.

    Provides multiple layout algorithms:
    - Hierarchical: NetworkX-based hierarchical layout
    - Topological: Left-to-right layers based on topological sort
    - Compact: Minimize vertical space usage
    """

    def __init__(self, dag: DAGViewModel):
        self.dag = dag
        self.positions: Dict[str, Position] = {}
        self.edge_paths: List[EdgePath] = []

    def compute_hierarchical_layout(
        self, spacing_x: float = 1.0, spacing_y: float = 1.0
    ) -> Dict[str, Position]:
        """
        Compute hierarchical layout using NetworkX.

        Uses a combination of topological sorting and Sugiyama-style
        hierarchical layout to minimize edge crossings.

        Args:
            spacing_x: Horizontal spacing between nodes
            spacing_y: Vertical spacing between layers

        Returns:
            Dictionary mapping task IDs to positions
        """
        logger.debug(f"Computing hierarchical layout for {len(self.dag.nodes)} nodes")

        if not self.dag.nodes:
            return {}

        # Build NetworkX directed graph from dependency edges
        graph = nx.DiGraph()

        for task_id in self.dag.nodes:
            graph.add_node(task_id)

        for edge in self.dag.edges:
            if edge.edge_type == EdgeType.DEPENDENCY:
                graph.add_edge(edge.from_task_id, edge.to_task_id)

        # Check if graph is acyclic
        if not nx.is_directed_acyclic_graph(graph):
            logger.warning("Graph contains cycles, using fallback layout")
            return self._fallback_layout()

        # Use multipartite layout based on topological generations
        try:
            # Get layers using topological sort
            layers = list(nx.topological_generations(graph))

            # Assign vertical positions based on layer
            positions = {}
            for layer_idx, layer_nodes in enumerate(layers):
                y = layer_idx * spacing_y

                # Distribute nodes horizontally within layer
                num_nodes = len(layer_nodes)
                for node_idx, node_id in enumerate(sorted(layer_nodes)):
                    # Center nodes in layer
                    x = (node_idx - num_nodes / 2) * spacing_x
                    positions[node_id] = Position(x, y)

            # Add nodes not in graph (orphaned)
            orphaned = set(self.dag.nodes.keys()) - set(positions.keys())
            if orphaned:
                max_y = max(pos.y for pos in positions.values()) if positions else 0
                for idx, node_id in enumerate(sorted(orphaned)):
                    positions[node_id] = Position(idx * spacing_x, max_y + spacing_y)

            logger.debug(f"Hierarchical layout computed: {len(layers)} layers")
            self.positions = positions
            return positions

        except Exception as e:
            logger.error(f"Error computing hierarchical layout: {e}")
            return self._fallback_layout()

    def compute_topological_layout(
        self, spacing_x: float = 2.0, spacing_y: float = 1.0
    ) -> Dict[str, Position]:
        """
        Compute left-to-right topological layout.

        Nodes are arranged in vertical columns based on their depth
        in the dependency graph. This layout emphasizes execution order.

        Args:
            spacing_x: Horizontal spacing between columns
            spacing_y: Vertical spacing between nodes in same column

        Returns:
            Dictionary mapping task IDs to positions
        """
        logger.debug(f"Computing topological layout for {len(self.dag.nodes)} nodes")

        if not self.dag.nodes:
            return {}

        # Build adjacency list and in-degree map
        adj: Dict[str, List[str]] = defaultdict(list)
        in_degree: Dict[str, int] = {task_id: 0 for task_id in self.dag.nodes}

        for edge in self.dag.edges:
            if edge.edge_type == EdgeType.DEPENDENCY:
                adj[edge.from_task_id].append(edge.to_task_id)
                in_degree[edge.to_task_id] = in_degree.get(edge.to_task_id, 0) + 1

        # Topological sort to assign columns
        queue = [task_id for task_id, degree in in_degree.items() if degree == 0]
        columns: Dict[int, List[str]] = defaultdict(list)
        node_column: Dict[str, int] = {}

        visited = set()
        while queue:
            current = queue.pop(0)
            if current in visited:
                continue
            visited.add(current)

            # Assign column (max of predecessors' columns + 1)
            predecessors_in_graph = [
                node_column[pred]
                for pred in self.dag.nodes[current].dependencies
                if pred in node_column
            ]
            col = max(predecessors_in_graph, default=-1) + 1
            node_column[current] = col
            columns[col].append(current)

            # Add neighbors to queue
            for neighbor in adj.get(current, []):
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        # Assign positions
        positions = {}
        for col_idx in sorted(columns.keys()):
            col_nodes = columns[col_idx]
            x = col_idx * spacing_x

            # Vertically center nodes in column
            num_nodes = len(col_nodes)
            for node_idx, node_id in enumerate(sorted(col_nodes)):
                y = (node_idx - num_nodes / 2) * spacing_y
                positions[node_id] = Position(x, y)

        # Handle orphaned nodes
        orphaned = set(self.dag.nodes.keys()) - set(positions.keys())
        if orphaned:
            max_x = max(pos.x for pos in positions.values()) if positions else 0
            for idx, node_id in enumerate(sorted(orphaned)):
                positions[node_id] = Position(max_x + spacing_x, idx * spacing_y)

        logger.debug(f"Topological layout computed: {len(columns)} columns")
        self.positions = positions
        return positions

    def compute_compact_layout(self, max_width: int = 10) -> Dict[str, Position]:
        """
        Compute compact layout that minimizes vertical space.

        Tries to fit nodes within a maximum width constraint while
        respecting dependency ordering.

        Args:
            max_width: Maximum number of nodes per row

        Returns:
            Dictionary mapping task IDs to positions
        """
        logger.debug(
            f"Computing compact layout for {len(self.dag.nodes)} nodes (max_width={max_width})"
        )

        if not self.dag.nodes:
            return {}

        # Use topological sort to get ordering
        graph = nx.DiGraph()
        for task_id in self.dag.nodes:
            graph.add_node(task_id)
        for edge in self.dag.edges:
            if edge.edge_type == EdgeType.DEPENDENCY:
                graph.add_edge(edge.from_task_id, edge.to_task_id)

        try:
            sorted_nodes = list(nx.topological_sort(graph))
        except nx.NetworkXError:
            # Fallback to task IDs if graph has cycles
            sorted_nodes = sorted(self.dag.nodes.keys())

        # Arrange in grid with max_width constraint
        positions = {}
        for idx, node_id in enumerate(sorted_nodes):
            row = idx // max_width
            col = idx % max_width
            positions[node_id] = Position(float(col) * 1.5, float(row) * 1.0)

        logger.debug(f"Compact layout computed: {len(sorted_nodes) // max_width + 1} rows")
        self.positions = positions
        return positions

    def route_edges(self) -> List[EdgePath]:
        """
        Compute edge paths between positioned nodes.

        Uses Bresenham-like algorithm for routing edges while
        avoiding overlaps where possible.

        Returns:
            List of edge paths
        """
        if not self.positions:
            logger.warning("No positions computed, cannot route edges")
            return []

        edge_paths = []

        for edge in self.dag.edges:
            from_id = edge.from_task_id
            to_id = edge.to_task_id

            if from_id not in self.positions or to_id not in self.positions:
                continue

            from_pos = self.positions[from_id]
            to_pos = self.positions[to_id]

            # Simple straight-line path for now
            # TODO: Add waypoint routing to avoid overlaps
            path = EdgePath(
                from_pos=from_pos, to_pos=to_pos, edge_type=edge.edge_type, waypoints=[]
            )
            edge_paths.append(path)

        logger.debug(f"Routed {len(edge_paths)} edges")
        self.edge_paths = edge_paths
        return edge_paths

    def get_bounding_box(self) -> Tuple[Position, Position]:
        """
        Get bounding box of all positioned nodes.

        Returns:
            Tuple of (min_position, max_position)
        """
        if not self.positions:
            return (Position(0, 0), Position(0, 0))

        min_x = min(pos.x for pos in self.positions.values())
        max_x = max(pos.x for pos in self.positions.values())
        min_y = min(pos.y for pos in self.positions.values())
        max_y = max(pos.y for pos in self.positions.values())

        return (Position(min_x, min_y), Position(max_x, max_y))

    def normalize_positions(self, margin: float = 1.0) -> None:
        """
        Normalize all positions to start from (margin, margin).

        Args:
            margin: Margin to add around the graph
        """
        if not self.positions:
            return

        min_pos, _ = self.get_bounding_box()

        for node_id, pos in self.positions.items():
            self.positions[node_id] = Position(
                pos.x - min_pos.x + margin, pos.y - min_pos.y + margin
            )

    def _fallback_layout(self) -> Dict[str, Position]:
        """
        Fallback layout for graphs with cycles or errors.

        Simply arranges nodes in a grid.
        """
        logger.warning("Using fallback grid layout")
        positions = {}
        nodes = sorted(self.dag.nodes.keys())
        grid_size = int(len(nodes) ** 0.5) + 1

        for idx, node_id in enumerate(nodes):
            row = idx // grid_size
            col = idx % grid_size
            positions[node_id] = Position(float(col), float(row))

        return positions


def compute_layout(
    dag: DAGViewModel, algorithm: str = "hierarchical", **kwargs
) -> Dict[str, Position]:
    """
    Convenience function to compute DAG layout.

    Args:
        dag: DAG view model to layout
        algorithm: Layout algorithm ("hierarchical", "topological", "compact")
        **kwargs: Additional arguments for the layout algorithm

    Returns:
        Dictionary mapping task IDs to positions
    """
    engine = DAGLayoutEngine(dag)

    if algorithm == "hierarchical":
        positions = engine.compute_hierarchical_layout(**kwargs)
    elif algorithm == "topological":
        positions = engine.compute_topological_layout(**kwargs)
    elif algorithm == "compact":
        positions = engine.compute_compact_layout(**kwargs)
    else:
        logger.warning(f"Unknown algorithm '{algorithm}', using hierarchical")
        positions = engine.compute_hierarchical_layout(**kwargs)

    engine.normalize_positions()
    engine.route_edges()

    # Store positions in DAG
    dag.set_node_positions(
        {node_id: pos.to_grid() for node_id, pos in engine.positions.items()}
    )

    return engine.positions