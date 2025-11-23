# ROMA-DSPy Quick Start

Get started in **under 30 seconds** with no infrastructure required!

## What is ROMA-DSPy?

ROMA-DSPy is a framework for building production-ready AI agents using [DSPy](https://github.com/stanfordnlp/dspy). It provides:

- **Hierarchical Task Decomposition** - Break complex tasks into manageable subtasks
- **Modular Agent Architecture** - Atomizer, Planner, Executor, Aggregator, Verifier
- **Extensive Toolkit System** - File ops, code execution, web search, crypto data, and more
- **MCP Integration** - Connect to any Model Context Protocol server
- **Optional Production Features** - REST API, PostgreSQL persistence, MLflow observability, Docker deployment

## Prerequisites

### Minimal Installation (Recommended)
- **Python 3.12+**
- **API key** from OpenRouter, OpenAI, Anthropic, or Fireworks

### Full Installation (Optional)
- **Docker & Docker Compose** (for production features)
- **Just** command runner (optional but recommended)

---

## Quick Start (3 paths)

Choose your preferred setup method:

### Path A: Minimal Installation (Recommended - Start in 30 Seconds)

**Best for**: Quick evaluation, development, testing - no infrastructure required

**What you get:**
- ✅ Core agent framework (all modules)
- ✅ All DSPy prediction strategies
- ✅ File storage (no database needed)
- ✅ Built-in toolkits (Calculator, File ops)
- ✅ Works with any LLM provider

**What you DON'T need:**
- ❌ No Docker
- ❌ No PostgreSQL
- ❌ No MLflow
- ❌ No infrastructure setup

**Install in 30 seconds:**

```bash
# Install with uv (10-100x faster, recommended)
uv pip install roma-dspy

# Or with pip
pip install roma-dspy

# Set your API key
export OPENROUTER_API_KEY="sk-or-v1-..."

# Start solving tasks immediately
python -c "from roma_dspy.core.engine.solve import solve; print(solve('What is 2+2?'))"
```

**Python usage:**

```python
from roma_dspy.core.engine.solve import solve

# Simple task
result = solve("What is 25 * 47?")
print(result)

# More complex task
result = solve("Analyze the pros and cons of electric vehicles")
print(result)
```

**Installation time:** < 30 seconds
**Package size:** ~15 core dependencies
**Ready to use:** Immediately

---

### Path B: Full Installation with Docker (Production Features)

**Best for**: Production deployment with persistence, observability, and REST API

**Additional features:**
- ✅ REST API server
- ✅ PostgreSQL persistence
- ✅ MLflow observability
- ✅ S3 storage integration
- ✅ E2B code execution sandbox
- ✅ Interactive TUI visualization

1. **Clone and Configure**
   ```bash
   git clone https://github.com/your-org/ROMA-DSPy.git
   cd ROMA-DSPy

   # Copy environment template
   cp .env.example .env
   ```

2. **Configure Environment**
   Edit `.env` and add your API keys:
   ```bash
   # Required
   OPENROUTER_API_KEY=your_key_here

   # Optional (for specific features)
   E2B_API_KEY=your_key_here
   EXA_API_KEY=your_key_here
   ```

3. **Start Services**
   ```bash
   # Build and start all services
   just docker-up

   # Or with MLflow observability
   just docker-up-full

   # Check health
   curl http://localhost:8000/health
   ```

4. **Run Your First Task**
   ```bash
   # Via Docker CLI
   just solve "What is the capital of France?"

   # Or via REST API
   curl -X POST http://localhost:8000/api/v1/executions \
     -H "Content-Type: application/json" \
     -d '{"goal": "What is the capital of France?"}'
   ```

**Services Running:**
- API: http://localhost:8000
- PostgreSQL: localhost:5432
- MinIO: http://localhost:9001
- MLflow: http://localhost:5000 (with `--profile observability`)

---

### Path C: Crypto Agent (Domain-Specific Example)

**Best for**: Cryptocurrency analysis use case

1. **Quick Setup**
   ```bash
   just docker-up
   ```

2. **Run Crypto Analysis**
   ```bash
   # Get Bitcoin price
   just solve "What is the current price of Bitcoin?" crypto_agent

   # Complex analysis
   just solve "Compare Bitcoin and Ethereum prices, analyze 7-day trends" crypto_agent

   # DeFi analysis
   just solve "Show top 10 DeFi protocols by TVL" crypto_agent
   ```

**Crypto Agent Includes:**
- CoinGecko (15,000+ cryptocurrencies)
- Binance (spot/futures markets)
- DefiLlama (DeFi protocol data)
- Arkham (blockchain analytics)
- Exa (web search)

---

## Installation Comparison

| Feature | Minimal | Docker Full |
|---------|---------|-------------|
| **Install time** | < 30 seconds | 2-5 minutes |
| **Prerequisites** | Python 3.12+ | Docker + Docker Compose |
| **Infrastructure** | None required | PostgreSQL, MinIO, MLflow (auto-deployed) |
| **Package size** | ~15 dependencies | All features |
| **Use case** | Quick eval, dev, testing | Production deployment |
| **Core framework** | ✅ | ✅ |
| **DSPy strategies** | ✅ | ✅ |
| **File storage** | ✅ | ✅ |
| **Built-in toolkits** | ✅ | ✅ |
| **REST API** | ❌ | ✅ |
| **PostgreSQL persistence** | ❌ | ✅ |
| **MLflow tracking** | ❌ | ✅ |
| **S3 storage** | ❌ | ✅ |
| **E2B sandbox** | ❌ | ✅ |
| **TUI visualization** | ❌ | ✅ |

**Key difference**:
- **Minimal** = Just Python package (no Docker, no services)
- **Docker** = Complete production stack (PostgreSQL, MLflow, API, all features via docker-compose)

---

## Adding Features to Minimal Install

You can install Python dependencies for optional features:

```bash
# Install dependencies for specific features
uv pip install roma-dspy[api]          # REST API dependencies
uv pip install roma-dspy[persistence]  # PostgreSQL client dependencies
uv pip install roma-dspy[observability] # MLflow client dependencies
uv pip install roma-dspy[e2b]          # E2B code execution
uv pip install roma-dspy[tui]          # TUI visualization
uv pip install roma-dspy[dev]          # Development tools

# Install all Python dependencies
uv pip install roma-dspy[all]
```

**Important**: Installing extras only adds Python dependencies. Services like PostgreSQL, MLflow, and the API server require Docker or separate deployment.

**For production use with all features, use Docker (Path B)**.

---

## Just Commands Cheat Sheet

### Basic Usage
```bash
just                      # List all commands
just solve "task"         # Solve task with Docker
just viz <execution_id>   # Visualize execution DAG
```

### Docker Management
```bash
just docker-up            # Start services
just docker-up-full       # Start with MLflow
just docker-down          # Stop services
just docker-logs          # View logs
just docker-ps            # Check status
just docker-shell         # Open shell in container
```

### Development
```bash
just install              # Install dependencies
just test                 # Run tests
just lint                 # Check code quality
just format               # Format code
just clean                # Clean cache
```

### List Available Profiles
```bash
just list-profiles
# Output:
#   - crypto_agent
#   - general
```

---

## Verify Installation

### 1. Check Health
```bash
curl http://localhost:8000/health
```

Expected response:
```json
{
  "status": "healthy",
  "version": "1.0.0",
  "storage_connected": true,
  "active_executions": 0,
  "uptime_seconds": 123.45
}
```

### 2. Test via CLI
```bash
# Simple calculation
just solve "Calculate 15% of 2500"

# Get execution ID from output, then visualize
just viz <execution_id>
```

### 3. Test via API
```bash
# Create execution (max_depth=1 or 2 recommended)
curl -X POST http://localhost:8000/api/v1/executions \
  -H "Content-Type: application/json" \
  -d '{
    "goal": "What are the prime numbers between 1 and 20?",
    "max_depth": 2
  }' | jq

# Poll status (use execution_id from response)
curl http://localhost:8000/api/v1/executions/<execution_id>/status | jq
```

---

## Configuration Profiles

ROMA-DSPy uses profiles to pre-configure agents for different use cases.

### Available Profiles

| Profile | Purpose | Models | Toolkits |
|---------|---------|--------|----------|
| **general** | General-purpose tasks | Gemini Flash + Claude Sonnet | E2B, FileToolkit, CalculatorToolkit, Exa MCP |
| **crypto_agent** | Cryptocurrency analysis | Multiple (task-aware) | CoinGecko, Binance, DefiLlama, Arkham, E2B |

### Using a Profile

```bash
# Via CLI (defaults to 'general' if not specified)
just solve "your task"
just solve "crypto task" crypto_agent

# Via API
curl -X POST http://localhost:8000/api/v1/executions \
  -H "Content-Type: application/json" \
  -d '{
    "goal": "Your task",
    "config_profile": "general"
  }'
```

### Custom Profile

Create `config/profiles/my_profile.yaml`:
```yaml
agents:
  executor:
    llm:
      model: openai/gpt-4o
      temperature: 0.3
    prediction_strategy: react
    toolkits:
      - class_name: FileToolkit
        enabled: true
      - class_name: CalculatorToolkit
        enabled: true

runtime:
  max_depth: 2  # 1-2 recommended for most tasks
```

Use it:
```bash
just solve "task" my_profile
```

See [CONFIGURATION.md](CONFIGURATION.md) for complete guide.

---

## Environment Variables

### Required
```bash
# LLM Provider (choose one or use OpenRouter for all)
OPENROUTER_API_KEY=xxx        # Recommended (single key for all models)
# OR individual providers:
OPENAI_API_KEY=xxx
ANTHROPIC_API_KEY=xxx
GOOGLE_API_KEY=xxx
```

### Optional Features
```bash
# Code Execution (E2B)
E2B_API_KEY=xxx

# Web Search (Exa MCP)
EXA_API_KEY=xxx

# Web Search (Serper Toolkit)
SERPER_API_KEY=xxx

# Crypto APIs (all public, no keys needed)
# CoinGecko, Binance, DefiLlama, Arkham work without keys
```

### Storage & Database
```bash
# PostgreSQL (auto-configured in Docker)
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/roma_dspy
POSTGRES_ENABLED=true

# S3 Storage (optional)
STORAGE_BASE_PATH=/opt/sentient
ROMA_S3_BUCKET=your-bucket
AWS_ACCESS_KEY_ID=xxx
AWS_SECRET_ACCESS_KEY=xxx
```

---

## Common Tasks

### 1. Solve a Task
```bash
# Simple (uses 'general' profile by default)
just solve "What is 2+2?"

# With specific profile
just solve "Analyze Bitcoin" crypto_agent

# With all options
just solve "Complex task" crypto_agent 5 true json
# Parameters: <task> [profile] [max_depth] [verbose] [output_format]
```

### 2. Check Execution
```bash
# List all executions
curl http://localhost:8000/api/v1/executions | jq

# Get specific execution
curl http://localhost:8000/api/v1/executions/<id> | jq

# Get execution status
curl http://localhost:8000/api/v1/executions/<id>/status | jq
```

### 3. View Logs
```bash
# All services
just docker-logs

# Specific service
just docker-logs-service roma-api
just docker-logs-service postgres
just docker-logs-service mlflow
```

### 4. Interactive Visualization
```bash
# After solving a task, get execution_id
just solve "Complex task"

# Visualize execution tree
just viz <execution_id>
```

---

## Examples

### Example 1: Simple Calculation
```bash
just solve "Calculate compound interest on $10,000 at 5% annual rate for 10 years"
```

### Example 2: Web Research
```bash
just solve "Research the latest developments in quantum computing and summarize in 3 bullet points"
```

### Example 3: Code Execution
```bash
just solve "Generate a Python script that creates a fibonacci sequence up to 100, execute it, and show results"
```

### Example 4: Crypto Analysis
```bash
just solve "Compare Bitcoin and Ethereum market caps, 24h volumes, and price changes" crypto_agent
```

### Example 5: File Operations
```bash
just solve "Create a JSON file with data about the top 5 programming languages and their use cases"
```

---

## Troubleshooting

### Docker not starting
```bash
# Check Docker is running
docker ps

# Rebuild images
just docker-down
just docker-build-clean
just docker-up

# Check logs
just docker-logs
```

### API not responding
```bash
# Check health
curl http://localhost:8000/health

# Check container status
just docker-ps

# View logs
just docker-logs-service roma-api
```

### Database connection errors
```bash
# Check postgres is running
docker ps | grep postgres

# Check connection
docker exec -it roma-dspy-postgres psql -U postgres -d roma_dspy -c "SELECT 1"

# Verify DATABASE_URL in .env matches docker-compose.yaml
```

### Missing API keys
```bash
# Verify keys are set
docker exec -it roma-dspy-api env | grep API_KEY

# Restart after changing .env
just docker-restart
```

### E2B not working
```bash
# Check E2B key is set
echo $E2B_API_KEY

# Test E2B connection
just e2b-test

# Build custom template (if using S3 mount)
just e2b-build
```

---

## Next Steps

### Learn More
- **[Configuration Guide](CONFIGURATION.md)** - Profiles, agents, settings
- **[Toolkits Reference](TOOLKITS.md)** - All available toolkits
- **[MCP Integration](MCP.md)** - Using MCP servers
- **[API Reference](API.md)** - REST API endpoints
- **[Deployment Guide](DEPLOYMENT.md)** - Production deployment
- **[Observability](OBSERVABILITY.md)** - MLflow tracking

### Explore Examples
```bash
# See all example configurations
ls config/examples/*/

# Try different examples
just solve "task" -c config/examples/basic/minimal.yaml
```

### Customize
1. Create custom profiles in `config/profiles/`
2. Add custom toolkits (see [TOOLKITS.md](TOOLKITS.md))
3. Configure agents per task type (see [CONFIGURATION.md](CONFIGURATION.md))

### Deploy
```bash
# Production deployment
just deploy-full

# Check deployment
just health-check
```

---

## REST API

ROMA-DSPy includes a production-ready REST API for programmatic access.

### Quick Start

```bash
# Start API server (via Docker)
just docker-up

# Verify server is running
curl http://localhost:8000/health
```

### API Documentation

FastAPI provides interactive API documentation:

- **Swagger UI** (interactive testing): http://localhost:8000/docs
- **ReDoc** (clean reference): http://localhost:8000/redoc
- **OpenAPI JSON**: http://localhost:8000/openapi.json

### Example Usage

```bash
# Start execution
curl -X POST http://localhost:8000/api/v1/executions \
  -H "Content-Type: application/json" \
  -d '{"goal": "What is 2+2?", "max_depth": 1}' | jq

# Get status (use execution_id from response)
curl http://localhost:8000/api/v1/executions/<execution_id>/status | jq

# Get metrics
curl http://localhost:8000/api/v1/executions/<execution_id>/metrics | jq
```

**See** http://localhost:8000/docs **for complete API reference with all endpoints, schemas, and interactive testing.**

---

## Getting Help

- **Documentation**: `docs/` directory
- **Examples**: `config/examples/`
- **Issues**: GitHub Issues
- **Just Commands**: Run `just` to see all available commands

---

**You're all set!** Start building with ROMA-DSPy 🚀
