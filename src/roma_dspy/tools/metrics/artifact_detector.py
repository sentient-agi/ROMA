"""
Automatic artifact detection from tool outputs.

Secondary detection layer that scans tool return values for file paths
and registers them as artifacts. Works in conjunction with priority
registration from DataStorage (parquet files).

Detection strategy:
- Scans ANY tool return format (JSON, string, dict, list, etc.)
- Extracts all strings that look like absolute file paths
- Only registers files inside execution directory
- Deduplication: Skips files already registered (e.g., by DataStorage)
"""

import asyncio
import re
from datetime import datetime
from pathlib import Path
from typing import Any, List, Optional, Set

import pandas as pd
from loguru import logger

from roma_dspy.core.artifacts import ArtifactBuilder
from roma_dspy.core.context import ExecutionContext
from roma_dspy.types import ArtifactType


# Regex to detect absolute file paths in strings
# Matches: /path/to/file.ext or /path/to/file
PATH_PATTERN = re.compile(r'(/[a-zA-Z0-9_./\-]+)')


def extract_file_paths_from_result(result: Any, execution_dir: Path) -> List[str]:
    """
    Extract file paths from tool result (any format).

    Recursively scans the result for strings that look like file paths,
    validates they exist and are inside execution directory.

    Args:
        result: Tool return value (any type: str, dict, list, int, etc.)
        execution_dir: Execution directory path (only files here are registered)

    Returns:
        List of validated file paths inside execution directory
    """
    file_paths: Set[str] = set()  # Use set to deduplicate

    _extract_paths_recursive(result, execution_dir, file_paths)

    return list(file_paths)


def _extract_paths_recursive(
    data: Any,
    execution_dir: Path,
    file_paths: Set[str]
) -> None:
    """
    Recursively extract file paths from any data structure.

    Args:
        data: Data to scan (any type)
        execution_dir: Execution directory for validation
        file_paths: Set to accumulate found paths
    """
    # Handle strings - scan for path patterns
    if isinstance(data, str):
        _scan_string_for_paths(data, execution_dir, file_paths)

    # Handle dicts - recurse on all values
    elif isinstance(data, dict):
        for value in data.values():
            _extract_paths_recursive(value, execution_dir, file_paths)

    # Handle lists - recurse on all items
    elif isinstance(data, list):
        for item in data:
            _extract_paths_recursive(item, execution_dir, file_paths)

    # Handle tuples - recurse on all items
    elif isinstance(data, tuple):
        for item in data:
            _extract_paths_recursive(item, execution_dir, file_paths)

    # Ignore other types (int, float, bool, None, etc.)


def _scan_string_for_paths(
    text: str,
    execution_dir: Path,
    file_paths: Set[str]
) -> None:
    """
    Scan string for file path patterns.

    Args:
        text: String to scan
        execution_dir: Execution directory for validation
        file_paths: Set to accumulate found paths
    """
    # Find all potential paths in string
    matches = PATH_PATTERN.findall(text)

    for match in matches:
        if _is_valid_execution_file(match, execution_dir):
            file_paths.add(match)


def _is_valid_execution_file(path_str: str, execution_dir: Path) -> bool:
    """
    Check if string is a valid file path inside execution directory.

    Args:
        path_str: String to validate
        execution_dir: Execution directory path

    Returns:
        True if path exists as file inside execution directory
    """
    try:
        path = Path(path_str)

        # Must be absolute path
        if not path.is_absolute():
            return False

        # Must exist as a file
        if not path.exists() or not path.is_file():
            return False

        # Must be inside execution directory
        try:
            path.relative_to(execution_dir)
            return True
        except ValueError:
            # Path is outside execution directory
            return False

    except Exception:
        return False


async def _build_rich_description(
    path: Path,
    toolkit_class: str,
    tool_name: str,
    tool_kwargs: Optional[dict] = None
) -> str:
    """
    Build rich description for artifact with metadata and context.

    For Parquet files: Extracts row/column counts, column names, date ranges.
    For other files: Returns basic description with tool invocation.

    Args:
        path: Path to artifact file
        toolkit_class: Name of toolkit that created the artifact
        tool_name: Name of tool that created the artifact
        tool_kwargs: Optional tool arguments for context

    Returns:
        Rich description string with metadata and usage guidance
    """
    # Build tool signature with full argument names and values
    if tool_kwargs:
        formatted_args = ", ".join(f"{key}={repr(value)}" for key, value in tool_kwargs.items())
        tool_signature = f"{toolkit_class}.{tool_name}({formatted_args})"
    else:
        tool_signature = f"{toolkit_class}.{tool_name}()"

    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")

    # Try to extract Parquet metadata
    if path.suffix.lower() == ".parquet":
        try:
            # Read Parquet file metadata in thread pool to avoid blocking event loop
            df = await asyncio.to_thread(pd.read_parquet, path)

            row_count = len(df)
            col_count = len(df.columns)

            # Get column names (limit to first 15 for readability)
            columns = df.columns.tolist()
            if len(columns) > 15:
                column_preview = ", ".join(columns[:15]) + ", ..."
            else:
                column_preview = ", ".join(columns)

            # Try to detect date range from timestamp columns
            date_range_info = ""
            timestamp_cols = [col for col in df.columns if df[col].dtype in ['datetime64[ns]', 'datetime64[ns, UTC]']]
            if timestamp_cols:
                try:
                    col = timestamp_cols[0]
                    min_date = df[col].min()
                    max_date = df[col].max()
                    date_range_info = f"\nDate range ({col}): {min_date} to {max_date}"
                except Exception:
                    pass

            # Build rich description
            description = f"""{tool_signature}
Fetched: {timestamp}

Dataset: {row_count:,} rows × {col_count} columns
Columns: {column_preview}{date_range_info}

⚠️ Use this artifact directly instead of calling {tool_name}() again with the same parameters."""

            return description

        except Exception as e:
            logger.debug(f"Could not read Parquet metadata from {path}: {e}")
            # Fall through to basic description

    # Fallback for non-Parquet files or if Parquet reading failed
    description = f"""{tool_signature}
Fetched: {timestamp}

File type: {path.suffix or 'unknown'}

⚠️ Use this artifact directly instead of calling {tool_name}() again."""

    return description


