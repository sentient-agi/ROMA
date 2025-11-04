"""Toolkit configuration schemas for ROMA-DSPy."""

from pydantic.dataclasses import dataclass
from pydantic import field_validator, model_validator
from typing import List, Dict, Any, Optional


@dataclass
class ToolkitConfig:
    """Configuration for a single toolkit."""

    class_name: str                                    # e.g., "FileToolkit", "CalculatorToolkit"
    enabled: bool = True                               # Whether this toolkit is enabled
    include_tools: Optional[List[str]] = None          # Specific tools to include (None = all available)
    exclude_tools: Optional[List[str]] = None          # Tools to exclude from available tools
    toolkit_config: Optional[Dict[str, Any]] = None    # Toolkit-specific configuration parameters
    mandatory: bool = False                            # Framework-managed toolkit (cannot be disabled by users)

    # BUG FIX D: Sensitive keys that should be redacted in logs
    SENSITIVE_KEYS = {
        'api_key', 'secret', 'token', 'password', 'credential',
        'access_key', 'private_key', 'auth', 'bearer', 'key',
        'apikey', 'api_secret', 'access_token', 'refresh_token'
    }

    def __post_init__(self):
        """Initialize defaults after creation."""
        if self.include_tools is None:
            self.include_tools = []
        if self.exclude_tools is None:
            self.exclude_tools = []
        if self.toolkit_config is None:
            self.toolkit_config = {}

    @field_validator("class_name")
    @classmethod
    def validate_class_name(cls, v: str) -> str:
        """Validate class name is not empty."""
        if not v or not v.strip():
            raise ValueError("Toolkit class name cannot be empty")
        return v.strip()

    @model_validator(mode="after")
    def validate_tool_overlap(self):
        """Validate that tools are not both included and excluded."""
        if self.include_tools and self.exclude_tools:
            overlap = set(self.include_tools) & set(self.exclude_tools)
            if overlap:
                raise ValueError(f"Tools cannot be both included and excluded: {overlap}")
        return self

    def safe_dict(self) -> Dict[str, Any]:
        """
        Return configuration dict with sensitive values redacted.

        Use this method when logging configuration to prevent
        credential exposure in log files and streams.

        Handles circular references by detecting cycles using object identity.

        Returns:
            Dict with sensitive keys replaced by '***REDACTED***'

        Example:
            >>> config = ToolkitConfig(
            ...     class_name="APIToolkit",
            ...     toolkit_config={"api_key": "sk-secret123", "timeout": 30}
            ... )
            >>> config.safe_dict()
            {'api_key': '***REDACTED***', 'timeout': 30}
        """
        if not self.toolkit_config:
            return {}

        # BUG FIX: NEW #4 - Start with empty seen set for cycle detection
        return self._redact_dict(self.toolkit_config, seen=set())

    def _redact_dict(self, d: Dict[str, Any], seen: set) -> Dict[str, Any]:
        """
        Recursively redact sensitive keys in nested dicts.

        Args:
            d: Dictionary to redact
            seen: Set of object IDs already visited (prevents cycles)

        Returns:
            New dictionary with sensitive values redacted
        """
        # BUG FIX: NEW #4 - Detect cycles using object identity
        obj_id = id(d)
        if obj_id in seen:
            # Circular reference detected - return placeholder
            return {"__circular_reference__": "***REDACTED***"}

        # Add to seen set (immutable pattern prevents mutation bugs)
        seen = seen | {obj_id}

        redacted = {}
        for key, value in d.items():
            key_lower = key.lower()

            # Check if key contains any sensitive keyword
            if any(sensitive in key_lower for sensitive in self.SENSITIVE_KEYS):
                redacted[key] = '***REDACTED***'
            elif isinstance(value, dict):
                # BUG FIX: NEW #4 - Pass seen set to detect cycles in nested dicts
                redacted[key] = self._redact_dict(value, seen)
            elif isinstance(value, list):
                # BUG FIX: NEW #4 - Pass seen set to detect cycles in list items
                redacted[key] = [
                    self._redact_dict(item, seen) if isinstance(item, dict) else item
                    for item in value
                ]
            else:
                redacted[key] = value

        return redacted