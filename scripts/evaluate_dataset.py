#!/usr/bin/env python3
"""
Parallel dataset evaluation script for ROMA-DSPy.

Evaluates a dataset using RecursiveSolver with parallel execution,
tracking results and MLflow experiments.
"""

import argparse
import asyncio
import os
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Tuple
import sys

import pandas as pd
import mlflow
from loguru import logger
from tqdm.asyncio import tqdm

# Add project root to path
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from roma_dspy.config.manager import ConfigManager
from roma_dspy.core.engine.solve import RecursiveSolver
from roma_dspy.types import TaskStatus
from prompt_optimization.dataset_loaders import (
    load_aimo_datasets,
    load_frames_dataset,
    load_seal0_dataset,
    load_simpleqa_verified_dataset,
    load_abgen_dataset,
)


# Dataset loader mapping
DATASET_LOADERS = {
    "aimo": load_aimo_datasets,
    "frames": load_frames_dataset,
    "seal0": load_seal0_dataset,
    "simpleqa_verified": load_simpleqa_verified_dataset,
    "abgen": load_abgen_dataset,
}


async def solve_example(
    example: Any,
    config: Any,
    max_depth: int,
    semaphore: asyncio.Semaphore,
    index: int,
    total: int
) -> Dict[str, Any]:
    """
    Solve a single example with a new solver instance.

    Args:
        example: Dataset example with 'goal' field
        config: ROMA config object
        max_depth: Maximum recursion depth
        semaphore: Asyncio semaphore for concurrency control
        index: Current example index (for logging)
        total: Total number of examples

    Returns:
        Dictionary with evaluation results
    """
    async with semaphore:
        logger.info(f"[{index + 1}/{total}] Starting: {example.goal[:100]}...")

        # Create new solver instance for this execution
        solver = RecursiveSolver(config=config, max_depth=max_depth)

        try:
            # Solve the task
            result = await solver.async_solve(example.goal)

            # Extract metrics
            node_metrics = result.get_node_metrics()

            # Build result dictionary
            result_data = {
                "index": index,
                "execution_id": result.execution_id,
                "goal": example.goal,
                "predicted_answer": result.result,
                "ground_truth": getattr(example, "answer", None),
                "status": result.status.value,
                "depth_reached": result.depth,
                "duration_seconds": result.execution_duration if result.execution_duration else 0.0,
                "error": result.error,
                "input_tokens": node_metrics.prompt_tokens,
                "output_tokens": node_metrics.completion_tokens,
                "total_tokens": node_metrics.total_tokens,
                "cost_usd": node_metrics.cost,
            }

            duration_display = (
                f"{result.execution_duration:.2f}s"
                if result.execution_duration is not None
                else "unknown"
            )
            logger.info(
                f"[{index + 1}/{total}] Completed: {result.status.value} "
                f"(depth={result.depth}, duration={duration_display})"
            )

            return result_data

        except Exception as e:
            logger.error(f"[{index + 1}/{total}] Error: {str(e)}")
            return {
                "index": index,
                "execution_id": None,
                "goal": example.goal,
                "predicted_answer": None,
                "ground_truth": getattr(example, "answer", None),
                "status": "ERROR",
                "depth_reached": 0,
                "duration_seconds": 0.0,
                "error": str(e),
                "input_tokens": 0,
                "output_tokens": 0,
                "total_tokens": 0,
                "cost_usd": 0.0,
            }


def get_mlflow_run_info(execution_id: str, tracking_uri: str) -> Tuple[str, str]:
    """
    Get MLflow run ID and URL for a given execution ID.

    Args:
        execution_id: Execution ID to search for
        tracking_uri: MLflow tracking URI

    Returns:
        Tuple of (run_id, run_url)
    """
    try:
        client = mlflow.tracking.MlflowClient(tracking_uri=tracking_uri)
        runs = client.search_runs(
            experiment_ids=client.search_experiments(),
            filter_string=f"tags.execution_id = '{execution_id}'"
        )

        if runs:
            run = runs[0]
            run_id = run.info.run_id
            experiment_id = run.info.experiment_id
            run_url = f"{tracking_uri}/#/experiments/{experiment_id}/runs/{run_id}"
            return run_id, run_url
        else:
            return "N/A", "N/A"

    except Exception as e:
        logger.warning(f"Could not fetch MLflow info for {execution_id}: {e}")
        return "N/A", "N/A"


