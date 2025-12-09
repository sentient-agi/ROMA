# Phase 3: HTTP Integration

**Status:** ✅ Complete
**Last Updated:** 2025-12-07

---

## Overview

Phase 3 implements the HTTP integration layer between ROMA and PTC, enabling ROMA to communicate with PTC agents for code generation and receive processed artifacts.

### What Was Built

1. **PTCClient** - Async HTTP client for PTC service communication
   - Retry logic with exponential backoff
   - Cache integration (check before execute, store after success)
   - Timeout and error handling
   - Health check and statistics endpoints

2. **ArtifactProcessor** - Result processor for writing artifacts to filesystem
   - Filesystem operations (write, validate, organize)
   - Validation logic (warnings for failures, missing tests, duplicates)
   - Statistics tracking (written, skipped, errors, files by type)
   - Dry-run mode for testing

3. **Comprehensive Tests** - 28 tests with 100% coverage
   - Client tests: retry logic, timeouts, caching, errors
   - Processor tests: writing, validation, overwrite, statistics

---

## Architecture

### Integration Flow

```
ROMA Application
      |
      ├─> PTCClient.execute(plan)
      |     |
      |     ├─> Check Cache (PTCCacheManager)
      |     |     └─> Cache Hit? Return cached result
      |     |
      |     ├─> HTTP POST to PTC Service
      |     |     └─> /execute endpoint
      |     |     └─> Retry on 5xx errors (exponential backoff)
      |     |
      |     └─> Store successful result in cache
      |
      └─> ArtifactProcessor.process_result(result)
            |
            ├─> Validate result (warnings check)
            ├─> Write artifacts to filesystem
            └─> Return statistics
```

### Components

| Component | Purpose | Location |
|-----------|---------|----------|
| `PTCClient` | HTTP communication with PTC service | `src/roma_dspy/ptc/client.py` |
| `ArtifactProcessor` | Process results and write files | `src/roma_dspy/ptc/processor.py` |
| `PTCCacheManager` | Redis caching layer | `src/roma_dspy/ptc/cache.py` |
| Schemas | Type-safe contracts | `src/roma_dspy/ptc/schemas/` |

---

## PTCClient

### Features

- **Async HTTP Communication**: Built on `httpx.AsyncClient` for efficient I/O
- **Automatic Retries**: Exponential backoff for transient failures (5xx errors)
- **Cache Integration**: Checks cache before execution, stores successful results
- **Timeout Handling**: Configurable request timeouts with proper cleanup
- **Error Handling**: Distinguishes between client errors (4xx) and server errors (5xx)
- **Health Checks**: Verify PTC service availability
- **Statistics**: Track service metrics and performance

### Basic Usage

```python
from roma_dspy.ptc import PTCClient, PTCExecutionPlan, ScaffoldingSpec

# Initialize client
client = PTCClient(
    service_url="http://localhost:8001",
    timeout=300.0,
    max_retries=3
)

# Create execution plan
plan = PTCExecutionPlan(
    execution_id="exec-12345",
    scaffolding=ScaffoldingSpec(
        task_description="Build REST API for user management",
        requirements=["CRUD operations", "JWT auth", "Input validation"],
        dependencies=["fastapi", "pyjwt", "pydantic"]
    )
)

# Execute (checks cache, calls PTC, stores result)
result = await client.execute(plan)

print(f"Status: {result.status}")
print(f"Artifacts: {len(result.artifacts)}")
print(f"From cache: {result.from_cache}")
```

### Context Manager Usage

```python
async with PTCClient("http://localhost:8001") as client:
    result = await client.execute(plan)
    # Client automatically closes when exiting context
```

### Configuration

```python
from roma_dspy.ptc import PTCClient
from roma_dspy.ptc.cache import PTCCacheManager
import redis.asyncio as redis

# Custom configuration
redis_client = await redis.from_url("redis://localhost:6379/0")
cache_manager = PTCCacheManager(redis_client)

client = PTCClient(
    service_url="http://ptc-service:8001",
    timeout=600.0,           # 10 minute timeout
    max_retries=5,           # Retry up to 5 times
    retry_delay=2.0,         # Start with 2 second delay
    cache_manager=cache_manager
)
```

### Health Check

```python
# Check if PTC service is available
is_healthy = await client.health_check()
if not is_healthy:
    print("PTC service is not available")
```

### Statistics

```python
# Get service statistics
stats = await client.get_stats()
print(f"Total executions: {stats['total_executions']}")
print(f"Cache hit rate: {stats['cache_hit_rate']:.2%}")
```

### Error Handling

