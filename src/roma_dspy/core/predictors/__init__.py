"""Predictor-related utilities and patches.

This module contains patches for DSPy predictors to fix issues and add functionality.
Patches are automatically applied on import.
"""

# Import patches to auto-apply them
from roma_dspy.core.predictors.code_act_patch import apply_code_act_patch  # noqa: F401

__all__: list[str] = ["apply_code_act_patch"]
