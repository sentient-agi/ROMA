"""Health check endpoints."""

from datetime import datetime, timezone

from fastapi import APIRouter, Request
from roma_dspy import __version__
from roma_dspy.api.schemas import HealthResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health_check(request: Request) -> HealthResponse:
    """
    Health check endpoint.

    Returns system status and basic metrics.
    """
    app_state = request.app.state.app_state

    # Calculate uptime
    uptime_seconds = (
        datetime.now(timezone.utc) - app_state.startup_time
    ).total_seconds()

    # Get active executions count
    active_executions = 0
    if app_state.execution_service:
        active_executions = len(app_state.execution_service.get_active_executions())

    # Check storage connection
    storage_connected = app_state.storage is not None

    # Get cache size
    cache_size = 0
    if app_state.execution_service:
        cache_size = app_state.execution_service.cache.size()

    return HealthResponse(
        status="healthy",
        version=__version__,
        uptime_seconds=uptime_seconds,
        active_executions=active_executions,
        storage_connected=storage_connected,
        cache_size=cache_size,
        timestamp=datetime.now(timezone.utc),
    )
