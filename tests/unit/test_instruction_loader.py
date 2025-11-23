"""Unit tests for InstructionLoader."""

import pytest
from pathlib import Path
from roma_dspy.core.utils import InstructionLoader, InstructionFormat


class TestFormatDetection:
    """Test format detection logic."""

    def test_detect_inline_string(self):
        """Test detection of inline strings."""
        loader = InstructionLoader()

        # Simple text
        assert (
            loader._detect_format("Classify as atomic")
            == InstructionFormat.INLINE_STRING
        )

        # Multi-line text
        assert (
            loader._detect_format("Line 1\nLine 2\nLine 3")
            == InstructionFormat.INLINE_STRING
        )

        # Text with special characters
        assert (
            loader._detect_format("Use : and -> symbols")
            == InstructionFormat.INLINE_STRING
        )

    def test_detect_jinja_file(self):
        """Test detection of Jinja template files."""
        loader = InstructionLoader()

        # .jinja extension
        assert (
            loader._detect_format("config/prompts/atomizer.jinja")
            == InstructionFormat.JINJA_FILE
        )

        # .jinja2 extension
        assert (
            loader._detect_format("path/to/template.jinja2")
            == InstructionFormat.JINJA_FILE
        )

        # Absolute path
        assert (
            loader._detect_format("/abs/path/template.jinja")
            == InstructionFormat.JINJA_FILE
        )

    def test_detect_python_module(self):
        """Test detection of Python module variables."""
        loader = InstructionLoader()

        # Standard module path
        assert (
            loader._detect_format(
                "prompt_optimization.seed_prompts.atomizer_seed:ATOMIZER_PROMPT"
            )
            == InstructionFormat.PYTHON_MODULE
        )

        # Single module
        assert (
            loader._detect_format("module:VARIABLE") == InstructionFormat.PYTHON_MODULE
        )

        # Deep module path
        assert (
            loader._detect_format("a.b.c.d.e:MY_VARIABLE")
            == InstructionFormat.PYTHON_MODULE
        )

    def test_detect_edge_cases(self):
        """Test edge cases in format detection."""
        loader = InstructionLoader()

        # Colon but invalid identifier → inline string
        assert (
            loader._detect_format("text: not-valid-id")
            == InstructionFormat.INLINE_STRING
        )
        assert (
            loader._detect_format("text:123invalid") == InstructionFormat.INLINE_STRING
        )

        # Multiple colons → inline string (only first split counts)
        assert loader._detect_format("a:b:c") == InstructionFormat.INLINE_STRING


class TestInlineStringLoading:
    """Test inline string loading (passthrough)."""

    def test_load_inline_string(self):
        """Test loading inline strings."""
        loader = InstructionLoader()

        instruction = "Classify the goal as ATOMIC or NOT"
        result = loader.load(instruction)
        assert result == instruction

    def test_load_inline_multiline(self):
        """Test loading multi-line inline strings."""
        loader = InstructionLoader()

        instruction = """
        Role: Classifier
        Task: Determine atomicity
        Output: JSON
        """
        result = loader.load(instruction)
        # Should strip leading/trailing whitespace
        assert "Role: Classifier" in result
        assert "Task: Determine atomicity" in result


