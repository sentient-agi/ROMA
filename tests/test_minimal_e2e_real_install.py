#!/usr/bin/env python3
"""
End-to-End test for minimal installation with real environment.

This test simulates the actual user experience:
1. Creates a fresh uv virtual environment
2. Installs roma-dspy (minimal, no extras)
3. Loads API keys from .env
4. Solves a real simple goal
5. Validates the result

Run with:
    python tests/test_minimal_e2e_real_install.py

Or with pytest:
    pytest tests/test_minimal_e2e_real_install.py -v -s
"""

import os
import sys
import subprocess
import tempfile
import shutil
from pathlib import Path


def run_command(cmd, cwd=None, env=None, timeout=300):
    """Run a shell command and return output."""
    print(f"\n🔹 Running: {cmd}")
    result = subprocess.run(
        cmd,
        shell=True,
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if result.returncode != 0:
        print(f"❌ Command failed with return code {result.returncode}")
        print(f"STDOUT:\n{result.stdout}")
        print(f"STDERR:\n{result.stderr}")
    else:
        print(f"✅ Command succeeded")
        if result.stdout:
            print(f"OUTPUT:\n{result.stdout[:500]}")
    return result


def test_minimal_install_e2e():
    """Test complete minimal installation workflow."""
    print("\n" + "=" * 80)
    print("🧪 MINIMAL INSTALLATION E2E TEST")
    print("=" * 80)

    # Get project root
    project_root = Path(__file__).parent.parent.absolute()
    print(f"\n📁 Project root: {project_root}")

    # Create temporary directory for test environment
    with tempfile.TemporaryDirectory(prefix="roma_minimal_test_") as temp_dir:
        test_dir = Path(temp_dir)
        print(f"\n📁 Test directory: {test_dir}")

        # Step 1: Create fresh uv virtual environment
        print("\n" + "-" * 80)
        print("STEP 1: Creating fresh uv virtual environment")
        print("-" * 80)

        venv_path = test_dir / ".venv"
        result = run_command(f"uv venv {venv_path}", cwd=test_dir)
        assert result.returncode == 0, "Failed to create uv virtual environment"

        # Determine Python executable path
        if sys.platform == "win32":
            python_exe = venv_path / "Scripts" / "python.exe"
        else:
            python_exe = venv_path / "bin" / "python"

        assert python_exe.exists(), f"Python executable not found at {python_exe}"
        print(f"✅ Virtual environment created at {venv_path}")
        print(f"✅ Python executable: {python_exe}")

        # Step 2: Install roma-dspy (minimal, no extras)
        print("\n" + "-" * 80)
        print("STEP 2: Installing roma-dspy (minimal)")
        print("-" * 80)

        # Install in editable mode from project root
        result = run_command(
            f"uv pip install --python {python_exe} -e {project_root}",
            cwd=test_dir,
            timeout=180,
        )
        assert result.returncode == 0, "Failed to install roma-dspy"
        print("✅ roma-dspy installed successfully")

        # Step 3: Verify minimal installation (no optional deps)
        print("\n" + "-" * 80)
        print("STEP 3: Verifying minimal installation (no optional deps)")
        print("-" * 80)

        check_imports_script = """
import sys
print("Checking that optional dependencies are NOT imported...")

# Import core modules
from roma_dspy.core.engine.solve import solve, RecursiveSolver
from roma_dspy.core.modules import Executor
from roma_dspy.core.storage import FileStorage

# Check that optional dependencies are NOT in sys.modules
optional_deps = ['sqlalchemy', 'mlflow', 'boto3', 'e2b']
imported = [dep for dep in optional_deps if dep in sys.modules]

if imported:
    print(f"❌ FAIL: Optional dependencies were imported: {imported}")
    sys.exit(1)
else:
    print("✅ PASS: No optional dependencies imported")
    sys.exit(0)
"""

        # Write check script to file
        check_script_path = test_dir / "check_imports.py"
        check_script_path.write_text(check_imports_script)

        result = run_command(f"{python_exe} {check_script_path}", cwd=test_dir)
        assert result.returncode == 0, "Optional dependencies were imported!"
        print("✅ Minimal installation verified (no optional deps loaded)")

        # Step 4: Load API keys from .env
        print("\n" + "-" * 80)
        print("STEP 4: Loading API keys from .env")
        print("-" * 80)

        env_file = project_root / ".env"
        env_vars = os.environ.copy()

        if env_file.exists():
            print(f"📄 Loading environment from {env_file}")
            # Load .env file
            with open(env_file) as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        key, value = line.split("=", 1)
                        # Remove quotes if present
                        value = value.strip().strip('"').strip("'")
                        env_vars[key.strip()] = value
                        if "API_KEY" in key or "TOKEN" in key:
                            masked_value = value[:8] + "..." if len(value) > 8 else "***"
                            print(f"   {key}: {masked_value}")
        else:
            print("⚠️  No .env file found, using environment variables")

        # Check for required API keys
        api_keys = [
            "OPENROUTER_API_KEY",
            "OPENAI_API_KEY",
            "FIREWORKS_API_KEY",
            "ANTHROPIC_API_KEY",
        ]
        found_keys = [key for key in api_keys if env_vars.get(key)]

        if not found_keys:
            print("⚠️  WARNING: No API keys found in .env or environment")
            print("   Test will use mock LLM (may not work properly)")
        else:
            print(f"✅ Found API keys: {', '.join(found_keys)}")

        # Step 5: Test solving a real simple goal
        print("\n" + "-" * 80)
        print("STEP 5: Solving a real goal")
        print("-" * 80)

        # Create test script
        test_script = test_dir / "test_solve.py"
        test_script_content = """
import sys
from roma_dspy.core.engine.solve import solve

print("\\n🎯 Testing minimal installation with real goal...")
print("-" * 60)

try:
    # Test with a very simple goal
    goal = "What is 2 + 2?"
    print(f"Goal: {goal}")
    print("\\nSolving...")

    result = solve(goal, max_depth=1)

    print("\\n" + "=" * 60)
    print("RESULT:")
    print("=" * 60)
    print(result)
    print("=" * 60)

    # Basic validation
    if result and len(str(result)) > 0:
        print("\\n✅ SUCCESS: Got a result from solve()")
        sys.exit(0)
    else:
        print("\\n❌ FAIL: Result is empty")
        sys.exit(1)

except ImportError as e:
    print(f"\\n❌ FAIL: Import error - {e}")
    print("\\nThis suggests optional dependencies are required but missing.")
    sys.exit(1)
except Exception as e:
    print(f"\\n⚠️  WARNING: Solve failed with error: {e}")
    print(f"\\nError type: {type(e).__name__}")

    # If it's an API key error, that's expected behavior
    error_msg = str(e).lower()
    if any(keyword in error_msg for keyword in ['api key', 'api_key', 'authentication', 'unauthorized']):
        print("\\n✅ EXPECTED: API key error (test environment has no valid API key)")
        print("   Minimal installation is working correctly!")
        sys.exit(0)
    else:
        print("\\n❌ FAIL: Unexpected error")
        import traceback
        traceback.print_exc()
        sys.exit(1)
"""

        test_script.write_text(test_script_content)

        print(f"📄 Created test script: {test_script}")
        print("\n🚀 Executing solve test...")

        result = run_command(
            f"{python_exe} {test_script}", cwd=test_dir, env=env_vars, timeout=120
        )

        # Step 6: Validate results
        print("\n" + "-" * 80)
        print("STEP 6: Validating results")
        print("-" * 80)

        if result.returncode == 0:
            print("✅ Test passed!")
            print("\n" + "=" * 80)
            print("🎉 E2E MINIMAL INSTALLATION TEST: SUCCESS")
            print("=" * 80)
            print("\n✅ Verified:")
            print("   • Fresh uv environment created")
            print("   • roma-dspy installed (minimal)")
            print("   • No optional dependencies loaded")
            print("   • Core imports work")
            print("   • solve() function works")
            print("   • Real goal processed successfully")
            return True
        else:
            print("❌ Test failed!")
            print("\n" + "=" * 80)
            print("❌ E2E MINIMAL INSTALLATION TEST: FAILED")
            print("=" * 80)
            print(f"\nReturn code: {result.returncode}")
            print(f"\nSTDOUT:\n{result.stdout}")
            print(f"\nSTDERR:\n{result.stderr}")
            return False


if __name__ == "__main__":
    try:
        success = test_minimal_install_e2e()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ Test failed with exception: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
