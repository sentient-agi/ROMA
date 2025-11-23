"""Lazy import utilities for optional dependencies.

This module provides utilities to check for optional dependencies and gracefully
handle their absence with helpful error messages promoting uv installation.
"""

import sys
from typing import Optional
import importlib.util


def is_available(module_name: str) -> bool:
    """
    Check if an optional module is available WITHOUT importing it.

    Uses importlib.util.find_spec() to check module availability without
    actually importing it, which prevents loading optional dependencies.

    Args:
        module_name: Name of the module to check (e.g., "sqlalchemy", "mlflow")

    Returns:
        True if module can be imported, False otherwise

    Example:
        >>> if is_available("mlflow"):
        ...     import mlflow
        ...     # Use MLflow
    """
    try:
        # Use find_spec to check availability WITHOUT importing
        spec = importlib.util.find_spec(module_name)
        return spec is not None
    except (ImportError, ModuleNotFoundError, ValueError):
        return False


def require_module(
    module_name: str,
    feature: str,
    install_extra: str,
    additional_info: Optional[str] = None,
) -> None:
    """
    Raise helpful ImportError if required module is not available.

    Provides clear installation instructions with uv-first approach.

    Args:
        module_name: Name of the required module
        feature: Human-readable feature name (e.g., "PostgreSQL persistence")
        install_extra: Extra name in pyproject.toml (e.g., "persistence")
        additional_info: Optional additional information to include in error message

    Raises:
        ImportError: If module is not available, with installation instructions

    Example:
        >>> require_module("mlflow", "MLflow tracking", "observability")
        ImportError: MLflow tracking requires mlflow.

        Install with uv (recommended):
          uv pip install roma-dspy[observability]

        Or with pip:
          pip install roma-dspy[observability]
    """
    if not is_available(module_name):
        error_msg = f"{feature} requires {module_name}.\n\n"
        error_msg += "Install with uv (recommended - 10-100x faster):\n"
        error_msg += f"  uv pip install roma-dspy[{install_extra}]\n\n"
        error_msg += "Or with pip:\n"
        error_msg += f"  pip install roma-dspy[{install_extra}]"

        if additional_info:
            error_msg += f"\n\n{additional_info}"

        raise ImportError(error_msg)


def lazy_import(module_name: str, package: Optional[str] = None):
    """
    Lazily import a module only when accessed.

    This allows optional dependencies to be imported without failing
    immediately if they're not installed.

    Args:
        module_name: Name of module to import
        package: Package name for relative imports

    Returns:
        Module if available, None otherwise

    Example:
        >>> mlflow = lazy_import("mlflow")
        >>> if mlflow:
        ...     mlflow.log_metric("test", 1.0)
    """
    try:
        return __import__(module_name, fromlist=[package] if package else [])
    except ImportError:
        return None


# Feature flags - check availability of optional dependencies
# These can be imported and checked throughout the codebase

# PostgreSQL persistence
HAS_POSTGRES = is_available("sqlalchemy")
HAS_ASYNCPG = is_available("asyncpg")
HAS_PERSISTENCE = HAS_POSTGRES and HAS_ASYNCPG

# MLflow observability
HAS_MLFLOW = is_available("mlflow")

# S3 storage
HAS_BOTO3 = is_available("boto3")
HAS_S3 = HAS_BOTO3

# E2B code execution
HAS_E2B = is_available("e2b")
HAS_E2B_CODE_INTERPRETER = is_available("e2b_code_interpreter")
HAS_CODE_EXECUTION = HAS_E2B and HAS_E2B_CODE_INTERPRETER

# API server
HAS_FASTAPI = is_available("fastapi")
HAS_UVICORN = is_available("uvicorn")
HAS_API_SERVER = HAS_FASTAPI and HAS_UVICORN

# TUI features
HAS_TEXTUAL = is_available("textual")
HAS_TUI = HAS_TEXTUAL

# W&B integration
HAS_WANDB = is_available("wandb")


def get_available_features() -> dict[str, bool]:
    """
    Get a dictionary of all optional features and their availability.

    Returns:
        Dictionary mapping feature names to availability status

    Example:
        >>> features = get_available_features()
        >>> if features["persistence"]:
        ...     print("PostgreSQL persistence available")
    """
    return {
        "persistence": HAS_PERSISTENCE,
        "observability": HAS_MLFLOW,
        "s3": HAS_S3,
        "code_execution": HAS_CODE_EXECUTION,
        "api_server": HAS_API_SERVER,
        "tui": HAS_TUI,
        "wandb": HAS_WANDB,
    }


def print_available_features() -> None:
    """
    Print a formatted list of available optional features.

    Useful for debugging and validation.
    """
    from rich.console import Console
    from rich.table import Table

    console = Console()
    table = Table(title="ROMA-DSPy Optional Features")
    table.add_column("Feature", style="cyan")
    table.add_column("Status", style="white")
    table.add_column("Install Command", style="yellow")

    features = {
        "PostgreSQL Persistence": ("persistence", HAS_PERSISTENCE),
        "MLflow Observability": ("observability", HAS_MLFLOW),
        "S3 Storage": ("s3", HAS_S3),
        "E2B Code Execution": ("e2b", HAS_CODE_EXECUTION),
        "REST API Server": ("api", HAS_API_SERVER),
        "TUI Features": ("tui", HAS_TUI),
        "W&B Integration": ("wandb", HAS_WANDB),
    }

    for feature_name, (extra_name, available) in features.items():
        if available:
            table.add_row(feature_name, "✓ Available", "")
        else:
            table.add_row(
                feature_name,
                "✗ Not installed",
                f"uv pip install roma-dspy[{extra_name}]",
            )

    console.print(table)


if __name__ == "__main__":
    # When run as script, print available features
    print_available_features()
