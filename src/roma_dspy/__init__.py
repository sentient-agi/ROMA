"""ROMA-DSPy: modular hierarchical task decomposition framework."""

__version__ = "0.1.0"

from typing import Optional, Sequence

# Apply LiteLLM compatibility patches (noop if LiteLLM unavailable).
try:  # pragma: no cover - defensive import
    from .utils.litellm_patch import (
        patch_litellm_logging_worker as _patch_litellm_logging_worker,
        patch_dspy_responses_dict_support as _patch_dspy_responses_dict_support,
    )
except Exception:  # pragma: no cover - LiteLLM optional or import issue
    _patch_litellm_logging_worker = None
    _patch_dspy_responses_dict_support = None

if _patch_litellm_logging_worker is not None:
    _patch_litellm_logging_worker()
if _patch_dspy_responses_dict_support is not None:
    _patch_dspy_responses_dict_support()

from .core import (
    TaskDAG,
    RecursiveSolver,
    solve,
    async_solve,
    event_solve,
    async_event_solve,
    Atomizer,
    Planner,
    Executor,
    Aggregator,
    Verifier,
    AtomizerSignature,
    PlannerSignature,
    ExecutorSignature,
    AggregatorSignature,
    VerifierSignature,
    SubTask,
    TaskNode,
    RecursiveSolverModule,
)

__all__ = [
    "__version__",
    "TaskDAG",
    "RecursiveSolver",
    "solve",
    "async_solve",
    "event_solve",
    "async_event_solve",
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
    "main",
]
