"""Demo loader for loading DSPy few-shot examples from Python modules.

This module provides utilities for loading dspy.Example demo lists from:
- Python module variables (e.g., "prompt_optimization.seed_prompts.executor_seed:EXECUTOR_DEMOS")

The loader supports caching for performance and graceful error handling.
"""

import importlib
from functools import lru_cache
from typing import List, Any
from pathlib import Path

from loguru import logger


class DemoLoader:
    """Loader for DSPy few-shot demo lists from Python modules.

    Supports loading demos from:
    - Python module variables: "module.path.to.file:VARIABLE_NAME"
      Example: "prompt_optimization.seed_prompts.executor_seed:EXECUTOR_DEMOS"

    The loader validates that the loaded variable is a list and caches results
    for performance.

    Example:
        ```python
        loader = DemoLoader()

        # Load from Python module
        demos = loader.load("prompt_optimization.seed_prompts.executor_seed:EXECUTOR_DEMOS")
        # Returns: List[dspy.Example]
        ```
    """

    def __init__(self, base_path: Path = Path.cwd()):
        """Initialize the DemoLoader.

        Args:
            base_path: Base directory for resolving relative paths (not currently used,
                      but kept for API consistency with InstructionLoader)
        """
        self.base_path = base_path

    @lru_cache(maxsize=128)
    def load(self, demos_path: str) -> List[Any]:
        """Load demos from a Python module variable.

        Args:
            demos_path: Path to demos in format "module.path:VARIABLE_NAME"
                       Example: "prompt_optimization.seed_prompts.executor_seed:EXECUTOR_DEMOS"

        Returns:
            List of dspy.Example objects (or empty list on error)

        Raises:
            ValueError: If format is invalid (not "module:variable" format)
            ImportError: If module cannot be imported
            AttributeError: If variable doesn't exist in module
            TypeError: If loaded variable is not a list
        """
        if not demos_path or not isinstance(demos_path, str):
            raise ValueError(
                f"demos_path must be a non-empty string, got: {demos_path}"
            )

        # Strip whitespace
        demos_path = demos_path.strip()

        # Must be Python module format
        if ":" not in demos_path:
            raise ValueError(
                f"Invalid demos path format: '{demos_path}'. "
                f"Expected format: 'module.path:VARIABLE_NAME'"
            )

        return self._load_python(demos_path)

    def _load_python(self, module_path: str) -> List[Any]:
        """Load demos from a Python module variable.

        Args:
            module_path: String like "module.path.to.file:VARIABLE_NAME"

        Returns:
            List of dspy.Example objects

        Raises:
            ValueError: If format is invalid
            ImportError: If module cannot be imported
            AttributeError: If variable doesn't exist
            TypeError: If variable is not a list
        """
        if ":" not in module_path:
            raise ValueError(
                f"Python module path must contain ':' separator: {module_path}"
            )

        module_name, var_name = module_path.split(":", 1)

        if not module_name or not var_name:
            raise ValueError(
                f"Invalid module path: '{module_path}'. "
                f"Both module and variable name must be non-empty."
            )

        try:
            # Import the module
            module = importlib.import_module(module_name)
            logger.debug(f"Successfully imported module: {module_name}")
        except ImportError as e:
            logger.error(f"Failed to import module '{module_name}': {e}")
            raise ImportError(f"Cannot import module '{module_name}': {e}") from e

        # Get the variable from the module
        if not hasattr(module, var_name):
            available_attrs = [attr for attr in dir(module) if not attr.startswith("_")]
            raise AttributeError(
                f"Module '{module_name}' has no attribute '{var_name}'. "
                f"Available attributes: {', '.join(available_attrs[:10])}"
            )

        demos = getattr(module, var_name)

        # Validate it's a list
        if not isinstance(demos, list):
            raise TypeError(
                f"Variable '{var_name}' in module '{module_name}' must be a list, "
                f"got {type(demos).__name__}"
            )

        logger.info(f"Loaded {len(demos)} demos from {module_name}:{var_name}")

        # Optionally validate that items are dspy.Example objects
        # (we can't import dspy here to avoid circular deps, so just log a warning)
        if demos and not hasattr(demos[0], "with_inputs"):
            logger.warning(
                f"Loaded demos from {module_path} may not be dspy.Example objects. "
                f"First item type: {type(demos[0]).__name__}"
            )

        return demos

    def clear_cache(self):
        """Clear the LRU cache.

        Useful for testing or when you need to reload demos after they've changed.
        """
        self.load.cache_clear()
        logger.debug("DemoLoader cache cleared")


def load_demos(demos_path: str) -> List[Any]:
    """Convenience function to load demos without instantiating DemoLoader.

    Args:
        demos_path: Path to demos in format "module.path:VARIABLE_NAME"

    Returns:
        List of dspy.Example objects (or empty list on error)

    Example:
        ```python
        from roma_dspy.core.utils.demo_loader import load_demos

        demos = load_demos("prompt_optimization.seed_prompts.executor_seed:EXECUTOR_DEMOS")
        ```
    """
    loader = DemoLoader()
    return loader.load(demos_path)
