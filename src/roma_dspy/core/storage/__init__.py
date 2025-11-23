"""Core storage infrastructure for execution isolation."""

# FileStorage is always available (no optional dependencies)
from .file_storage import FileStorage

# PostgreSQL storage and models require sqlalchemy (optional dependency)
# Import them lazily to avoid forcing sqlalchemy requirement
# Usage:
#   from roma_dspy.core.storage import PostgresStorage  # Lazy import
#   from roma_dspy.core.storage import Base, Execution, etc.  # Lazy import


def __getattr__(name):
    """Lazy import for optional PostgreSQL storage components."""
    if name == "PostgresStorage":
        from .postgres_storage import PostgresStorage

        return PostgresStorage
    elif name == "Base":
        from .models import Base

        return Base
    elif name == "Execution":
        from .models import Execution

        return Execution
    elif name == "Checkpoint":
        from .models import Checkpoint

        return Checkpoint
    elif name == "TaskTrace":
        from .models import TaskTrace

        return TaskTrace
    elif name == "LMTrace":
        from .models import LMTrace

        return LMTrace
    elif name == "CircuitBreaker":
        from .models import CircuitBreaker

        return CircuitBreaker
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")


__all__ = [
    "FileStorage",
    "PostgresStorage",  # Lazy
    "Base",  # Lazy
    "Execution",  # Lazy
    "Checkpoint",  # Lazy
    "TaskTrace",  # Lazy
    "LMTrace",  # Lazy
    "CircuitBreaker",  # Lazy
]
