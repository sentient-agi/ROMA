"""
Filesystem scanner for automatic artifact detection.

Scans execution directory for files created during execution and automatically
registers them as artifacts. Works as fallback detection layer after priority
registration and tool output detection.

Detection Strategy:
- Scan execution directory recursively
- Filter by mtime >= start_time (created during execution)
- Skip temp/hidden files (.tmp, __pycache__, .git, .DS_Store)
- Infer artifact type from file extension
- Deduplication via registry.get_by_path()
"""

from pathlib import Path
from typing import List, Set
from time import time

from loguru import logger

from roma_dspy.core.artifacts import ArtifactBuilder
from roma_dspy.core.context import ExecutionContext
from roma_dspy.types import ArtifactType


# File patterns to skip
SKIP_PATTERNS = {
    ".tmp",           # Temporary files
    ".git",           # Git directory
    ".DS_Store",      # macOS metadata
    "__pycache__",    # Python cache
    ".pyc",           # Python bytecode
    ".pyo",           # Python optimized bytecode
    ".swp",           # Vim swap files
    ".bak",           # Backup files
    "~",              # Backup suffix
}


def should_skip_file(file_path: Path) -> bool:
    """
    Check if file should be skipped based on patterns.

    Args:
        file_path: Path to check

    Returns:
        True if file should be skipped
    """
    # Skip hidden files (start with .)
    if file_path.name.startswith("."):
        return True

    # Skip __pycache__ directories and contents
    if "__pycache__" in file_path.parts:
        return True

    # Skip by extension/suffix
    for pattern in SKIP_PATTERNS:
        if file_path.name.endswith(pattern):
            return True
        if file_path.suffix == pattern:
            return True

    return False


def scan_execution_directory(
    execution_dir: Path,
    start_time: float
) -> List[Path]:
    """
    Scan execution directory for files created after start_time.

    Recursively scans directory and returns all files that:
    - Were created/modified after start_time
    - Are not in skip patterns (temp files, hidden files, etc.)

    Args:
        execution_dir: Execution directory to scan
        start_time: Timestamp (from time.time()) to filter files

    Returns:
        List of Path objects for files to register
    """
    found_files: List[Path] = []

    try:
        # Recursive scan
        for item in execution_dir.rglob("*"):
            # Only process files (not directories)
            if not item.is_file():
                continue

            # Skip temp/hidden files
            if should_skip_file(item):
                logger.debug(f"Skipping file: {item.name}")
                continue

            # Check mtime (modified time)
            try:
                mtime = item.stat().st_mtime
                if mtime >= start_time:
                    found_files.append(item)
                    logger.debug(
                        f"Found new file: {item.name}",
                        mtime=mtime,
                        start_time=start_time
                    )
            except OSError as e:
                # File might have been deleted during scan
                logger.debug(f"Could not stat file {item}: {e}")
                continue

    except Exception as e:
        # Don't break execution if scan fails
        logger.warning(
            f"Filesystem scan failed for {execution_dir}: {e}",
            exc_info=True
        )

    logger.info(
        f"Filesystem scan found {len(found_files)} new file(s)",
        execution_dir=str(execution_dir),
        count=len(found_files)
    )

    return found_files


async def auto_register_scanned_files(
    file_paths: List[str],
    execution_id: str
) -> int:
    """
    Automatically register scanned files as artifacts.

    Deduplication: Skips files already registered (by priority registration
    or tool output detection).

    Args:
        file_paths: List of file paths to register
        execution_id: Execution ID for context

    Returns:
        Number of artifacts successfully registered
    """
    if not file_paths:
        return 0

    # Get ExecutionContext
    try:
        ctx = ExecutionContext.get()
        if not ctx or not ctx.artifact_registry:
            logger.debug("No artifact registry available for filesystem scanner")
            return 0
    except Exception as e:
        logger.debug(f"Could not get ExecutionContext for filesystem scanner: {e}")
        return 0

    artifact_builder = ArtifactBuilder()
    registry = ctx.artifact_registry
    registered_count = 0

    for file_path_str in file_paths:
        try:
            # Check if already registered (deduplication)
            existing = await registry.get_by_path(file_path_str)
            if existing:
                logger.debug(
                    f"File already registered, skipping: {file_path_str}",
                    existing_name=existing.name,
                    detected_by="filesystem_scanner"
                )
                continue

            file_path = Path(file_path_str)

            # Infer artifact type from extension
            artifact_type = ArtifactType.from_file_extension(file_path.suffix)

            # Generate name from filename
            name = file_path.stem or file_path.name

            # Build artifact with scanner metadata
            artifact = await artifact_builder.build(
                name=name,
                artifact_type=artifact_type,
                storage_path=str(file_path.resolve()),
                created_by_task=execution_id or ctx.execution_id,
                created_by_module="filesystem_scanner",
                description=f"Auto-detected by filesystem scanner",
                derived_from=[],
            )

            # Register with registry
            await registry.register(artifact)
            registered_count += 1

            logger.debug(
                f"Filesystem scanner registered artifact: {name}",
                artifact_type=artifact_type.value,
                path=str(file_path)
            )

        except Exception as e:
            logger.warning(
                f"Failed to register scanned file: {file_path_str}",
                error=str(e)
            )

    if registered_count > 0:
        logger.info(
            f"Filesystem scanner registered {registered_count} artifact(s)",
            execution_id=execution_id
        )

    return registered_count
