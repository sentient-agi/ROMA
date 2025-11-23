"""Checkpoint management endpoints."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from loguru import logger

from roma_dspy.api.schemas import (
    CheckpointResponse,
    CheckpointListResponse,
    CheckpointRestoreRequest,
    ExecutionResponse,
)
from roma_dspy.api.helpers import checkpoint_to_response, execution_to_response
from roma_dspy.api.dependencies import (
    get_storage,
    verify_execution_exists,
    verify_checkpoint_exists,
)
from roma_dspy.core.storage.postgres_storage import PostgresStorage

router = APIRouter()


@router.get(
    "/executions/{execution_id}/checkpoints", response_model=CheckpointListResponse
)
async def list_checkpoints(
    execution_id: str = Depends(verify_execution_exists),
    storage: PostgresStorage = Depends(get_storage),
    limit: int = Query(50, ge=1, le=100),
) -> CheckpointListResponse:
    """
    List all checkpoints for an execution.

    Args:
        execution_id: Execution ID
        limit: Maximum number of checkpoints to return

    Returns:
        List of checkpoints ordered by creation time (newest first)
    """
    try:
        checkpoints = await storage.list_checkpoints(
            execution_id=execution_id, limit=limit
        )

        checkpoint_responses = [
            checkpoint_to_response(checkpoint) for checkpoint in checkpoints
        ]

        return CheckpointListResponse(
            checkpoints=checkpoint_responses, total=len(checkpoint_responses)
        )

    except Exception as e:
        logger.error(f"Failed to list checkpoints for {execution_id}: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to list checkpoints: {str(e)}"
        )


@router.get("/checkpoints/{checkpoint_id}", response_model=CheckpointResponse)
async def get_checkpoint(
    checkpoint_id: str = Depends(verify_checkpoint_exists),
    storage: PostgresStorage = Depends(get_storage),
) -> CheckpointResponse:
    """
    Get checkpoint details.

    Args:
        checkpoint_id: Checkpoint ID

    Returns:
        Checkpoint metadata
    """
    try:
        # Load checkpoint data
        checkpoint_data = await storage.load_checkpoint(checkpoint_id)

        if not checkpoint_data:
            raise HTTPException(
                status_code=404, detail=f"Checkpoint {checkpoint_id} not found"
            )

        # Get the checkpoint model for response
        checkpoints = await storage.list_checkpoints(
            execution_id=checkpoint_data.execution_id, limit=100
        )

        # Find matching checkpoint
        checkpoint = next(
            (cp for cp in checkpoints if cp.checkpoint_id == checkpoint_id), None
        )

        if not checkpoint:
            raise HTTPException(
                status_code=404, detail=f"Checkpoint {checkpoint_id} not found"
            )

        return checkpoint_to_response(checkpoint)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get checkpoint {checkpoint_id}: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to get checkpoint: {str(e)}"
        )


@router.post("/checkpoints/{checkpoint_id}/restore", response_model=ExecutionResponse)
async def restore_checkpoint(
    restore_request: CheckpointRestoreRequest,
    checkpoint_id: str = Depends(verify_checkpoint_exists),
    storage: PostgresStorage = Depends(get_storage),
) -> ExecutionResponse:
    """
    Restore execution from checkpoint.

    This creates a new execution with the state restored from the checkpoint.

    Args:
        checkpoint_id: Checkpoint ID to restore from
        restore_request: Restore options

    Returns:
        New execution with restored state
    """
    try:
        # Load checkpoint
        checkpoint_data = await storage.load_checkpoint(checkpoint_id)

        if not checkpoint_data:
            raise HTTPException(
                status_code=404, detail=f"Checkpoint {checkpoint_id} not found"
            )

        # For MVP: We'll create a note in the execution metadata about restoration
        # Full implementation would require RecursiveSolver integration
        # which is better done through the CLI

        raise HTTPException(
            status_code=501,
            detail="Checkpoint restoration is available via CLI. Use: roma-dspy checkpoint restore <checkpoint_id>",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to restore checkpoint {checkpoint_id}: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to restore checkpoint: {str(e)}"
        )


@router.delete("/checkpoints/{checkpoint_id}", status_code=204)
async def delete_checkpoint(
    checkpoint_id: str = Depends(verify_checkpoint_exists),
    storage: PostgresStorage = Depends(get_storage),
) -> None:
    """
    Delete a checkpoint.

    Args:
        checkpoint_id: Checkpoint ID to delete

    Returns:
        204 No Content on success
    """
    try:
        deleted = await storage.delete_checkpoint(checkpoint_id)

        if not deleted:
            raise HTTPException(
                status_code=404, detail=f"Checkpoint {checkpoint_id} not found"
            )

        logger.info(f"Deleted checkpoint {checkpoint_id}")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete checkpoint {checkpoint_id}: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to delete checkpoint: {str(e)}"
        )
