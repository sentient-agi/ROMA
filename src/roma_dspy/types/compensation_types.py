"""Compensation and rollback type definitions for Saga pattern implementation."""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional, Callable
from datetime import datetime

from pydantic import BaseModel, Field


class CompensationAction(str, Enum):
    """Types of compensation actions that can be performed."""

    UNDO = "undo"  # Reverse a completed operation
    CLEANUP = "cleanup"  # Clean up resources/side effects
    ROLLBACK = "rollback"  # Revert to previous state
    NOTIFY = "notify"  # Send notification about failure
    LOG = "log"  # Log failure for audit trail
    CUSTOM = "custom"  # Custom compensation logic


class CompensationStatus(str, Enum):
    """Status of compensation execution."""

    PENDING = "pending"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class SagaState(str, Enum):
    """Overall state of a saga transaction."""

    RUNNING = "running"
    COMPENSATING = "compensating"
    COMPLETED = "completed"
    FAILED = "failed"
    COMPENSATED = "compensated"


class CompensationError(Exception):
    """Raised when compensation actions fail."""

    pass


class SagaExecutionError(Exception):
    """Raised when saga execution encounters unrecoverable errors."""

    pass


class CompensationTimeoutError(CompensationError):
    """Raised when compensation action times out."""

    pass
