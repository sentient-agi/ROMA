import dspy
from typing import Optional, Dict, List, Any
from roma_dspy.core.signatures.base_models.subtask import SubTask
from roma_dspy.types import NodeType


class AtomizerSignature(dspy.Signature):
    """Signature for task atomization."""

    goal: str = dspy.InputField(description="Task to atomize")
    context: Optional[str] = dspy.InputField(
        default=None, description="Execution context (XML)"
    )
    is_atomic: bool = dspy.OutputField(
        description="True if task can be executed directly"
    )
    node_type: NodeType = dspy.OutputField(
        description="Type of node to process (PLAN or EXECUTE)"
    )


class PlannerSignature(dspy.Signature):
    """
    Planner decomposition result.

    Contains the breakdown of a complex task into executable subtasks.
    """

    goal: str = dspy.InputField(
        description="Task that needs to be decomposed into subtasks through planner"
    )
    context: Optional[str] = dspy.InputField(
        default=None, description="Execution context (XML)"
    )
    subtasks: List[SubTask] = dspy.OutputField(
        description="List of generated subtasks from planner"
    )
    dependencies_graph: Optional[Dict[str, List[str]]] = dspy.OutputField(
        default=None,
        description="Task dependency mapping. Keys are subtask indices as strings (e.g., '0', '1'), values are lists of dependency indices as strings. Example: {'1': ['0'], '2': ['0', '1']}",
    )


class ExecutorSignature(dspy.Signature):
    """
    Executor execution result.

    Contains the output of atomic task execution.
    """

    goal: str = dspy.InputField(description="Task that needs to be executed")
    context: Optional[str] = dspy.InputField(
        default=None, description="Execution context (XML)"
    )
    output: str = dspy.OutputField(description="Execution result")
    sources: Optional[List[str]] = dspy.OutputField(
        default_factory=list, description="Information sources used"
    )


class AggregatorSignature(dspy.Signature):
    """
    Aggregator synthesis result.

    Contains the synthesis of multiple subtask results into a cohesive output.
    """

    original_goal: str = dspy.InputField(description="Original goal of the task")
    subtasks_results: List[SubTask] = dspy.InputField(
        description="List of subtask results to synthesize"
    )
    context: Optional[str] = dspy.InputField(
        default=None, description="Execution context (XML)"
    )
    synthesized_result: str = dspy.OutputField(description="Final synthesized output")


class VerifierSignature(dspy.Signature):
    """Signature for validating synthesized results against the goal."""

    goal: str = dspy.InputField(description="Task goal the output should satisfy")
    candidate_output: str = dspy.InputField(
        description="Output produced by previous modules"
    )
    context: Optional[str] = dspy.InputField(
        default=None, description="Execution context (XML)"
    )
    verdict: bool = dspy.OutputField(
        description="True if the candidate output satisfies the goal"
    )
    feedback: Optional[str] = dspy.OutputField(
        default=None, description="Explanation or fixes when the verdict is False"
    )
