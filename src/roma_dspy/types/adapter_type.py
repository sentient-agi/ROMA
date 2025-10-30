"""Adapter type enumeration for DSPy adapters."""

from enum import Enum
from typing import Any, Callable, Literal
import dspy


class AdapterType(str, Enum):
    """DSPy adapter types for LLM communication."""

    JSON = "json"
    CHAT = "chat"

    def __str__(self) -> str:
        return self.value

    @classmethod
    def from_string(cls, value: str) -> "AdapterType":
        """
        Parse adapter type from string with normalization.

        Args:
            value: Adapter type string (case-insensitive)

        Returns:
            AdapterType enum value

        Raises:
            ValueError: If value is not a valid adapter type
        """
        norm = value.strip().lower()

        # Direct match
        for member in cls:
            if member.value == norm:
                return member

        # Aliases
        if norm in ("jsonadapter", "json_adapter"):
            return cls.JSON
        elif norm in ("chatadapter", "chat_adapter"):
            return cls.CHAT

        raise ValueError(
            f"Invalid adapter type '{value}'. Must be 'json' or 'chat'."
        )

    def create_adapter(self, use_native_function_calling: bool = True) -> Any:
        """
        Create DSPy adapter instance with configuration.

        Args:
            use_native_function_calling: Enable native function calling (default: True)

        Returns:
            DSPy adapter instance (JSONAdapter or ChatAdapter)
        """
        if self == AdapterType.JSON:
            return dspy.JSONAdapter(use_native_function_calling=use_native_function_calling)
        elif self == AdapterType.CHAT:
            return dspy.ChatAdapter(use_native_function_calling=use_native_function_calling)
        else:
            raise ValueError(f"Unknown adapter type: {self}")


# Type alias for Literal type hints
AdapterTypeLiteral = Literal["json", "chat"]
