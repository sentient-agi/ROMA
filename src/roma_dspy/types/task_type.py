"""
TaskType enumeration for ROMA v2.0

Implements the MECE (Mutually Exclusive, Collectively Exhaustive) framework
for task classification with RETRIEVE replacing SEARCH from v1.

ROMA v2 task types (five total):
- RETRIEVE: External data acquisition from multiple sources
- WRITE: Content generation and synthesis
- THINK: Analysis, reasoning, decision making
- CODE_INTERPRET: Code execution and data processing
- IMAGE_GENERATION: Visual content creation

Note: AGGREGATE is an agent type (Aggregator), not a task type.
"""

from enum import Enum
from typing import Literal


class TaskType(str, Enum):
    """
    MECE task classification for universal task decomposition.
    """

    RETRIEVE = "RETRIEVE"  # Multi-source data acquisition
    WRITE = "WRITE"  # Content generation and synthesis
    THINK = "THINK"  # Analysis, reasoning, decision making
    CODE_INTERPRET = "CODE_INTERPRET"  # Code execution and data processing
    IMAGE_GENERATION = "IMAGE_GENERATION"  # Visual content creation

    def __str__(self) -> str:
        return self.value

    @classmethod
    def from_string(cls, value: str) -> "TaskType":
        """
        Convert string to TaskType.

        Args:
            value: String representation of task type

        Returns:
            TaskType enum value

        Raises:
            ValueError: If value is not a valid task type
        """
        try:
            return cls(value.upper())
        except ValueError:
            valid_types = [t.value for t in cls]
            raise ValueError(f"Invalid task type '{value}'. Valid types: {valid_types}")

    @property
    def is_retrieve(self) -> bool:
        """Check if this is a RETRIEVE task type."""
        return self == TaskType.RETRIEVE

    @property
    def is_write(self) -> bool:
        """Check if this is a WRITE task type."""
        return self == TaskType.WRITE

    @property
    def is_think(self) -> bool:
        """Check if this is a THINK task type."""
        return self == TaskType.THINK

    @property
    def is_code_interpret(self) -> bool:
        """Check if this is a CODE_INTERPRET task type."""
        return self == TaskType.CODE_INTERPRET

    @property
    def is_image_generation(self) -> bool:
        """Check if this is an IMAGE_GENERATION task type."""
        return self == TaskType.IMAGE_GENERATION


# Type hints for use in other modules
TaskTypeLiteral = Literal[
    "RETRIEVE", "WRITE", "THINK", "CODE_INTERPRET", "IMAGE_GENERATION"
]
