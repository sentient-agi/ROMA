"""GEPA optimizer factory for prompt optimization."""

from typing import Optional

import dspy
from dspy import GEPA
from prompt_optimization.config import OptimizationConfig
from prompt_optimization.metrics import MetricWithFeedback
from prompt_optimization.component_selectors import SELECTORS


def create_optimizer(
    config: OptimizationConfig,
    metric: MetricWithFeedback,
    component_selector: Optional[str] = None,
    run_name: Optional[str] = None
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

    # Prepare W&B init kwargs if enabled
    wandb_init_kwargs = None
    if config.use_wandb:
        wandb_init_kwargs = {
            "project": config.wandb_project or "roma-optimization",
            "tags": config.wandb_tags or [],
        }
        if run_name:
            wandb_init_kwargs["name"] = run_name  # Use same run name format as MLflow
        if config.wandb_entity:
            wandb_init_kwargs["entity"] = config.wandb_entity
        if config.wandb_notes:
            wandb_init_kwargs["notes"] = config.wandb_notes

    # Create GEPA optimizer with observability features (MLflow + W&B)
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
        reflection_lm=reflection_lm,
        # W&B observability
        use_wandb=config.use_wandb,
        wandb_api_key=config.wandb_api_key,
        wandb_init_kwargs=wandb_init_kwargs,
    )