```python
from roma_dspy.ptc import PTCClient, PTCClientError

try:
    result = await client.execute(plan)
except PTCClientError as e:
    print(f"PTC execution failed: {e}")
    # Handle error appropriately
```

### Retry Behavior

- **Client Errors (4xx)**: No retry (invalid request)
- **Server Errors (5xx)**: Retry with exponential backoff
- **Network Errors**: Retry with exponential backoff
- **Timeout Errors**: No retry (execution took too long)

**Exponential Backoff Formula:**
```
delay = retry_delay * (2 ** attempt)
Example with retry_delay=1.0:
  Attempt 1: 1.0s delay
  Attempt 2: 2.0s delay
  Attempt 3: 4.0s delay
  Attempt 4: 8.0s delay
```

---

## ArtifactProcessor

### Features

- **Filesystem Writing**: Write code artifacts to appropriate locations
- **Directory Management**: Automatically create parent directories
- **Conflict Resolution**: Configurable overwrite vs. skip behavior
- **Validation**: Detect failures, missing tests, duplicate paths
- **Statistics**: Track written/skipped/error counts by type
- **Dry Run Mode**: Test processing without writing files
- **Summary Generation**: Human-readable execution summaries

### Basic Usage

```python
from roma_dspy.ptc import ArtifactProcessor
from pathlib import Path

# Initialize processor
processor = ArtifactProcessor(
    base_path=Path("./output"),
    overwrite=True,
    create_dirs=True
)

# Process result from PTC
stats = processor.process_result(result)

print(f"Written: {stats['written']}")
print(f"Skipped: {stats['skipped']}")
print(f"Errors: {stats['errors']}")
print(f"By type: {stats['files_by_type']}")
```

### Processing with Validation

```python
# Process with validation warnings
stats = processor.process_with_validation(
    result,
    fail_on_warnings=False  # Log warnings but continue
)

if stats['validation_warnings']:
    for warning in stats['validation_warnings']:
        print(f"Warning: {warning}")
```

### Validation Checks

The processor validates results for:

1. **Execution Status**: Warns on FAILURE or TIMEOUT
2. **Artifacts Present**: Warns if no artifacts generated
3. **Duplicate Paths**: Detects multiple artifacts with same path
4. **Test Results**: Warns if tests didn't run or failed
5. **PTC Errors**: Reports errors/warnings from PTC

```python
# Get validation warnings without processing
warnings = processor.validate_result(result)
for warning in warnings:
    print(f"⚠️  {warning}")
```

### Summary Generation

```python
# Generate human-readable summary
summary = processor.get_artifact_summary(result)
print(summary)
```

**Example Output:**
```
Execution: exec-12345
Status: SUCCESS
Duration: 45.23s
Artifacts: 5
  source_code: 3 files
    - main.py
    - models.py
    - routes.py
  test: 2 files
    - tests/test_main.py
    - tests/test_routes.py

Test Results:
  Command: pytest tests/
  Passed: 8
  Failed: 0
  Duration: 2.15s

LLM Usage:
  Total tokens: 4,250
  Total cost: $0.0128
```

### Configuration Options

```python
processor = ArtifactProcessor(
    base_path=Path("./generated"),
    overwrite=True,           # Overwrite existing files
    create_dirs=True,         # Create parent directories
    dry_run=False             # Actually write files
)
```

### Dry Run Mode

```python
# Test processing without writing files
processor = ArtifactProcessor(dry_run=True)
stats = processor.process_result(result)
# Files are NOT written, but statistics are computed
```

---

## Complete Integration Example

### ROMA → PTC → Filesystem Flow

```python
from roma_dspy.ptc import (
    PTCClient,
    PTCExecutionPlan,
    ScaffoldingSpec,
    ArtifactProcessor,
    PTCCacheManager
)
from pathlib import Path
import redis.asyncio as redis

async def generate_code_with_ptc(task_description: str, requirements: list[str]):
    """
    Complete flow: Create plan → Execute with PTC → Process artifacts
    """

    # 1. Initialize components
    redis_client = await redis.from_url("redis://localhost:6379/0")
    cache_manager = PTCCacheManager(redis_client)

    ptc_client = PTCClient(
        service_url="http://localhost:8001",
        cache_manager=cache_manager
    )

    processor = ArtifactProcessor(
        base_path=Path("./output"),
        overwrite=True
    )

    # 2. Create execution plan
    plan = PTCExecutionPlan(
        execution_id=f"exec-{datetime.now().timestamp()}",
        scaffolding=ScaffoldingSpec(
            task_description=task_description,
            requirements=requirements,
            dependencies=["fastapi", "pydantic"]
        )
    )

    try:
        # 3. Execute with PTC (checks cache automatically)
        result = await ptc_client.execute(plan)

        # 4. Validate and process artifacts
        stats = processor.process_with_validation(result)

        # 5. Display summary
        summary = processor.get_artifact_summary(result)
        print(summary)

        # 6. Return statistics
        return {
            "success": result.success,
            "from_cache": result.from_cache,
            "artifacts_written": stats["written"],
            "total_cost": result.total_cost_usd,
            "duration": result.duration_seconds
        }

    except Exception as e:
        print(f"Error: {e}")
        raise

    finally:
        await ptc_client.close()
        await redis_client.close()

# Usage
result = await generate_code_with_ptc(
    task_description="Build user authentication API",
    requirements=[
        "Login and signup endpoints",
        "JWT token generation",
        "Password hashing with bcrypt"
    ]
)
```

