#!/usr/bin/env python3
"""CLI for running GEPA optimization experiments with MLflow tracking."""

import argparse
import asyncio
import os
import sys
from datetime import datetime
from pathlib import Path

from loguru import logger

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from prompt_optimization.config import load_config_from_yaml, get_default_config, save_config_to_yaml
from prompt_optimization.dataset_loaders import (
    load_aimo_datasets,
    load_frames_dataset,
    load_simpleqa_dataset,
    load_simpleqa_verified_dataset,
    load_seal0_dataset,
)
from prompt_optimization.judge import ComponentJudge
from prompt_optimization.metrics import MetricWithFeedback, NumberMetric, SearchMetric
from prompt_optimization.optimizer import create_optimizer
from prompt_optimization.prompts.grader_prompts import SEARCH_GRADER_PROMPT
from prompt_optimization.solver_setup import create_solver_module

from roma_dspy.utils.async_executor import AsyncParallelExecutor
from roma_dspy.core.observability.mlflow_manager import MLflowManager
from roma_dspy.core.observability.span_manager import ROMASpanManager, set_span_manager
from roma_dspy.config.schemas.observability import MLflowConfig


DATASET_LOADERS = {
    "aimo": load_aimo_datasets,
    "frames": load_frames_dataset,
    "simpleqa": load_simpleqa_dataset,
    "simpleqa_verified": load_simpleqa_verified_dataset,
    "seal0": load_seal0_dataset,
}


def parse_args():
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description="Run GEPA optimization experiments",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )

    # Config file (primary way to configure)
    parser.add_argument(
        "--config", "-c",
        type=str,
        help="Path to YAML config file (loads all settings from file)"
    )

    # Quick overrides
    parser.add_argument("--name", help="Experiment name")
    parser.add_argument("--dataset", choices=list(DATASET_LOADERS.keys()), help="Dataset type")
    parser.add_argument("--profile", help="ROMA config profile (e.g., test, default)")
    parser.add_argument("--num-threads", type=int, help="GEPA num_threads")
    parser.add_argument("--selector", help="Component selector (e.g., round_robin)")

    # MLflow options
    parser.add_argument("--mlflow-uri", default="http://localhost:5000", help="MLflow tracking URI")
    parser.add_argument("--mlflow-experiment", default="roma-optimization", help="MLflow experiment name")
    parser.add_argument("--no-mlflow", action="store_true", help="Disable MLflow tracking")

    # Output
    parser.add_argument("--output-dir", help="Output directory")
    parser.add_argument("--save-config", help="Save effective config to this path")
    parser.add_argument("--verbose", action="store_true", help="Verbose logging")

    return parser.parse_args()


def setup_mlflow(args, config):
    """Setup MLflow using ROMA's MLflowManager (handles S3/MinIO automatically)."""
    if args.no_mlflow or not config.use_mlflow:
        return None

    try:
        # Create MLflow config using ROMA's schema
        # Note: Don't modify the tracking URI - it's already correct for the environment
        # (http://mlflow:5000 inside Docker, http://localhost:5000 for local)
        mlflow_config = MLflowConfig(
            enabled=True,
            tracking_uri=os.getenv('MLFLOW_TRACKING_URI', args.mlflow_uri),
            experiment_name=args.mlflow_experiment,
            log_traces=True,
            log_traces_from_compile=True,
            log_traces_from_eval=True,
            log_compiles=True,
            log_evals=True
        )

        # Initialize MLflow manager (automatically configures S3/MinIO)
        mlflow_manager = MLflowManager(mlflow_config)
        mlflow_manager.initialize()

        # Initialize ROMA span manager for agent wrapper spans
        # This creates the root ROMA agent spans in MLflow traces during optimization
        span_manager = ROMASpanManager(
            enabled=True,
            tracking_uri=mlflow_config.tracking_uri
        )
        set_span_manager(span_manager)
        logger.info(f"✓ ROMA span manager initialized: enabled={span_manager.enabled}, uri={span_manager._tracking_uri}")

        logger.info(f"✓ MLflow initialized via ROMA (S3/MinIO configured): {mlflow_config.tracking_uri}")
        return mlflow_manager
    except Exception as e:
        logger.error(f"MLflow setup failed: {e}")
        return None


