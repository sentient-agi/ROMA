# ROMA v0.2.0 Release Notes

## 🎉 Major Release: Complete Framework Rewrite

We're excited to announce **ROMA v0.2.0**, a complete rewrite of the framework built on [DSPy](https://github.com/stanfordnlp/dspy). This release transforms ROMA into a production-ready, hierarchical multi-agent framework with powerful new capabilities.

---

## ⚠️ Breaking Changes

**This is a major architectural rewrite.** Code written for v1.0.0 is **not compatible** with v0.2.0.

### What Changed:
- Complete migration to DSPy-based module system
- New configuration system using OmegaConf
- Restructured API and module interfaces
- Updated storage and execution model

### Migration Guide:
If you're upgrading from v1.0.0:

1. **Review the new module system**: All agents now inherit from `BaseModule`
2. **Update configuration**: Switch to YAML-based profiles (see `config/profiles/`)
3. **Update imports**: Core modules moved to `roma_dspy.core.modules`
4. **Check toolkit usage**: New toolkit system with 9 built-in toolkits
5. **API changes**: If using programmatically, review the new signatures

See the updated [README](README.md) and [Quick Start Guide](docs/QUICKSTART.md) for examples.

---

## 🚀 What's New

### 🏗️ DSPy-Powered Architecture

Complete rewrite using Stanford's DSPy framework:
- **BaseModule**: Unified base class for all agent modules
- **Flexible prediction strategies**: CoT, ReAct, CodeAct, BestOfN, and more
- **LM abstraction**: Easy model swapping and runtime configuration
- **Async-first**: Native support for async execution with graceful fallbacks

### 🐳 Production-Ready Deployment

One-command Docker deployment with full production stack:

```bash
just setup  # Interactive setup with all services
```

**Included Services:**
- 🚀 **FastAPI REST API** with OpenAPI documentation
- 🗄️ **PostgreSQL** for persistence
- 📦 **MinIO** S3-compatible object storage
- 📊 **MLflow** for experiment tracking and observability

### 🧰 9 Built-in Toolkits

Powerful toolkit system extending agent capabilities:

**Core Toolkits:**
- **FileToolkit**: File system operations
- **CalculatorToolkit**: Mathematical computations
- **E2BToolkit**: Secure code execution in sandboxed environments

**Crypto Toolkits:**
- **CoinGeckoToolkit**: Cryptocurrency data and pricing
- **BinanceToolkit**: Exchange data and trading info
- **DefiLlamaToolkit**: DeFi protocol analytics
- **ArkhamToolkit**: Blockchain intelligence

**Search:**
- **SerperToolkit**: Web search capabilities

