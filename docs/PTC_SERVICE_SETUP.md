# PTC Service Setup Guide

**Purpose:** Manual steps to set up the PTC (Prompt-Test-Code) service for integration with ROMA

**Prerequisites:**
- ✅ Phase 1 complete (Redis, Daytona configured)
- ✅ Phase 2 complete (Schemas and cache implemented)
- ✅ Phase 3 complete (HTTP client and processor implemented)
- ✅ Daytona API key configured in `.env`
- ✅ Claude API key configured in `.env`

---

## Overview

The PTC service is a separate FastAPI application that:
1. Receives code generation requests from ROMA (PTCExecutionPlan)
2. Generates code using LLM agents (Claude, Kimi)
3. Tests code in Daytona sandbox environments
4. Returns complete artifacts (PTCArtifactResult)

This guide covers setting up the PTC service to work with ROMA.

---

## Step 1: Clone PTC Repository

### 1.1 Navigate to Projects Directory

```powershell
# Navigate to parent directory (where ROMA is located)
cd C:\Users\dkell\projects

# Verify ROMA directory exists
ls ROMA
```

### 1.2 Clone open-ptc-agent Repository

```powershell
# Clone the repository
git clone https://github.com/prompt-test-code/open-ptc-agent.git

# Navigate into directory
cd open-ptc-agent

# Verify clone successful
ls
```

**Expected Output:**
```
Directory: C:\Users\dkell\projects\open-ptc-agent

Mode                 LastWriteTime         Length Name
----                 -------------         ------ ----
d-----                                            src
d-----                                            tests
d-----                                            docs
-a----                                            README.md
-a----                                            pyproject.toml
-a----                                            .env.example
```

---

## Step 2: Install PTC Dependencies

### 2.1 Create Python Virtual Environment

```powershell
# Inside open-ptc-agent directory
uv venv

# Activate virtual environment
.venv\Scripts\activate
```

### 2.2 Install Dependencies

```powershell
# Install with uv
uv pip install -e .

# Or with pip
pip install -e .
```

**Key Dependencies:**
- FastAPI (web framework)
- Uvicorn (ASGI server)
- Anthropic SDK (Claude integration)
- Daytona SDK (sandbox execution)
- Redis client (caching)
- Pydantic (schema validation)

---

## Step 3: Configure PTC Service

### 3.1 Copy Environment Template

```powershell
# Copy example to actual .env file
cp .env.example .env
```

### 3.2 Configure API Keys

Edit `.env` file with your credentials:

```bash
# LLM Provider Keys
ANTHROPIC_API_KEY=sk-wgfw2sEL0ZTO9zgVPGuVdlQVpn2G7SbUvvSn0uCoPGy4ICCq
KIMI_API_KEY=your_kimi_key_here  # Optional fallback

# Daytona Configuration
DAYTONA_API_KEY=dtn_fee7f751e8e48c1a44bdd405464e157a0efe4d8f8a9ff0d1f78fb8ded99b2a84
DAYTONA_API_URL=https://api.daytona.io/v1  # Default

# Redis Configuration
REDIS_URL=redis://localhost:6379/1  # Note: Different DB than ROMA (db=1)
REDIS_PASSWORD=  # If required

# PTC Service Configuration
PTC_HOST=0.0.0.0
PTC_PORT=8001
PTC_WORKERS=4  # Number of worker processes
PTC_LOG_LEVEL=info  # debug, info, warning, error

# Execution Defaults
DEFAULT_TIMEOUT=300  # seconds
DEFAULT_MAX_ITERATIONS=3
MAX_CONCURRENT_EXECUTIONS=10
```

**Important Notes:**
- Use the same `ANTHROPIC_API_KEY` from ROMA's `.env`
- Use the same `DAYTONA_API_KEY` from ROMA's `.env`
- Use a **different Redis database** (db=1) to avoid conflicts with ROMA (db=0)

### 3.3 Verify Configuration

```powershell
# Test configuration loading
uv run python -c "from src.ptc.config import settings; print(settings)"
```

---

## Step 4: Install ROMA Schemas in PTC

The PTC service needs access to ROMA's schema definitions for compatibility.

### Option A: Install ROMA Package (Recommended)

```powershell
# Inside open-ptc-agent directory
uv pip install -e ../ROMA
```

This installs `roma-dspy` package so PTC can import schemas:
```python
from roma_dspy.ptc.schemas import PTCExecutionPlan, PTCArtifactResult
```

