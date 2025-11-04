"""Execution management endpoints."""

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from loguru import logger

from roma_dspy.api.schemas import (
    SolveRequest,
    ExecutionResponse,
    ExecutionDetailResponse,
    ExecutionListResponse,
    StatusPollingResponse,
    ExecutionDataResponse,
    ErrorResponse,
)
from roma_dspy.api.helpers import (
    execution_to_response,
    execution_to_detail_response,
    calculate_progress,
)
from roma_dspy.api.dependencies import (
    get_storage,
    verify_execution_exists,
    validate_pagination,
)
from roma_dspy.core.storage.postgres_storage import PostgresStorage
from roma_dspy.core.engine.dag import TaskDAG
from roma_dspy.types import TaskStatus

router = APIRouter()


@router.post("/executions", response_model=ExecutionResponse, status_code=202)
async def create_execution(
    request: Request,
    solve_request: SolveRequest
) -> ExecutionResponse:
    """
    Start a new task execution.

    Creates a background task that decomposes and executes the goal.

    Returns:
        ExecutionResponse with execution_id for polling status
    """
    app_state = request.app.state.app_state

    if not app_state.execution_service:
        raise HTTPException(
            status_code=503,
            detail="ExecutionService not available (storage may be disabled)"
        )

    try:
        # Start execution
        execution_id = await app_state.execution_service.start_execution(
            goal=solve_request.goal,
            max_depth=solve_request.max_depth,
            config_profile=solve_request.config_profile,
            config_overrides=solve_request.config_overrides,
            metadata=solve_request.metadata
        )

        # Get execution record
        storage = app_state.storage
        execution = await storage.get_execution(execution_id)

        if not execution:
            raise HTTPException(
                status_code=500,
                detail="Failed to create execution record"
            )

        return execution_to_response(execution)

    except Exception as e:
        logger.error(f"Failed to create execution: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create execution: {str(e)}"
        )


@router.get("/executions", response_model=ExecutionListResponse)
async def list_executions(
    storage: PostgresStorage = Depends(get_storage),
    status: Optional[str] = Query(None, description="Filter by status"),
    experiment_name: Optional[str] = Query(None, description="Filter by experiment name"),
    profile: Optional[str] = Query(None, description="Filter by profile"),
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000)
) -> ExecutionListResponse:
    """
    List all executions with optional filtering.

    Args:
        status: Optional status filter (running, completed, failed)
        experiment_name: Optional experiment name filter
        profile: Optional profile name filter
        offset: Number of records to skip
        limit: Maximum number of records to return

    Returns:
        List of executions with pagination info
    """
    # Validate pagination
    offset, limit = validate_pagination(offset, limit)

    try:
        # Get executions from storage
        executions = await storage.list_executions(
            status=status,
            experiment_name=experiment_name,
            profile=profile,
            offset=offset,
            limit=limit
        )

        # Get total count (without pagination)
        total = await storage.count_executions(status=status, experiment_name=experiment_name, profile=profile)

        # Convert to response schemas
        execution_responses = [
            execution_to_response(execution)
            for execution in executions
        ]

        return ExecutionListResponse(
            executions=execution_responses,
            total=total,
            offset=offset,
            limit=limit
        )

    except Exception as e:
        logger.error(f"Failed to list executions: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to list executions: {str(e)}"
        )


@router.get("/executions/{execution_id}", response_model=ExecutionDetailResponse)
async def get_execution(
    execution_id: str = Depends(verify_execution_exists),
    storage: PostgresStorage = Depends(get_storage)
) -> ExecutionDetailResponse:
    """
    Get detailed execution information including DAG visualization.

    Args:
        execution_id: Execution ID

    Returns:
        Detailed execution info with DAG snapshot
    """
    try:
        execution = await storage.get_execution(execution_id)

        if not execution:
            raise HTTPException(
                status_code=404,
                detail=f"Execution {execution_id} not found"
            )

        # Convert to detail response (includes DAG snapshot from checkpoints)
        return await execution_to_detail_response(execution, storage=storage)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get execution {execution_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get execution: {str(e)}"
        )


