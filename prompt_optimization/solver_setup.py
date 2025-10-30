"""Solver setup that adapts ROMA configs for prompt optimization."""

from typing import Optional

from roma_dspy import RecursiveSolverModule
from roma_dspy.config import load_config
from roma_dspy.core.engine.solve import RecursiveSolver

from prompt_optimization.config import OptimizationConfig, patch_romaconfig


def create_solver_module(
    config: OptimizationConfig,
    *,
    profile: Optional[str] = None,
    mlflow_tracking_uri: Optional[str] = None
) -> RecursiveSolverModule:
    """
    Create a RecursiveSolverModule configured with optimization-specific settings.

    Args:
        config: Prompt optimization configuration.
        profile: Optional ROMA config profile to load before patching.
        mlflow_tracking_uri: Optional MLflow tracking URI for observability.

    Returns:
        RecursiveSolverModule wired to a RecursiveSolver that uses optimization LMs.
    """
    base_config = load_config(profile=profile)
    patched_config = patch_romaconfig(config, base_config, mlflow_tracking_uri)

    solver = RecursiveSolver(
        config=patched_config,
        max_depth=config.max_depth,
        enable_logging=config.enable_logging,
        enable_checkpoints=False,
    )
    return RecursiveSolverModule(solver=solver)
