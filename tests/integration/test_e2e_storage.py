"""End-to-end integration tests for storage and E2B system.

Tests the complete flow:
1. Host writes file to S3 via FileStorage
2. E2B sandbox reads same file via goofys mount
3. E2B writes result back to S3
4. Host reads E2B result

Run with: pytest tests/integration/test_e2e_storage.py -v -s
"""

import json
import os
import pytest
import asyncio
from pathlib import Path

from roma_dspy.config.manager import ConfigManager
from roma_dspy.core.storage import FileStorage
from roma_dspy.tools.core.e2b import E2BToolkit


# Skip all tests if required env vars not set
pytestmark = pytest.mark.skipif(
    not all(
        [
            os.getenv("E2B_API_KEY"),
            os.getenv("ROMA_S3_BUCKET"),
            os.getenv("AWS_ACCESS_KEY_ID"),
            os.getenv("AWS_SECRET_ACCESS_KEY"),
        ]
    ),
    reason="E2B and S3 credentials not set - skipping E2E tests",
)


class TestE2EStorageIntegration:
    """End-to-end storage and E2B integration tests."""

    @pytest.fixture
    async def config(self):
        """Load configuration."""
        return ConfigManager().load_config()

    @pytest.fixture
    async def storage(self, config):
        """Create FileStorage for testing."""
        execution_id = f"e2e_test_{os.getpid()}"
        return FileStorage(config=config.storage, execution_id=execution_id)

    @pytest.fixture
    async def e2b_toolkit(self):
        """Create E2B toolkit."""
        toolkit = E2BToolkit(timeout=300)
        yield toolkit
        # Cleanup
        toolkit.close()

    @pytest.mark.asyncio
    async def test_complete_storage_flow(self, storage, e2b_toolkit):
        """Test complete storage flow: host write → E2B read → E2B write → host read."""

        # Step 1: Host writes file to storage
        test_data = "Hello from host! This is a test message."
        test_key = "e2e_test_input.txt"

        await storage.put_text(test_key, test_data)
        input_path = storage.get_artifacts_path(test_key)

        print(f"\n✓ Host wrote file to: {input_path}")
        assert input_path.exists(), "File should exist after write"

        # Step 2: E2B reads file from storage
        read_code = f"""
import os

# Read input file
input_path = '{input_path}'
print(f'Reading from: {{input_path}}')

with open(input_path, 'r') as f:
    content = f.read()
    print(f'Content: {{content}}')

# Verify we can read it
assert content == '{test_data}', f'Content mismatch: {{content}}'
print('✓ Successfully read file in E2B')
"""

        result = e2b_toolkit.run_python_code(read_code)
        result_data = json.loads(result)

        print(f"\n✓ E2B read result: {result_data['stdout']}")
        assert result_data["success"], f"E2B read failed: {result_data.get('error')}"
        assert "Successfully read file in E2B" in str(result_data["stdout"])

        # Step 3: E2B writes processed result back to storage
        output_key = "e2e_test_output.txt"
        output_path = storage.get_outputs_path(output_key)

        write_code = f"""
# Process data (simple transformation)
processed_data = '{test_data}'.upper() + ' (processed by E2B)'

# Write to output path
output_path = '{output_path}'
print(f'Writing to: {{output_path}}')

with open(output_path, 'w') as f:
    f.write(processed_data)

print('✓ Successfully wrote output file')
"""

        result = e2b_toolkit.run_python_code(write_code)
        result_data = json.loads(result)

        print(f"\n✓ E2B write result: {result_data['stdout']}")
        assert result_data["success"], f"E2B write failed: {result_data.get('error')}"

        # Step 4: Host reads E2B output
        # Wait a moment for S3 sync
        await asyncio.sleep(2)

        output_content = await storage.get_text(f"outputs/{output_key}")

        print(f"\n✓ Host read E2B output: {output_content}")
        assert output_content is not None, "Output file should exist"
        assert "PROCESSED BY E2B" in output_content, "Output should be processed"
        assert test_data.upper() in output_content, "Should contain transformed data"

        print("\n✅ Complete E2E flow successful!")

    @pytest.mark.asyncio
    async def test_storage_path_consistency(self, storage, e2b_toolkit):
        """Test that storage paths are consistent between host and E2B."""

        # Get all storage paths
        paths_to_test = {
            "artifacts": storage.get_artifacts_path(),
            "temp": storage.get_temp_path(),
            "results": storage.get_results_path(),
            "plots": storage.get_plots_path(),
            "reports": storage.get_reports_path(),
            "outputs": storage.get_outputs_path(),
            "logs": storage.get_logs_path(),
        }

        # Verify paths exist on E2B
        verify_code = f"""
import os

paths = {paths_to_test}

for name, path in paths.items():
    path_str = str(path)
    exists = os.path.exists(path_str)
    print(f'{{name}}: {{path_str}} - {{\"EXISTS\" if exists else \"MISSING\"}}')

    if not exists:
        raise AssertionError(f'Path missing: {{path_str}}')

print('✓ All paths exist in E2B sandbox')
"""

        result = e2b_toolkit.run_python_code(verify_code)
        result_data = json.loads(result)

        print(f"\n✓ Path verification: {result_data['stdout']}")
        assert result_data["success"], (
            f"Path verification failed: {result_data.get('error')}"
        )

    @pytest.mark.asyncio
    async def test_large_file_transfer(self, storage, e2b_toolkit):
        """Test transfer of larger files through storage."""

        # Create a larger test file (1MB of JSON data)
        large_data = {
            "test": "data",
            "numbers": list(range(10000)),
            "metadata": {"size": "large", "purpose": "testing"},
        }
        large_json = json.dumps(large_data, indent=2)

        test_key = "large_test.json"
        await storage.put_text(test_key, large_json)

        file_path = storage.get_artifacts_path(test_key)

        # Read and validate in E2B
        read_code = f"""
import json

file_path = '{file_path}'

with open(file_path, 'r') as f:
    data = json.load(f)

# Validate structure
assert 'numbers' in data, 'Missing numbers key'
assert len(data['numbers']) == 10000, f'Wrong count: {{len(data["numbers"])}}'
assert data['metadata']['size'] == 'large', 'Wrong metadata'

print(f'✓ Successfully read large file ({{len(data["numbers"])}} numbers)')
"""

        result = e2b_toolkit.run_python_code(read_code)
        result_data = json.loads(result)

        assert result_data["success"], (
            f"Large file test failed: {result_data.get('error')}"
        )
        print(f"\n✓ Large file transfer successful")

    @pytest.mark.asyncio
    async def test_concurrent_storage_access(self, storage, e2b_toolkit):
        """Test concurrent access to storage from E2B."""

        # Write multiple files
        for i in range(5):
            await storage.put_text(f"concurrent_test_{i}.txt", f"File {i} content")

        # Read all files concurrently in E2B
        read_all_code = f"""
import os
from concurrent.futures import ThreadPoolExecutor

artifacts_path = '{storage.get_artifacts_path()}'

def read_file(i):
    file_path = os.path.join(artifacts_path, f'concurrent_test_{{i}}.txt')
    with open(file_path, 'r') as f:
        content = f.read()
    return f'File {{i}}: {{content}}'

with ThreadPoolExecutor(max_workers=5) as executor:
    results = list(executor.map(read_file, range(5)))

for result in results:
    print(result)

print('✓ Concurrent reads successful')
"""

        result = e2b_toolkit.run_python_code(read_all_code)
        result_data = json.loads(result)

        assert result_data["success"], (
            f"Concurrent access failed: {result_data.get('error')}"
        )
        print(f"\n✓ Concurrent access successful")

    @pytest.mark.asyncio
    async def test_environment_variables_passed(self, e2b_toolkit):
        """Test that required environment variables are passed to E2B."""

        check_env_code = """
import os

required_vars = [
    'STORAGE_BASE_PATH',
    'ROMA_S3_BUCKET',
    'AWS_ACCESS_KEY_ID',
    'AWS_SECRET_ACCESS_KEY',
    'AWS_REGION'
]

for var in required_vars:
    value = os.getenv(var)
    if not value:
        raise AssertionError(f'Missing env var: {var}')
    # Don't print sensitive values, just confirm they exist
    if 'KEY' in var or 'SECRET' in var:
        print(f'{var}: ***')
    else:
        print(f'{var}: {value}')

print('✓ All required env vars present')
"""

        result = e2b_toolkit.run_python_code(check_env_code)
        result_data = json.loads(result)

        print(f"\n✓ Environment variables: {result_data['stdout']}")
        assert result_data["success"], (
            f"Env var check failed: {result_data.get('error')}"
        )

    @pytest.mark.asyncio
    async def test_storage_cleanup(self, config):
        """Test storage cleanup functionality."""

        # Create temp storage
        temp_storage = FileStorage(
            config=config.storage, execution_id=f"cleanup_test_{os.getpid()}"
        )

        # Write temp files
        for i in range(3):
            await temp_storage.put_text(f"temp/test_{i}.txt", f"Temp file {i}")

        # Verify files exist
        temp_files = await temp_storage.list_keys("temp/")
        assert len(temp_files) == 3, "Should have 3 temp files"

        # Cleanup temp files
        cleaned = await temp_storage.cleanup_execution_temp_files()
        assert cleaned == 3, f"Should clean 3 files, cleaned {cleaned}"

        # Verify cleanup
        remaining_files = await temp_storage.list_keys("temp/")
        assert len(remaining_files) == 0, "Temp files should be cleaned"

        print(f"\n✓ Cleanup successful: removed {cleaned} files")


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v", "-s"])
