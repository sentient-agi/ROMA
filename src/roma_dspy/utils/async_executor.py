"""Async-aware executor for parallel DSPy module execution."""

import asyncio
import logging
from typing import List, Any, Callable, Optional
from concurrent.futures import ThreadPoolExecutor
import dspy

logger = logging.getLogger(__name__)


class AsyncParallelExecutor:
    """
    Async-aware executor for running DSPy modules in parallel.

    Replaces thread-based parallelism with asyncio.gather() + Semaphore.
    All tasks run on a single event loop, avoiding "different loop" errors.

    Example:
        executor = AsyncParallelExecutor(max_concurrency=10)

        # Async usage
        results = await executor.execute_batch(module, examples)

        # Sync wrapper
        results = executor.run_sync(module, examples)
    """

    def __init__(self, max_concurrency: int = 10):
        """
        Initialize executor with concurrency limit.

        Args:
            max_concurrency: Max number of concurrent async tasks
        """
        self._max_concurrency = max_concurrency
        # Create a dedicated ThreadPoolExecutor to prevent accumulation
        # Only used for sync fallback when aforward() is not available
        self._executor = ThreadPoolExecutor(max_workers=max_concurrency)

    async def _run_with_semaphore(
        self,
        sem: asyncio.Semaphore,
        module: dspy.Module,
        example: dspy.Example,
    ) -> dspy.Prediction:
        """Run single module call under semaphore."""
        async with sem:
            # Extract input from example - try common fields
            if hasattr(example, "goal"):
                input_text = example.goal
            elif hasattr(example, "question"):
                input_text = example.question
            elif hasattr(example, "input"):
                input_text = example.input
            else:
                # Fallback: use first field that's a string
                for field_name in example.__dict__:
                    if field_name not in ("answer", "output", "label"):
                        value = getattr(example, field_name)
                        if isinstance(value, str):
                            input_text = value
                            break
                else:
                    raise ValueError(
                        f"Could not find input field in example: {example.__dict__.keys()}"
                    )

            # Prefer aforward if available, fallback to sync
            if hasattr(module, "aforward"):
                return await module.aforward(input_text)
            else:
                # Fallback to sync (wrap in executor to avoid blocking)
                loop = asyncio.get_running_loop()
                return await loop.run_in_executor(
                    self._executor,  # Use dedicated executor
                    lambda: module.forward(input_text),
                )

    async def execute_batch(
        self,
        module: dspy.Module,
        examples: List[dspy.Example],
        show_progress: bool = False,
    ) -> List[Any]:
        """
        Execute batch of examples with concurrency control.

        Args:
            module: DSPy module with aforward() or forward()
            examples: List of dspy.Example instances
            show_progress: Log progress updates

        Returns:
            List of predictions (or exceptions if return_exceptions=True)
        """
        sem = asyncio.Semaphore(self._max_concurrency)

        if show_progress:
            logger.info(
                f"🔄 [EXECUTOR] Starting batch | Examples: {len(examples)} | Max concurrent: {self._max_concurrency}"
            )

        tasks = [self._run_with_semaphore(sem, module, ex) for ex in examples]

        # return_exceptions=True isolates failures
        results = await asyncio.gather(*tasks, return_exceptions=True)

        if show_progress:
            successes = sum(1 for r in results if not isinstance(r, Exception))
            failures = len(results) - successes
            logger.info(
                f"✅ [EXECUTOR] Completed | Success: {successes} | Failed: {failures}"
            )

        return results

    def run_sync(
        self,
        module: dspy.Module,
        examples: List[dspy.Example],
        show_progress: bool = False,
    ) -> List[Any]:
        """
        Sync wrapper - creates single event loop for all tasks.

        Args:
            module: DSPy module
            examples: List of examples
            show_progress: Log progress updates

        Returns:
            List of predictions
        """
        return asyncio.run(
            self.execute_batch(module, examples, show_progress=show_progress)
        )

    async def map_async(
        self,
        module: dspy.Module,
        inputs: List[str],
        show_progress: bool = False,
    ) -> List[Any]:
        """
        Map async execution over a list of input strings.

        Args:
            module: DSPy module with aforward()
            inputs: List of input strings
            show_progress: Log progress updates

        Returns:
            List of predictions
        """
        sem = asyncio.Semaphore(self._max_concurrency)

        if show_progress:
            logger.info(
                f"🔄 [EXECUTOR] Mapping {len(inputs)} inputs | Max concurrent: {self._max_concurrency}"
            )

        async def run_one(input_str: str):
            async with sem:
                if hasattr(module, "aforward"):
                    return await module.aforward(input_str)
                else:
                    loop = asyncio.get_running_loop()
                    return await loop.run_in_executor(
                        self._executor,  # Use dedicated executor
                        lambda: module.forward(input_str),
                    )

        results = await asyncio.gather(
            *[run_one(inp) for inp in inputs], return_exceptions=True
        )

        if show_progress:
            successes = sum(1 for r in results if not isinstance(r, Exception))
            failures = len(results) - successes
            logger.info(
                f"✅ [EXECUTOR] Completed | Success: {successes} | Failed: {failures}"
            )

        return results

    def map_sync(
        self,
        module: dspy.Module,
        inputs: List[str],
        show_progress: bool = False,
    ) -> List[Any]:
        """
        Sync wrapper for map_async.

        Args:
            module: DSPy module
            inputs: List of input strings
            show_progress: Log progress updates

        Returns:
            List of predictions
        """
        return asyncio.run(self.map_async(module, inputs, show_progress=show_progress))

    def __del__(self):
        """Cleanup executor on deletion."""
        try:
            self._executor.shutdown(wait=False)
        except Exception:
            pass  # Best effort cleanup
