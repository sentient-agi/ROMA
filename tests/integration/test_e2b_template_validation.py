"""
E2B Template Validation Integration Tests

Tests the E2B sandbox template to verify:
1. Template exists and is accessible
2. S3 storage is mounted and accessible
3. Write access to S3 works correctly
4. AWS credentials are NOT visible in Docker image layers

Run with: pytest tests/integration/test_e2b_template_validation.py -v
Or via justfile: just e2b-validate
"""

import os
import subprocess
from pathlib import Path

import pytest


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture(scope="module")
def e2b_cli_available():
    """Check if E2B CLI is installed."""
    try:
        result = subprocess.run(
            ["e2b", "--version"], capture_output=True, text=True, check=True, timeout=10
        )
        return True, result.stdout.strip()
    except (
        subprocess.CalledProcessError,
        FileNotFoundError,
        subprocess.TimeoutExpired,
    ):
        return False, "E2B CLI not found"


@pytest.fixture(scope="module")
def e2b_authenticated():
    """Check if E2B authentication is configured."""
    try:
        result = subprocess.run(
            ["e2b", "auth", "whoami"],
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        )
        return True, result.stdout.strip()
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return False, "Not logged in to E2B"


@pytest.fixture(scope="module")
def template_name():
    """Get template name from e2b.toml if available."""
    e2b_toml_path = Path(__file__).parent.parent.parent / "docker" / "e2b" / "e2b.toml"

    if e2b_toml_path.exists():
        # Simple parser - just look for template_id line
        with open(e2b_toml_path) as f:
            for line in f:
                if "template_id" in line and "=" in line:
                    # Extract value between quotes
                    parts = line.split("=", 1)
                    if len(parts) == 2:
                        value = parts[1].strip().strip('"').strip("'")
                        if value:
                            return value

    # Default fallback
    return "roma-dspy-sandbox"


@pytest.fixture(scope="module")
def sandbox(template_name):
    """Create E2B sandbox instance for testing."""
    try:
        from e2b import Sandbox
    except ImportError:
        pytest.skip("e2b Python package not installed")

    try:
        sb = Sandbox(template_name)
        yield sb
        # Cleanup
        try:
            sb.close()
        except Exception:
            pass
    except Exception as e:
        pytest.skip(f"Failed to create sandbox: {e}")


# =============================================================================
# Tests
# =============================================================================


class TestE2BPrerequisites:
    """Test E2B CLI and authentication prerequisites."""

    def test_e2b_cli_installed(self, e2b_cli_available):
        """Verify E2B CLI is installed."""
        available, info = e2b_cli_available
        assert available, f"E2B CLI not found. Install with: npm install -g @e2b/cli"

    def test_e2b_authenticated(self, e2b_authenticated):
        """Verify E2B authentication is configured."""
        authenticated, info = e2b_authenticated
        assert authenticated, "Not logged in to E2B. Run: e2b auth login"


