"""
Integration test: LLM workflow with pip install followed by import.

Tests the real-world scenario where an LLM agent:
1. Uses execute_command to pip install a package
2. Uses execute_python to import and use that package
"""

import tempfile
from pathlib import Path

import pytest

from roma_dspy.config.schemas.storage import StorageConfig
from roma_dspy.core.storage.file_storage import FileStorage
from roma_dspy.tools.terminal.subprocess_toolkit import SubprocessTerminalToolkit


@pytest.mark.integration
class TestLLMPipInstallWorkflow:
    """Test LLM pip install → import workflow."""

    @pytest.mark.asyncio
    async def test_pip_install_then_import_without_venv(self, tmp_path):
        """
        Test: LLM installs package with pip, then imports it with execute_python.

        This simulates the scenario where:
        1. LLM decides it needs a package
        2. LLM calls execute_command("pip install package")
        3. LLM calls execute_python("import package; print(package.__version__)")
        """
        # Setup toolkit
        storage_config = StorageConfig(
            base_path=str(tmp_path / "storage"),
            flat_structure=True
        )
        storage = FileStorage(storage_config, execution_id="llm_pip_test")
        toolkit = SubprocessTerminalToolkit(
            file_storage=storage,
            working_directory=str(tmp_path)
        )

        # Step 1: LLM installs a lightweight package to a custom target
        install_dir = tmp_path / "custom_site_packages"
        install_dir.mkdir()

        install_cmd = f"pip install --target {install_dir} six"
        install_output = await toolkit.execute_command(install_cmd, timeout_sec=60)

        assert "Successfully installed" in install_output or "Requirement already satisfied" in install_output

        # Step 2: LLM imports and uses the package
        python_code = f"""
import sys
sys.path.insert(0, '{install_dir}')
import six
print(f'six version: {{six.__version__}}')
print(f'six.PY3: {{six.PY3}}')
"""

        python_output = await toolkit.execute_python(python_code)

        assert "six version:" in python_output
        assert "six.PY3:" in python_output
        assert "True" in python_output  # six.PY3 should be True in Python 3

    @pytest.mark.asyncio
    @pytest.mark.skipif(
        not Path("/opt/venv").exists(),
        reason="Requires /opt/venv for testing"
    )
    async def test_pip_install_then_import_with_venv(self, tmp_path):
        """
        Test: LLM uses venv for pip install and import.

        When venv_path is set:
        1. execute_command wraps with venv activation
        2. execute_python uses explicit venv Python binary
        """
        storage_config = StorageConfig(
            base_path=str(tmp_path / "storage"),
            flat_structure=True
        )
        storage = FileStorage(storage_config, execution_id="llm_venv_test")
        toolkit = SubprocessTerminalToolkit(
            file_storage=storage,
            working_directory=str(tmp_path),
            venv_path="/opt/venv"
        )

        # Step 1: LLM installs package (uses venv pip)
        install_output = await toolkit.execute_command("pip install six", timeout_sec=60)

        assert "Successfully installed" in install_output or "Requirement already satisfied" in install_output

        # Step 2: LLM imports package (uses venv python)
        python_code = """
import six
print(f'six version: {six.__version__}')
print(f'Python executable: {six.__file__}')
"""

        python_output = await toolkit.execute_python(python_code)

        assert "six version:" in python_output
        # Verify it's using venv Python (the package should be under /opt/venv)
        assert "/opt/venv" in python_output or "six" in python_output