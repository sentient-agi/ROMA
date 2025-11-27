"""Thin DSPy module wrapper around the RecursiveSolver orchestration engine."""

from __future__ import annotations

import copy
from typing import Optional, Callable, List, Tuple, Any

import dspy

from roma_dspy.core.engine.solve import RecursiveSolver
from roma_dspy.core.engine.dag import TaskDAG
from roma_dspy.core.signatures import TaskNode
from roma_dspy.core.utils.trace_formatter import format_solver_trace
from roma_dspy.types import AgentType, TaskType
from loguru import logger


class RecursiveSolverModule(dspy.Module):
    """Expose RecursiveSolver through a DSPy module interface.

    This is a thin wrapper: it accepts a pre-configured `RecursiveSolver` and
    delegates execution to it. Attributes and methods not found on the module
    are proxied to the underlying solver for convenience.
    """

    def __init__(self, *, solver: RecursiveSolver) -> None:
        super().__init__()
        self._solver = solver
        self._last_solver: Optional[RecursiveSolver] = (
            None  # Snapshot from most recent run
        )

        # Expose solver's core attributes (these actually exist on RecursiveSolver)
        self.runtime = solver.runtime
        self.max_depth = solver.max_depth
        self.registry = (
            solver.registry
        )  # For accessing agents via registry.get_agent(AgentType, TaskType)

    def forward(
        self,
        goal: str,
        *,
        dag: Optional[TaskDAG] = None,
        depth: int = 0,
        priority_fn: Optional[Callable[[TaskNode], int]] = None,
        concurrency: Optional[int] = None,
    ) -> dspy.Prediction:
        solver_instance = self._spawn_solver()

        # Use runtime config's max_concurrency if not explicitly provided
        effective_concurrency = (
            concurrency
            if concurrency is not None
            else self._solver.config.runtime.max_concurrency
        )

        completed_task = solver_instance.event_solve(
            task=goal,
            dag=dag,
            depth=depth,
            priority_fn=priority_fn,
            concurrency=effective_concurrency,
        )

        # Format trace using lightweight formatter
        trace = format_solver_trace(self._solver)

        return dspy.Prediction(
            goal=goal,
            completed_task=completed_task,
            status=completed_task.status,
            result_text=str(completed_task.result)
            if completed_task.result is not None
            else None,
            output_trace=trace,
        )

    def named_predictors(self) -> List[Tuple[str, Any]]:
        """
        Surface all predictors exposed by the recursive solver's agents.

        GEPA inspects DSPy modules via named_predictors(); exposing the agents'
        predictors here allows the optimizer to mutate individual instructions.
        """
        predictors = list(super().named_predictors())

        if not hasattr(self._solver, "registry"):
            return predictors

        seen_ids = {id(pred) for _, pred in predictors}

        for agent_type, task_type, module in self._solver.registry.iter_agents():
            if not hasattr(module, "named_predictors"):
                continue

            agent_predictors = module.named_predictors()
            if not agent_predictors:
                logger.debug(
                    "Agent %s (task=%s) has no named predictors (type=%s)",
                    getattr(agent_type, "value", agent_type),
                    getattr(task_type, "value", task_type)
                    if task_type is not None
                    else "default",
                    type(module).__name__,
                )
                continue

            agent_label = (
                agent_type.value.lower()
                if isinstance(agent_type, AgentType)
                else str(agent_type).lower()
            )
            task_label = (
                task_type.value.lower()
                if isinstance(task_type, TaskType)
                else ("default" if task_type is None else str(task_type).lower())
            )

            for predictor_name, predictor in agent_predictors:
                if predictor is None:
                    logger.debug(
                        "Skipping None predictor from agent %s (task=%s)",
                        getattr(agent_type, "value", agent_type),
                        getattr(task_type, "value", task_type)
                        if task_type is not None
                        else "default",
                    )
                    continue

                predictor_id = id(predictor)
                if predictor_id in seen_ids:
                    continue

                composite_name = f"{agent_label}__{task_label}__{predictor_name}"
                predictors.append((composite_name, predictor))
                seen_ids.add(predictor_id)

        exported_names = [name for name, _ in predictors]
        logger.debug(
            f"RecursiveSolverModule.named_predictors exported {len(exported_names)} predictors: {exported_names}"
        )

        return predictors

    def __deepcopy__(self, memo):
        """
        Custom deep copy for RecursiveSolverModule.

        RecursiveSolver contains non-copyable objects (locks, database connections, singletons).
        Instead of deep copying the solver, we reuse the same instance (shallow copy).
        This is safe because:
        1. RecursiveSolver is thread-safe (fixed with thread-local storage)
        2. Solver config/registry are read-only after initialization
        3. GEPA only needs to copy module parameters (predictors), not infrastructure

        Args:
            memo: Deep copy memo dict

        Returns:
            New RecursiveSolverModule instance sharing the same solver
        """
        # Create new instance without calling __init__
        new_instance = self.__class__.__new__(self.__class__)

        # Register in memo to handle circular references
        memo[id(self)] = new_instance

        # Copy DSPy base attributes (history, callbacks, etc.)
        if hasattr(self, "__dict__"):
            for key, value in self.__dict__.items():
                if key == "_solver":
                    # Shallow copy solver (share same instance - it's thread-safe)
                    setattr(new_instance, key, value)
                elif key in ("runtime", "registry", "max_depth"):
                    # Shallow copy infrastructure attributes (read-only, shared)
                    setattr(new_instance, key, value)
                else:
                    # Deep copy other attributes (history, callbacks, etc.)
                    try:
                        setattr(new_instance, key, copy.deepcopy(value, memo))
                    except Exception:
                        # Fallback to shallow copy if deep copy fails
                        setattr(new_instance, key, value)

        return new_instance

    async def aforward(
        self,
        goal: str,
        *,
        dag: Optional[TaskDAG] = None,
        depth: int = 0,
        priority_fn: Optional[Callable[[TaskNode], int]] = None,
        concurrency: Optional[int] = None,
    ) -> dspy.Prediction:
        solver_instance = self._spawn_solver()

        # Use runtime config's max_concurrency if not explicitly provided
        effective_concurrency = (
            concurrency
            if concurrency is not None
            else self._solver.config.runtime.max_concurrency
        )

        completed_task = await solver_instance.async_event_solve(
            task=goal,
            dag=dag,
            depth=depth,
            priority_fn=priority_fn,
            concurrency=effective_concurrency,
        )

        # Format trace using lightweight formatter
        trace = format_solver_trace(self._solver)

        return dspy.Prediction(
            goal=goal,
            completed_task=completed_task,
            status=completed_task.status,
            result_text=str(completed_task.result)
            if completed_task.result is not None
            else None,
            output_trace=trace,
        )

    def _spawn_solver(self) -> RecursiveSolver:
        """
        Create an isolated solver instance for a single call.

        DSPy optimizers (e.g., GEPA) run multiple rollouts concurrently. The
        underlying RecursiveSolver mutates execution state (overall objective,
        DAG, context), so sharing the same instance across concurrent calls can
        mix traces/goals between rollouts. Deep copying ensures each execution
        has isolated state while preserving any prompt/LM edits applied to the
        template solver.
        """
        return copy.deepcopy(self._solver)
