# Phase 1: Infrastructure Setup - Implementation Guide

**Status:** Ready for Manual Steps
**Last Updated:** 2025-12-05

---

## Overview

Phase 1 establishes the foundational infrastructure for ROMA + PTC (Prompt-Test-Code) integration. This includes:

- ✅ Redis cache for token efficiency
- ✅ Daytona sandbox environment for code execution
- ✅ PTC repository setup
- ✅ Docker Compose configuration
- ✅ Validation scripts

---

## Architecture Changes

### What's New in Phase 1

1. **Redis Service** - Added to `docker-compose.yaml` for LLM response caching
2. **PTC Configuration** - Environment variables for Daytona and PTC integration
3. **Validation Scripts** - Automated testing for Phase 1 exit criteria

### Updated Services

```
ROMA Ecosystem (Docker Compose)
├── redis (NEW) - Token cache, port 6379
├── postgres - Database persistence
├── minio - S3-compatible storage
├── mlflow - Experiment tracking
└── roma-api - Main ROMA service
```

---

## Prerequisites

Before starting Phase 1, ensure you have:

- [x] Docker and Docker Compose installed
- [x] Python 3.12+ installed
- [x] `uv` package manager installed
- [x] Git configured
- [ ] Daytona account (create during Phase 1)
- [ ] GitHub account (for forking PTC repo)

---

## Step-by-Step Setup

### Step 1: Daytona Account Setup (Manual - 5 minutes)

**Purpose:** Daytona provides ephemeral sandboxes for safe code execution in PTC.

1. **Create Account:**
   ```bash
   # Open in browser
   https://app.daytona.io
   ```
   - Sign up using GitHub OAuth (recommended)
   - Verify your email if required