async def auto_register_artifacts(
    file_paths: List[str],
    toolkit_class: str,
    tool_name: str,
    execution_id: Optional[str] = None,
    tool_kwargs: Optional[dict] = None
) -> int:
    """
    Automatically register detected file paths as artifacts.

    Deduplication: Skips files already registered (e.g., parquet files
    registered by DataStorage priority registration).

    Args:
        file_paths: List of file paths to register
        toolkit_class: Name of toolkit that created the files
        tool_name: Name of tool that created the files
        execution_id: Optional execution ID for context
        tool_kwargs: Optional tool arguments for rich description

    Returns:
        Number of artifacts successfully registered
    """
    if not file_paths:
        return 0

    # Get ExecutionContext
    try:
        ctx = ExecutionContext.get()
        if not ctx or not ctx.artifact_registry:
            logger.debug("No artifact registry available for auto-registration")
            return 0
    except Exception as e:
        logger.debug(f"Could not get ExecutionContext for auto-registration: {e}")
        return 0

    artifact_builder = ArtifactBuilder()
    registry = ctx.artifact_registry

    # Build all artifacts first (batch processing)
    artifacts_to_register = []
    skipped_count = 0
    failed_builds = []

    for file_path in file_paths:
        try:
            # Check if already registered (deduplication)
            existing = await registry.get_by_path(file_path)
            if existing:
                logger.debug(
                    f"File already registered, skipping: {file_path}",
                    existing_name=existing.name,
                    toolkit=toolkit_class,
                    tool=tool_name
                )
                skipped_count += 1
                continue

            path = Path(file_path)

            # Infer artifact type from extension
            artifact_type = ArtifactType.from_file_extension(path.suffix)

            # Generate name from filename
            name = path.stem or path.name

            # Build rich description with metadata preview (before building artifact)
            description = await _build_rich_description(
                path=path,
                toolkit_class=toolkit_class,
                tool_name=tool_name,
                tool_kwargs=tool_kwargs
            )

            # Build artifact with enriched metadata
            artifact = await artifact_builder.build(
                name=name,
                artifact_type=artifact_type,
                storage_path=str(path.resolve()),
                created_by_task=execution_id or ctx.execution_id,
                created_by_module=toolkit_class,
                description=description,
                derived_from=[],  # No lineage for auto-detected artifacts (yet)
            )

            artifacts_to_register.append(artifact)

        except Exception as e:
            logger.warning(
                f"Failed to build artifact for auto-registration: {file_path}",
                error=str(e),
                toolkit=toolkit_class,
                tool=tool_name
            )
            failed_builds.append(file_path)

    # Register all artifacts in batch (single lock acquisition)
    if artifacts_to_register:
        try:
            registered = await registry.register_batch(artifacts_to_register)

            # Log individual artifacts with rich descriptions
            for artifact in registered:
                logger.info(
                    f"Auto-registered artifact with rich metadata: {artifact.name}",
                    artifact_id=str(artifact.artifact_id),
                    artifact_type=artifact.artifact_type.value,
                    toolkit=toolkit_class,
                    tool=tool_name,
                    path=artifact.storage_path,
                    description=artifact.metadata.description,
                )

            # Summary log
            logger.info(
                f"Batch auto-registered {len(registered)} artifact(s)",
                toolkit=toolkit_class,
                tool=tool_name,
                execution_id=execution_id,
                skipped=skipped_count,
                failed=len(failed_builds),
            )

            return len(registered)

        except Exception as e:
            logger.error(
                f"Failed to batch register artifacts",
                error=str(e),
                toolkit=toolkit_class,
                tool=tool_name,
                artifact_count=len(artifacts_to_register)
            )
            return 0
    else:
        if skipped_count > 0:
            logger.debug(
                f"All {skipped_count} file(s) already registered, nothing to do",
                toolkit=toolkit_class,
                tool=tool_name
            )
        return 0