### Option B: Copy Schema Files

If installing ROMA package is not feasible:

```powershell
# Copy schema files to PTC project
mkdir -p src/ptc/schemas
cp ../ROMA/src/roma_dspy/ptc/schemas/*.py src/ptc/schemas/
```

**Note:** Option A is preferred to ensure schema consistency.

---

## Step 5: Implement PTC Service Endpoint

### 5.1 Create FastAPI Application

Create `src/ptc/service.py`:

```python
"""
PTC Service - FastAPI Application

Provides REST API for code generation via PTC agents.
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from roma_dspy.ptc.schemas import PTCExecutionPlan, PTCArtifactResult
from .agent import PTCAgent  # Your PTC agent implementation

app = FastAPI(
    title="PTC Service",
    description="Prompt-Test-Code Agent Service",
    version="0.1.0"
)

# CORS configuration (adjust for production)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production: ["http://localhost:3000"]
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize PTC agent
agent = PTCAgent()


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "ptc",
        "version": "0.1.0"
    }


@app.get("/stats")
async def get_stats():
    """Get service statistics."""
    return await agent.get_stats()


@app.post("/execute", response_model=PTCArtifactResult)
async def execute_plan(plan: PTCExecutionPlan) -> PTCArtifactResult:
    """
    Execute PTC code generation.

    Args:
        plan: Execution plan from ROMA

    Returns:
        Artifact result with generated code
    """
    logger.info(f"Received execution request: {plan.execution_id}")

    try:
        # Execute with PTC agent
        result = await agent.execute(plan)

        logger.info(
            f"Execution complete: {plan.execution_id}, "
            f"status={result.status}, "
            f"artifacts={len(result.artifacts)}"
        )

        return result

    except Exception as e:
        logger.exception(f"Execution failed: {plan.execution_id}")
        raise HTTPException(
            status_code=500,
            detail=f"Execution failed: {str(e)}"
        )


@app.on_event("startup")
async def startup():
    """Initialize resources on startup."""
    logger.info("PTC Service starting...")
    await agent.initialize()


@app.on_event("shutdown")
async def shutdown():
    """Cleanup resources on shutdown."""
    logger.info("PTC Service shutting down...")
    await agent.cleanup()
```

### 5.2 Implement PTC Agent

Create `src/ptc/agent.py`:

```python
"""
PTC Agent Implementation

Core logic for code generation, testing, and artifact packaging.
"""

from datetime import datetime
from typing import Dict, List
from loguru import logger

from roma_dspy.ptc.schemas import (
    PTCExecutionPlan,
    PTCArtifactResult,
    ExecutionStatus,
    CodeArtifact,
    TestResult,
    LLMUsage,
)

# Import your actual PTC agent implementation
# from your_ptc_implementation import generate_code, run_tests


class PTCAgent:
    """PTC agent for code generation and testing."""

    def __init__(self):
        self.stats = {
            "total_executions": 0,
            "successful_executions": 0,
            "failed_executions": 0,
        }

    async def initialize(self):
        """Initialize agent resources."""
        logger.info("Initializing PTC Agent...")
        # Setup LLM clients, Daytona client, etc.

    async def cleanup(self):
        """Cleanup agent resources."""
        logger.info("Cleaning up PTC Agent...")
        # Close connections, cleanup temp files, etc.

    async def execute(self, plan: PTCExecutionPlan) -> PTCArtifactResult:
        """
        Execute code generation plan.

        Args:
            plan: Execution plan from ROMA

        Returns:
            Artifact result with generated code
        """
        started_at = datetime.utcnow()
        self.stats["total_executions"] += 1

        try:
            # TODO: Implement actual PTC logic here
            # 1. Generate code using LLM (Claude/Kimi)
            # 2. Test code in Daytona sandbox
            # 3. Package artifacts

            # Placeholder implementation
            artifacts = [
                CodeArtifact(
                    file_path="main.py",
                    content=f"# Generated for: {plan.scaffolding.task_description}",
                    artifact_type="source_code",
                    language="python"
                )
            ]

            completed_at = datetime.utcnow()
            duration = (completed_at - started_at).total_seconds()

            self.stats["successful_executions"] += 1

            return PTCArtifactResult(
                execution_id=plan.execution_id,
                status=ExecutionStatus.SUCCESS,
                artifacts=artifacts,
                iterations_used=1,
                started_at=started_at,
                completed_at=completed_at,
                duration_seconds=duration,
            )

        except Exception as e:
            logger.exception(f"Execution failed: {plan.execution_id}")
            self.stats["failed_executions"] += 1

            completed_at = datetime.utcnow()
            duration = (completed_at - started_at).total_seconds()

            return PTCArtifactResult(
                execution_id=plan.execution_id,
                status=ExecutionStatus.FAILURE,
                error_message=str(e),
                started_at=started_at,
                completed_at=completed_at,
                duration_seconds=duration,
            )

    async def get_stats(self) -> Dict:
        """Get agent statistics."""
        return self.stats
```