class TestJinjaFileLoading:
    """Test Jinja template file loading."""

    @pytest.fixture
    def temp_jinja_file(self, tmp_path):
        """Create temporary Jinja template file."""
        template_content = """# Test Template

Role: {{ role | default('Classifier') }}
Task: Classify the goal as ATOMIC or NOT

Output: JSON format only
"""
        template_file = tmp_path / "test_template.jinja"
        template_file.write_text(template_content)
        return template_file

    def test_load_jinja_file_absolute_path(self, temp_jinja_file):
        """Test loading Jinja file with absolute path."""
        loader = InstructionLoader()

        result = loader.load(str(temp_jinja_file))

        assert "# Test Template" in result
        assert "Role: Classifier" in result  # Default value rendered
        assert "Task: Classify the goal" in result
        assert "Output: JSON format only" in result

    def test_load_jinja_file_relative_path(self, temp_jinja_file, monkeypatch):
        """Test loading Jinja file with relative path."""
        # Set project root to parent of temp file
        project_root = temp_jinja_file.parent
        loader = InstructionLoader(project_root=project_root)

        # Load with relative path
        result = loader.load(temp_jinja_file.name)

        assert "# Test Template" in result
        assert "Role: Classifier" in result

    def test_load_jinja_file_not_found(self):
        """Test error handling for missing Jinja file."""
        loader = InstructionLoader()

        with pytest.raises(FileNotFoundError, match="Jinja template not found"):
            loader.load("nonexistent/template.jinja")

    def test_load_jinja_file_caching(self, temp_jinja_file):
        """Test that Jinja loading is cached."""
        loader = InstructionLoader()

        # Load twice - second should be cached
        result1 = loader.load(str(temp_jinja_file))
        result2 = loader.load(str(temp_jinja_file))

        assert result1 == result2
        # Both should contain rendered content
        assert "Role: Classifier" in result1


class TestPythonModuleLoading:
    """Test Python module variable loading."""

    def test_load_python_module_atomizer_seed(self):
        """Test loading ATOMIZER_PROMPT from seed_prompts."""
        loader = InstructionLoader()

        result = loader.load(
            "prompt_optimization.seed_prompts.atomizer_seed:ATOMIZER_PROMPT"
        )

        # Verify content from atomizer_seed.py
        assert isinstance(result, str)
        assert len(result) > 0
        assert "Atomizer" in result or "ATOMIC" in result

    def test_load_python_module_planner_seed(self):
        """Test loading PLANNER_PROMPT from seed_prompts."""
        loader = InstructionLoader()

        result = loader.load(
            "prompt_optimization.seed_prompts.planner_seed:PLANNER_PROMPT"
        )

        assert isinstance(result, str)
        assert len(result) > 0
        assert "Planner" in result or "subtasks" in result

    def test_load_python_module_invalid_format(self):
        """Test error handling for invalid module path format."""
        loader = InstructionLoader()

        # No colon
        with pytest.raises(ValueError, match="Invalid Python module path format"):
            loader.load("module.without.colon")

    def test_load_python_module_invalid_variable_name(self):
        """Test error handling for invalid variable names."""
        loader = InstructionLoader()

        # Invalid identifier
        with pytest.raises(ValueError, match="Invalid Python variable name"):
            loader.load("module.path:123invalid")

        with pytest.raises(ValueError, match="Invalid Python variable name"):
            loader.load("module.path:not-valid")

    def test_load_python_module_import_error(self):
        """Test error handling for import errors."""
        loader = InstructionLoader()

        with pytest.raises(ImportError, match="Cannot import module"):
            loader.load("nonexistent.module:VARIABLE")

    def test_load_python_module_variable_not_found(self):
        """Test error handling for missing variables."""
        loader = InstructionLoader()

        # Module exists but variable doesn't
        with pytest.raises(AttributeError, match="has no attribute"):
            loader.load(
                "prompt_optimization.seed_prompts.atomizer_seed:NONEXISTENT_VAR"
            )

    def test_load_python_module_not_string(self):
        """Test error handling for non-string variables."""
        loader = InstructionLoader()

        # ATOMIZER_DEMOS is a list, not a string
        with pytest.raises(TypeError, match="is not a string"):
            loader.load("prompt_optimization.seed_prompts.atomizer_seed:ATOMIZER_DEMOS")

    def test_load_python_module_caching(self):
        """Test that Python module loading is cached."""
        loader = InstructionLoader()

        # Load twice - second should be cached
        result1 = loader.load(
            "prompt_optimization.seed_prompts.atomizer_seed:ATOMIZER_PROMPT"
        )
        result2 = loader.load(
            "prompt_optimization.seed_prompts.atomizer_seed:ATOMIZER_PROMPT"
        )

        assert result1 == result2
        assert result1 is result2  # Same object from cache


