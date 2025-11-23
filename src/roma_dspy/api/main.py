"""FastAPI application for ROMA-DSPy REST API."""

import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from loguru import logger

from roma_dspy.api.execution_service import ExecutionService
from roma_dspy.api.middleware import RequestLoggingMiddleware, RateLimitMiddleware
from roma_dspy.api.dependencies import init_dependencies
from roma_dspy.config.manager import ConfigManager
from roma_dspy.core.storage.postgres_storage import PostgresStorage
from roma_dspy.logging_config import configure_from_config


# ============================================================================
# Application State
# ============================================================================


class AppState:
    """Application state container."""

    def __init__(self):
        self.storage: PostgresStorage | None = None
        self.config_manager: ConfigManager | None = None
        self.execution_service: ExecutionService | None = None
        self.startup_time: datetime = datetime.now(timezone.utc)


# ============================================================================
# Lifespan Management
# ============================================================================


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Manage application lifecycle.

    Startup:
    - Initialize PostgreSQL connection
    - Initialize ConfigManager
    - Initialize ExecutionService
    - Setup dependency injection

    Shutdown:
    - Shutdown ExecutionService (cancel running tasks)
    - Close PostgreSQL connection
    """
    logger.info("Starting ROMA-DSPy API server")

    # Initialize state
    app.state.app_state = AppState()

    try:
        # Initialize ConfigManager
        logger.info("Initializing ConfigManager")
        config_manager = ConfigManager()
        app.state.app_state.config_manager = config_manager

        # Load default config to get storage settings
        default_config = config_manager.load_config()

        # Configure logging from config
        if default_config.logging:
            configure_from_config(default_config.logging)
            logger.info("Logging configured from config")

        # Initialize PostgreSQL storage (guard against missing section)
        if (
            default_config.storage
            and default_config.storage.postgres
            and default_config.storage.postgres.enabled
        ):
            logger.info("Initializing PostgreSQL storage")
            storage = PostgresStorage(default_config.storage.postgres)
            await storage.initialize()
            app.state.app_state.storage = storage
            logger.info("PostgreSQL storage initialized")
        else:
            logger.warning("PostgreSQL storage is disabled in config")
            storage = None
            app.state.app_state.storage = None

        # Initialize ExecutionService
        if storage:
            logger.info("Initializing ExecutionService")
            execution_service = ExecutionService(
                storage=storage, config_manager=config_manager, cache_ttl_seconds=5
            )
            app.state.app_state.execution_service = execution_service
            logger.info("ExecutionService initialized")
        else:
            logger.warning("ExecutionService not initialized (storage disabled)")
            app.state.app_state.execution_service = None

        # Initialize dependency injection
        if storage and config_manager:
            init_dependencies(storage, config_manager)
            logger.info("Dependency injection initialized")

        logger.info("ROMA-DSPy API server startup complete")

        # Yield control to application
        yield

    finally:
        # Shutdown
        logger.info("Shutting down ROMA-DSPy API server")

        # Shutdown ExecutionService
        if app.state.app_state.execution_service:
            logger.info("Shutting down ExecutionService")
            await app.state.app_state.execution_service.shutdown()

        # Close PostgreSQL connection
        if app.state.app_state.storage:
            logger.info("Closing PostgreSQL connection")
            await app.state.app_state.storage.close()

        logger.info("ROMA-DSPy API server shutdown complete")


# ============================================================================
# Application Factory
# ============================================================================


def create_app(enable_rate_limit: bool = True) -> FastAPI:
    """
    Create and configure FastAPI application.

    Args:
        enable_rate_limit: Whether to enable rate limiting middleware

    Returns:
        Configured FastAPI application
    """
    app = FastAPI(
        title="ROMA-DSPy API",
        description="REST API for hierarchical task decomposition with DSPy",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    # CORS middleware with environment-based configuration
    allowed_origins_env = os.getenv("ALLOWED_ORIGINS", "")
    allowed_origins = (
        [origin.strip() for origin in allowed_origins_env.split(",") if origin.strip()]
        if allowed_origins_env
        else ["*"]  # Allow all in development (not recommended for production)
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Request logging middleware
    app.add_middleware(RequestLoggingMiddleware)

    # Rate limiting middleware (optional)
    if enable_rate_limit:
        app.add_middleware(RateLimitMiddleware, requests_per_minute=60)

    # Register routers
    from roma_dspy.api.routers import (
        health,
        executions,
        checkpoints,
        metrics,
        traces,
    )

    app.include_router(health.router, tags=["health"])
    app.include_router(executions.router, prefix="/api/v1", tags=["executions"])
    app.include_router(checkpoints.router, prefix="/api/v1", tags=["checkpoints"])
    app.include_router(metrics.router, prefix="/api/v1", tags=["metrics"])
    app.include_router(traces.router, prefix="/api/v1", tags=["traces"])

    # Global exception handler
    @app.exception_handler(Exception)
    async def global_exception_handler(request, exc):
        logger.error(f"Unhandled exception: {exc}")
        return JSONResponse(
            status_code=500,
            content={
                "error": "Internal server error",
                "detail": str(exc),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )

    return app


# ============================================================================
# Application Instance
# ============================================================================

app = create_app()
