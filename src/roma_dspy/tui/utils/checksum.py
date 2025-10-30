"""Checksum utilities for export/import data integrity verification.

Provides SHA256 checksum computation with deterministic JSON serialization.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Dict


def compute_checksum(data: Dict[str, Any]) -> str:
    """Compute SHA256 checksum of JSON-serializable data.

    Uses deterministic JSON serialization with sorted keys and consistent
    separators to ensure checksum consistency across export/import cycles.

    This method computes the checksum from the final JSON string representation,
    ensuring that serialization/deserialization cycles don't cause mismatches.

    Args:
        data: JSON-serializable dictionary

    Returns:
        Checksum string in format "sha256:hexdigest"

    Example:
        >>> data = {"foo": 123, "bar": "test"}
        >>> checksum = compute_checksum(data)
        >>> checksum.startswith("sha256:")
        True
    """
    # Serialize with deterministic settings:
    # - sort_keys=True: Consistent key ordering
    # - default=str: Handle non-JSON types (datetime, Path, etc.)
    # - separators=(',', ':'): No extra whitespace (compact, deterministic)
    json_str = json.dumps(data, sort_keys=True, default=str, separators=(',', ':'))
    json_bytes = json_str.encode("utf-8")

    # Compute SHA256
    hasher = hashlib.sha256()
    hasher.update(json_bytes)
    hex_digest = hasher.hexdigest()

    return f"sha256:{hex_digest}"


def verify_checksum(data: Dict[str, Any], expected_checksum: str) -> bool:
    """Verify data matches expected checksum.

    Args:
        data: Data to check
        expected_checksum: Expected checksum string

    Returns:
        True if checksums match, False otherwise

    Example:
        >>> data = {"test": 123}
        >>> checksum = compute_checksum(data)
        >>> verify_checksum(data, checksum)
        True
        >>> verify_checksum(data, "sha256:invalid")
        False
    """
    actual_checksum = compute_checksum(data)
    return actual_checksum == expected_checksum