async def evaluate_dataset(
    dataset_name: str,
    split: str,
    size: int | None,
    num_threads: int,
    profile: str,
    max_depth: int,
    output_path: str,
    seed: int = 0,
    no_split: bool = False,
    skip_mlflow_info: bool = False
) -> pd.DataFrame:
    """
    Evaluate a dataset with parallel execution and incremental result saving.

    Args:
        dataset_name: Name of dataset loader
        split: Dataset split (train/val/test), ignored if no_split=True
        size: Number of examples to evaluate. If None, evaluates entire dataset/split.
              If specified with no_split=True, loads full dataset then takes first 'size' examples.
              If specified with no_split=False, loads only 'size' examples from the split.
        num_threads: Maximum concurrent executions
        profile: Config profile name
        max_depth: Maximum solver depth
        output_path: Path to save CSV results (saved incrementally as examples complete)
        seed: Random seed for dataset loading
        no_split: If True, loads entire dataset without splitting (size then controls how many to evaluate)
        skip_mlflow_info: Ignored. MLflow run URLs are always skipped for incremental saves.

    Returns:
        DataFrame with evaluation results
    """
    # Load configuration
    logger.info(f"Loading config profile: {profile}")
    config = ConfigManager().load_config(profile=profile)

    # Configure MLflow
    config.observability.mlflow.enabled = not skip_mlflow_info
    if not skip_mlflow_info:
        config.observability.mlflow.tracking_uri = os.getenv(
            "MLFLOW_TRACKING_URI", "http://127.0.0.1:5000"
        )
        config.observability.mlflow.experiment_name = os.getenv(
            "MLFLOW_EXPERIMENT", "ROMA-Dataset-Evaluation"
        )
        config.observability.mlflow.log_traces = True
        config.observability.mlflow.log_compiles = True
        config.observability.mlflow.log_evals = True
    else:
        logger.info("MLflow disabled (set skip-mlflow-info=False to enable)")
        
    # Disable Postgres if not needed
    config.storage.postgres.enabled = False

    tracking_uri = config.observability.mlflow.tracking_uri

    # Load dataset
    logger.info(f"Loading dataset: {dataset_name}")
    if dataset_name not in DATASET_LOADERS:
        raise ValueError(
            f"Unknown dataset: {dataset_name}. "
            f"Available: {list(DATASET_LOADERS.keys())}"
        )

    loader = DATASET_LOADERS[dataset_name]

    if no_split:
        # Load entire dataset without splitting
        dataset = loader(seed=seed, no_split=True)
        logger.info(f"Loaded {len(dataset)} examples from full dataset (no split)")
        # Apply size limit if specified
        if size is not None and size < len(dataset):
            dataset = dataset[:size]
            logger.info(f"Limited to {size} examples")
    else:
        # Load with splits
        if size is None:
            # Load entire split
            train_set, val_set, test_set = loader(seed=seed, no_split=False)
            dataset = {"train": train_set, "val": val_set, "test": test_set}[split]
            logger.info(f"Loaded {len(dataset)} examples from {split} split (entire split)")
        else:
            # Load split with specific size
            train_set, val_set, test_set = loader(
                train_size=size if split == "train" else 1,
                val_size=size if split == "val" else 1,
                test_size=size if split == "test" else 1,
                seed=seed
            )
            dataset = {"train": train_set, "val": val_set, "test": test_set}[split]
            logger.info(f"Loaded {len(dataset)} examples from {split} split")

    # Create semaphore for concurrency control
    semaphore = asyncio.Semaphore(num_threads)

    # Run parallel evaluation with incremental saving
    logger.info(f"Starting evaluation with {num_threads} concurrent threads")
    logger.info("Results will be saved incrementally as they complete")

    # Prepare output path
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    tasks = [
        solve_example(example, config, max_depth, semaphore, i, len(dataset))
        for i, example in enumerate(dataset)
    ]

    # Process results as they complete and save incrementally
    results = []
    with tqdm(total=len(tasks), desc="Evaluating examples") as pbar:
        for coro in asyncio.as_completed(tasks):
            result = await coro

            # Add MLflow placeholder fields (skipping fetch for incremental saves)
            result["mlflow_run_id"] = "N/A"
            result["mlflow_url"] = "N/A"

            # Convert to DataFrame and save immediately
            df_row = pd.DataFrame([result])

            # Write header only on first save, append afterwards
            if len(results) == 0:
                df_row.to_csv(output_path, mode='w', header=True, index=False)
                logger.info(f"Created results file: {output_path}")
            else:
                df_row.to_csv(output_path, mode='a', header=False, index=False)

            results.append(result)
            pbar.update(1)

    logger.info(f"All results saved to: {output_path}")

    # Read back the saved results for summary statistics
    df = pd.read_csv(output_path)

    # Print summary statistics
    print("\n" + "=" * 80)
    print("EVALUATION SUMMARY")
    print("=" * 80)
    if no_split:
        print(f"Dataset: {dataset_name} (full dataset, no split)")
    else:
        print(f"Dataset: {dataset_name} ({split} split)")
    print(f"Total examples: {len(df)}")
    print(f"Max depth: {max_depth}")
    print(f"Concurrency: {num_threads}")
    print()

    # Status breakdown
    print("Status breakdown:")
    status_counts = df["status"].value_counts()
    for status, count in status_counts.items():
        percentage = (count / len(df)) * 100
        print(f"  {status}: {count} ({percentage:.1f}%)")
    print()

    # Duration statistics
    successful = df[df["status"] == TaskStatus.COMPLETED.value]
    if len(successful) > 0:
        print("Duration statistics (successful runs):")
        print(f"  Mean: {successful['duration_seconds'].mean():.2f}s")
        print(f"  Median: {successful['duration_seconds'].median():.2f}s")
        print(f"  Min: {successful['duration_seconds'].min():.2f}s")
        print(f"  Max: {successful['duration_seconds'].max():.2f}s")
        print()

        # Token usage statistics
        print("Token usage (successful runs):")
        print(f"  Total input tokens: {successful['input_tokens'].sum():,}")
        print(f"  Total output tokens: {successful['output_tokens'].sum():,}")
        print(f"  Total tokens: {successful['total_tokens'].sum():,}")
        print(f"  Avg tokens per run: {successful['total_tokens'].mean():.0f}")
        print()

        # Cost statistics
        print("Cost statistics (successful runs):")
        print(f"  Total cost: ${successful['cost_usd'].sum():.4f}")
        print(f"  Avg cost per run: ${successful['cost_usd'].mean():.4f}")
        print()

    print("=" * 80)
    print(f"Results saved to: {output_path}")
    if config.observability.mlflow.enabled:
        print(f"MLflow tracking URI: {tracking_uri}")
    print("=" * 80 + "\n")

    return df


