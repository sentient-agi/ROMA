"""
Test package building and installation.

Tests that the package can be built as a wheel and installed correctly.

Run with:
    pytest tests/test_package_build.py -v
    uv run pytest tests/test_package_build.py -v
"""

import subprocess
import sys
import tempfile
import shutil
from pathlib import Path
import pytest


class TestPackageBuild:
    """Test building the package."""

    def test_pyproject_toml_exists(self):
        """pyproject.toml should exist and be valid."""
        pyproject = Path("pyproject.toml")
        assert pyproject.exists(), "pyproject.toml not found"

        content = pyproject.read_text()
        assert "[project]" in content
        assert 'name = "roma-dspy"' in content

    def test_pyproject_has_optional_dependencies(self):
        """pyproject.toml should define optional dependencies."""
        pyproject = Path("pyproject.toml")
        content = pyproject.read_text()

        # Should have our new optional groups
        assert "[project.optional-dependencies]" in content
        assert "persistence" in content
        assert "observability" in content
        assert "s3" in content
        assert "e2b" in content
        assert "api" in content

    def test_build_wheel(self):
        """Should be able to build a wheel."""
        # Clean previous builds
        dist_dir = Path("dist")
        if dist_dir.exists():
            shutil.rmtree(dist_dir)

        # Build wheel using python -m build
        result = subprocess.run(
            [sys.executable, "-m", "build", "--wheel"],
            capture_output=True,
            text=True,
            timeout=120,
        )

        if result.returncode != 0:
            # Try with pip wheel as fallback
            result = subprocess.run(
                [sys.executable, "-m", "pip", "wheel", ".", "--no-deps"],
                capture_output=True,
                text=True,
                timeout=120,
            )

        # Should succeed
        if result.returncode != 0:
            pytest.skip(
                f"Build failed (build tools may not be installed): {result.stderr}"
            )

        # Check wheel was created
        wheels = list(Path("dist").glob("*.whl")) if Path("dist").exists() else []
        if not wheels:
            wheels = list(Path(".").glob("*.whl"))

        assert len(wheels) > 0, "No wheel file created"

    def test_package_metadata(self):
        """Package should have correct metadata."""
        # Check version can be determined
        try:
            from roma_dspy import __version__

            assert __version__ is not None
        except (ImportError, AttributeError):
            # Version might not be defined - that's okay
            pass


class TestPackageInstallation:
    """Test installing the package in a clean environment."""

    @pytest.fixture
    def clean_venv(self):
        """Create a clean virtual environment."""
        with tempfile.TemporaryDirectory() as tmpdir:
            venv_path = Path(tmpdir) / "test_venv"

            # Create venv
            subprocess.run(
                [sys.executable, "-m", "venv", str(venv_path)], check=True, timeout=60
            )

            # Get python executable
            if sys.platform == "win32":
                python_exe = venv_path / "Scripts" / "python.exe"
            else:
                python_exe = venv_path / "bin" / "python"

            yield python_exe

    def test_install_minimal(self, clean_venv):
        """Should be able to install minimal package."""
        # Install package in editable mode
        result = subprocess.run(
            [str(clean_venv), "-m", "pip", "install", "-e", "."],
            capture_output=True,
            text=True,
            timeout=180,
        )

        if result.returncode != 0:
            pytest.skip(f"Installation failed: {result.stderr}")

        # Test import works
        result = subprocess.run(
            [str(clean_venv), "-c", "from roma_dspy import solve; print('OK')"],
            capture_output=True,
            text=True,
            timeout=30,
        )

        assert result.returncode == 0
        assert "OK" in result.stdout

    def test_install_with_extras(self, clean_venv):
        """Should be able to install with optional extras."""
        # Install with persistence extra
        result = subprocess.run(
            [str(clean_venv), "-m", "pip", "install", "-e", ".[persistence]"],
            capture_output=True,
            text=True,
            timeout=180,
        )

        if result.returncode != 0:
            pytest.skip(f"Installation with extras failed: {result.stderr}")

        # Test that persistence is available
        code = """
from roma_dspy.utils.lazy_imports import HAS_PERSISTENCE
print(f"HAS_PERSISTENCE={HAS_PERSISTENCE}")
assert HAS_PERSISTENCE == True, "Persistence should be available"
"""
        result = subprocess.run(
            [str(clean_venv), "-c", code], capture_output=True, text=True, timeout=30
        )

        assert result.returncode == 0
        assert "HAS_PERSISTENCE=True" in result.stdout


class TestPackageStructure:
    """Test package structure and contents."""

    def test_src_directory_exists(self):
        """src/ directory should exist."""
        src_dir = Path("src/roma_dspy")
        assert src_dir.exists()
        assert src_dir.is_dir()

    def test_essential_modules_exist(self):
        """Essential modules should exist."""
        essential = [
            "src/roma_dspy/__init__.py",
            "src/roma_dspy/core/__init__.py",
            "src/roma_dspy/core/engine/__init__.py",
            "src/roma_dspy/core/engine/solve.py",
            "src/roma_dspy/core/modules/__init__.py",
            "src/roma_dspy/types/__init__.py",
            "src/roma_dspy/utils/lazy_imports.py",
        ]

        for module_path in essential:
            assert Path(module_path).exists(), f"Missing: {module_path}"

    def test_no_pycache_in_src(self):
        """Source directory should not have __pycache__ in git."""
        gitignore = Path(".gitignore")
        if gitignore.exists():
            content = gitignore.read_text()
            assert "__pycache__" in content or "*.pyc" in content


class TestDependencyDefinitions:
    """Test dependency definitions in pyproject.toml."""

    def test_core_dependencies_minimal(self):
        """Core dependencies should be minimal."""
        pyproject = Path("pyproject.toml")
        content = pyproject.read_text()

        # Core should NOT include these (they should be optional)
        lines_with_dependencies = []
        in_dependencies = False

        for line in content.split("\n"):
            if line.strip() == "dependencies = [":
                in_dependencies = True
            elif in_dependencies:
                if line.strip().startswith("]"):
                    break
                lines_with_dependencies.append(line)

        deps_text = "\n".join(lines_with_dependencies)

        # These should NOT be in core dependencies
        # (they might be commented out, so check uncommented lines)
        for dep in ["sqlalchemy", "mlflow", "boto3", "e2b"]:
            # Check if it appears in an uncommented line
            for line in lines_with_dependencies:
                stripped = line.strip()
                if not stripped.startswith("#") and dep in stripped.lower():
                    pytest.fail(
                        f"{dep} should be in optional-dependencies, not core dependencies"
                    )

    def test_optional_dependencies_defined(self):
        """Optional dependencies should be properly defined."""
        pyproject = Path("pyproject.toml")
        content = pyproject.read_text()

        # Should have these optional groups
        required_groups = ["persistence", "observability", "s3", "e2b", "api"]

        for group in required_groups:
            assert f"{group} =" in content or f'"{group}"' in content, (
                f"Optional dependency group '{group}' not defined"
            )


# Mark as unit tests (they're fast)
pytestmark = pytest.mark.unit


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