**Universal:**
- **MCPToolkit**: Connect to any [Model Context Protocol](https://github.com/wong2/awesome-mcp-servers) server

### ⚙️ Advanced Configuration System

Flexible YAML-based configuration with profiles:

```yaml
# config/profiles/crypto_agent.yaml
agents:
  executor:
    llm:
      model: "openrouter/anthropic/claude-3.5-sonnet"
      temperature: 0.7
    toolkits:
      - class_name: "CoinGeckoToolkit"
        enabled: true
      - class_name: "E2BToolkit"
        enabled: true
```

**Features:**
- Profile-based configuration (general, crypto_agent, test)
- Runtime overrides via command-line
- Task-aware agent mapping
- Custom prompt templates with Jinja2

### 📂 Execution-Scoped Storage

Isolated storage for each task execution:

- Automatic directory creation per execution ID
- S3-compatible storage via MinIO
- Parquet integration for large data (>100KB threshold)
- Built-in FileStorage for toolkit access

### 🌐 REST API & CLI

**REST API:**
```bash
# Interactive API documentation
http://localhost:8000/docs

# Create execution
POST /api/v1/executions

# Get execution status
GET /api/v1/executions/{id}

# Visualize execution tree
GET /api/v1/executions/{id}/visualize
```

**CLI:**
```bash
# Local execution
roma-dspy solve "Your task" --profile crypto_agent

# Server management
roma-dspy server start
roma-dspy server health

# Execution management
roma-dspy exec create "Task"
roma-dspy exec status <id> --watch

# Interactive TUI visualization
just viz <execution_id>
```

### 📊 Enhanced Observability

**MLflow Integration:**
- Automatic experiment tracking
- Metric logging (cost, latency, token usage)
- Parameter tracking
- Execution artifact storage

**Built-in Visualization:**
- Interactive TUI for execution trees
- LLM-friendly text visualizations
- DAG integrity validation
- Checkpoint support for long-running tasks

### 🔧 Developer Experience

**Improved Module System:**
```python
from roma_dspy import Atomizer, Planner, Executor, Aggregator, Verifier

# Consistent interface across all modules
executor = Executor(
    model="openrouter/openai/gpt-4o-mini",
    prediction_strategy="react",
    tools=[get_weather, search_web]
)

result = executor.forward("What's the weather in Tokyo?")
```

**Resilience Features:**
- Automatic retry with exponential backoff
- Circuit breaker pattern
- Checkpoint/resume for long tasks
- Error handling and recovery

**Testing Infrastructure:**
- Unit test suite
- Integration tests
- Test profile configuration
- Justfile commands for easy testing

---

## 📚 New Documentation

Comprehensive documentation in the `docs/` directory:

- **[Quick Start Guide](docs/QUICKSTART.md)** - Get started in under 10 minutes
- **[Configuration Guide](docs/CONFIGURATION.md)** - Complete configuration reference
- **[Toolkits Reference](docs/TOOLKITS.md)** - All built-in and custom toolkits
- **[Deployment Guide](docs/DEPLOYMENT.md)** - Production deployment with Docker
- **[E2B Setup](docs/E2B_SETUP.md)** - Code execution toolkit setup
- **[Observability](docs/OBSERVABILITY.md)** - MLflow tracking and monitoring

---

## 🛠️ Technical Improvements

### Core Engine
- Event-driven execution scheduler
- DAG-based task management with integrity validation
- Transitive property propagation in execution context
- Cost tracking across all LLM calls
- Deep copy support for DSPy signatures

### Prompt Optimization
- GEPA (Grounded Efficient Prompt Adaptation) support
- Automatic prompt optimization with DSPy
- Custom instruction templates per module
- Jinja2 template system

### Data & Metrics
- Added multiple search-related datasets
- Enhanced metrics collection
- Automatic data storage for large responses
- Parquet format for efficient storage

### Infrastructure
- Docker multi-stage builds
- Environment-based configuration
- Database migrations with Alembic
- Volume mounting for S3 storage
- Health check endpoints

---

## 🔄 Migration from v1.0.0

### Key Changes to Address:

1. **Module Initialization:**
   ```python
   # v1.0.0 (old)
   from roma import Agent
   agent = Agent(config)

   # v0.2.0 (new)
   from roma_dspy import Executor
   executor = Executor(
       model="openrouter/openai/gpt-4o-mini",
       prediction_strategy="react"
   )
   ```

2. **Configuration:**
   ```python
   # v1.0.0 (old)
   config = load_config("config.json")

   # v0.2.0 (new)
   from roma_dspy.config import load_config
   config = load_config(profile="general")
   ```

3. **Task Execution:**
   ```python
   # v1.0.0 (old)
   result = agent.run(task)

   # v0.2.0 (new)
   from roma_dspy.core.engine.solve import solve
   result = solve("Your task", profile="general")
   ```

---

## 🙏 Acknowledgments

This release builds on amazing open-source work:
- [DSPy](https://dspy.ai/) - Framework for programming AI agents
- [E2B](https://github.com/e2b-dev/e2b) - Cloud runtime for AI agents
- [Pydantic](https://github.com/pydantic/pydantic) - Data validation
- Inspired by ["Beyond Outlining: Heterogeneous Recursive Planning"](https://arxiv.org/abs/2503.08275)

---

## 📦 Installation

**Docker (Recommended):**
```bash
git clone https://github.com/sentient-agi/ROMA.git
cd ROMA
just setup
```

**Local Development:**
```bash
pip install -e .
# or with API support
pip install -e ".[api]"
```

---

## 🐛 Known Issues

- Prompt optimization (GEPA) requires manual tuning for optimal results
- Some async operations may fall back to sync in specific scenarios
- E2B template setup requires manual configuration (guided in setup)

---

## 🔮 What's Next

We're committed to making ROMA the best hierarchical agent framework. Future releases will focus on:
- Additional toolkit integrations
- Enhanced prompt optimization
- Performance improvements
- Community-contributed toolkits and profiles

---

## 💬 Community

- **Discord**: [Join our community](https://discord.gg/sentientfoundation)
- **Twitter/X**: [@SentientAGI](https://x.com/SentientAGI)
- **Issues**: [GitHub Issues](https://github.com/sentient-agi/ROMA/issues)
- **Homepage**: [sentient.xyz](https://www.sentient.xyz/)

---

**Full Changelog**: https://github.com/sentient-agi/ROMA/compare/v1.0.0...v0.2.0
