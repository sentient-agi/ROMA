"""
Test CLI works in minimal install (without TUI/textual).

This smoke test ensures the CLI can be imported and basic commands
work even when optional dependencies like textual are not installed.
"""

import subprocess
import sys
import pytest


class TestCLIMinimalInstall:
    """Test CLI functionality in minimal installation."""

    def test_cli_module_imports_without_textual(self):
        """Test that CLI module can be imported without textual installed."""
        # This test assumes textual is available in dev, so we just verify
        # that the import structure is correct (lazy imports)
        from roma_dspy import cli

        assert hasattr(cli, "app")
        assert hasattr(cli, "solve")
        assert hasattr(cli, "config")
        assert hasattr(cli, "version")

    def test_cli_help_command(self):
        """Test that CLI --help works without textual."""
        result = subprocess.run(
            [sys.executable, "-m", "roma_dspy.cli", "--help"],
            capture_output=True,
            text=True,
            timeout=10,
        )

        assert result.returncode == 0
        assert "ROMA-DSPy" in result.stdout
        assert "Hierarchical task decomposition" in result.stdout

    def test_cli_version_command(self):
        """Test that CLI version command works."""
        result = subprocess.run(
            [sys.executable, "-m", "roma_dspy.cli", "version"],
            capture_output=True,
            text=True,
            timeout=10,
        )

        assert result.returncode == 0
        assert "ROMA-DSPy" in result.stdout

    def test_cli_config_show_command(self):
        """Test that config show command works."""
        result = subprocess.run(
            [sys.executable, "-m", "roma_dspy.cli", "config"],
            capture_output=True,
            text=True,
            timeout=10,
        )

        # Should succeed and show config
        assert result.returncode == 0
        # Should show runtime config
        assert "Runtime" in result.stdout or "runtime" in result.stdout.lower()

    def test_viz_command_fails_gracefully_without_tui(self, monkeypatch):
        """Test that viz command fails gracefully when TUI not installed."""
        # This test would need textual to not be installed, which is hard to test
        # in dev environment. Instead, we verify the lazy import structure exists.
        import inspect
        from roma_dspy import cli

        # Get the viz_interactive function
        viz_func = cli.viz_interactive

        # Check that it has the try/except for lazy TUI import
        source = inspect.getsource(viz_func)
        assert "from roma_dspy.tui import run_viz" in source
        assert "ImportError" in source
        assert "TUI dependencies not installed" in source


class TestCLIErrorMessages:
    """Test that CLI provides helpful error messages."""

    def test_viz_error_message_suggests_tui_extra(self):
        """Verify viz command error suggests installing [tui] extra."""
        import inspect
        from roma_dspy import cli

        source = inspect.getsource(cli.viz_interactive)

        # Should suggest the correct installation command
        assert "pip install 'roma-dspy[tui]'" in source or "uv pip install 'roma-dspy[tui]'" in source

    def test_export_error_message_suggests_tui_extra(self):
        """Verify export command error suggests installing [tui] extra."""
        import inspect
        from roma_dspy import cli

        source = inspect.getsource(cli.exec_export)

        # Should suggest the correct installation command
        assert "pip install 'roma-dspy[tui]'" in source or "uv pip install 'roma-dspy[tui]'" in source


@pytest.mark.integration
class TestCLIMinimalE2E:
    """End-to-end tests for minimal CLI functionality."""

    def test_cli_can_load_config_and_show_help(self):
        """Integration test: Load config and show commands."""
        # Test that basic CLI workflow works
        result1 = subprocess.run(
            [sys.executable, "-m", "roma_dspy.cli", "--help"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result1.returncode == 0

        result2 = subprocess.run(
            [sys.executable, "-m", "roma_dspy.cli", "config"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result2.returncode == 0

        # Both commands should complete successfully
        assert "Commands" in result1.stdout
        assert "Runtime" in result2.stdout or "runtime" in result2.stdout.lower()
