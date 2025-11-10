"""Edge type enumeration for DAG visualization."""

from enum import Enum
from typing import Literal


class EdgeType(str, Enum):
    """
    Types of edges in the task execution graph.

    Used for DAG visualization to distinguish different relationships:
    - DEPENDENCY: Task execution dependencies (A must complete before B)
    - DATA_FLOW: Data passed between tasks
    - CONTROL_FLOW: Control/decision flow between tasks
    - PARENT_CHILD: Hierarchical parent-child relationship
    """

    DEPENDENCY = "dependency"
    DATA_FLOW = "data_flow"
    CONTROL_FLOW = "control_flow"
    PARENT_CHILD = "parent_child"

    @property
    def symbol(self) -> str:
        """ASCII symbol for rendering this edge type."""
        return {
            EdgeType.DEPENDENCY: "─",  # Solid line
            EdgeType.DATA_FLOW: "═",   # Double line
            EdgeType.CONTROL_FLOW: "┄",  # Dashed line
            EdgeType.PARENT_CHILD: "│",  # Vertical line
        }[self]

    @property
    def description(self) -> str:
        """Human-readable description."""
        return {
            EdgeType.DEPENDENCY: "Execution dependency",
            EdgeType.DATA_FLOW: "Data transfer",
            EdgeType.CONTROL_FLOW: "Control flow",
            EdgeType.PARENT_CHILD: "Hierarchical relationship",
        }[self]


EdgeTypeLiteral = Literal["dependency", "data_flow", "control_flow", "parent_child"]