def main():
    """Main entry point for CLI."""
    parser = argparse.ArgumentParser(
        description="Evaluate datasets with ROMA-DSPy RecursiveSolver in parallel"
    )

    parser.add_argument(
        "--dataset",
        type=str,
        default="seal0",
        choices=list(DATASET_LOADERS.keys()),
        help="Dataset to evaluate (default: seal0)"
    )

    parser.add_argument(
        "--split",
        type=str,
        default="test",
        choices=["train", "val", "test"],
        help="Dataset split to use (default: test)"
    )

    parser.add_argument(
        "--size",
        type=int,
        default=None,
        help="Number of examples to evaluate. If not specified, evaluates entire dataset/split. "
             "With --no-split, loads full dataset then takes first N examples. "
             "Without --no-split, loads N examples from the specified split."
    )

    parser.add_argument(
        "--num-threads",
        type=int,
        default=4,
        help="Maximum concurrent executions (default: 4)"
    )

    parser.add_argument(
        "--profile",
        type=str,
        default="test",
        help="Config profile to use (default: test)"
    )

    parser.add_argument(
        "--max-depth",
        type=int,
        default=1,
        help="Maximum solver recursion depth (default: 1)"
    )

    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Output CSV path (default: results/evaluation_{timestamp}.csv)"
    )

    parser.add_argument(
        "--seed",
        type=int,
        default=0,
        help="Random seed for dataset loading (default: 0)"
    )

    parser.add_argument(
        "--no-split",
        action="store_true",
        help="Load entire dataset without splitting (ignores --split, but --size still controls how many to evaluate)"
    )

    parser.add_argument(
        "--skip-mlflow-info",
        action="store_true",
        help="Skip fetching MLflow run URLs (faster, avoids overhead and potential API failures)"
    )

    args = parser.parse_args()

    # Generate default output path if not provided
    if args.output is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        if args.no_split:
            args.output = f"results/evaluation_{args.dataset}_full_{timestamp}.csv"
        else:
            args.output = f"results/evaluation_{args.dataset}_{args.split}_{timestamp}.csv"

    # Run evaluation
    asyncio.run(evaluate_dataset(
        dataset_name=args.dataset,
        split=args.split,
        size=args.size,
        num_threads=args.num_threads,
        profile=args.profile,
        max_depth=args.max_depth,
        output_path=args.output,
        seed=args.seed,
        no_split=args.no_split,
        skip_mlflow_info=args.skip_mlflow_info
    ))


if __name__ == "__main__":
    main()
