"""Sensitive data redaction for export privacy."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Pattern

from loguru import logger


class SensitiveDataRedactor:
    """Detects and redacts sensitive information in export data.

    Uses pattern matching to identify and replace:
    - API keys (OpenAI, Anthropic, AWS, Google, etc.)
    - Bearer tokens
    - Passwords and secrets
    - URLs with credentials
    - Environment variables with sensitive names
    """

    # Sensitive field names (case-insensitive)
    SENSITIVE_FIELD_NAMES = {
        "password",
        "secret",
        "token",
        "api_key",
        "apikey",
        "access_key",
        "private_key",
        "auth",
        "authorization",
        "credential",
        "credentials",
    }

    def __init__(self, preserve_chars: int = 4) -> None:
        """Initialize redactor with patterns.

        Args:
            preserve_chars: Number of chars to preserve at start/end (for debugging)
        """
        self.preserve_chars = preserve_chars
        self.patterns = self._build_patterns()

    def _build_patterns(self) -> List[tuple[Pattern, str]]:
        """Build regex patterns for sensitive data detection.

        Returns:
            List of (pattern, label) tuples
        """
        return [
            # OpenAI API keys
            (re.compile(r"sk-[a-zA-Z0-9]{20,}"), "API_KEY"),
            # Anthropic API keys
            (re.compile(r"sk-ant-[a-zA-Z0-9\-]{20,}"), "API_KEY"),
            # AWS access keys
            (re.compile(r"AKIA[0-9A-Z]{16}"), "AWS_KEY"),
            # Google API keys
            (re.compile(r"AIza[0-9A-Za-z\-_]{35}"), "GOOGLE_KEY"),
            # Bearer tokens
            (re.compile(r"Bearer\s+[a-zA-Z0-9\-_.~+/]+=*", re.IGNORECASE), "BEARER_TOKEN"),
            # Generic tokens (long alphanumeric strings)
            (re.compile(r"\b[a-f0-9]{32,}\b"), "TOKEN"),
            # JWT tokens
            (re.compile(r"eyJ[a-zA-Z0-9_-]{10,}\.[a-zA-Z0-9_-]{10,}\.[a-zA-Z0-9_-]{10,}"), "JWT_TOKEN"),
            # URLs with credentials (http://user:pass@host)
            (re.compile(r"https?://[^:]+:[^@]+@[^\s]+"), "URL_WITH_CREDS"),
            # Private SSH keys
            (re.compile(r"-----BEGIN\s+(?:RSA\s+)?PRIVATE\s+KEY-----[\s\S]+?-----END\s+(?:RSA\s+)?PRIVATE\s+KEY-----"), "PRIVATE_KEY"),
        ]

    def redact(self, data: Any) -> Any:
        """Recursively redact sensitive data.

        Args:
            data: Data to redact (dict, list, str, or other)

        Returns:
            Redacted data (same type as input)
        """
        if isinstance(data, dict):
            return self._redact_dict(data)
        elif isinstance(data, list):
            return [self.redact(item) for item in data]
        elif isinstance(data, str):
            return self._redact_string(data)
        else:
            return data

    def _redact_dict(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Redact dictionary (checks field names and values).

        Args:
            data: Dictionary to redact

        Returns:
            Redacted dictionary
        """
        redacted = {}

        for key, value in data.items():
            # Check if field name is sensitive
            if self._is_sensitive_field(key):
                # Redact entire value
                redacted[key] = self._redact_value(value, "SENSITIVE_FIELD")
            elif isinstance(value, (dict, list, str)):
                # Recursively redact nested data
                redacted[key] = self.redact(value)
            else:
                redacted[key] = value

        return redacted

    def _is_sensitive_field(self, field_name: str) -> bool:
        """Check if field name indicates sensitive data.

        Args:
            field_name: Field name to check

        Returns:
            True if field is sensitive
        """
        field_lower = field_name.lower()

        # Exact match
        if field_lower in self.SENSITIVE_FIELD_NAMES:
            return True

        # Partial match (e.g., "openai_api_key")
        for sensitive_name in self.SENSITIVE_FIELD_NAMES:
            if sensitive_name in field_lower:
                return True

        return False

    def _redact_value(self, value: Any, label: str) -> str:
        """Redact a value with label.

        Args:
            value: Value to redact
            label: Redaction label

        Returns:
            Redacted string
        """
        if value is None:
            return None

        value_str = str(value)

        # Preserve first/last chars if long enough
        if len(value_str) > self.preserve_chars * 2 + 4:
            prefix = value_str[:self.preserve_chars]
            suffix = value_str[-self.preserve_chars:]
            return f"{prefix}****[REDACTED:{label}]****{suffix}"
        else:
            return f"[REDACTED:{label}]"

    def _redact_string(self, text: str) -> str:
        """Redact sensitive patterns in string.

        Args:
            text: String to redact

        Returns:
            Redacted string
        """
        if not text:
            return text

        redacted = text

        # Apply all patterns
        for pattern, label in self.patterns:
            matches = list(pattern.finditer(redacted))

            # Process matches in reverse to maintain indices
            for match in reversed(matches):
                matched_text = match.group(0)
                replacement = self._redact_matched_text(matched_text, label)

                # Replace match
                redacted = (
                    redacted[:match.start()] +
                    replacement +
                    redacted[match.end():]
                )

        return redacted

    def _redact_matched_text(self, text: str, label: str) -> str:
        """Create redaction replacement for matched text.

        Args:
            text: Matched sensitive text
            label: Redaction label

        Returns:
            Replacement string
        """
        # Preserve first/last chars if long enough
        if len(text) > self.preserve_chars * 2 + 4:
            prefix = text[:self.preserve_chars]
            suffix = text[-self.preserve_chars:]
            return f"{prefix}****[REDACTED:{label}]****{suffix}"
        else:
            return f"[REDACTED:{label}]"

    def get_redaction_summary(self, original: Any, redacted: Any) -> Dict[str, int]:
        """Get summary of redactions performed.

        Args:
            original: Original data
            redacted: Redacted data

        Returns:
            Dict with redaction counts by type
        """
        summary = {}

        # Count redaction markers
        redacted_str = str(redacted)
        for _, label in self.patterns:
            count = redacted_str.count(f"[REDACTED:{label}]")
            if count > 0:
                summary[label] = count

        # Count sensitive field redactions
        sensitive_count = redacted_str.count("[REDACTED:SENSITIVE_FIELD]")
        if sensitive_count > 0:
            summary["SENSITIVE_FIELD"] = sensitive_count

        return summary