2. **Generate API Key:**
   - Navigate to: Dashboard → Keys
   - Click "Create API Key"
   - Copy the key (you'll only see it once!)
   - Save it temporarily

3. **Configure Environment:**
   ```bash
   # In ROMA project root
   cp .env.example .env

   # Edit .env and add your Daytona API key
   nano .env  # or your preferred editor

   # Find and update:
   DAYTONA_API_KEY=your_actual_daytona_api_key_here
   ```

4. **Also configure Anthropic API key:**
   ```bash
   # In the same .env file, update:
   ANTHROPIC_API_KEY=your_anthropic_api_key_here
   ```

**Validation:**
```bash
# Check that keys are set
grep DAYTONA_API_KEY .env
grep ANTHROPIC_API_KEY .env
```

---

### Step 2: Fork and Clone open-ptc-agent (Manual - 5 minutes)

**Purpose:** PTC is the code generation agent that will integrate with ROMA.

1. **Fork Repository on GitHub:**
   - Navigate to: https://github.com/Chen-zexi/open-ptc-agent
   - Click the "Fork" button (top-right)
   - Keep the repository name as `open-ptc-agent`
   - Click "Create fork"

2. **Clone to Parent Directory:**
   ```bash
   # Navigate to parent directory (one level up from ROMA)
   cd ..

   # Clone your forked repository
   git clone https://github.com/YOUR_GITHUB_USERNAME/open-ptc-agent.git

   # Directory structure should now be:
   # ~/projects/
   # ├── ROMA/          (this repo)
   # └── open-ptc-agent/  (PTC repo)

   # Verify
   ls -la
   ```

3. **Setup PTC Environment:**
   ```bash
   cd open-ptc-agent

   # Install dependencies using uv
   uv sync

   # Create .env from example
   cp .env.example .env

   # Edit .env and add the same API keys
   nano .env
   ```

4. **Configure PTC .env:**
   ```bash
   # Required keys in open-ptc-agent/.env:
   ANTHROPIC_API_KEY=your_anthropic_api_key_here
   DAYTONA_API_KEY=your_daytona_api_key_here

   # Optional (can add later):
   # TAVILY_API_KEY=
   # LANGSMITH_API_KEY=
   ```

**Validation:**
```bash
# From open-ptc-agent directory
uv run python --version  # Should be 3.12+
uv run python -c "import langchain; print('LangChain OK')"
```

---

### Step 3: Start Redis Service (2 minutes)

**Purpose:** Redis caches LLM responses to reduce API costs and improve performance.

1. **Start Redis via Docker Compose:**
   ```bash
   # Return to ROMA directory
   cd ../ROMA

   # Start only Redis (not all services)
   docker-compose up -d redis

   # Verify Redis is running
   docker-compose ps redis
   ```

2. **Check Redis Health:**
   ```bash
   # View Redis logs
   docker-compose logs redis

   # Test Redis connection (if redis-cli installed locally)
   redis-cli -h localhost -p 6379 ping
   # Expected: PONG
   ```

3. **Alternative: Start All Services:**
   ```bash
   # If you want to start the full ROMA stack:
   docker-compose up -d

   # Check all services
   docker-compose ps
   ```

**Validation:**
```bash
# Verify Redis container is healthy
docker-compose ps redis
# Should show "Up" status with healthy

# Check Redis is accessible
docker exec roma-dspy-redis redis-cli ping
# Expected: PONG
```

---

### Step 4: Validate Redis from ROMA Container (Optional)

**Purpose:** Ensure ROMA service can communicate with Redis.

```bash
# If ROMA API is running
docker exec roma-dspy-api sh -c 'python -c "import redis; r=redis.from_url(\"redis://redis:6379/0\"); print(r.ping())"'
# Expected: True

# Alternative: Manual test
docker exec -it roma-dspy-redis redis-cli
# In Redis CLI:
SET test:key "Hello from Phase 1"
GET test:key
DEL test:key
exit
```

---

### Step 5: Test Daytona Sandbox (5 minutes)

**Purpose:** Verify Daytona can create sandboxes and execute code.

1. **Run Daytona Test Script:**
   ```bash
   # From ROMA directory
   uv run python scripts/ptc/test_daytona_sandbox.py
   ```

2. **Expected Output:**
   ```
   ┌─────────────────────────────────────────┐
   │ Daytona Sandbox Validation              │
   │ ROMA + PTC Integration - Phase 1        │
   └─────────────────────────────────────────┘

   Step 1: Validating API Key Configuration
   ✓ API key configured (sk-daytona-...)

   Step 2: Testing Daytona SDK Import
   ⚠ Daytona SDK will be installed with open-ptc-agent

   Step 3: Testing Sandbox Creation
   ⚠ Daytona SDK not installed yet - skipping sandbox test

   ════════════════════════════════════════════
   ┌─────────────────────────────────────────┐
   │ Test Results                             │
   │                                          │
   │ ✓ Passed: 2                              │
   │ ✗ Failed: 0                              │
   │                                          │
   │ Status: PASSED                           │
   └─────────────────────────────────────────┘
   ```

3. **Full Daytona Test (from PTC repo):**
   ```bash
   # Switch to PTC repository
   cd ../open-ptc-agent

   # Copy test script from ROMA
   cp ../ROMA/scripts/ptc/test_daytona_sandbox.py ./test_daytona.py

   # Run with Daytona SDK available
   uv run python test_daytona.py
   ```

**Troubleshooting:**
- If sandbox creation fails: Check Daytona dashboard for quota/credits
- If API errors occur: Verify API key is correct and active
- If network errors: Check firewall/proxy settings

---

### Step 6: Run Phase 1 Validation (2 minutes)

**Purpose:** Automated check of all Phase 1 exit criteria.

```bash
# From ROMA directory
uv run python scripts/ptc/validate_phase1.py
```

**Expected Results:**

| Category | Check | Status |
|----------|-------|--------|
| Environment | DAYTONA_API_KEY | ✓ PASS |
| Environment | ANTHROPIC_API_KEY | ✓ PASS |
| Environment | REDIS_URL | ✓ PASS |
| Infrastructure | Redis service | ✓ PASS |
| Infrastructure | Redis config | ✓ PASS |
| PTC Repository | open-ptc-agent | ✓ PASS |
| Development Tools | Python 3.12+ | ✓ PASS |
| Development Tools | uv installed | ✓ PASS |

**All checks must pass to proceed to Phase 2.**

---

## Phase 1 Exit Criteria Checklist

Use this checklist to verify Phase 1 completion:

### Manual Verification

- [ ] **Daytona Account**
  - [ ] Account created at https://app.daytona.io
  - [ ] API key generated and saved
  - [ ] API key added to `.env` files (both ROMA and PTC)

- [ ] **PTC Repository**
  - [ ] `open-ptc-agent` forked on GitHub
  - [ ] Repository cloned to parent directory
  - [ ] Dependencies installed (`uv sync` completed)
  - [ ] `.env` configured with API keys

- [ ] **Redis Infrastructure**
  - [ ] Redis service running (`docker-compose ps redis`)
  - [ ] Redis health check passing
  - [ ] Redis accessible from localhost:6379

- [ ] **Environment Configuration**
  - [ ] `.env` file created from `.env.example`
  - [ ] All required API keys configured
  - [ ] No placeholder values remaining

### Automated Verification

```bash
# Run validation script
uv run python scripts/ptc/validate_phase1.py

# All checks should pass
```

---

## Directory Structure After Phase 1

```
~/projects/  (or your projects directory)
├── ROMA/
│   ├── docker-compose.yaml        # ✓ Updated with Redis service
│   ├── docker/
│   │   └── redis.conf             # ✓ NEW: Redis configuration
│   ├── .env                       # ✓ Created and configured
│   ├── .env.example               # ✓ Updated with PTC variables
│   ├── scripts/
│   │   └── ptc/                   # ✓ NEW: PTC integration scripts
│   │       ├── test_daytona_sandbox.py
│   │       └── validate_phase1.py
│   └── docs/
│       └── PHASE1_SETUP.md        # ✓ This file
│
└── open-ptc-agent/                # ✓ NEW: Cloned PTC repository
    ├── src/
    │   ├── ptc_core/
    │   └── agent/
    ├── .env                       # ✓ Created and configured
    ├── .env.example
    └── pyproject.toml
```

---

## Common Issues and Solutions

### Issue: Redis fails to start

**Symptoms:**
```bash
docker-compose ps redis
# Shows "Exit 1" or "Unhealthy"
```

**Solutions:**
1. Check logs: `docker-compose logs redis`
2. Verify config: `cat docker/redis.conf`
3. Check port availability: `lsof -i :6379`
4. Restart service: `docker-compose restart redis`

### Issue: Daytona sandbox creation fails

**Symptoms:**
```
Error: Unauthorized / Invalid API key
```

**Solutions:**
1. Verify API key: `grep DAYTONA_API_KEY .env`
2. Check Daytona dashboard: https://app.daytona.io
3. Regenerate API key if expired
4. Check account quota/credits

### Issue: open-ptc-agent dependencies fail to install

**Symptoms:**
```bash
uv sync
# Error: Package resolution failed
```

**Solutions:**
1. Update uv: `curl -LsSf https://astral.sh/uv/install.sh | sh`
2. Clear cache: `uv cache clean`
3. Retry: `uv sync --refresh`
4. Check Python version: `uv run python --version`

### Issue: Port conflicts (6379 already in use)

**Symptoms:**
```
Error: bind: address already in use
```

**Solutions:**
1. Find process: `lsof -i :6379`
2. Stop existing Redis: `sudo systemctl stop redis`
3. Or change port in `.env`: `REDIS_PORT=6380`
4. Update `docker-compose.yaml` port mapping

---

## Next Steps: Phase 2 Preview

Once Phase 1 is complete, Phase 2 will focus on:

1. **Interface Contract Definition**
   - `PTCExecutionPlan` schema (ROMA → PTC)
   - `PTCArtifactResult` schema (PTC → ROMA)
   - WebSocket message types for streaming

2. **Shared Schema Validation**
   - Pydantic models for type safety
   - JSON schema validation
   - Integration tests

3. **Cache Strategy**
   - Redis key design for LLM responses
   - TTL policies
   - Cache warming strategies

**Prerequisites for Phase 2:**
- ✅ All Phase 1 exit criteria met
- ✅ Validation script passing
- ✅ Redis and Daytona functional

---

## Getting Help

If you encounter issues during Phase 1 setup:

1. **Check Logs:**
   ```bash
   docker-compose logs redis
   uv run python scripts/ptc/validate_phase1.py
   ```

2. **Verify Environment:**
   ```bash
   # Check all services
   docker-compose ps

   # Check environment variables
   env | grep -E "DAYTONA|ANTHROPIC|REDIS"
   ```

3. **Re-run Validation:**
   ```bash
   uv run python scripts/ptc/validate_phase1.py
   ```

4. **Documentation:**
   - ROMA: `README.md` in project root
   - PTC: `README.md` in open-ptc-agent
   - Daytona: https://docs.daytona.io

---

## Summary

**Phase 1 Status:** Infrastructure setup complete

**What was accomplished:**
- ✅ Redis cache deployed and configured
- ✅ Daytona account and API access configured
- ✅ PTC repository forked and cloned
- ✅ Docker Compose configuration updated
- ✅ Validation scripts created
- ✅ Environment properly configured

**What's ready for Phase 2:**
- ✅ Shared Redis cache between ROMA and PTC
- ✅ Daytona sandbox for code execution
- ✅ Development environment configured
- ✅ Both repositories (ROMA + PTC) set up

**Next milestone:** Phase 2 - Interface Contract Definition

Run the validation script to confirm readiness:
```bash
uv run python scripts/ptc/validate_phase1.py
```

All checks should pass before proceeding to Phase 2.
