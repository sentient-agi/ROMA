#!/usr/bin/env python3
"""Main script for running prompt optimization."""

import asyncio
import argparse
import logging
from pathlib import Path

from roma_dspy.utils import log_async_execution
from roma_dspy.utils.async_executor import AsyncParallelExecutor

from .config import get_default_config, OptimizationConfig
from .dataset_loaders import load_aimo_datasets
from .solver_setup import create_solver_module
from .judge import ComponentJudge
from .metrics import MetricWithFeedback, SearchMetric
from .prompts.grader_prompts import SEARCH_GRADER_PROMPT, COMPONENT_GRADER_PROMPT
from .optimizer import create_optimizer

logger = logging.getLogger(__name__)


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Run ROMA-DSPy prompt optimization with GEPA",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )

    # Dataset arguments
    parser.add_argument("--train-size", type=int, default=5,
                        help="Number of training examples")
    parser.add_argument("--val-size", type=int, default=5,
                        help="Number of validation examples")
    parser.add_argument("--test-size", type=int, default=15,
                        help="Number of test examples")

    # Execution arguments
    parser.add_argument("--max-parallel", type=int, default=12,
                        help="Maximum parallel executions")
    parser.add_argument("--concurrency", type=int, default=12,
                        help="Concurrency limit for solver")

    # Optimization arguments
    parser.add_argument("--max-metric-calls", type=int, default=10,
                        help="Maximum GEPA metric calls")
    parser.add_argument("--num-threads", type=int, default=4,
                        help="Number of GEPA threads")
    parser.add_argument("--selector",
                        choices=["planner_only", "atomizer_only", "executor_only",
                                "aggregator_only", "round_robin"],
                        default="planner_only",
                        help="Component selector strategy")

    # Output arguments
    parser.add_argument("--output", type=str,
                        help="Output path for optimized program")
    parser.add_argument("--verbose", action="store_true",
                        help="Enable verbose logging")
    parser.add_argument("--skip-eval", action="store_true",
                        help="Skip test set evaluation")

    return parser.parse_args()


async def evaluate_async(module, examples, max_parallel=12):
    """
    Evaluate module on examples using async executor.

    Args:
        module: RecursiveSolverModule to evaluate
        examples: List of dspy.Example instances
        max_parallel: Maximum parallel executions

    Returns:
        List of predictions
    """
    executor = AsyncParallelExecutor(max_concurrency=max_parallel)
    return await executor.execute_batch(module, examples, show_progress=True)


def main():
    """Main optimization pipeline."""
    args = parse_args()

    # Setup logging
    log_async_execution(verbose=args.verbose)

    # Load configuration
    config = get_default_config()
    config.train_size = args.train_size
    config.val_size = args.val_size
    config.test_size = args.test_size
    config.max_parallel = args.max_parallel
    config.concurrency = args.concurrency
    config.max_metric_calls = args.max_metric_calls
    config.num_threads = args.num_threads
    config.output_path = args.output

    logger.info("=" * 60)
    logger.info("ROMA-DSPy Prompt Optimization")
    logger.info("=" * 60)

    # Load datasets
    logger.info(f"Loading datasets (train={config.train_size}, val={config.val_size}, test={config.test_size})...")
    train_set, val_set, test_set = load_aimo_datasets(
        train_size=config.train_size,
        val_size=config.val_size,
        test_size=config.test_size,
        seed=config.dataset_seed
    )
    logger.info(f"✓ Loaded {len(train_set)} train, {len(val_set)} val, {len(test_set)} test examples")

    # Create solver module
    logger.info("Creating solver module...")
    solver_module = create_solver_module(config)
    logger.info("✓ Solver module created")

    # Create judge and metric (following notebook pattern)
    logger.info("Initializing LLM judge and metric...")
    judge = ComponentJudge(lm_config=config.judge_lm, prompt=COMPONENT_GRADER_PROMPT)
    search_metric = SearchMetric(lm_config=config.judge_lm, prompt=SEARCH_GRADER_PROMPT)
    metric = MetricWithFeedback(judge=judge, scoring_metric=search_metric)
    logger.info("✓ Judge and metric initialized")

    # Create optimizer
    logger.info(f"Creating GEPA optimizer (selector={args.selector})...")
    optimizer = create_optimizer(config, metric, component_selector=args.selector)
    logger.info("✓ Optimizer created")

    # Run optimization
    logger.info("=" * 60)
    logger.info("Starting optimization...")
    logger.info("=" * 60)
    optimized_program = optimizer.compile(
        solver_module,
        trainset=train_set,
        valset=val_set,
    )
    logger.info("✓ Optimization complete!")

    # Save optimized program if requested
    if config.output_path:
        logger.info(f"Saving optimized program to {config.output_path}...")
        optimized_program.save(config.output_path)
        logger.info("✓ Saved optimized program")

    # Evaluate on test set
    if not args.skip_eval:
        logger.info("=" * 60)
        logger.info("Evaluating on test set...")
        logger.info("=" * 60)

        test_results = asyncio.run(
            evaluate_async(optimized_program, test_set, max_parallel=config.max_parallel)
        )

        # Calculate metrics using search_metric (scoring only, no feedback needed for test)
        scores = []
        for ex, pred in zip(test_set, test_results):
            score = search_metric.forward(ex, pred)
            scores.append(score)
        accuracy = sum(scores) / len(scores) if scores else 0

        logger.info("=" * 60)
        logger.info(f"Test Accuracy: {accuracy:.2%} ({sum(scores)}/{len(scores)})")
        logger.info("=" * 60)

    logger.info("✓ Done!")


if __name__ == "__main__":
    main()
