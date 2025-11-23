"""Checkpoint and recovery type definitions."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Set
from pathlib import Path

from pydantic import BaseModel, Field


class CheckpointState(str, Enum):
    """Checkpoint creation and recovery states."""

    CREATED = "created"
    VALID = "valid"
    CORRUPTED = "corrupted"
    EXPIRED = "expired"


class RecoveryStrategy(str, Enum):
    """Recovery strategy options."""

    PARTIAL = "partial"  # Only retry failed tasks
    FULL = "full"  # Restart entire DAG
    SELECTIVE = "selective"  # User-defined recovery scope


class CheckpointTrigger(str, Enum):
    """Events that trigger checkpoint creation."""

    EXECUTION_START = "execution_start"  # Initial checkpoint when execution begins
    EXECUTION_COMPLETE = (
        "execution_complete"  # Final checkpoint when execution finishes
    )
    BEFORE_PLANNING = "before_planning"
    AFTER_PLANNING = "after_planning"
    BEFORE_AGGREGATION = "before_aggregation"
    ON_FAILURE = "on_failure"
    PERIODIC = "periodic"
    MANUAL = "manual"


class RecoveryError(Exception):
    """Raised when checkpoint recovery fails."""

    pass


class CheckpointCorruptedError(RecoveryError):
    """Raised when checkpoint data is corrupted or invalid."""

    pass


class CheckpointExpiredError(RecoveryError):
    """Raised when checkpoint has expired."""

    pass


class CheckpointNotFoundError(RecoveryError):
    """Raised when requested checkpoint doesn't exist."""

    pass