---

## Step 6: Start PTC Service

### 6.1 Start with Uvicorn (Development)

```powershell
# Inside open-ptc-agent directory
uv run uvicorn src.ptc.service:app --host 0.0.0.0 --port 8001 --reload
```

**Expected Output:**
```
INFO:     Uvicorn running on http://0.0.0.0:8001 (Press CTRL+C to quit)
INFO:     Started reloader process
INFO:     Started server process
INFO:     Waiting for application startup.
INFO:     PTC Service starting...
INFO:     Initializing PTC Agent...
INFO:     Application startup complete.
```

### 6.2 Verify Service is Running

**Terminal 1 (PTC Service):**
```powershell
uv run uvicorn src.ptc.service:app --host 0.0.0.0 --port 8001
```

**Terminal 2 (Test):**
```powershell
# Test health endpoint
curl http://localhost:8001/health

# Expected response
# {"status":"healthy","service":"ptc","version":"0.1.0"}
```

---

## Step 7: Test ROMA → PTC Integration

### 7.1 Create Integration Test Script

Create `scripts/test_roma_ptc_integration.py` in ROMA directory:

```python
"""
Test ROMA → PTC Integration

Sends a sample execution plan to PTC service and processes the result.
"""

import asyncio
from pathlib import Path
from roma_dspy.ptc import (
    PTCClient,
    PTCExecutionPlan,
    ScaffoldingSpec,
    ArtifactProcessor,
)


async def test_integration():
    """Test full ROMA → PTC → Artifacts flow."""

    # 1. Create client
    client = PTCClient(service_url="http://localhost:8001")

    # 2. Verify service is healthy
    is_healthy = await client.health_check()
    print(f"PTC service healthy: {is_healthy}")

    if not is_healthy:
        print("❌ PTC service is not available")
        return

    # 3. Create execution plan
    plan = PTCExecutionPlan(
        execution_id="integration-test-001",
        scaffolding=ScaffoldingSpec(
            task_description="Build a simple calculator CLI",
            requirements=[
                "Add, subtract, multiply, divide operations",
                "Command-line interface",
                "Error handling for division by zero"
            ],
            dependencies=["click"]
        )
    )

    print(f"\n📋 Execution Plan: {plan.execution_id}")
    print(f"Task: {plan.scaffolding.task_description}")

    # 4. Execute with PTC
    print("\n🚀 Sending to PTC service...")
    result = await client.execute(plan)

    print(f"\n✅ Execution complete!")
    print(f"Status: {result.status}")
    print(f"Artifacts: {len(result.artifacts)}")
    print(f"Duration: {result.duration_seconds:.2f}s")

    # 5. Process artifacts
    processor = ArtifactProcessor(
        base_path=Path("./output/integration_test")
    )

    stats = processor.process_with_validation(result)

    print(f"\n📁 Artifacts written:")
    print(f"  Written: {stats['written']}")
    print(f"  Skipped: {stats['skipped']}")
    print(f"  Errors: {stats['errors']}")

    # 6. Display summary
    print("\n" + "="*60)
    summary = processor.get_artifact_summary(result)
    print(summary)
    print("="*60)

    # Cleanup
    await client.close()


if __name__ == "__main__":
    asyncio.run(test_integration())
```

### 7.2 Run Integration Test

```powershell
# From ROMA directory
uv run python scripts/test_roma_ptc_integration.py
```

**Expected Output:**
```
PTC service healthy: True

📋 Execution Plan: integration-test-001
Task: Build a simple calculator CLI

🚀 Sending to PTC service...

✅ Execution complete!
Status: SUCCESS
Artifacts: 1
Duration: 2.34s

📁 Artifacts written:
  Written: 1
  Skipped: 0
  Errors: 0

============================================================
Execution: integration-test-001
Status: SUCCESS
Duration: 2.34s
Artifacts: 1
  source_code: 1 files
    - main.py
============================================================
```

---

## Step 8: Production Deployment

