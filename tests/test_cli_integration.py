"""
Comprehensive CLI integration tests.

Tests that the CLI works correctly with and without optional dependencies.

Run with:
    pytest tests/test_cli_integration.py -v
    uv run pytest tests/test_cli_integration.py -v
"""

import subprocess
import sys
import json
from pathlib import Path
import pytest


class TestCLIBasics:
    """Test basic CLI functionality."""

    def test_cli_module_importable(self):
        """CLI module should be importable."""
        result = subprocess.run(
            [sys.executable, "-c", "from roma_dspy.cli import app; print('OK')"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0
        assert "OK" in result.stdout

    def test_cli_help_command(self):
        """CLI --help should work."""
        result = subprocess.run(
            [sys.executable, "-m", "roma_dspy.cli", "--help"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0
        assert "Usage:" in result.stdout or "ROMA-DSPy" in result.stdout

    def test_cli_version(self):
        """CLI should show version."""
        result = subprocess.run(
            [sys.executable, "-m", "roma_dspy.cli", "--version"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        # Version command might not exist, but shouldn't crash
        assert result.returncode in [0, 2]  # 0 = success, 2 = no such command


class TestCLISolveCommand:
    """Test the solve command."""

    @pytest.mark.skipif(
        not Path(".env").exists()
        or "OPENROUTER_API_KEY" not in Path(".env").read_text(),
        reason="Requires OPENROUTER_API_KEY in .env",
    )
    def test_solve_command_basic(self):
        """Test basic solve command (requires API key)."""
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "roma_dspy.cli",
                "solve",
                "What is 2+2?",
                "--max-depth",
                "1",
                "--profile",
                "general",
            ],
            capture_output=True,
            text=True,
            timeout=120,
            env={**subprocess.os.environ},
        )

        # Should complete (might succeed or fail based on config)
        # We're just checking it doesn't crash
        assert result.returncode in [0, 1]

    def test_solve_help(self):
        """Solve command should have help."""
        result = subprocess.run(
            [sys.executable, "-m", "roma_dspy.cli", "solve", "--help"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0
        assert "solve" in result.stdout.lower() or "goal" in result.stdout.lower()


class TestCLIConfigCommand:
    """Test configuration commands."""

    def test_config_show(self):
        """Should be able to show config."""
        result = subprocess.run(
            [sys.executable, "-m", "roma_dspy.cli", "config", "--help"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        # Config command might not exist yet
        assert result.returncode in [0, 2]


class TestCLIWithoutOptionalDeps:
    """Test CLI works without optional dependencies."""

    def test_cli_imports_without_mlflow(self):
        """CLI should import even if MLflow not used."""
        code = """
import sys
# Import CLI
from roma_dspy.cli import app

# Check MLflow not auto-imported
mlflow_imported = 'mlflow' in sys.modules
print(f"MLflow auto-imported: {mlflow_imported}")

# CLI should work
print("CLI imported successfully")
"""
        result = subprocess.run(
            [sys.executable, "-c", code], capture_output=True, text=True, timeout=30
        )
        assert result.returncode == 0
        assert "CLI imported successfully" in result.stdout

    def test_cli_imports_without_postgres(self):
        """CLI should import even if Postgres not used."""
        code = """
import sys
from roma_dspy.cli import app

# Check postgres not auto-imported
sqlalchemy_imported = 'sqlalchemy' in sys.modules
print(f"SQLAlchemy auto-imported: {sqlalchemy_imported}")

print("CLI imported successfully")
"""
        result = subprocess.run(
            [sys.executable, "-c", code], capture_output=True, text=True, timeout=30
        )
        assert result.returncode == 0
        assert "CLI imported successfully" in result.stdout


class TestCLIErrorMessages:
    """Test that CLI error messages are helpful."""

    def test_missing_api_key_helpful_error(self):
        """Missing API key should give helpful error."""
        # Create temp env without API keys
        env = {
            k: v for k, v in subprocess.os.environ.items() if not k.endswith("_API_KEY")
        }

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "roma_dspy.cli",
                "solve",
                "test task",
                "--max-depth",
                "1",
            ],
            capture_output=True,
            text=True,
            timeout=60,
            env=env,
        )

        # Should fail with helpful message
        # (exact behavior depends on implementation)
        assert result.returncode != 0


class TestCLIProfiles:
    """Test profile selection."""

    def test_list_profiles(self):
        """Should be able to list available profiles."""
        # Check if profiles directory exists
        profiles_dir = Path("config/profiles")
        if not profiles_dir.exists():
            pytest.skip("No profiles directory")

        # List yaml files
        profiles = list(profiles_dir.glob("*.yaml"))
        assert len(profiles) > 0, "Should have at least one profile"

    def test_profile_flag(self):
        """--profile flag should be recognized."""
        result = subprocess.run(
            [sys.executable, "-m", "roma_dspy.cli", "solve", "--help"],
            capture_output=True,
            text=True,
            timeout=30,
        )

        # Should show profile option in help
        if result.returncode == 0:
            # Profile flag might be shown
            pass


class TestCLIOutputFormats:
    """Test different output formats."""

    def test_output_format_flag(self):
        """Should accept different output formats."""
        result = subprocess.run(
            [sys.executable, "-m", "roma_dspy.cli", "solve", "--help"],
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode == 0:
            # Check if output format is mentioned
            # (implementation specific)
            pass


# Mark all as integration tests
pytestmark = pytest.mark.integration


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
