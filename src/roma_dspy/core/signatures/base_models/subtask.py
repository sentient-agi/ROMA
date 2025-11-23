from pydantic import BaseModel, Field
from typing import List, Optional
from roma_dspy.types import TaskType


class SubTask(BaseModel):
    """
    Individual subtask in a decomposition plan.
    """

    goal: str = Field(..., min_length=1, description="Precise subtask objective")
    task_type: TaskType = Field(..., description="Type of subtask")
    dependencies: List[str] = Field(
        default_factory=list, description="List of subtask IDs this depends on"
    )
    result: Optional[str] = Field(
        default=None, description="Result of subtask execution (for aggregation)"
    )
    context_input: Optional[str] = Field(
        default=None, description="Context from dependent tasks (left-to-right flow)"
    )