### 8.1 Start with Multiple Workers

```powershell
# Production configuration
uv run uvicorn src.ptc.service:app \
    --host 0.0.0.0 \
    --port 8001 \
    --workers 4 \
    --log-level info
```

### 8.2 Use Supervisor or Docker

**Docker Compose (Recommended):**

Add to `docker-compose.yml` in ROMA directory:

```yaml
  ptc-service:
    build:
      context: ../open-ptc-agent
      dockerfile: Dockerfile
    container_name: roma-ptc-service
    ports:
      - "8001:8001"
    environment:
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
      - DAYTONA_API_KEY=${DAYTONA_API_KEY}
      - REDIS_URL=redis://redis:6379/1
      - PTC_HOST=0.0.0.0
      - PTC_PORT=8001
    depends_on:
      - redis
    networks:
      - roma-network
    restart: unless-stopped
```

Create `Dockerfile` in `open-ptc-agent` directory:

```dockerfile
FROM python:3.12-slim

WORKDIR /app

# Install uv
RUN pip install uv

# Copy project files
COPY pyproject.toml .
COPY src/ src/

# Install dependencies
RUN uv pip install --system -e .

# Expose port
EXPOSE 8001

# Run service
CMD ["uvicorn", "src.ptc.service:app", "--host", "0.0.0.0", "--port", "8001"]
```

Start with Docker Compose:

```powershell
cd C:\Users\dkell\projects\ROMA
docker compose up -d ptc-service
```

---

## Troubleshooting

### Service Won't Start

**Issue:** `ModuleNotFoundError: No module named 'roma_dspy'`

**Solution:**
```powershell
# Install ROMA package in PTC environment
cd open-ptc-agent
uv pip install -e ../ROMA
```

**Issue:** `Connection refused` when testing

**Solution:**
- Verify service is running: `curl http://localhost:8001/health`
- Check firewall settings
- Ensure port 8001 is not in use: `netstat -ano | findstr :8001`

### Redis Connection Issues

**Issue:** `redis.exceptions.ConnectionError`

**Solution:**
- Verify Redis is running: `docker ps | grep redis`
- Check Redis URL in PTC's `.env`
- Ensure different database numbers (ROMA=0, PTC=1)

### Daytona Sandbox Issues

**Issue:** `DaytonaError: Workspace creation failed`

**Solution:**
- Verify Daytona API key is correct
- Check Daytona account has available credits
- Review Daytona service status: https://status.daytona.io

### Schema Validation Errors

**Issue:** `ValidationError` when receiving requests

**Solution:**
- Ensure PTC has latest ROMA schemas
- Reinstall ROMA package: `uv pip install -e ../ROMA --force-reinstall`
- Check schema versions match

---

## Verification Checklist

After setup, verify each component:

- [ ] PTC repository cloned and dependencies installed
- [ ] Environment variables configured in PTC's `.env`
- [ ] ROMA schemas accessible to PTC (`from roma_dspy.ptc import ...`)
- [ ] PTC service starts without errors
- [ ] Health check endpoint responds: `http://localhost:8001/health`
- [ ] Integration test completes successfully
- [ ] Artifacts are written to filesystem
- [ ] Redis caching is working (check cache hits on repeat executions)

---

## Next Steps

Once PTC service is running:

1. **Run End-to-End Tests**: Test full ROMA → PTC workflow
2. **Monitor Performance**: Track execution times, cache hit rates
3. **Optimize Configuration**: Adjust workers, timeouts, cache TTL
4. **Setup Logging**: Configure structured logging for debugging
5. **Production Deployment**: Deploy with Docker Compose or Kubernetes

---

## Additional Resources

- **PTC Repository**: https://github.com/prompt-test-code/open-ptc-agent
- **Daytona Documentation**: https://docs.daytona.io
- **FastAPI Documentation**: https://fastapi.tiangolo.com
- **ROMA Phase 3 Documentation**: `docs/PHASE3_HTTP_INTEGRATION.md`

---

## Support

For issues or questions:

1. Check troubleshooting section above
2. Review PTC service logs: `docker logs roma-ptc-service`
3. Review ROMA logs for client errors
4. Check Redis for cache statistics

**Common Commands:**

```powershell
# View PTC logs
docker logs -f roma-ptc-service

# Check Redis cache
redis-cli
> SELECT 1
> KEYS ptc:*
> GET ptc:exec:abc123

# Restart services
docker compose restart ptc-service redis
```