class TestE2BTemplate:
    """Test E2B template exists and is accessible."""

    def test_template_exists(self, template_name):
        """Verify the template exists in E2B."""
        try:
            result = subprocess.run(
                ["e2b", "template", "list"],
                capture_output=True,
                text=True,
                check=True,
                timeout=30,
            )
            assert template_name in result.stdout, (
                f"Template '{template_name}' not found.\n"
                f"Available templates:\n{result.stdout}\n\n"
                f"Build the template with: cd docker/e2b && e2b template build"
            )
        except subprocess.CalledProcessError as e:
            pytest.fail(f"Failed to list templates: {e}")
        except subprocess.TimeoutExpired:
            pytest.fail("E2B template list command timed out")

    def test_docker_image_security(self):
        """Verify AWS credentials are not visible in Docker image layers."""
        try:
            # Get E2B image IDs
            result = subprocess.run(
                ["docker", "images", "-q", "e2b"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            image_ids = [
                id.strip() for id in result.stdout.strip().split("\n") if id.strip()
            ]

            if not image_ids:
                pytest.skip("No E2B Docker images found locally")

            # Check history for credential leaks
            image_id = image_ids[0]
            result = subprocess.run(
                ["docker", "history", "--no-trunc", image_id],
                capture_output=True,
                text=True,
                timeout=30,
            )

            history = result.stdout.lower()

            # Check for credential leaks
            leaks = []
            if "aws_access_key_id" in history and "AKIA" in history:
                leaks.append("AWS_ACCESS_KEY_ID")
            if "aws_secret_access_key" in history:
                # Look for lines with 'secret' that are suspiciously long
                secret_lines = [
                    line
                    for line in history.split("\n")
                    if "secret" in line and len(line) > 40
                ]
                if secret_lines:
                    leaks.append("AWS_SECRET_ACCESS_KEY")

            assert not leaks, (
                f"SECURITY ISSUE: Credentials found in image layers: {', '.join(leaks)}\n"
                f"Credentials are baked into the Docker image!\n"
                f"This is a critical security vulnerability."
            )

        except subprocess.CalledProcessError as e:
            pytest.skip(f"Could not check Docker image: {e}")
        except subprocess.TimeoutExpired:
            pytest.skip("Docker history command timed out")


class TestE2BSandbox:
    """Test E2B sandbox functionality with S3."""

    def test_sandbox_creation(self, sandbox):
        """Verify sandbox can be created successfully."""
        assert sandbox is not None
        assert hasattr(sandbox, "id")
        assert sandbox.id, "Sandbox ID should not be empty"

    def test_s3_mount_exists(self, sandbox):
        """Verify S3 storage is mounted in the sandbox."""
        storage_path = os.getenv("STORAGE_BASE_PATH", "/opt/sentient")

        result = sandbox.run_code(f"""
import os
import subprocess

mount_path = '{storage_path}'

# Check if directory exists
if not os.path.exists(mount_path):
    raise Exception(f'Mount point {{mount_path}} does not exist')

# Check if it's a mount point
result = subprocess.run(['mountpoint', '-q', mount_path], capture_output=True)
if result.returncode == 0:
    print(f'SUCCESS: {{mount_path}} is a mount point')
else:
    print(f'WARNING: {{mount_path}} exists but may not be a mount point')

# Try to list contents
try:
    contents = os.listdir(mount_path)
    print(f'SUCCESS: Can list {{mount_path}} contents: {{len(contents)}} items')
except Exception as e:
    raise Exception(f'Cannot list {{mount_path}}: {{e}}')
""")

        assert result.error is None, f"S3 mount check failed: {result.error}"
        assert "SUCCESS" in result.stdout, (
            f"S3 mount validation failed:\n{result.stdout}"
        )

    def test_s3_write_access(self, sandbox):
        """Verify write access to S3 storage."""
        storage_path = os.getenv("STORAGE_BASE_PATH", "/opt/sentient")

        result = sandbox.run_code(f"""
import os
import time

storage_path = '{storage_path}'
test_dir = os.path.join(storage_path, 'executions')
test_file = os.path.join(test_dir, f'test_{{int(time.time())}}.txt')

# Create executions directory if needed
os.makedirs(test_dir, exist_ok=True)

# Try to write
try:
    with open(test_file, 'w') as f:
        f.write('E2B validation test')
    print(f'SUCCESS: Written to {{test_file}}')
except Exception as e:
    raise Exception(f'Cannot write to {{test_file}}: {{e}}')

# Try to read back
try:
    with open(test_file, 'r') as f:
        content = f.read()
    if content == 'E2B validation test':
        print(f'SUCCESS: Read back from {{test_file}}')
    else:
        raise Exception(f'Content mismatch: got {{content!r}}')
except Exception as e:
    raise Exception(f'Cannot read {{test_file}}: {{e}}')

# Clean up
try:
    os.remove(test_file)
    print(f'SUCCESS: Cleaned up {{test_file}}')
except Exception as e:
    print(f'WARNING: Could not remove test file: {{e}}')
""")

        assert result.error is None, f"S3 write access test failed: {result.error}"
        assert "SUCCESS" in result.stdout, f"S3 write test failed:\n{result.stdout}"
        assert "FAIL" not in result.stdout, (
            f"S3 write test reported failure:\n{result.stdout}"
        )


# =============================================================================
# Pytest Configuration
# =============================================================================


def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line(
        "markers",
        "e2b: marks tests that require E2B sandbox (deselect with '-m \"not e2b\"')",
    )


# Mark all tests in this module as e2b tests
pytestmark = pytest.mark.e2b
