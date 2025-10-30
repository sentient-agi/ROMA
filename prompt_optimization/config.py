"""Configuration management for prompt optimization."""

from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from omegaconf import OmegaConf, DictConfig

from roma_dspy.config.schemas.root import ROMAConfig

from prompt_optimization.prompts import AGGREGATOR_PROMPT, ATOMIZER_PROMPT, PLANNER_PROMPT


@dataclass
class LMConfig:
    """Language model configuration."""
    model: str
    temperature: float = 0.6
    max_tokens: int = 120000
    timeout: int = 120  # Timeout in seconds (default 2 minutes)
    cache: bool = False


@dataclass
class OptimizationConfig:
    """Complete configuration for optimization pipeline."""

    # LM configs
    executor_lm: LMConfig = field(default_factory=lambda: LMConfig("fireworks_ai/accounts/fireworks/models/gpt-oss-120b"))
    atomizer_lm: LMConfig = field(default_factory=lambda: LMConfig("gemini/gemini-2.5-flash"))
    planner_lm: LMConfig = field(default_factory=lambda: LMConfig("gemini/gemini-2.5-flash"))
    aggregator_lm: LMConfig = field(default_factory=lambda: LMConfig("fireworks_ai/accounts/fireworks/models/gpt-oss-120b"))
    judge_lm: LMConfig = field(default_factory=lambda: LMConfig("openrouter/anthropic/claude-sonnet-4.5", temperature=1.0, max_tokens=64000))
    reflection_lm: LMConfig = field(default_factory=lambda: LMConfig("openrouter/anthropic/claude-sonnet-4.5", temperature=1.0, max_tokens=64000))

    # Dataset configs
    train_size: int = 32
    val_size: int = 8
    test_size: int = 8
    dataset_seed: int = 0

    # Execution configs
    max_parallel: int = 4
    concurrency: int = 4

    # GEPA configs
    max_metric_calls: int = 10
    num_threads: int = 4
    reflection_minibatch_size: int = 8
    component_selector: str = "round_robin"

    # GEPA observability
    track_stats: bool = True
    track_best_outputs: bool = True
    log_dir: Optional[str] = "logs/gepa_experiments"
    use_mlflow: bool = True

    # W&B observability (Weights & Biases)
    use_wandb: bool = False
    wandb_project: Optional[str] = "roma-optimization"
    wandb_entity: Optional[str] = None  # W&B team/username
    wandb_api_key: Optional[str] = None  # Set via env var WANDB_API_KEY if None
    wandb_tags: list[str] = field(default_factory=list)  # Tags for W&B runs
    wandb_notes: Optional[str] = None  # Optional notes for W&B run

    # Solver configs
    max_depth: int = 1
    enable_logging: bool = True

    # Output
    output_path: Optional[str] = None

    # Environment
    env_file: Optional[str] = "../../.env"  # Relative to experiment_cli dir or absolute path


def patch_romaconfig(
    opt_config: OptimizationConfig,
    base_config: ROMAConfig,
    mlflow_tracking_uri: Optional[str] = None
) -> ROMAConfig:
    """
    Merge prompt optimization overrides into a ROMAConfig.

    Args:
        opt_config: Optimization settings with LM overrides.
        base_config: Existing ROMA configuration to patch.
        mlflow_tracking_uri: Optional MLflow tracking URI for observability.

    Returns:
        Deep-copied ROMAConfig with optimization-specific overrides applied.
    """
    cfg = deepcopy(base_config)

    def _apply_agent_lm(agent_cfg, lm_cfg: LMConfig, instructions: Optional[str] = None) -> None:
        if agent_cfg is None:
            return
        agent_cfg.llm.model = lm_cfg.model
        agent_cfg.llm.temperature = lm_cfg.temperature
        agent_cfg.llm.max_tokens = lm_cfg.max_tokens
        agent_cfg.llm.timeout = lm_cfg.timeout
        agent_cfg.llm.cache = lm_cfg.cache
        if instructions is not None:
            agent_cfg.signature_instructions = instructions

    _apply_agent_lm(cfg.agents.atomizer, opt_config.atomizer_lm, ATOMIZER_PROMPT)
    _apply_agent_lm(cfg.agents.planner, opt_config.planner_lm, PLANNER_PROMPT)
    _apply_agent_lm(cfg.agents.executor, opt_config.executor_lm)
    _apply_agent_lm(cfg.agents.aggregator, opt_config.aggregator_lm, AGGREGATOR_PROMPT)

    cfg.runtime.max_depth = opt_config.max_depth
    cfg.runtime.enable_logging = opt_config.enable_logging

    # Enable MLflow observability if tracking URI is provided
    if opt_config.use_mlflow and mlflow_tracking_uri:
        cfg.observability.mlflow.enabled = True
        cfg.observability.mlflow.tracking_uri = mlflow_tracking_uri
        cfg.observability.mlflow.log_traces = True
        # Note: Don't enable log_compiles/log_evals - those are for GEPA's autolog

    return cfg


def get_default_config() -> OptimizationConfig:
    """Returns default optimization configuration."""
    return OptimizationConfig()


def load_config_from_yaml(path: str) -> OptimizationConfig:
    """
    Load optimization configuration from YAML file using OmegaConf.

    Args:
        path: Path to YAML configuration file

    Returns:
        OptimizationConfig instance
    """
    # Load YAML with OmegaConf
    cfg = OmegaConf.load(path)

    # Convert to structured config
    structured = OmegaConf.structured(OptimizationConfig)

    # Merge loaded config with structured defaults
    merged = OmegaConf.merge(structured, cfg)

    # Convert to dataclass instance
    return OmegaConf.to_object(merged)


def save_config_to_yaml(config: OptimizationConfig, path: str) -> None:
    """
    Save optimization configuration to YAML file using OmegaConf.

    Args:
        config: OptimizationConfig instance
        path: Path to save YAML file
    """
    Path(path).parent.mkdir(parents=True, exist_ok=True)

    # Convert to OmegaConf DictConfig
    cfg = OmegaConf.structured(config)

    # Save to YAML
    OmegaConf.save(cfg, path)