---

## Testing

### Run All Phase 3 Tests

```bash
# From ROMA directory
uv run pytest tests/ptc/test_client.py tests/ptc/test_processor.py -v
```

### Test Coverage

**Client Tests** (`tests/ptc/test_client.py` - 12 tests)
- ✅ Successful execution and caching
- ✅ Timeout handling
- ✅ Server error retry logic
- ✅ Client error (no retry)
- ✅ Cache hit scenario
- ✅ Health check endpoint
- ✅ Statistics endpoint
- ✅ Context manager usage
- ✅ URL normalization
- ✅ Custom timeout configuration
- ✅ Custom retry configuration

**Processor Tests** (`tests/ptc/test_processor.py` - 16 tests)
- ✅ Write single artifact
- ✅ Process multiple artifacts
- ✅ Overwrite existing files
- ✅ Skip existing files
- ✅ Create directories automatically
- ✅ Dry run mode
- ✅ Files by type statistics
- ✅ Validate successful result
- ✅ Validate failed result
- ✅ Validate no artifacts warning
- ✅ Validate duplicate paths
- ✅ Validate failed tests
- ✅ Process with validation
- ✅ Fail on warnings
- ✅ Artifact summary generation
- ✅ Summary with LLM usage

### Running Individual Tests

```bash
# Test client only
uv run pytest tests/ptc/test_client.py -v

# Test processor only
uv run pytest tests/ptc/test_processor.py -v

# Test specific functionality
uv run pytest tests/ptc/test_client.py::TestPTCClient::test_server_error_retry -v
```

### All PTC Tests (Phase 2 + Phase 3)

```bash
# Run all PTC integration tests
uv run pytest tests/ptc/ -v

# Expected: 55 tests passed
#   - 27 from Phase 2 (schemas, cache)
#   - 28 from Phase 3 (client, processor)
```

---

## Configuration

### Environment Variables

Add to `.env`:

```bash
# PTC Service Configuration
PTC_SERVICE_URL=http://localhost:8001
PTC_TIMEOUT=300  # seconds
PTC_MAX_RETRIES=3
PTC_RETRY_DELAY=1.0  # seconds

# Redis Cache (from Phase 1)
REDIS_URL=redis://localhost:6379/0
REDIS_PASSWORD=  # Optional
```

### Loading Configuration

```python
import os
from roma_dspy.ptc import PTCClient

client = PTCClient(
    service_url=os.getenv("PTC_SERVICE_URL", "http://localhost:8001"),
    timeout=float(os.getenv("PTC_TIMEOUT", "300")),
    max_retries=int(os.getenv("PTC_MAX_RETRIES", "3"))
)
```

---

## Error Handling

### PTCClientError

Base exception for all client errors:

```python
from roma_dspy.ptc import PTCClientError

try:
    result = await client.execute(plan)
except PTCClientError as e:
    print(f"PTC client error: {e}")
```

### Common Error Scenarios

**1. PTC Service Unavailable**
```python
is_healthy = await client.health_check()
if not is_healthy:
    # Handle service unavailable
    print("PTC service is down")
```

**2. Timeout During Execution**
```python
try:
    result = await client.execute(plan)
except asyncio.TimeoutError:
    print("Execution timed out")
```

**3. Validation Warnings**
```python
warnings = processor.validate_result(result)
if warnings:
    for warning in warnings:
        logger.warning(f"Validation warning: {warning}")
```

**4. Failed to Write Artifacts**
```python
from roma_dspy.ptc import ArtifactProcessorError

try:
    stats = processor.process_result(result)
except ArtifactProcessorError as e:
    print(f"Failed to write artifacts: {e}")
```

---

