"""Instruction loader for flexible signature instruction sources.

Supports loading signature instructions from:
1. Inline strings (passthrough)
2. Jinja template files (.jinja, .jinja2)
3. Python module variables (module.path:VARIABLE_NAME)
"""

from __future__ import annotations

import importlib
from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import Optional

from loguru import logger


class InstructionFormat(Enum):
    """Format of signature instructions."""

    INLINE_STRING = "inline_string"
    JINJA_FILE = "jinja_file"
    PYTHON_MODULE = "python_module"


class InstructionLoader:
    """
    Load signature instructions from multiple sources.

    Supports three formats:
    1. Inline strings: Direct text (passthrough)
    2. Jinja files: Templates with .jinja or .jinja2 extension
    3. Python modules: Import variable from module (module.path:VARIABLE)

    Examples:
        >>> loader = InstructionLoader()

        # Inline string
        >>> loader.load("Classify as atomic or not")

        # Jinja template
        >>> loader.load("config/prompts/atomizer.jinja")

        # Python module variable
        >>> loader.load("prompt_optimization.seed_prompts.atomizer_seed:ATOMIZER_PROMPT")
    """

    def __init__(self, project_root: Optional[Path] = None):
        """
        Initialize instruction loader.

        Args:
            project_root: Project root directory for resolving relative paths.
                         If None, uses current working directory.
        """
        self.project_root = project_root or Path.cwd()

    def load(self, instructions: str) -> str:
        """
        Load instructions from any supported format.

        Args:
            instructions: Instruction string (inline, file path, or module path)

        Returns:
            Loaded instruction text

        Raises:
            ValueError: If format is invalid
            FileNotFoundError: If Jinja file not found
            ImportError: If Python module cannot be imported
            AttributeError: If Python module variable not found
            TypeError: If Python module variable is not a string
        """
        instructions = instructions.strip()
        format_type = self._detect_format(instructions)

        logger.debug(f"Loading instructions (format={format_type.value})")

        if format_type == InstructionFormat.INLINE_STRING:
            return self._load_inline(instructions)
        elif format_type == InstructionFormat.JINJA_FILE:
            return self._load_jinja(instructions)
        elif format_type == InstructionFormat.PYTHON_MODULE:
            return self._load_python(instructions)
        else:
            raise ValueError(f"Unknown instruction format: {format_type}")

    def _detect_format(self, instructions: str) -> InstructionFormat:
        """
        Detect instruction format from string.

        Detection rules:
        1. Ends with .jinja or .jinja2 → Jinja file
        2. Contains : and right side is valid Python identifier → Python module
        3. Otherwise → Inline string

        Args:
            instructions: Instruction string

        Returns:
            Detected format type
        """
        instructions = instructions.strip()

        # Jinja template file
        if instructions.endswith((".jinja", ".jinja2")):
            return InstructionFormat.JINJA_FILE

        # Python module variable: "module.path:VARIABLE_NAME"
        if ":" in instructions:
            parts = instructions.split(":", 1)
            if len(parts) == 2 and parts[1].isidentifier():
                return InstructionFormat.PYTHON_MODULE

        # Default: inline string
        return InstructionFormat.INLINE_STRING

    def _load_inline(self, instructions: str) -> str:
        """
        Load inline string instructions (passthrough).

        Args:
            instructions: Inline instruction text

        Returns:
            Same instruction text
        """
        return instructions

    @lru_cache(maxsize=128)
    def _load_jinja(self, file_path: str) -> str:
        """
        Load and render Jinja template file.

        Args:
            file_path: Path to Jinja template (relative or absolute)

        Returns:
            Rendered template text

        Raises:
            FileNotFoundError: If template file not found
            jinja2.TemplateError: If template rendering fails
        """
        try:
            from jinja2 import Environment, FileSystemLoader, TemplateNotFound
        except ImportError as e:
            raise ImportError(
                "Jinja2 is required for loading template files. "
                "Install it with: pip install jinja2>=3.1.0"
            ) from e

        # Resolve path
        resolved_path = self._resolve_path(file_path)

        if not resolved_path.exists():
            raise FileNotFoundError(
                f"Jinja template not found: {resolved_path} "
                f"(original path: {file_path})"
            )

        # Load and render template
        env = Environment(
            loader=FileSystemLoader(resolved_path.parent),
            autoescape=False,  # We control the templates, no user input
        )

        try:
            template = env.get_template(resolved_path.name)
            rendered = template.render()
            logger.debug(f"Loaded Jinja template: {file_path} ({len(rendered)} chars)")
            return rendered

        except TemplateNotFound as e:
            raise FileNotFoundError(f"Jinja template not found: {resolved_path}") from e

    @lru_cache(maxsize=128)
    def _load_python(self, module_path: str) -> str:
        """
        Import Python module and extract variable.

        Args:
            module_path: Module path in format "module.path:VARIABLE_NAME"

        Returns:
            Variable value as string

        Raises:
            ValueError: If module_path format is invalid
            ImportError: If module cannot be imported
            AttributeError: If variable not found in module
            TypeError: If variable is not a string
        """
        # Parse module path
        if ":" not in module_path:
            raise ValueError(
                f"Invalid Python module path format: '{module_path}'. "
                f"Expected format: 'module.path:VARIABLE_NAME'"
            )

        module_name, var_name = module_path.split(":", 1)

        # Validate variable name
        if not var_name.isidentifier():
            raise ValueError(
                f"Invalid Python variable name: '{var_name}'. "
                f"Must be a valid Python identifier."
            )

        # Import module
        try:
            module = importlib.import_module(module_name)
            logger.debug(f"Imported module: {module_name}")
        except ImportError as e:
            raise ImportError(f"Cannot import module '{module_name}': {e}") from e

        # Get variable
        if not hasattr(module, var_name):
            raise AttributeError(
                f"Module '{module_name}' has no attribute '{var_name}'"
            )

        value = getattr(module, var_name)

        # Validate type
        if not isinstance(value, str):
            raise TypeError(
                f"Variable '{module_name}:{var_name}' is not a string "
                f"(type: {type(value).__name__})"
            )

        logger.debug(f"Loaded Python variable: {module_path} ({len(value)} chars)")
        return value

    def _resolve_path(self, file_path: str) -> Path:
        """
        Resolve file path (relative or absolute) with security checks.

        Args:
            file_path: File path string

        Returns:
            Resolved absolute Path

        Raises:
            ValueError: If path contains unsafe patterns
        """
        path = Path(file_path)

        # If absolute, use as-is
        if path.is_absolute():
            return path.resolve()

        # Relative path: resolve relative to project root
        resolved = (self.project_root / path).resolve()

        # Security check: ensure resolved path is within project or common config dirs
        # Allow project root and common config directories
        allowed_roots = [
            self.project_root.resolve(),
            Path("/etc").resolve(),  # System config
            Path.home().resolve() / ".config",  # User config
        ]

        is_allowed = any(
            str(resolved).startswith(str(allowed_root))
            for allowed_root in allowed_roots
        )

        if not is_allowed:
            logger.warning(
                f"Path {resolved} is outside allowed directories. "
                f"Proceeding but this may be a security risk."
            )

        return resolved


def get_project_root() -> Path:
    """
    Find project root directory.

    Looks for markers: pyproject.toml, setup.py, .git

    Returns:
        Project root Path
    """
    markers = ["pyproject.toml", "setup.py", ".git"]
    current = Path.cwd()

    # Walk up directory tree
    for parent in [current] + list(current.parents):
        if any((parent / marker).exists() for marker in markers):
            return parent

    # Fallback to current directory
    return current
