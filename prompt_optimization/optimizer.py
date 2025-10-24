"""GEPA optimizer factory for prompt optimization."""

from typing import Optional

import dspy
from dspy import GEPA
from config import OptimizationConfig
from metrics import MetricWithFeedback
from component_selectors import SELECTORS


def create_optimizer(
    config: OptimizationConfig,
    metric: MetricWithFeedback,
    component_selector: Optional[str] = None
) -> GEPA:
    """
    Create configured GEPA optimizer with MLflow support.

    Args:
        config: Optimization configuration
        metric: Metric function (typically MetricWithFeedback)
        component_selector: Override selector from config (optional)

    Returns:
        Configured GEPA optimizer

    Example:
        >>> config = get_default_config()
        >>> judge = ComponentJudge(config.judge_lm)
        >>> metric = MetricWithFeedback(judge)
        >>> optimizer = create_optimizer(config, metric)
    """

    # Initialize reflection LM
    reflection_lm = dspy.LM(
        model=config.reflection_lm.model,
        temperature=config.reflection_lm.temperature,
        max_tokens=config.reflection_lm.max_tokens,
        cache=config.reflection_lm.cache
    )

    # Get selector function
    selector = component_selector or config.component_selector
    selector_fn = SELECTORS.get(selector, SELECTORS["round_robin"])

    # Create GEPA optimizer with observability features
    return GEPA(
        metric=metric,
        component_selector=selector_fn,
        max_metric_calls=config.max_metric_calls,
        num_threads=config.num_threads,
        track_stats=config.track_stats,
        track_best_outputs=config.track_best_outputs,
        log_dir=config.log_dir,
        use_mlflow=config.use_mlflow,
        reflection_minibatch_size=config.reflection_minibatch_size,
        reflection_lm=reflection_lm
    )