async def evaluate_test(module, test_set, max_parallel):
    """Evaluate on test set."""
    executor = AsyncParallelExecutor(max_concurrency=max_parallel)
    return await executor.execute_batch(module, test_set, show_progress=True)


def main():
    args = parse_args()

    if args.verbose:
        logger.remove()
        logger.add(sys.stderr, level="DEBUG")

    # Resolve config path before changing directory
    config_path = None
    if args.config:
        config_path = (Path(__file__).parent / args.config).resolve()

    # Change to project root for config loading (ROMA profiles are there)
    project_root = Path(__file__).parent.parent.parent
    os.chdir(project_root)
    logger.debug(f"Changed to project root: {project_root}")

    # Load config from YAML or use defaults
    if config_path:
        logger.info(f"Loading config from {config_path}")
        config = load_config_from_yaml(str(config_path))
        logger.info("✓ Config loaded from YAML")
    else:
        logger.info("Using default config")
        config = get_default_config()

    # Load environment variables from .env file if specified in config
    if config.env_file:
        from dotenv import load_dotenv

        # Resolve relative path from script location
        env_path = Path(config.env_file)
        if not env_path.is_absolute():
            env_path = (Path(__file__).parent / env_path).resolve()

        if env_path.exists():
            load_dotenv(env_path)
            logger.info(f"✓ Loaded environment from {env_path}")
        else:
            logger.warning(f"Env file not found: {env_path}")

    # Apply CLI overrides
    if args.num_threads is not None:
        config.num_threads = args.num_threads
    if args.selector:
        config.component_selector = args.selector
    if args.output_dir:
        config.output_path = args.output_dir
    if args.no_mlflow:
        config.use_mlflow = False

    # Determine experiment name
    exp_name = args.name or f"experiment_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    # Determine dataset type (from args or infer from config)
    dataset_type = args.dataset or "aimo"  # Default to aimo

    # Determine ROMA profile
    profile = args.profile or "test"

    logger.info("=" * 80)
    logger.info(f"ROMA-DSPy Optimization: {exp_name}")
    logger.info("=" * 80)
    logger.info(f"Dataset: {dataset_type} (train={config.train_size}, val={config.val_size}, test={config.test_size})")
    logger.info(f"ROMA Profile: {profile}")
    logger.info(f"GEPA: threads={config.num_threads}, selector={config.component_selector}, max_calls={config.max_metric_calls}")
    logger.info(f"MLflow: {'enabled' if config.use_mlflow else 'disabled'}")
    logger.info("=" * 80)

    # Save effective config if requested
    if args.save_config:
        save_config_to_yaml(config, args.save_config)
        logger.info(f"✓ Saved effective config to {args.save_config}")

    # Setup MLflow using ROMA's manager (handles S3/MinIO automatically)
    mlflow_manager = setup_mlflow(args, config)

    # Start MLflow run manually BEFORE optimization
    # Per MLflow docs: autolog will use this run instead of creating a new one
    if mlflow_manager:
        import mlflow
        # Generate run name: optimization_<selector>_<profile>_<datetime>
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        run_name = f"optimization_{config.component_selector}_{profile}_{timestamp}"
        mlflow.start_run(run_name=run_name)

        # Log experiment metadata as parameters
        mlflow.log_params({
            "dataset": dataset_type,
            "profile": profile,
            "train_size": config.train_size,
            "val_size": config.val_size,
            "test_size": config.test_size,
            "num_threads": config.num_threads,
            "component_selector": config.component_selector,
            "max_metric_calls": config.max_metric_calls,
        })

        # Set tags for better organization
        mlflow.set_tags({
            "experiment_name": exp_name,
            "framework": "ROMA-DSPy",
            "optimizer": "GEPA",
        })

    try:
        # Load dataset
        logger.info("Loading dataset...")
        dataset_loader = DATASET_LOADERS[dataset_type]
        train, val, test = dataset_loader(
            train_size=config.train_size,
            val_size=config.val_size,
            test_size=config.test_size,
            seed=config.dataset_seed
        )
        logger.info(f"✓ Loaded {len(train)} train, {len(val)} val, {len(test)} test")

        # Create solver module (agents come from ROMA profile)
        logger.info("Creating solver...")
        # Pass MLflow tracking URI if enabled so solver config has observability enabled
        mlflow_uri = mlflow_manager._mlflow.get_tracking_uri() if mlflow_manager else None
        solver_module = create_solver_module(config, profile=profile, mlflow_tracking_uri=mlflow_uri)
        logger.info("✓ Solver created")

        # Create metric
        logger.info("Creating metric...")
        judge = ComponentJudge(lm_config=config.judge_lm)
        scoring_metric = SearchMetric(lm_config=config.judge_lm, prompt=SEARCH_GRADER_PROMPT)
        metric = MetricWithFeedback(judge=judge, scoring_metric=scoring_metric)
        logger.info("✓ Metric created")

        # Create GEPA optimizer (MLflow autolog tracks automatically)
        logger.info("Creating GEPA optimizer...")
        optimizer = create_optimizer(config, metric, run_name=run_name)
        logger.info("✓ Optimizer created")

        # Run optimization
        logger.info("=" * 80)
        logger.info("Starting GEPA optimization...")
        logger.info("Note: MLflow autolog tracks params, metrics, datasets, traces automatically")
        logger.info("=" * 80)

        start = datetime.now()
        optimized = optimizer.compile(solver_module, trainset=train, valset=val)
        duration = (datetime.now() - start).total_seconds()

        logger.info("=" * 80)
        logger.info(f"✓ Optimization complete ({duration:.1f}s)")
        logger.info("=" * 80)

        if mlflow_manager:
            mlflow.log_metrics({"optimization_time_seconds": duration})

        # Note: GEPA autolog automatically logs "metric progression over time" as step-wise metrics
        # No need to manually log detailed_results - autolog handles it!

        # Evaluate on test set
        logger.info("Evaluating on test set...")
        test_results = asyncio.run(evaluate_test(optimized, test, config.max_parallel))

        # Calculate accuracy (use NumberMetric for now as fallback)
        scores = []
        for _, pred in zip(test, test_results):
            if hasattr(pred, 'result_text') and pred.result_text:
                scores.append(1)
            else:
                scores.append(0)

        accuracy = sum(scores) / len(scores) if scores else 0

        logger.info("=" * 80)
        logger.info(f"Test Accuracy: {accuracy:.2%} ({sum(scores)}/{len(scores)})")
        logger.info("=" * 80)

        if mlflow_manager:
            mlflow.log_metrics({
                "test_accuracy": accuracy,
                "test_correct": float(sum(scores)),
                "test_total": float(len(scores)),
            })

        # Save optimized program
        output_dir = Path(config.output_path or "outputs") / exp_name
        output_dir.mkdir(parents=True, exist_ok=True)

        program_path = output_dir / "optimized_program.json"
        optimized.save(str(program_path))
        logger.info(f"✓ Saved to {program_path}")

        if mlflow_manager:
            mlflow.log_artifact(str(program_path))

    finally:
        # End MLflow run (must be in finally to ensure cleanup even on errors)
        if mlflow_manager:
            import mlflow
            mlflow.end_run()
            logger.info(f"✓ MLflow run ended: {exp_name}")

    logger.info("=" * 80)
    logger.info("✓ Experiment complete!")
    logger.info("=" * 80)


if __name__ == "__main__":
    main()