## Troubleshooting

### Client Issues

**Issue:** `PTCClientError: Failed to connect to PTC service`
**Solution:**
- Verify PTC service is running: `curl http://localhost:8001/health`
- Check `PTC_SERVICE_URL` environment variable
- Ensure network connectivity

**Issue:** `TimeoutError` during execution
**Solution:**
- Increase timeout: `PTCClient(timeout=600.0)`
- Check PTC service logs for performance issues
- Consider breaking down complex tasks

**Issue:** No cache hits despite identical plans
**Solution:**
- Verify Redis is running: `redis-cli ping`
- Check cache strategy is not set to NEVER
- Verify execution plans are truly identical (case-sensitive, order-independent)

### Processor Issues

**Issue:** `Permission denied` when writing files
**Solution:**
- Check write permissions on `base_path`
- Run with appropriate user permissions
- Verify path exists and is writable

**Issue:** Files not being written
**Solution:**
- Check `dry_run` mode is False
- Verify `overwrite` setting if files exist
- Check processor logs for errors

**Issue:** Validation warnings for successful execution
**Solution:**
- Review validation logic in processor
- Check if test results are included when `enable_testing=True`
- Verify artifact types are set correctly

---

## API Reference

### PTCClient

```python
class PTCClient:
    def __init__(
        self,
        service_url: str,
        timeout: float = 300.0,
        max_retries: int = 3,
        retry_delay: float = 1.0,
        cache_manager: Optional[PTCCacheManager] = None
    )

    async def execute(self, plan: PTCExecutionPlan) -> PTCArtifactResult
    async def health_check(self) -> bool
    async def get_stats(self) -> Dict[str, any]
    async def close(self) -> None
```

### ArtifactProcessor

```python
class ArtifactProcessor:
    def __init__(
        self,
        base_path: Optional[Path] = None,
        overwrite: bool = True,
        create_dirs: bool = True,
        dry_run: bool = False
    )

    def process_result(self, result: PTCArtifactResult) -> Dict[str, any]
    def process_with_validation(
        self,
        result: PTCArtifactResult,
        fail_on_warnings: bool = False
    ) -> Dict[str, any]
    def validate_result(self, result: PTCArtifactResult) -> List[str]
    def write_artifact(self, artifact: CodeArtifact) -> bool
    def get_artifact_summary(self, result: PTCArtifactResult) -> str
```

---

## Migration from Phase 2

### Phase 2 → Phase 3 Changes

**Phase 2** (Interface Contract):
- ✅ Schemas defined (PTCExecutionPlan, PTCArtifactResult)
- ✅ Cache strategy implemented
- ✅ All tests passing (27/27)

**Phase 3** (HTTP Integration):
- ✅ PTCClient for HTTP communication
- ✅ ArtifactProcessor for result handling
- ✅ Error handling and retry logic
- ✅ All tests passing (28/28)

**Key Additions:**
- HTTP client with retry logic
- Filesystem artifact processing
- Validation and statistics
- Health checks and monitoring

---

## Next Steps: Phase 4

**Remaining Work for Full Integration:**

1. **PTC Service Setup** (Manual - see PTC_SERVICE_SETUP.md)
   - Clone and configure open-ptc-agent repository
   - Setup PTC FastAPI service
   - Configure Daytona workspace integration
   - Deploy PTC service endpoint

2. **End-to-End Integration** (Development)
   - ROMA → PTC full workflow testing
   - Error recovery and retry scenarios
   - Performance optimization
   - Production deployment configuration

3. **Monitoring and Observability**
   - Logging integration
   - Metrics collection
   - Alert configuration
   - Performance monitoring

---

## Summary

**Phase 3 Achievements:**
- ✅ Complete HTTP integration layer
- ✅ Robust error handling with retry logic
- ✅ Artifact processing and validation
- ✅ 28 integration tests (100% coverage)
- ✅ Comprehensive documentation

**Files Created:**
- `src/roma_dspy/ptc/client.py` (PTCClient)
- `src/roma_dspy/ptc/processor.py` (ArtifactProcessor)
- `tests/ptc/test_client.py` (12 tests)
- `tests/ptc/test_processor.py` (16 tests)

**Files Modified:**
- `src/roma_dspy/ptc/__init__.py` (added exports)
- `src/roma_dspy/ptc/schemas/artifact_result.py` (uppercase enum values)

**Test Results:**
- ✅ 55/55 total PTC tests passing
  - Phase 2: 27/27 (schemas, cache)
  - Phase 3: 28/28 (client, processor)

**Ready for:** PTC service setup and end-to-end integration testing