@router.get("/executions/{execution_id}/status", response_model=StatusPollingResponse)
async def get_execution_status(
    request: Request,
    execution_id: str = Depends(verify_execution_exists)
) -> StatusPollingResponse:
    """
    Get current execution status for polling.

    This endpoint is optimized for frequent polling with caching.

    Args:
        execution_id: Execution ID

    Returns:
        Current execution status with progress information
    """
    app_state = request.app.state.app_state

    if not app_state.execution_service:
        raise HTTPException(
            status_code=503,
            detail="ExecutionService not available"
        )

    try:
        # Get status (uses cache)
        status_data = await app_state.execution_service.get_execution_status(execution_id)

        if not status_data:
            raise HTTPException(
                status_code=404,
                detail=f"Execution {execution_id} not found"
            )

        # Get execution from storage for progress calculation
        storage = app_state.storage
        execution = await storage.get_execution(execution_id)

        if not execution:
            raise HTTPException(
                status_code=404,
                detail=f"Execution {execution_id} not found"
            )

        # Calculate progress
        progress = calculate_progress(execution)

        # Get current task from checkpoint DAG snapshot
        current_task_id = None
        current_task_goal = None

        dag_data = None
        # Read from checkpoint (primary and only source post-migration)
        try:
            checkpoint = await storage.get_latest_checkpoint(execution_id, valid_only=True)
            if checkpoint and checkpoint.root_dag:
                dag_data = checkpoint.root_dag
                # Convert DAGSnapshot model to dict if needed
                if hasattr(dag_data, 'model_dump'):
                    dag_data = dag_data.model_dump(mode="python")
        except Exception as e:
            logger.warning(f"Failed to load checkpoint for current task: {e}")

        if dag_data:
            try:
                dag = TaskDAG.from_dict(dag_data)
                in_progress_tasks = [
                    task for task in dag.get_all_tasks()
                    if task.status == TaskStatus.IN_PROGRESS
                ]
                if in_progress_tasks:
                    current_task = in_progress_tasks[0]
                    current_task_id = current_task.task_id
                    current_task_goal = current_task.goal
            except Exception as e:
                logger.warning(f"Failed to extract current task from DAG: {e}")

        return StatusPollingResponse(
            execution_id=execution_id,
            status=execution.status,
            progress=progress,
            current_task_id=current_task_id,
            current_task_goal=current_task_goal,
            completed_tasks=execution.completed_tasks,
            total_tasks=execution.total_tasks,
            estimated_remaining_seconds=None,  # Could be calculated with timing data
            last_updated=execution.updated_at
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get execution status {execution_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get execution status: {str(e)}"
        )


@router.post("/executions/{execution_id}/cancel", response_model=ExecutionResponse)
async def cancel_execution(
    request: Request,
    execution_id: str = Depends(verify_execution_exists)
) -> ExecutionResponse:
    """
    Cancel a running execution.

    Args:
        execution_id: Execution ID

    Returns:
        Updated execution with cancelled status
    """
    app_state = request.app.state.app_state

    if not app_state.execution_service:
        raise HTTPException(
            status_code=503,
            detail="ExecutionService not available"
        )

    try:
        # Cancel execution
        cancelled = await app_state.execution_service.cancel_execution(execution_id)

        if not cancelled:
            raise HTTPException(
                status_code=400,
                detail=f"Execution {execution_id} is not running (cannot cancel)"
            )

        # Get updated execution
        storage = app_state.storage
        execution = await storage.get_execution(execution_id)

        if not execution:
            raise HTTPException(
                status_code=404,
                detail=f"Execution {execution_id} not found"
            )

        return execution_to_response(execution)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to cancel execution {execution_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to cancel execution: {str(e)}"
        )


@router.get("/executions/{execution_id}/data", response_model=ExecutionDataResponse)
async def get_execution_data(
    request: Request,
    execution_id: str,
    storage: PostgresStorage = Depends(get_storage)
) -> ExecutionDataResponse:
    """
    Get consolidated execution data from MLflow traces.

    This endpoint fetches and consolidates MLflow trace data for real-time visualization.
    It uses ExecutionDataService to fetch traces and build task/agent execution structure.

    Use this for:
    - Live TUI updates (poll this endpoint periodically)
    - Real-time visualization of task progress
    - Accessing detailed span/token metrics

    Args:
        execution_id: Execution ID

    Returns:
        Consolidated execution data with tasks, agent executions, spans, and metrics
    """
    # Verify execution exists in storage
    execution = await storage.get_execution(execution_id)
    if not execution:
        raise HTTPException(
            status_code=404,
            detail=f"Execution {execution_id} not found"
        )

    # Get MLflow tracking URI from environment
    # Docker sets MLFLOW_TRACKING_URI=http://mlflow:5000
    import os
    mlflow_tracking_uri = os.getenv('MLFLOW_TRACKING_URI', 'http://127.0.0.1:5000')

    try:
        # Import ExecutionDataService here to avoid circular dependencies
        from roma_dspy.core.services.execution_data_service import ExecutionDataService

        # Create service instance
        # Searches all experiments by execution_id tag (no experiment name needed)
        service = ExecutionDataService(
            mlflow_tracking_uri=mlflow_tracking_uri,
        )

        # Get consolidated data
        data = service.get_execution_data(execution_id)

        return ExecutionDataResponse(**data)

    except Exception as e:
        logger.error(f"Failed to get execution data for {execution_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get execution data: {str(e)}"
        )