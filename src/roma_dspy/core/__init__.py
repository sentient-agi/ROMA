"""
Core runtime components for ROMA-DSPy.

This module exposes the main building blocks of the framework, including:
- Engine components (Solver, DAG)
- Modules (Atomizer, Planner, Executor, Aggregator, Verifier)
- Signatures and Data Structures
"""

from .engine import (
    TaskDAG,
    RecursiveSolver,
    solve,
    async_solve,
    event_solve,
    async_event_solve,
)
from .modules import (
    BaseModule,
    Atomizer,
    Planner,
    Executor,
    Aggregator,
    Verifier,
)
from .signatures import (
    AtomizerSignature,
    PlannerSignature,
    ExecutorSignature,
    AggregatorSignature,
    VerifierSignature,
    SubTask,
    TaskNode,
)

# Import the wrapper lazily after engine to avoid circular import
from .modules.recursive_solver import RecursiveSolverModule

__all__ = [
    "TaskDAG",
    "RecursiveSolver",
    "solve",
    "async_solve",
    "event_solve",
    "async_event_solve",
    "BaseModule",
    "Atomizer",
    "Planner",
    "Executor",
    "Aggregator",
    "Verifier",
    "AtomizerSignature",
    "PlannerSignature",
    "ExecutorSignature",
    "AggregatorSignature",
    "VerifierSignature",
    "SubTask",
    "TaskNode",
    "RecursiveSolverModule",
]
