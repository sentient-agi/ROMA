# ROMA Multi-Agent System - Development Guide

> **Living Document** - Last Updated: 2025-12-10
>
> This document serves as the central reference for ROMA development. Update as the system evolves.

---

## Table of Contents

1. [Project Overview](#project-overview)
2. [Core Agent Architecture](#core-agent-architecture)
3. [Technology Stack](#technology-stack)
4. [Repository Structure](#repository-structure)
5. [Configuration System](#configuration-system)
6. [Development Workflow](#development-workflow)
7. [API Reference](#api-reference)
8. [Testing Strategy](#testing-strategy)
9. [Deployment](#deployment)
10. [Cost Optimization](#cost-optimization)
11. [Troubleshooting](#troubleshooting)
12. [Changelog](#changelog)

---

## Project Overview

**ROMA** (Recursive Open Meta-Agent) is a hierarchical task decomposition framework built on DSPy that implements a multi-agent system for autonomous task execution.

### Core Concept

```
User Goal → Decompose → Execute → Aggregate → Verify → Result
```

Tasks are recursively broken down into atomic subtasks, executed in parallel where possible, and results are aggregated and verified for correctness.

### Current Status

| Component | Status | Notes |
|-----------|--------|-------|
| Core Agents | ✅ Production-ready | All 5 agents implemented |
| PTC Integration | ✅ Complete | Options A, B, C implemented |
| API | ✅ Functional | FastAPI endpoints |
| Testing | ✅ Comprehensive | 40+ integration tests |
| Deployment | ⚠️ Proxy blocked | Deploy externally |

---

## Core Agent Architecture

### The Five Agents

| Agent | Purpose | Temperature | Model |
|-------|---------|-------------|-------|
| **Atomizer** | Determines if task is atomic or needs decomposition | 0.1 (deterministic) | Gemini 2.5 Flash |
| **Planner** | Creates task decomposition plans | 0.3 (balanced) | Gemini 2.5 Flash |
| **Executor** | Executes atomic tasks | 0.7 (creative) | Claude Sonnet 4.5 |
| **Aggregator** | Combines results from subtasks | 0.3 (balanced) | Gemini 2.5 Flash |
| **Verifier** | Validates execution outcomes | 0.1 (deterministic) | Gemini 2.5 Flash |

### Execution Flow

```
                    ┌─────────────────┐
                    │   User Request  │
                    └────────┬────────┘
                             ▼
                    ┌─────────────────┐
                    │    Atomizer     │
                    │  "Is it atomic?"│
                    └────────┬────────┘
                             │
              ┌──────────────┴──────────────┐
              ▼                             ▼
        ┌──────────┐                 ┌──────────────┐
        │   YES    │                 │      NO      │
        │ (atomic) │                 │ (composite)  │
        └────┬─────┘                 └──────┬───────┘
             │                              ▼
             │                       ┌─────────────┐
             │                       │   Planner   │
             │                       │  Decompose  │
             │                       └──────┬──────┘
             │                              ▼
             │                       ┌─────────────┐
             │                       │  Executor   │
             │                       │  (per task) │
             │                       └──────┬──────┘
             │                              │
             └──────────────┬───────────────┘
                            ▼
                    ┌─────────────────┐
                    │   Aggregator    │
                    │ Combine Results │
                    └────────┬────────┘
                             ▼
                    ┌─────────────────┐
                    │    Verifier     │
                    │    Validate     │
                    └────────┬────────┘
                             ▼
                    ┌─────────────────┐
                    │     Result      │
                    └─────────────────┘
```

### PTC Integration (Prompt-Test-Code)

For code generation tasks, ROMA integrates with the PTC service:

```
ROMA Task (CODE_GENERATION/CODE_INTERPRET)
         ↓
    PTC Service (HTTP :8001)
         ↓
    Code Generation (LLM)
    ├─ Kimi (cost-effective)
    ├─ Claude (premium)
    └─ OpenRouter (fallback)
         ↓
    Daytona Sandbox Testing
    ├─ Isolated execution
    └─ Auto dependencies
         ↓
    Results → ROMA
```

---

## Technology Stack

### Backend (Python)

| Category | Technology |
|----------|------------|
| Framework | FastAPI, DSPy, Pydantic |
| LLM | Anthropic Claude, Gemini, Kimi, OpenRouter |
| Database | PostgreSQL (asyncpg), Redis |
| Observability | MLflow, OpenTelemetry |
| Code Execution | E2B Sandbox, Daytona Sandbox |
| Storage | S3/MinIO, Filesystem |
| Config | OmegaConf (YAML-based) |

### Frontend (TypeScript)

| Category | Technology |
|----------|------------|
| Runtime | Node.js, pnpm monorepo |
| Packages | @roma/core, @roma/schemas |
| Testing | Vitest |
| Logging | Pino |

### Infrastructure

| Category | Technology |
|----------|------------|
| Containers | Docker (multi-stage builds) |
| Orchestration | Docker Compose, Kubernetes |
| IaC | Terraform |
| CI/CD | GitHub Actions |

---

## Repository Structure

```
ROMA/
├── src/roma_dspy/           # Core Python source
│   ├── agents/              # Agent implementations
│   ├── api/                 # FastAPI endpoints
│   ├── config/              # Configuration management
│   ├── core/                # Core engine
│   │   ├── artifacts/       # Artifact management
│   │   ├── context/         # Execution context
│   │   ├── engine/          # DAG, scheduler, runtime
│   │   ├── factory/         # Agent factory
│   │   ├── modules/         # Base agent modules
│   │   ├── observability/   # Tracing
│   │   ├── predictors/      # DSPy predictors
│   │   ├── registry/        # Agent registry
│   │   ├── services/        # Execution services
│   │   └── storage/         # Storage backends
│   ├── integrations/        # ACE, etc.
│   ├── ptc/                 # PTC service client
│   ├── tools/               # Tool integrations
│   │   ├── core/            # File, artifact, e2b
│   │   ├── crypto/          # Binance, CoinGecko
│   │   ├── mcp/             # MCP toolkit
│   │   └── web_search/      # Serper API
│   ├── tui/                 # Terminal UI
│   └── cli.py               # CLI interface
├── config/                  # Configuration files
│   ├── defaults/            # Default configs
│   ├── profiles/            # Environment profiles
│   └── ptc_integration.yaml # PTC config
├── docker/                  # Docker files
├── tests/                   # Test suite
│   ├── integration/         # Integration tests
│   └── fixtures/            # Test data
├── docs/                    # Documentation
├── examples/                # Usage examples
├── k8s/                     # Kubernetes manifests
├── terraform/               # IaC
├── docker-compose.yaml      # Local infrastructure
├── pyproject.toml           # Python config
└── justfile                 # Task automation
```

### Key Files

| File | Purpose |
|------|---------|
| `config/defaults/config.yaml` | Main configuration |
| `config/ptc_integration.yaml` | PTC service config |
| `docker-compose.yaml` | Local dev infrastructure |
| `src/roma_dspy/cli.py` | CLI entry point |
| `src/roma_dspy/api/main.py` | API entry point |

---

## Configuration System

### Main Config (`config/defaults/config.yaml`)

```yaml
agents:
  atomizer:
    model: "openrouter/google/gemini-2.5-flash-preview"
    temperature: 0.1
    max_tokens: 1024
  planner:
    model: "openrouter/google/gemini-2.5-flash-preview"
    temperature: 0.3
    max_tokens: 4096
  executor:
    model: "openrouter/anthropic/claude-sonnet-4"
    temperature: 0.7
    max_tokens: 8192
  aggregator:
    model: "openrouter/google/gemini-2.5-flash-preview"
    temperature: 0.3
    max_tokens: 4096
  verifier:
    model: "openrouter/google/gemini-2.5-flash-preview"
    temperature: 0.1
    max_tokens: 2048

runtime:
  max_depth: 5
  timeout_seconds: 900
  cache_enabled: true

storage:
  type: "postgresql"
  connection_string: "${DATABASE_URL}"

observability:
  mlflow:
    enabled: true
    tracking_uri: "${MLFLOW_TRACKING_URI}"
  opentelemetry:
    enabled: true

resilience:
  checkpointing:
    enabled: true
    interval_seconds: 60
  retries:
    max_attempts: 3
    backoff_factor: 2
```

### Environment Variables

```bash
# LLM APIs
ANTHROPIC_API_KEY=sk-ant-...
OPENROUTER_API_KEY=sk-or-...
KIMI_API_KEY=sk-...

# Database
DATABASE_URL=postgresql://user:pass@localhost:5432/roma

# Redis
REDIS_URL=redis://localhost:6379

# Storage
S3_ENDPOINT=http://localhost:9000
S3_ACCESS_KEY=minioadmin
S3_SECRET_KEY=minioadmin

# MLflow
MLFLOW_TRACKING_URI=http://localhost:5000
```

### Profiles

- **lightweight**: Minimal resources, fast startup
- **tool_enabled**: Full toolkit integration
- **production**: All features, optimized settings

---

## Development Workflow

### Local Setup

```bash
# Clone and setup
git clone <repo>
cd ROMA

# Create virtual environment
python -m venv venv
source venv/bin/activate  # or venv\Scripts\activate on Windows

# Install dependencies
pip install -e ".[dev]"

# Start infrastructure
docker-compose up -d redis postgres minio

# Run ROMA
python -m roma_dspy.cli solve "Your task here"
```

### Common Commands

```bash
# Run tests
pytest tests/

# Run specific test category
pytest -m integration
pytest -m "not requires_llm"

# Start API server
uvicorn src.roma_dspy.api.main:app --reload --port 8000

# Start with Docker
docker-compose up roma-api

# Format code
black src/ tests/
isort src/ tests/

# Type checking
mypy src/
```

### Git Workflow

1. Create feature branch from `main`
2. Make changes with descriptive commits
3. Run tests locally
4. Create PR with summary
5. Wait for CI checks
6. Merge after approval

---

## API Reference

### Core Endpoints (Port 8000)

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/solve` | Execute task with ROMA |
| `POST` | `/executions/{id}/resume` | Resume execution |
| `GET` | `/executions/{id}` | Get execution details |
| `GET` | `/checkpoints` | List checkpoints |
| `POST` | `/checkpoints/restore/{id}` | Restore checkpoint |
| `GET` | `/health` | Health check |
| `GET` | `/metrics` | Prometheus metrics |
| `GET` | `/traces` | Execution traces |

### PTC Service (Port 8001)

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/execute` | Generate and test code |
| `GET` | `/health` | Health check |
| `GET` | `/status/{id}` | Execution status |

### Example: Solve Task

```bash
curl -X POST http://localhost:8000/solve \
  -H "Content-Type: application/json" \
  -d '{"goal": "Create a Python function to calculate fibonacci numbers"}'
```

---

## Testing Strategy

### Test Categories

| Marker | Purpose | Requires |
|--------|---------|----------|
| `integration` | Component interaction | Infrastructure |
| `requires_db` | Database operations | PostgreSQL |
| `requires_llm` | LLM API calls | API keys |
| `e2b` | Sandbox execution | E2B API |

### Running Tests

```bash
# All tests
pytest

# Skip LLM tests (faster)
pytest -m "not requires_llm"

# Only integration
pytest -m integration

# With coverage
pytest --cov=src/roma_dspy --cov-report=html
```

### Test Files (`tests/integration/`)

- `test_atomizer.py` - Atomizer behavior
- `test_planner.py` - Plan generation
- `test_executor.py` - Task execution
- `test_aggregator.py` - Result aggregation
- `test_verifier.py` - Verification logic
- `test_ptc_integration.py` - PTC service
- `test_e2b_sandbox.py` - Sandbox execution
- `test_storage.py` - Storage backends
- `test_resilience.py` - Retry/checkpoint

---

## Deployment

### Docker Compose (Development)

```bash
# Start all services
docker-compose up -d

# View logs
docker-compose logs -f roma-api

# Stop all
docker-compose down
```

### Kubernetes (Production)

```bash
# Apply manifests
kubectl apply -f k8s/namespace.yml
kubectl apply -f k8s/configmap.yml
kubectl apply -f k8s/deployment.yml
kubectl apply -f k8s/service.yml

# Check status
kubectl get pods -n roma
kubectl logs -f deployment/roma-api -n roma
```

### Services Topology

```
┌─────────────────────────────────────────────────┐
│                   Load Balancer                  │
└────────────────────┬────────────────────────────┘
                     │
         ┌───────────┴───────────┐
         ▼                       ▼
   ┌───────────┐          ┌───────────┐
   │ ROMA API  │          │ PTC Svc   │
   │  :8000    │          │  :8001    │
   └─────┬─────┘          └─────┬─────┘
         │                      │
    ┌────┴────┬────────┬───────┘
    ▼         ▼        ▼
┌───────┐ ┌───────┐ ┌───────┐
│ Redis │ │Postgres│ │ MinIO │
│ :6379 │ │ :5432 │ │ :9000 │
└───────┘ └───────┘ └───────┘
```

---

## Cost Optimization

### LLM Costs (per 1M tokens)

| Provider | Input | Output | Best For |
|----------|-------|--------|----------|
| **Kimi** | $3.29 | $3.29 | Cost-effective code gen |
| Claude Sonnet | $3 | $15 | Premium reasoning |
| Gemini Flash | ~$0.10 | ~$0.40 | Fast decisions |

### Strategy

1. Use **Gemini Flash** for Atomizer/Verifier (deterministic, cheap)
2. Use **Kimi** for code generation (67% savings vs Claude)
3. Reserve **Claude** for complex reasoning tasks
4. Enable caching to reduce repeat calls

### Monthly Estimate (100 tasks/day)

- With Kimi: ~$18/month
- With Claude: ~$54/month
- **Savings: $36/month**

---

## Troubleshooting

### Common Issues

| Issue | Solution |
|-------|----------|
| LLM API timeout | Check API keys, increase timeout |
| Database connection | Verify PostgreSQL is running |
| Redis connection | Verify Redis is running |
| Checkpoint restore fails | Check storage permissions |
| PTC service unavailable | Start PTC service, check port 8001 |

### Debug Mode

```bash
# Enable verbose logging
export ROMA_LOG_LEVEL=DEBUG
python -m roma_dspy.cli solve "task"

# Check API health
curl http://localhost:8000/health
curl http://localhost:8001/health
```

### Logs Location

- API logs: stdout (Docker) or `logs/roma.log`
- MLflow: `http://localhost:5000`
- Traces: `http://localhost:8000/traces`

---

## Changelog

### 2025-12-10
- Initial agents.md created
- Documented all 5 core agents
- Added PTC integration details
- Included cost optimization strategy

### Future Updates

- [ ] Add new agent types as implemented
- [ ] Update API endpoints
- [ ] Add performance benchmarks
- [ ] Document new tool integrations

---

## Quick Reference

### Agent Temperatures

```
Atomizer:   0.1 (deterministic)
Planner:    0.3 (balanced)
Executor:   0.7 (creative)
Aggregator: 0.3 (balanced)
Verifier:   0.1 (deterministic)
```

### Default Ports

```
ROMA API:    8000
PTC Service: 8001
Redis:       6379
PostgreSQL:  5432
MinIO:       9000, 9001
MLflow:      5000
```

### Key Paths

```
Config:      config/defaults/config.yaml
PTC Config:  config/ptc_integration.yaml
Tests:       tests/integration/
Docs:        docs/
Examples:    examples/
```

---

> **Maintainer**: Update this document when making significant changes to the agent system, configuration, or deployment process.
