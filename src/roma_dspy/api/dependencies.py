"""FastAPI dependency injection for ROMA-DSPy API."""

import os
from typing import Optional
from fastapi import Depends, HTTPException, Header
from roma_dspy.core.storage.postgres_storage import PostgresStorage
from roma_dspy.config.manager import ConfigManager


# ============================================================================
# Global State (will be injected via app.state in main.py)
# ============================================================================

_storage: Optional[PostgresStorage] = None
_config_manager: Optional[ConfigManager] = None


def init_dependencies(storage: PostgresStorage, config_manager: ConfigManager):
    """Initialize global dependencies (called from main.py on startup)."""
    global _storage, _config_manager
    _storage = storage
    _config_manager = config_manager


# ============================================================================
# Dependency Getters
# ============================================================================


async def get_storage() -> PostgresStorage:
    """Dependency to get PostgresStorage instance."""
    if _storage is None:
        raise HTTPException(
            status_code=503,
            detail="Storage not initialized. Server is starting up or misconfigured.",
        )
    return _storage


async def get_config_manager() -> ConfigManager:
    """Dependency to get ConfigManager instance."""
    if _config_manager is None:
        raise HTTPException(
            status_code=503,
            detail="ConfigManager not initialized. Server is starting up or misconfigured.",
        )
    return _config_manager


async def verify_execution_exists(
    execution_id: str, storage: PostgresStorage = Depends(get_storage)
) -> str:
    """
    Verify that an execution exists in storage.

    Args:
        execution_id: Execution ID to verify
        storage: PostgresStorage dependency

    Returns:
        Execution ID if it exists

    Raises:
        HTTPException: If execution doesn't exist
    """
    execution = await storage.get_execution(execution_id)
    if not execution:
        raise HTTPException(
            status_code=404, detail=f"Execution {execution_id} not found"
        )
    return execution_id


async def verify_checkpoint_exists(
    checkpoint_id: str, storage: PostgresStorage = Depends(get_storage)
) -> str:
    """
    Verify that a checkpoint exists in storage.

    Args:
        checkpoint_id: Checkpoint ID to verify
        storage: PostgresStorage dependency

    Returns:
        Checkpoint ID if it exists

    Raises:
        HTTPException: If checkpoint doesn't exist
    """
    checkpoint = await storage.get_checkpoint(checkpoint_id)
    if not checkpoint:
        raise HTTPException(
            status_code=404, detail=f"Checkpoint {checkpoint_id} not found"
        )
    return checkpoint_id


async def verify_api_key(
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
) -> Optional[str]:
    """
    Verify API key if authentication is enabled.

    Set REQUIRE_AUTH=true and API_KEY=your-key in environment to enable.

    Args:
        x_api_key: API key from X-API-Key header

    Returns:
        API key if valid

    Raises:
        HTTPException: If authentication is required but key is invalid
    """
    require_auth = os.getenv("REQUIRE_AUTH", "false").lower() == "true"

    if not require_auth:
        # Authentication is disabled
        return x_api_key

    # Authentication is enabled - verify key
    expected_key = os.getenv("API_KEY")

    if not expected_key:
        raise HTTPException(
            status_code=500,
            detail="Server misconfigured: REQUIRE_AUTH=true but API_KEY not set",
        )

    if not x_api_key:
        raise HTTPException(
            status_code=401,
            detail="Authentication required. Please provide X-API-Key header.",
        )

    if x_api_key != expected_key:
        raise HTTPException(status_code=403, detail="Invalid API key")

    return x_api_key


def validate_max_depth(max_depth: int) -> int:
    """
    Validate max_depth parameter.

    Args:
        max_depth: Maximum recursion depth

    Returns:
        Validated max_depth

    Raises:
        HTTPException: If max_depth is invalid
    """
    if max_depth < 0:
        raise HTTPException(status_code=400, detail="max_depth must be non-negative")
    if max_depth > 10:
        raise HTTPException(
            status_code=400,
            detail="max_depth cannot exceed 10 (to prevent infinite recursion)",
        )
    return max_depth


def validate_pagination(offset: int = 0, limit: int = 100) -> tuple[int, int]:
    """
    Validate pagination parameters.

    Args:
        offset: Number of records to skip
        limit: Maximum number of records to return

    Returns:
        Tuple of (offset, limit)

    Raises:
        HTTPException: If pagination params are invalid
    """
    if offset < 0:
        raise HTTPException(status_code=400, detail="offset must be non-negative")
    if limit < 1:
        raise HTTPException(status_code=400, detail="limit must be at least 1")
    if limit > 1000:
        raise HTTPException(status_code=400, detail="limit cannot exceed 1000")
    return offset, limit
