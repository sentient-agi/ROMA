"""Component selector functions for GEPA optimization."""

from typing import Any, Dict, List


def planner_only_selector(
    state: Any,
    trajectories: Any,
    subsample_scores: Any,
    candidate_idx: int,
    candidate: Dict[str, Any]
) -> str:
    """
    Selector that only optimizes the planner component.

    This is the most common selector for math problems, as the planner
    is typically the most important component for task decomposition.

    Args:
        state: GEPA optimization state
        trajectories: Optimization trajectories
        subsample_scores: Scores for current subsample
        candidate_idx: Index of current candidate
        candidate: Dict of component names -> prompts

    Returns:
        Component name to optimize
    """
    components = list(candidate.keys())
    if "planner" in components:
        return components[components.index('planner')]
    return components[0]


def atomizer_only_selector(
    state: Any,
    trajectories: Any,
    subsample_scores: Any,
    candidate_idx: int,
    candidate: Dict[str, Any]
) -> str:
    """
    Selector that only optimizes the atomizer component.

    Use this when you want to improve the atomicity detection logic.

    Args:
        state: GEPA optimization state
        trajectories: Optimization trajectories
        subsample_scores: Scores for current subsample
        candidate_idx: Index of current candidate
        candidate: Dict of component names -> prompts

    Returns:
        Component name to optimize
    """
    components = list(candidate.keys())
    if "atomizer" in components:
        return components[components.index('atomizer')]
    return components[0]


def executor_only_selector(
    state: Any,
    trajectories: Any,
    subsample_scores: Any,
    candidate_idx: int,
    candidate: Dict[str, Any]
) -> str:
    """
    Selector that only optimizes the executor component.

    Use this when you want to improve atomic task execution.

    Args:
        state: GEPA optimization state
        trajectories: Optimization trajectories
        subsample_scores: Scores for current subsample
        candidate_idx: Index of current candidate
        candidate: Dict of component names -> prompts

    Returns:
        Component name to optimize
    """
    components = list(candidate.keys())
    if "executor" in components:
        return components[components.index('executor')]
    return components[0]


def aggregator_only_selector(
    state: Any,
    trajectories: Any,
    subsample_scores: Any,
    candidate_idx: int,
    candidate: Dict[str, Any]
) -> str:
    """
    Selector that only optimizes the aggregator component.

    Use this when you want to improve result synthesis.

    Args:
        state: GEPA optimization state
        trajectories: Optimization trajectories
        subsample_scores: Scores for current subsample
        candidate_idx: Index of current candidate
        candidate: Dict of component names -> prompts

    Returns:
        Component name to optimize
    """
    components = list(candidate.keys())
    if "aggregator" in components:
        return components[components.index('aggregator')]
    return components[0]


def round_robin_selector(
    state: Any,
    trajectories: Any,
    subsample_scores: Any,
    candidate_idx: int,
    candidate: Dict[str, Any]
) -> str:
    """
    Selector that cycles through all available components.

    Args mirror other selectors. Falls back to candidate index if state
    does not expose a usable counter.
    """
    components: List[str] = list(candidate.keys())
    if not components:
        raise ValueError("Candidate prompt dictionary is empty")

    # GEPA's state may expose `step` or `iteration`. Fall back to candidate_idx.
    if hasattr(state, "step"):
        idx = getattr(state, "step") % len(components)
    elif isinstance(state, dict) and "step" in state:
        idx = int(state["step"]) % len(components)
    elif hasattr(state, "iteration"):
        idx = getattr(state, "iteration") % len(components)
    else:
        idx = candidate_idx % len(components)

    return components[idx]




# Map string names to selector functions for CLI
SELECTORS = {
    "planner_only": planner_only_selector,
    "atomizer_only": atomizer_only_selector,
    "executor_only": executor_only_selector,
    "aggregator_only": aggregator_only_selector,
    "round_robin": round_robin_selector,
}
