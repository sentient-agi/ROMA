"""ASCII renderer for DAG visualization.

Renders positioned DAG nodes and edges as ASCII art using Unicode box-drawing
characters. Supports multiple edge types with different visual styles.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Set, Tuple

from loguru import logger
from rich.console import Console
from rich.style import Style
from rich.text import Text

from roma_dspy.tui.models import DAGEdge, DAGViewModel, TaskViewModel
from roma_dspy.tui.rendering.dag_layout import EdgePath, Position
from roma_dspy.types import EdgeType


class DAGRenderer:
    """
    ASCII renderer for DAG visualization.

    Renders a positioned DAG as text with Unicode box-drawing characters.
    Supports colored output via Rich library.
    """

    # Box drawing characters
    BOX_HORIZONTAL = "─"
    BOX_VERTICAL = "│"
    BOX_DOWN_RIGHT = "┌"
    BOX_DOWN_LEFT = "┐"
    BOX_UP_RIGHT = "└"
    BOX_UP_LEFT = "┘"
    BOX_VERTICAL_RIGHT = "├"
    BOX_VERTICAL_LEFT = "┤"
    BOX_HORIZONTAL_DOWN = "┬"
    BOX_HORIZONTAL_UP = "┴"
    BOX_CROSS = "┼"

    # Arrow characters
    ARROW_RIGHT = "→"
    ARROW_DOWN = "↓"
    ARROW_UP = "↑"
    ARROW_LEFT = "←"

    # Status icons
    STATUS_ICONS = {
        "completed": "●",
        "done": "●",
        "running": "◐",
        "in_progress": "◐",
        "pending": "○",
        "ready": "○",
        "failed": "✗",
        "error": "✗",
        "blocked": "⊗",
        "waiting": "⊙",
        "cancelled": "⊘",
    }

    # Status colors (Rich style names)
    STATUS_COLORS = {
        "completed": "green",
        "done": "green",
        "running": "yellow",
        "in_progress": "yellow",
        "pending": "dim",
        "ready": "cyan",
        "failed": "red",
        "error": "red",
        "blocked": "magenta",
        "waiting": "blue",
        "cancelled": "dim",
    }

    def __init__(
        self,
        dag: DAGViewModel,
        positions: Dict[str, Position],
        cell_width: int = 20,
        cell_height: int = 3,
        show_metrics: bool = True,
        colorize: bool = True,
    ):
        self.dag = dag
        self.positions = positions
        self.cell_width = cell_width
        self.cell_height = cell_height
        self.show_metrics = show_metrics
        self.colorize = colorize
        self.console = Console()

        # Canvas for rendering
        self.canvas: List[List[str]] = []
        self.width = 0
        self.height = 0

    def render(self) -> str:
        """
        Render the DAG as ASCII art.

        Returns:
            String containing the rendered DAG
        """
        if not self.positions:
            return "No layout computed"

        # Initialize canvas
        self._initialize_canvas()

        # Render edges first (so nodes appear on top)
        self._render_edges()

        # Render nodes
        self._render_nodes()

        # Convert canvas to string
        return self._canvas_to_string()

    def render_rich(self) -> Text:
        """
        Render the DAG with Rich formatting (colors).

        Returns:
            Rich Text object with colored output
        """
        if not self.positions:
            return Text("No layout computed")

        # Initialize canvas
        self._initialize_canvas()

        # Render edges
        self._render_edges()

        # Render nodes
        self._render_nodes()

        # Convert to Rich Text with colors
        return self._canvas_to_rich_text()

    def _initialize_canvas(self) -> None:
        """Initialize the rendering canvas."""
        # Calculate canvas size from positions
        max_x = max(int(pos.x * self.cell_width) for pos in self.positions.values())
        max_y = max(int(pos.y * self.cell_height) for pos in self.positions.values())

        # Add padding
        self.width = max_x + self.cell_width * 2
        self.height = max_y + self.cell_height * 2

        # Initialize with spaces
        self.canvas = [[" " for _ in range(self.width)] for _ in range(self.height)]

    def _render_nodes(self) -> None:
        """Render all nodes on the canvas."""
        for task_id, position in self.positions.items():
            if task_id not in self.dag.nodes:
                continue

            task = self.dag.nodes[task_id]
            self._render_node(task, position)

    def _render_node(self, task: TaskViewModel, position: Position) -> None:
        """
        Render a single node.

        Node format:
        ┌──────────────┐
        │ ● Task 1     │
        │ Executor     │
        │ 1.2s │ $0.05 │
        └──────────────┘
        """
        # Calculate position on canvas
        x = int(position.x * self.cell_width)
        y = int(position.y * self.cell_height)

        # Node dimensions
        node_width = self.cell_width - 2
        node_height = self.cell_height

        # Truncate task goal to fit
        goal = task.goal[:node_width - 4] if len(task.goal) > node_width - 4 else task.goal

        # Get status icon
        status_icon = self.STATUS_ICONS.get(task.status.lower(), "○")

        # Format lines
        lines = []

        # Line 1: Status + Goal
        line1 = f"{status_icon} {goal}"
        lines.append(line1[:node_width])

        # Line 2: Module
        if task.module:
            module_text = task.module[:node_width]
            lines.append(module_text)
        else:
            lines.append("")

        # Line 3: Metrics (if enabled)
        if self.show_metrics and node_height > 2:
            duration = f"{task.total_duration:.1f}s"
            cost = f"${task.total_cost:.2f}"
            metrics_text = f"{duration} │ {cost}"
            lines.append(metrics_text[:node_width])

        # Draw box
        try:
            # Top border
            self._draw_text(x, y, self.BOX_DOWN_RIGHT + self.BOX_HORIZONTAL * node_width + self.BOX_DOWN_LEFT)

            # Content lines
            for i, line in enumerate(lines):
                if y + i + 1 < self.height:
                    content = line.ljust(node_width)
                    self._draw_text(x, y + i + 1, self.BOX_VERTICAL + content + self.BOX_VERTICAL)

            # Bottom border
            if y + node_height < self.height:
                self._draw_text(x, y + node_height, self.BOX_UP_RIGHT + self.BOX_HORIZONTAL * node_width + self.BOX_UP_LEFT)

        except IndexError:
            logger.warning(f"Node at ({x}, {y}) exceeds canvas bounds")

    def _render_edges(self) -> None:
        """Render all edges on the canvas."""
        for edge in self.dag.edges:
            if edge.from_task_id not in self.positions or edge.to_task_id not in self.positions:
                continue

            from_pos = self.positions[edge.from_task_id]
            to_pos = self.positions[edge.to_task_id]

            self._render_edge(from_pos, to_pos, edge.edge_type)

    def _render_edge(self, from_pos: Position, to_pos: Position, edge_type: EdgeType) -> None:
        """
        Render a single edge between two positions.

        Uses Bresenham's line algorithm for drawing.
        """
        # Get grid positions (center of nodes)
        x1 = int(from_pos.x * self.cell_width) + self.cell_width // 2
        y1 = int(from_pos.y * self.cell_height) + self.cell_height // 2
        x2 = int(to_pos.x * self.cell_width) + self.cell_width // 2
        y2 = int(to_pos.y * self.cell_height) + self.cell_height // 2

        # Get edge symbol
        symbol = edge_type.symbol

        # Bresenham's line algorithm
        points = self._bresenham_line(x1, y1, x2, y2)

        for i, (x, y) in enumerate(points):
            if 0 <= x < self.width and 0 <= y < self.height:
                # Don't overwrite existing node characters
                if self.canvas[y][x] not in (" ", symbol):
                    continue

                # Draw arrow at the end point
                if i == len(points) - 1:
                    if abs(x2 - x1) > abs(y2 - y1):
                        self.canvas[y][x] = self.ARROW_RIGHT if x2 > x1 else self.ARROW_LEFT
                    else:
                        self.canvas[y][x] = self.ARROW_DOWN if y2 > y1 else self.ARROW_UP
                else:
                    self.canvas[y][x] = symbol

    def _bresenham_line(self, x1: int, y1: int, x2: int, y2: int) -> List[Tuple[int, int]]:
        """
        Bresenham's line algorithm for drawing lines.

        Returns list of (x, y) points along the line.
        """
        points = []
        dx = abs(x2 - x1)
        dy = abs(y2 - y1)
        sx = 1 if x1 < x2 else -1
        sy = 1 if y1 < y2 else -1
        err = dx - dy

        x, y = x1, y1
        while True:
            points.append((x, y))

            if x == x2 and y == y2:
                break

            e2 = 2 * err
            if e2 > -dy:
                err -= dy
                x += sx
            if e2 < dx:
                err += dx
                y += sy

        return points

    def _draw_text(self, x: int, y: int, text: str) -> None:
        """Draw text at position (x, y) on canvas."""
        if 0 <= y < self.height:
            for i, char in enumerate(text):
                if x + i < self.width:
                    self.canvas[y][x + i] = char

    def _canvas_to_string(self) -> str:
        """Convert canvas to string."""
        return "\n".join("".join(row) for row in self.canvas)

    def _canvas_to_rich_text(self) -> Text:
        """Convert canvas to Rich Text with colors."""
        result = Text()

        for y, row in enumerate(self.canvas):
            line_text = Text()
            for x, char in enumerate(row):
                # Check if this character is part of a node
                task = self._get_task_at_position(x, y)
                if task:
                    color = self.STATUS_COLORS.get(task.status.lower(), "white")
                    line_text.append(char, style=color)
                else:
                    line_text.append(char)

            result.append(line_text)
            if y < len(self.canvas) - 1:
                result.append("\n")

        return result

    def _get_task_at_position(self, x: int, y: int) -> Optional[TaskViewModel]:
        """Get task at canvas position (x, y)."""
        for task_id, position in self.positions.items():
            node_x = int(position.x * self.cell_width)
            node_y = int(position.y * self.cell_height)
            node_width = self.cell_width - 2
            node_height = self.cell_height

            if (
                node_x <= x <= node_x + node_width + 1
                and node_y <= y <= node_y + node_height
            ):
                return self.dag.nodes.get(task_id)

        return None


def render_dag_ascii(
    dag: DAGViewModel,
    positions: Dict[str, Position],
    cell_width: int = 20,
    cell_height: int = 3,
    show_metrics: bool = True,
) -> str:
    """
    Convenience function to render DAG as ASCII art.

    Args:
        dag: DAG view model
        positions: Node positions from layout engine
        cell_width: Width of each cell in characters
        cell_height: Height of each cell in lines
        show_metrics: Whether to show metrics in nodes

    Returns:
        ASCII art string
    """
    renderer = DAGRenderer(dag, positions, cell_width, cell_height, show_metrics)
    return renderer.render()


def render_dag_rich(
    dag: DAGViewModel,
    positions: Dict[str, Position],
    cell_width: int = 20,
    cell_height: int = 3,
    show_metrics: bool = True,
) -> Text:
    """
    Convenience function to render DAG with Rich formatting.

    Args:
        dag: DAG view model
        positions: Node positions from layout engine
        cell_width: Width of each cell in characters
        cell_height: Height of each cell in lines
        show_metrics: Whether to show metrics in nodes

    Returns:
        Rich Text object with colors
    """
    renderer = DAGRenderer(dag, positions, cell_width, cell_height, show_metrics, colorize=True)
    return renderer.render_rich()