class TestPathResolution:
    """Test path resolution and security checks."""

    def test_resolve_absolute_path(self, tmp_path):
        """Test resolving absolute paths."""
        loader = InstructionLoader()

        template_file = tmp_path / "test.jinja"
        template_file.write_text("Test content")

        resolved = loader._resolve_path(str(template_file))
        assert resolved == template_file.resolve()

    def test_resolve_relative_path(self, tmp_path):
        """Test resolving relative paths."""
        # Create project structure
        project_root = tmp_path / "project"
        project_root.mkdir()
        config_dir = project_root / "config"
        config_dir.mkdir()

        template_file = config_dir / "test.jinja"
        template_file.write_text("Test content")

        # Load with relative path
        loader = InstructionLoader(project_root=project_root)
        resolved = loader._resolve_path("config/test.jinja")

        assert resolved == template_file.resolve()

    def test_resolve_path_security_warning(self, tmp_path, caplog):
        """Test security warning for paths outside allowed directories."""
        loader = InstructionLoader(project_root=tmp_path / "project")

        # Path outside project root
        external_path = tmp_path / "external" / "file.jinja"
        external_path.parent.mkdir(parents=True)
        external_path.write_text("External content")

        # Should resolve but log warning
        resolved = loader._resolve_path(str(external_path))
        assert resolved == external_path.resolve()
        # Check for security warning in logs (if captured)


class TestIntegration:
    """Integration tests for full loading pipeline."""

    def test_load_with_whitespace(self):
        """Test loading handles whitespace correctly."""
        loader = InstructionLoader()

        # Inline with extra whitespace
        result = loader.load("  \n  Test instruction  \n  ")
        assert result.strip() == "Test instruction"

    def test_load_empty_string(self):
        """Test loading empty strings."""
        loader = InstructionLoader()

        # Empty string → inline string → passthrough
        result = loader.load("   ")
        assert result == "   "

    def test_load_multiple_formats_sequentially(self, tmp_path):
        """Test loading different formats in sequence."""
        loader = InstructionLoader(project_root=tmp_path)

        # 1. Inline string
        result1 = loader.load("Inline instruction")
        assert result1 == "Inline instruction"

        # 2. Python module
        result2 = loader.load(
            "prompt_optimization.seed_prompts.atomizer_seed:ATOMIZER_PROMPT"
        )
        assert "Atomizer" in result2 or "ATOMIC" in result2

        # 3. Jinja file
        template_file = tmp_path / "test.jinja"
        template_file.write_text("Jinja template content")
        result3 = loader.load(str(template_file))
        assert result3 == "Jinja template content"


class TestProjectRootFinding:
    """Test project root detection."""

    def test_get_project_root_with_pyproject(self, tmp_path):
        """Test finding project root with pyproject.toml."""
        from roma_dspy.core.utils.instruction_loader import get_project_root

        # Create project structure
        project = tmp_path / "myproject"
        project.mkdir()
        (project / "pyproject.toml").write_text("")

        subdir = project / "src" / "module"
        subdir.mkdir(parents=True)

        # Change to subdirectory and find root
        import os

        original_cwd = os.getcwd()
        try:
            os.chdir(subdir)
            root = get_project_root()
            assert root == project
        finally:
            os.chdir(original_cwd)

    def test_get_project_root_with_git(self, tmp_path):
        """Test finding project root with .git."""
        from roma_dspy.core.utils.instruction_loader import get_project_root

        # Create project structure
        project = tmp_path / "myproject"
        project.mkdir()
        git_dir = project / ".git"
        git_dir.mkdir()

        subdir = project / "deep" / "nested" / "dir"
        subdir.mkdir(parents=True)

        import os

        original_cwd = os.getcwd()
        try:
            os.chdir(subdir)
            root = get_project_root()
            assert root == project
        finally:
            os.chdir(original_cwd)

    def test_get_project_root_fallback(self, tmp_path):
        """Test fallback to current directory."""
        from roma_dspy.core.utils.instruction_loader import get_project_root

        # No markers in path
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()

        import os

        original_cwd = os.getcwd()
        try:
            os.chdir(empty_dir)
            root = get_project_root()
            assert root == empty_dir
        finally:
            os.chdir(original_cwd)
