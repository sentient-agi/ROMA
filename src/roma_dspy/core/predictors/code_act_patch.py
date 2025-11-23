"""Monkey patch for DSPy's CodeAct to fix typing import issues.

DSPy's CodeAct uses inspect.getsource() to extract tool source code, which doesn't
include module-level imports. This causes NameError when tools use type hints like
Union, Optional, etc.

This patch injects common typing imports into the PythonInterpreter before defining tools.
"""

import inspect
from loguru import logger

try:
    import dspy
    from dspy.predict.code_act import CodeAct

    HAS_DSPY = True
except ImportError:
    HAS_DSPY = False
    logger.warning("DSPy not available, skipping CodeAct patch")


def _patched_code_act_forward(self, **kwargs):
    """Patched forward method that injects typing imports before loading tools."""

    # Inject common typing imports into the interpreter namespace
    # This prevents NameError when tool functions use type hints
    typing_imports = """
from typing import Union, Optional, List, Dict, Tuple, Set, Any, Callable
from typing import Sequence, Mapping, Iterable
from decimal import Decimal
import numpy as np
"""

    try:
        self.interpreter(typing_imports)
        logger.debug("Injected typing imports into CodeAct interpreter")
    except Exception as e:
        logger.warning(f"Failed to inject typing imports into CodeAct interpreter: {e}")

    # Define the tool functions in the interpreter
    for tool in self.tools.values():
        try:
            self.interpreter(inspect.getsource(tool.func))
        except Exception as e:
            logger.error(f"Failed to load tool {tool.name} into interpreter: {e}")
            # Try to continue with other tools
            continue

    trajectory = {}
    max_iters = kwargs.pop("max_iters", self.max_iters)
    for idx in range(max_iters):
        code_data = self.codeact(trajectory=trajectory, **kwargs)
        output = None
        code, error = self._parse_code(code_data)

        if error:
            trajectory[f"observation_{idx}"] = (
                f"Failed to parse the generated code: {error}"
            )
            continue

        trajectory[f"generated_code_{idx}"] = code
        output, error = self._execute_code(code)

        if not error:
            trajectory[f"code_output_{idx}"] = output
        else:
            trajectory[f"observation_{idx}"] = (
                f"Failed to execute the generated code: {error}"
            )

        if code_data.finished:
            break

    extract = self._call_with_potential_trajectory_truncation(
        self.extractor, trajectory, **kwargs
    )
    self.interpreter.shutdown()
    return dspy.Prediction(trajectory=trajectory, **extract)


def apply_code_act_patch():
    """Apply the CodeAct patch to inject typing imports."""
    if not HAS_DSPY:
        logger.warning("DSPy not available, cannot apply CodeAct patch")
        return False

    try:
        # Store original method
        CodeAct._original_forward = CodeAct.forward

        # Apply patch
        CodeAct.forward = _patched_code_act_forward

        logger.info("Applied CodeAct patch to inject typing imports into interpreter")
        return True

    except Exception as e:
        logger.error(f"Failed to apply CodeAct patch: {e}")
        return False


# Auto-apply patch on import
if HAS_DSPY:
    apply_code_act_patch()
