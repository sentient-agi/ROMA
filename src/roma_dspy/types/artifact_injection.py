"""
Artifact injection type system.

Defines how artifacts are injected into agent context to control scope and
prevent context bloat.
"""

from enum import Enum


class ArtifactInjectionMode(str, Enum):
    """
    Controls which artifacts are injected into agent context.

    Modes are ordered from least to most context size:
    - NONE: No artifacts injected (minimal context)
    - DEPENDENCIES: Only artifacts from direct dependency tasks (default)
    - SUBTASK: All artifacts within the current subtask tree
    - FULL: All artifacts in the entire execution

    The default mode (DEPENDENCIES) provides a good balance between context
    size and artifact visibility for most use cases.
    """

    NONE = "none"
    """No artifacts injected into context."""

    DEPENDENCIES = "dependencies"
    """Only artifacts from direct dependency tasks (default)."""

    SUBTASK = "subtask"
    """All artifacts within the current subtask tree."""

    FULL = "full"
    """All artifacts in the entire execution."""

    @classmethod
    def from_string(cls, value: str) -> "ArtifactInjectionMode":
        """
        Create ArtifactInjectionMode from string value.

        Args:
            value: String value (case-insensitive)

        Returns:
            ArtifactInjectionMode enum value

        Raises:
            ValueError: If value is not a valid injection mode
        """
        try:
            return cls(value.lower())
        except ValueError:
            valid = ", ".join([mode.value for mode in cls])
            raise ValueError(
                f"Invalid artifact injection mode: {value}. Valid modes: {valid}"
            )
