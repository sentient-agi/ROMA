# ROMA-DSPy Configuration Guide

Complete reference for configuring ROMA-DSPy agents, profiles, toolkits, and runtime settings.

## Table of Contents

- [Overview](#overview)
- [Configuration System](#configuration-system)
- [Profiles](#profiles)
- [Agents Configuration](#agents-configuration)
- [Task-Aware Agent Mapping](#task-aware-agent-mapping)
- [Toolkit Configuration](#toolkit-configuration)
- [LLM Configuration](#llm-configuration)
- [Runtime Settings](#runtime-settings)
- [Storage Configuration](#storage-configuration)
- [Observability (MLflow)](#observability-mlflow)
- [Resilience Settings](#resilience-settings)
- [Logging Configuration](#logging-configuration)
- [Environment Variables](#environment-variables)
- [Custom Prompts and Demos](#custom-prompts-and-demos)
- [Configuration Examples](#configuration-examples)
- [Best Practices](#best-practices)

---

## Overview

ROMA-DSPy uses a **layered configuration system** combining:
- **OmegaConf**: Flexible YAML configuration with interpolation
- **Pydantic**: Type-safe validation and defaults
- **Profiles**: Pre-configured setups for different use cases
- **Environment Variables**: Runtime overrides

### Key Features

- **Hierarchical Merging**: Combine defaults, profiles, and overrides
- **Type Validation**: Catch configuration errors early
- **Environment Interpolation**: `${oc.env:API_KEY}` for secrets
- **Profile System**: Pre-configured agents for different domains
- **Task-Aware Mapping**: Different executors for different task types

---

## Configuration System

### Resolution Order

Configuration is loaded and merged in this order:

1. **Pydantic Defaults** - Base defaults from schema classes
2. **YAML Config** - Explicit configuration file
3. **Profile** - Profile overlay (if specified)
4. **CLI/Runtime Overrides** - Command-line arguments
5. **Environment Variables** - `ROMA__*` variables
6. **Validation** - Final validation via Pydantic

Later layers override earlier ones.

### Using Configuration

#### Via CLI
```bash
# Use a profile
uv run python -m roma_dspy.cli solve "task" --profile crypto_agent

# Use custom config file
uv run python -m roma_dspy.cli solve "task" --config config/examples/basic/minimal.yaml

# With overrides
uv run python -m roma_dspy.cli solve "task" \
  --profile general \
  --override agents.executor.llm.temperature=0.5
```

#### Via Docker (Just)
```bash
# Use profile
just solve "task" crypto_agent

# With all parameters
just solve "task" general 2 true json
# Parameters: <task> [profile] [max_depth] [verbose] [output]
```

#### Via API
```bash
curl -X POST http://localhost:8000/api/v1/executions \
  -H "Content-Type: application/json" \
  -d '{
    "goal": "Your task",
    "config_profile": "general",
    "max_depth": 2
  }'
```

#### Programmatically
```python
from roma_dspy.config.manager import ConfigManager

# Load profile
config_mgr = ConfigManager()
config = config_mgr.load_config(profile="general")

# Load custom config
config = config_mgr.load_config(
    config_path="config/custom.yaml",
    overrides=["runtime.max_depth=2"]
)

# With environment prefix
config = config_mgr.load_config(
    profile="crypto_agent",
    env_prefix="ROMA_"
)
```

---

## Profiles

Profiles are pre-configured agent setups for different use cases. Located in `config/profiles/`.

### Available Profiles

| Profile | Purpose | Use Cases | Models |
|---------|---------|-----------|--------|
| **general** | General-purpose agent | Web research, code execution, file ops, calculations | Gemini Flash + Claude Sonnet 4.5 |
| **crypto_agent** | Cryptocurrency analysis | Price tracking, DeFi analysis, on-chain data | Task-aware (Gemini Flash / Claude Sonnet 4.5) |

### Profile Structure

```yaml
# config/profiles/general.yaml
agents:
  atomizer:
    llm:
      model: openrouter/google/gemini-2.5-flash
      temperature: 0.0
      max_tokens: 8000
    signature_instructions: "prompt_optimization.seed_prompts.atomizer_seed:ATOMIZER_PROMPT"
    demos: "prompt_optimization.seed_prompts.atomizer_seed:ATOMIZER_DEMOS"

  executor:
    llm:
      model: openrouter/anthropic/claude-sonnet-4.5
      temperature: 0.2
      max_tokens: 32000
    prediction_strategy: react
    toolkits:
      - class_name: E2BToolkit
        enabled: true
      - class_name: FileToolkit
        enabled: true

runtime:
  max_depth: 6
  enable_logging: true
```

### Creating Custom Profiles

Create `config/profiles/my_profile.yaml`:

```yaml
agents:
  executor:
    llm:
      model: openrouter/anthropic/claude-sonnet-4.5
      temperature: 0.3
      max_tokens: 16000
    prediction_strategy: react
    toolkits:
      - class_name: MCPToolkit
        enabled: true
        toolkit_config:
          server_name: my_server
          server_type: http
          url: https://my-mcp-server.com

runtime:
  max_depth: 2  # Recommended: 1-2 for most tasks
  timeout: 120
  enable_logging: true
```

Use it:
```bash
just solve "task" my_profile
```

---

## Agents Configuration

ROMA-DSPy has 5 core agent modules. Each can be configured independently.

### Agent Types

| Agent | Role | Default Strategy | Toolkits |
|-------|------|-----------------|----------|
| **Atomizer** | Classifies tasks as atomic or decomposable | chain_of_thought | None |
| **Planner** | Breaks complex tasks into subtasks | chain_of_thought | None |
| **Executor** | Executes atomic tasks | react | All toolkits |
| **Aggregator** | Synthesizes subtask results | chain_of_thought | None |
| **Verifier** | Validates outputs | chain_of_thought | None |

### Agent Configuration Schema

```yaml
agents:
  executor:  # Agent type: atomizer, planner, executor, aggregator, verifier
    # LLM configuration
    llm:
      model: openrouter/anthropic/claude-sonnet-4.5
      temperature: 0.2
      max_tokens: 32000
      timeout: 30
      num_retries: 3
      cache: true

    # Prediction strategy (chain_of_thought or react)
    prediction_strategy: react

    # Custom prompts (optional)
    signature_instructions: "module.path:VARIABLE_NAME"
    demos: "module.path:DEMOS_LIST"

    # Agent-specific settings
    agent_config:
      max_executions: 10  # Max iterations for executor
      # max_subtasks: 12  # Max subtasks for planner

    # Strategy-specific settings
    strategy_config:
      # ReAct-specific settings

    # Toolkits (executor only)
    toolkits:
      - class_name: E2BToolkit
        enabled: true
        toolkit_config:
          timeout: 600
```

### Per-Agent Defaults

Each agent has sensible defaults. Override only what you need:

```yaml
# Minimal executor override
agents:
  executor:
    llm:
      temperature: 0.3  # Override just temperature
    # All other settings use defaults
```

### Agent-Specific Settings

#### Atomizer
```yaml
atomizer:
  agent_config:
    confidence_threshold: 0.8  # Threshold for atomic classification
```

#### Planner
```yaml
planner:
  agent_config:
    max_subtasks: 12  # Maximum subtasks to generate
```

#### Executor
```yaml
executor:
  agent_config:
    max_executions: 10  # Maximum ReAct iterations
```

#### Aggregator
```yaml
aggregator:
  agent_config:
    synthesis_strategy: hierarchical  # How to aggregate results
```

#### Verifier
```yaml
verifier:
  agent_config:
    verification_depth: moderate  # Verification thoroughness
```

---

## Task-Aware Agent Mapping

**Advanced Feature**: Use different executor configurations for different task types.

### Task Types

ROMA-DSPy classifies tasks into 5 types:

| Task Type | Description | Example Tasks |
|-----------|-------------|---------------|
| **RETRIEVE** | Data fetching, web search | "price of bitcoin", "find documentation" |
| **CODE_INTERPRET** | Code execution, analysis | "run this script", "analyze CSV data" |
| **THINK** | Deep reasoning, analysis | "compare approaches", "analyze sentiment" |
| **WRITE** | Content creation | "write report", "create documentation" |
| **IMAGE_GENERATION** | Image creation | "generate diagram", "create visualization" |

### Mapping Configuration

```yaml
# Default agents (used for atomizer, planner, aggregator, verifier)
agents:
  executor:
    llm:
      model: openrouter/anthropic/claude-sonnet-4.5
    prediction_strategy: react
    toolkits:
      - class_name: FileToolkit
        enabled: true

# Task-specific executor configurations
agent_mapping:
  executors:
    # RETRIEVE: Fast model + web search
    RETRIEVE:
      llm:
        model: openrouter/google/gemini-2.5-flash  # Fast & cheap
        temperature: 0.0
        max_tokens: 16000
      prediction_strategy: react
      agent_config:
        max_executions: 6
      toolkits:
        - class_name: MCPToolkit
          enabled: true
          toolkit_config:
            server_name: exa
            server_type: http
            url: https://mcp.exa.ai/mcp

    # CODE_INTERPRET: Powerful model + code execution
    CODE_INTERPRET:
      llm:
        model: openrouter/anthropic/claude-sonnet-4.5  # Powerful
        temperature: 0.1
        max_tokens: 32000
      agent_config:
        max_executions: 15
      toolkits:
        - class_name: E2BToolkit
          enabled: true
        - class_name: FileToolkit
          enabled: true
```

### Benefits

- **Cost Optimization**: Use cheap models for simple tasks
- **Quality Optimization**: Use powerful models for complex tasks
- **Right Tools**: Each task type gets appropriate toolkits
- **Performance**: Faster execution with task-specific configs

### Example: crypto_agent Profile

The `crypto_agent` profile uses task-aware mapping:

- **RETRIEVE**: Gemini Flash (fast, cheap) + CoinGecko/Binance
- **CODE_INTERPRET**: Claude Sonnet 4.5 (powerful) + E2B + crypto data
- **THINK**: Claude Sonnet 4.5 + all toolkits
- **WRITE**: Claude Sonnet 4.5 (creative) + FileToolkit + research

---

## Toolkit Configuration

Toolkits provide tools (functions) that agents can use. Configured per-agent.

### Available Toolkits

#### Native Toolkits

ROMA-DSPy includes these built-in toolkits:

| Toolkit | Purpose | API Key Required | Config Options |
|---------|---------|-----------------|----------------|
| **FileToolkit** | File I/O operations | ❌ No | `enable_delete`, `max_file_size` |
| **CalculatorToolkit** | Math operations | ❌ No | None |
| **E2BToolkit** | Code execution sandbox | ✅ Yes | `timeout`, `auto_reinitialize` |
| **SerperToolkit** | Web search | ✅ Yes | `num_results`, `search_type` |
| **BinanceToolkit** | Crypto market data | ❌ No | `default_market`, `enable_analysis` |
| **CoinGeckoToolkit** | Crypto prices | ❌ No | `use_pro_api` |
| **DefiLlamaToolkit** | DeFi protocol data | ❌ No | `enable_pro_features` |
| **ArkhamToolkit** | Blockchain analytics | ❌ No | `enable_analysis` |

#### MCP Toolkit

The **MCPToolkit** is special - it can connect to **any** MCP (Model Context Protocol) server, giving you access to thousands of potential tools.

**Two Types of MCP Servers:**

1. **HTTP MCP Servers** (Remote)
   - Public or private HTTP endpoints
   - No installation required
   - Examples: CoinGecko MCP, Exa MCP, or any custom HTTP MCP server

2. **Stdio MCP Servers** (Local)
   - Run as local subprocesses
   - Typically npm packages or custom scripts
   - Examples: Filesystem, GitHub, SQLite, or any npm MCP server

**Finding MCP Servers:**
- **Awesome MCP Servers**: https://github.com/wong2/awesome-mcp-servers (hundreds of servers)
- **MCP Documentation**: https://modelcontextprotocol.io/
- **Build your own**: Any server implementing MCP protocol

### Basic Toolkit Configuration

```yaml
agents:
  executor:
    toolkits:
      # Simple toolkit with no config
      - class_name: CalculatorToolkit
        enabled: true

      # Toolkit with basic config
      - class_name: FileToolkit
        enabled: true
        toolkit_config:
          enable_delete: false
          max_file_size: 10485760  # 10MB
```

### E2B Toolkit Configuration

```yaml
- class_name: E2BToolkit
  enabled: true
  toolkit_config:
    timeout: 600  # Execution timeout (seconds)
    max_lifetime_hours: 23.5  # Sandbox lifetime
    auto_reinitialize: true  # Auto-restart on failure
```

**Environment Variables**:
```bash
E2B_API_KEY=your_e2b_api_key
E2B_TEMPLATE_ID=roma-dspy-sandbox  # Custom template
STORAGE_BASE_PATH=/opt/sentient  # Shared storage
```

### MCP Toolkit Configuration

#### HTTP MCP Server (Public)

Connect to any public HTTP MCP server:

```yaml
- class_name: MCPToolkit
  enabled: true
  toolkit_config:
    server_name: coingecko_mcp
    server_type: http
    url: "https://mcp.api.coingecko.com/sse"
    use_storage: true  # Store large results to Parquet
    storage_threshold_kb: 10  # Store if > 10KB
```

#### HTTP MCP Server (With Authentication)

Connect to any authenticated HTTP MCP server:

```yaml
- class_name: MCPToolkit
  enabled: true
  toolkit_config:
    server_name: exa
    server_type: http
    url: https://mcp.exa.ai/mcp
    headers:
      Authorization: Bearer ${oc.env:EXA_API_KEY}
      # Add any custom headers your MCP server needs
    transport_type: streamable
    use_storage: false
    tool_timeout: 60
```

#### Stdio MCP Server (Local)

Connect to any stdio MCP server (npm package or custom script):

```yaml
- class_name: MCPToolkit
  enabled: true
  toolkit_config:
    server_name: filesystem
    server_type: stdio
    command: npx  # or python, node, etc.
    args:
      - "-y"
      - "@modelcontextprotocol/server-filesystem"
      - "/Users/yourname/Documents"  # Server-specific arguments
    env:  # Optional environment variables for the server
      CUSTOM_VAR: value
    use_storage: false
```

**Common Stdio Examples:**

```yaml
# GitHub MCP Server
- class_name: MCPToolkit
  toolkit_config:
    server_name: github
    server_type: stdio
    command: npx
    args:
      - "-y"
      - "@modelcontextprotocol/server-github"
    env:
      GITHUB_PERSONAL_ACCESS_TOKEN: ${oc.env:GITHUB_PERSONAL_ACCESS_TOKEN}

# SQLite MCP Server
- class_name: MCPToolkit
  toolkit_config:
    server_name: sqlite
    server_type: stdio
    command: npx
    args:
      - "-y"
      - "@modelcontextprotocol/server-sqlite"
      - "/path/to/database.db"

# Custom Python MCP Server
- class_name: MCPToolkit
  toolkit_config:
    server_name: my_custom_server
    server_type: stdio
    command: python
    args:
      - "/path/to/my_mcp_server.py"
```

**Prerequisites for Stdio Servers**:
- npm packages: `npm install -g <package-name>`
- Custom scripts: Ensure executable and implements MCP protocol

### Crypto Toolkit Configuration

#### Binance

```yaml
- class_name: BinanceToolkit
  enabled: true
  include_tools:  # Optional: limit to specific tools
    - get_current_price
    - get_ticker_stats
    - get_klines
  toolkit_config:
    enable_analysis: true
    default_market: spot  # spot or futures
```

#### DefiLlama

```yaml
- class_name: DefiLlamaToolkit
  enabled: true
  include_tools:
    - get_protocols
    - get_protocol_tvl
    - get_chains
  toolkit_config:
    enable_analysis: true
    enable_pro_features: true
```

### Tool Filtering

Limit which tools from a toolkit are available:

```yaml
- class_name: MCPToolkit
  enabled: true
  include_tools:  # Only these tools
    - get_simple_price
    - get_coins_markets
    - get_search
  toolkit_config:
    server_name: coingecko_mcp
    server_type: http
    url: "https://mcp.api.coingecko.com/sse"
```

---

## LLM Configuration

Configure language models for each agent.

### Basic LLM Config

```yaml
agents:
  executor:
    llm:
      model: openrouter/anthropic/claude-sonnet-4.5
      temperature: 0.2
      max_tokens: 32000
      timeout: 30
      num_retries: 3
      cache: true
```

### LLM Parameters

| Parameter | Description | Range | Default |
|-----------|-------------|-------|---------|
| **model** | Model identifier | Provider-specific | `gpt-4o-mini` |
| **temperature** | Randomness (0=deterministic, 2=creative) | 0.0 - 2.0 | 0.7 |
| **max_tokens** | Maximum output tokens | 1 - 200000 | 2000 |
| **timeout** | Request timeout (seconds) | > 0 | 30 |
| **num_retries** | Retry attempts on failure | 0 - 10 | 3 |
| **cache** | Enable DSPy caching | true/false | true |
| **adapter_type** | DSPy adapter type | `json` or `chat` | `json` |
| **use_native_function_calling** | Enable native tool calling | true/false | `true` |

### DSPy Adapter Configuration

ROMA-DSPy uses DSPy adapters to format inputs/outputs for LLMs. Two adapter types are available:

**JSONAdapter** (default, recommended):
- Uses structured JSON for inputs/outputs
- Better performance for Claude and Gemini models
- Cleaner prompt formatting

**ChatAdapter**:
- Uses chat message format
- Better performance for some OpenAI models
- More conversational style

**Native Function Calling** (enabled by default):
- Leverages LLM provider's native tool calling APIs (OpenAI, Anthropic, etc.)
- Automatic fallback to text-based parsing for unsupported models
- No reliability difference, cleaner provider integration

Both parameters have sensible defaults and are **optional** in configuration:

```yaml
agents:
  executor:
    llm:
      model: openrouter/anthropic/claude-sonnet-4.5
      temperature: 0.2
      max_tokens: 16000
      # Defaults: adapter_type=json, use_native_function_calling=true
      # Uncomment to override:
      # adapter_type: chat
      # use_native_function_calling: false
```

### Model Naming

#### OpenRouter (Recommended)

Single API key for all models:

```yaml
model: openrouter/anthropic/claude-sonnet-4.5
model: openrouter/google/gemini-2.5-flash
model: openrouter/openai/gpt-4o
```

**Environment**: `OPENROUTER_API_KEY=your_key`

#### Direct Providers

```yaml
# Anthropic
model: claude-sonnet-4.5
# Requires: ANTHROPIC_API_KEY

# OpenAI
model: gpt-4o
# Requires: OPENAI_API_KEY

# Google
model: gemini-2.5-flash
# Requires: GOOGLE_API_KEY
```

### Temperature Guidelines

| Temperature | Use Case | Example |
|-------------|----------|---------|
| **0.0** | Deterministic, factual | Data retrieval, classification |
| **0.1-0.2** | Slight creativity | Code generation, analysis |
| **0.3-0.5** | Balanced | General tasks, reasoning |
| **0.6-1.0** | Creative | Content writing, brainstorming |
| **1.0+** | Very creative | Poetry, experimental |

### Token Limits

Recommended `max_tokens` by agent:

| Agent | Recommended | Rationale |
|-------|-------------|-----------|
| **Atomizer** | 1000-8000 | Simple classification |
| **Planner** | 4000-32000 | Complex task breakdowns |
| **Executor** | 16000-32000 | Detailed execution |
| **Aggregator** | 5000-32000 | Result synthesis |
| **Verifier** | 3000-16000 | Validation checks |

### Provider-Specific Parameters (`extra_body`)

Pass provider-specific features via the `extra_body` parameter. This is particularly useful for OpenRouter's advanced features like web search, model routing, and provider preferences.

**Security Note**: Never include sensitive keys (api_key, secret, token) in `extra_body`. Use the `api_key` field instead.

#### OpenRouter Web Search

Enable real-time web search for up-to-date information:

```yaml
agents:
  executor:
    llm:
      model: openrouter/google/gemini-2.5-flash
      temperature: 0.0
      extra_body:
        plugins:
          - id: web
            engine: exa  # Options: "exa", "native", or omit for auto
            max_results: 3
```

**Alternative**: Use the `:online` suffix for quick setup:
```yaml
model: openrouter/anthropic/claude-sonnet-4.5:online
```

#### OpenRouter Native Search with Context Size

For OpenRouter's native search engine with customizable context:

```yaml
extra_body:
  plugins:
    - id: web
      engine: native
  web_search_options:
    search_context_size: high  # Options: "low", "medium", "high"
```

#### Model Fallback Array

Automatic failover to alternative models:

```yaml
extra_body:
  models:
    - anthropic/claude-sonnet-4.5
    - openai/gpt-4o
    - google/gemini-2.5-pro
  route: fallback  # Options: "fallback", "lowest-cost", "lowest-latency"
```

#### Provider Preferences

Control which providers to use:

```yaml
extra_body:
  provider:
    order:
      - Anthropic
      - OpenAI
    data_collection: deny  # Privacy control: "allow" or "deny"
```

#### Full OpenRouter Web Search Example

```yaml
agents:
  executor:
    llm:
      model: openrouter/anthropic/claude-sonnet-4.5
      temperature: 0.2
      max_tokens: 16000
      extra_body:
        # Enable web search with custom settings
        plugins:
          - id: web
            engine: exa
            max_results: 5
            search_prompt: "Relevant information:"
        # Fallback models for reliability
        models:
          - anthropic/claude-sonnet-4.5
          - openai/gpt-4o
        route: fallback
```

**Documentation**: See [OpenRouter Web Search Docs](https://openrouter.ai/docs/features/web-search) for all available options.

**Cost Warning**: Web search plugins may significantly increase API costs per request.

---

## Runtime Settings

Control execution behavior, timeouts, and logging.

### Runtime Configuration

```yaml
runtime:
  max_depth: 6  # Recursion depth (recommended: 1-2)
  max_concurrency: 5  # Parallel task limit
  timeout: 120  # Global timeout (seconds)
  verbose: true  # Detailed output
  enable_logging: true  # Log to file
  log_level: INFO  # DEBUG, INFO, WARNING, ERROR

  # Cache configuration
  cache:
    enabled: true
    enable_disk_cache: true
    enable_memory_cache: true
    disk_cache_dir: .cache/dspy
    disk_size_limit_bytes: 30000000000  # 30GB
    memory_max_entries: 1000000
```

### Runtime Parameters

| Parameter | Description | Range | Default | Recommended |
|-----------|-------------|-------|---------|-------------|
| **max_depth** | Maximum task decomposition depth | 1-20 | 5 | **1-2** |
| **max_concurrency** | Parallel subtasks | 1-50 | 5 | 5-10 |
| **timeout** | Global execution timeout (sec) | 1-300 | 30 | 120-300 |
| **verbose** | Print detailed output | bool | false | true (dev) |
| **enable_logging** | File logging | bool | false | true |
| **log_level** | Logging verbosity | DEBUG-CRITICAL | INFO | INFO |

### Max Depth Guidelines

**IMPORTANT**: Lower max_depth = faster, cheaper, more reliable execution.

| max_depth | Use Case | Trade-offs |
|-----------|----------|-----------|
| **1** | Simple, atomic tasks | Fast, cheap, limited decomposition |
| **2** | Most production use cases | **Recommended** - good balance |
| **3-4** | Complex multi-step tasks | Slower, more expensive |
| **5+** | Highly complex hierarchical tasks | Very slow, expensive, may fail |

**Best Practice**: Start with `max_depth=1`, increase only if needed.

---

## Storage Configuration

Configure persistent storage for execution data and tool results.

### Storage Config

```yaml
storage:
  base_path: ${oc.env:STORAGE_BASE_PATH,/opt/sentient}
  max_file_size: 104857600  # 100MB

  # PostgreSQL (execution tracking)
  postgres:
    enabled: ${oc.env:POSTGRES_ENABLED,true}
    connection_url: ${oc.env:DATABASE_URL,postgresql+asyncpg://localhost/roma_dspy}
    pool_size: 10
    max_overflow: 20
```

### Storage Backends

#### Local Filesystem

```bash
# .env
STORAGE_BASE_PATH=/opt/sentient
```

#### S3 via goofys

```bash
# .env
STORAGE_BASE_PATH=/opt/sentient
ROMA_S3_BUCKET=my-bucket
AWS_REGION=us-east-1
AWS_ACCESS_KEY_ID=your_key
AWS_SECRET_ACCESS_KEY=your_secret
```

#### PostgreSQL

```bash
# .env
POSTGRES_ENABLED=true
DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/roma_dspy
```

Or via docker-compose (automatic):

```bash
just docker-up  # Starts postgres automatically
```

### Tool Result Storage

MCP and native toolkits can store large results to Parquet:

```yaml
toolkits:
  - class_name: MCPToolkit
    toolkit_config:
      use_storage: true
      storage_threshold_kb: 10  # Store results > 10KB
```

**Benefits**:
- Reduces context size
- Enables large dataset handling
- Automatic compression
- Queryable via DuckDB

---

## Observability (MLflow)

Track execution metrics, traces, and model performance with MLflow.

### MLflow Configuration

```yaml
observability:
  mlflow:
    enabled: ${oc.env:MLFLOW_ENABLED,false}
    tracking_uri: ${oc.env:MLFLOW_TRACKING_URI,http://mlflow:5000}
    experiment_name: ROMA-General-Agent
    log_traces: true  # Log full execution traces
    log_compiles: true  # Log DSPy compilations
    log_evals: true  # Log evaluations
```

### Environment Variables

```bash
# .env
MLFLOW_ENABLED=true
MLFLOW_TRACKING_URI=http://mlflow:5000
MLFLOW_EXPERIMENT=ROMA-DSPy
```

### Using MLflow

#### Start MLflow Server

```bash
# Via Docker Compose (recommended)
just docker-up-full  # Includes MLflow

# Access UI
open http://localhost:5000
```

#### Track Executions

```bash
# Run task with MLflow enabled
MLFLOW_ENABLED=true just solve "analyze bitcoin price"

# View traces in MLflow UI
open http://localhost:5000
```

### What MLflow Tracks

- **Execution metrics**: Duration, depth, token usage
- **LLM calls**: Model, parameters, latency
- **Tool usage**: Tool calls, results, errors
- **Traces**: Full execution tree with spans
- **Parameters**: All config values
- **Artifacts**: Outputs, logs, checkpoints

---

## Resilience Settings

Automatic error handling, retries, and recovery.

### Resilience Configuration

```yaml
resilience:
  # Retry configuration
  retry:
    enabled: true
    max_attempts: 5
    strategy: exponential_backoff
    base_delay: 2.0  # Initial delay (seconds)
    max_delay: 60.0  # Maximum delay

  # Circuit breaker
  circuit_breaker:
    enabled: true
    failure_threshold: 5  # Failures before opening
    recovery_timeout: 120.0  # Seconds before retry
    half_open_max_calls: 3  # Test calls when recovering

  # Checkpointing
  checkpoint:
    enabled: true
    storage_path: ${oc.env:ROMA_CHECKPOINT_PATH,.checkpoints}
    max_checkpoints: 20
    max_age_hours: 48.0
    compress_checkpoints: true
    verify_integrity: true
```

### Retry Strategies

| Strategy | Behavior | Use Case |
|----------|----------|----------|
| **exponential_backoff** | Delay doubles each retry | Most cases (default) |
| **fixed_delay** | Same delay each retry | Predictable timing |
| **random_backoff** | Random jitter | Avoid thundering herd |

### Circuit Breaker States

- **Closed**: Normal operation
- **Open**: Failing, reject new requests
- **Half-Open**: Testing recovery

### Checkpoint Recovery

Automatic recovery from failures:

```python
from roma_dspy.core.engine.solve import solve

# Execution will checkpoint automatically
result = solve("complex task", max_depth=3)

# If interrupted, resume from checkpoint
result = solve("complex task", resume_from_checkpoint=True)
```

---

## Logging Configuration

Structured logging with loguru.

### Logging Config

```yaml
logging:
  level: ${oc.env:LOG_LEVEL,INFO}
  log_dir: ${oc.env:LOG_DIR,logs}  # null = console only
  console_format: detailed  # minimal, default, detailed
  file_format: json  # default, detailed, json
  colorize: true
  serialize: true  # JSON serialization
  rotation: 500 MB  # File rotation size
  retention: 90 days  # Keep logs for
  compression: zip  # Compress rotated logs
  backtrace: true  # Full tracebacks
  diagnose: false  # Variable values (disable in prod)
  enqueue: true  # Thread-safe
```

### Log Levels

| Level | Use Case |
|-------|----------|
| **DEBUG** | Development, detailed tracing |
| **INFO** | Production, important events |
| **WARNING** | Potential issues |
| **ERROR** | Errors, exceptions |
| **CRITICAL** | Fatal errors |

### Environment Variables

```bash
# .env
LOG_LEVEL=INFO
LOG_DIR=logs  # or null for console only
LOG_CONSOLE_FORMAT=detailed
LOG_FILE_FORMAT=json
```

### Log Formats

#### Console Formats

- **minimal**: Level + message
- **default**: Time, level, module, message (colored)
- **detailed**: Full context with execution_id, line numbers

#### File Formats

- **default**: Standard text format
- **detailed**: Includes process/thread info
- **json**: Machine-parseable structured logs

---

## Environment Variables

Environment variables override configuration values.

### LLM Provider Keys

```bash
# OpenRouter (recommended - single key for all models)
OPENROUTER_API_KEY=your_key

# Or individual providers
OPENAI_API_KEY=your_key
ANTHROPIC_API_KEY=your_key
GOOGLE_API_KEY=your_key
```

### Toolkit Keys

```bash
# Code Execution
E2B_API_KEY=your_key
E2B_TEMPLATE_ID=roma-dspy-sandbox

# Web Search
EXA_API_KEY=your_key
SERPER_API_KEY=your_key

# Crypto APIs (all optional, public endpoints work without keys)
COINGECKO_API_KEY=your_key  # For Pro API
DEFILLAMA_API_KEY=your_key  # For Pro features
ARKHAM_API_KEY=your_key
BINANCE_API_KEY=your_key
BINANCE_API_SECRET=your_secret

# GitHub MCP
GITHUB_PERSONAL_ACCESS_TOKEN=your_token

# Any MCP server may require its own environment variables
```

### Storage & Database

```bash
# Storage
STORAGE_BASE_PATH=/opt/sentient
ROMA_S3_BUCKET=my-bucket
AWS_ACCESS_KEY_ID=your_key
AWS_SECRET_ACCESS_KEY=your_secret

# PostgreSQL
POSTGRES_ENABLED=true
DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/roma_dspy
```

### MLflow

```bash
MLFLOW_ENABLED=true
MLFLOW_TRACKING_URI=http://mlflow:5000
MLFLOW_EXPERIMENT=ROMA-DSPy
```

### Runtime Overrides

Use `ROMA__` prefix with double underscores:

```bash
# Override agents.executor.llm.temperature
ROMA__AGENTS__EXECUTOR__LLM__TEMPERATURE=0.5

# Override runtime.max_depth
ROMA__RUNTIME__MAX_DEPTH=2
```

**Format**: `ROMA__<path>__<to>__<setting>=value`

### Docker Compose

In docker-compose, set in `.env`:

```bash
# .env
OPENROUTER_API_KEY=your_key
E2B_API_KEY=your_key
POSTGRES_ENABLED=true
MLFLOW_ENABLED=true
```

Then:
```bash
just docker-up  # Automatically loads .env
```

---

## Custom Prompts and Demos

Enhance agent performance with optimized prompts and few-shot examples.

### Signature Instructions

Custom instructions guide the agent's behavior.

#### Three Formats

**1. Inline String**
```yaml
agents:
  executor:
    signature_instructions: "Execute the task step-by-step with clear reasoning."
```

**2. Jinja Template File**
```yaml
agents:
  executor:
    signature_instructions: "config/prompts/executor.jinja"
```

**3. Python Module Variable**
```yaml
agents:
  executor:
    signature_instructions: "prompt_optimization.seed_prompts.executor_seed:EXECUTOR_PROMPT"
```

#### Seed Prompts

ROMA-DSPy includes optimized seed prompts in `prompt_optimization/seed_prompts/`:

| Module | Variable | Purpose |
|--------|----------|---------|
| `atomizer_seed` | `ATOMIZER_PROMPT` | Task classification |
| `planner_seed` | `PLANNER_PROMPT` | Task decomposition |
| `executor_seed` | `EXECUTOR_PROMPT` | General execution |
| `executor_retrieve_seed` | `EXECUTOR_RETRIEVE_PROMPT` | Data retrieval |
| `executor_code_seed` | `EXECUTOR_CODE_PROMPT` | Code execution |
| `executor_think_seed` | `EXECUTOR_THINK_PROMPT` | Deep reasoning |
| `executor_write_seed` | `EXECUTOR_WRITE_PROMPT` | Content creation |
| `aggregator_seed` | `AGGREGATOR_PROMPT` | Result synthesis |
| `verifier_seed` | `VERIFIER_PROMPT` | Output validation |

### Demos (Few-Shot Examples)

Provide examples to guide the agent.

#### Format

```yaml
agents:
  executor:
    demos: "prompt_optimization.seed_prompts.executor_seed:EXECUTOR_DEMOS"
```

#### Creating Custom Demos

```python
# my_prompts/executor_demos.py
import dspy

EXECUTOR_DEMOS = [
    dspy.Example(
        goal="Calculate 15% of 2500",
        answer="375"
    ).with_inputs("goal"),
    dspy.Example(
        goal="What is the capital of France?",
        answer="Paris"
    ).with_inputs("goal")
]
```

Use in config:
```yaml
agents:
  executor:
    demos: "my_prompts.executor_demos:EXECUTOR_DEMOS"
```

### Custom Signature

Override the default DSPy signature:

```yaml
agents:
  executor:
    signature: "goal -> answer: str, confidence: float"
```

**Note**: Most users don't need this. Use `signature_instructions` instead.

---

## Configuration Examples

ROMA-DSPy includes comprehensive configuration examples in `config/examples/`. These are real, working configurations that demonstrate different concepts and patterns.

### Available Examples

#### Basic Examples (`config/examples/basic/`)

| Example | Description | Use It |
|---------|-------------|--------|
| **minimal.yaml** | Simplest possible configuration | `just solve "task" -c config/examples/basic/minimal.yaml` |
| **multi_toolkit.yaml** | Multiple toolkits (E2B + File + Calculator) | `just solve "task" -c config/examples/basic/multi_toolkit.yaml` |

**Demonstrates**: Fundamentals, toolkit usage, basic configuration patterns

#### MCP Examples (`config/examples/mcp/`)

| Example | Description | Use It |
|---------|-------------|--------|
| **http_public_server.yaml** | Public HTTP MCP server (CoinGecko) - no setup | `just solve "task" -c config/examples/mcp/http_public_server.yaml` |
| **stdio_local_server.yaml** | Local stdio MCP server via npx | `just solve "task" -c config/examples/mcp/stdio_local_server.yaml` |
| **multi_server.yaml** | Multiple MCP servers (HTTP + stdio) | `just solve "task" -c config/examples/mcp/multi_server.yaml` |
| **common_servers.yaml** | Common MCP servers (GitHub, Filesystem, SQLite) | `just solve "task" -c config/examples/mcp/common_servers.yaml` |

**Demonstrates**: HTTP vs stdio MCP servers, multi-server orchestration, storage configuration

#### Crypto Example (`config/examples/crypto/`)

| Example | Description | Use It |
|---------|-------------|--------|
| **crypto_agent.yaml** | Real-world crypto analysis agent | `just solve "task" -c config/examples/crypto/crypto_agent.yaml` |

**Demonstrates**: Domain-specific agent, combining MCP + native toolkits, multi-source data aggregation

#### Advanced Examples (`config/examples/advanced/`)

| Example | Description | Use It |
|---------|-------------|--------|
| **task_aware_mapping.yaml** | Task-specific executor configurations | `just solve "task" -c config/examples/advanced/task_aware_mapping.yaml` |
| **custom_prompts.yaml** | Custom prompts and demos | `just solve "task" -c config/examples/advanced/custom_prompts.yaml` |

**Demonstrates**: Task-aware agent mapping, cost/quality optimization per task type, loading custom signature instructions and demos

### Quick Reference

```bash
# Use a profile (recommended)
just solve "task" general

# Use an example configuration
just solve "task" -c config/examples/basic/minimal.yaml

# With CLI parameters
uv run python -m roma_dspy.cli solve "task" \
  --config config/examples/basic/minimal.yaml \
  --override runtime.max_depth=1
```

### Example Structure

Each example includes:
- **Inline comments** explaining each section
- **Setup requirements** (API keys, npm packages)
- **Usage examples** showing how to run
- **Key learnings** about what the example demonstrates

### Detailed Guide

See **[config/examples/README.md](../config/examples/README.md)** for:
- Complete examples directory structure
- Detailed descriptions of each example
- Setup instructions
- Common issues and solutions
- Tips for success

---

## Best Practices

### 1. Start Simple

```yaml
# Start with minimal config
agents:
  executor:
    llm:
      model: openrouter/anthropic/claude-sonnet-4.5
    prediction_strategy: react
    toolkits:
      - class_name: FileToolkit
        enabled: true

runtime:
  max_depth: 1  # Start with 1, increase if needed
```

Add complexity only when needed.

### 2. Use Profiles

Don't create configs from scratch. Start with a profile:

```bash
# Use existing profile
just solve "task" general

# Or copy and customize
cp config/profiles/general.yaml config/profiles/my_profile.yaml
# Edit my_profile.yaml
just solve "task" my_profile
```

### 3. Environment Variables for Secrets

Never hardcode API keys in config files:

```yaml
# ❌ Bad
headers:
  Authorization: Bearer sk-1234567890

# ✅ Good
headers:
  Authorization: Bearer ${oc.env:EXA_API_KEY}
```

### 4. Optimize max_depth

**Most tasks need max_depth=1 or 2**:

- Start with 1
- Increase to 2 if task needs decomposition
- Only use 3+ for complex hierarchical tasks
- Higher depth = slower + more expensive

### 5. Task-Aware Mapping for Cost Optimization

Use cheap models for simple tasks:

```yaml
agent_mapping:
  executors:
    RETRIEVE:
      llm:
        model: openrouter/google/gemini-2.5-flash  # $0.075/1M tokens
    CODE_INTERPRET:
      llm:
        model: openrouter/anthropic/claude-sonnet-4.5  # $3/1M tokens
```

### 6. Enable Caching

```yaml
agents:
  executor:
    llm:
      cache: true  # Enable DSPy caching

runtime:
  cache:
    enabled: true
    enable_disk_cache: true
```

Saves money and improves speed.

### 7. Use Storage for Large Data

```yaml
toolkits:
  - class_name: MCPToolkit
    toolkit_config:
      use_storage: true
      storage_threshold_kb: 10  # Store results > 10KB
```

Prevents context overflow.

### 8. Monitor with MLflow

```yaml
observability:
  mlflow:
    enabled: true
    log_traces: true
```

Track performance, costs, and errors.

### 9. Configure Resilience

```yaml
resilience:
  retry:
    enabled: true
    max_attempts: 5
  circuit_breaker:
    enabled: true
  checkpoint:
    enabled: true
```

Automatic recovery from failures.

### 10. Validate Configuration

```python
from roma_dspy.config.manager import ConfigManager

# Validate before using
try:
    config = ConfigManager().load_config(profile="my_profile")
    print("✅ Configuration valid")
except ValueError as e:
    print(f"❌ Invalid configuration: {e}")
```

---

## Next Steps

- **[QUICKSTART.md](QUICKSTART.md)** - Get started quickly
- **[TOOLKITS.md](TOOLKITS.md)** - Complete toolkit reference
- **[MCP.md](MCP.md)** - MCP integration guide
- **[API.md](API.md)** - REST API reference
- **[DEPLOYMENT.md](DEPLOYMENT.md)** - Production deployment
- **Examples**: `config/examples/` - Real-world examples

---

**Questions?** Check the examples in `config/examples/` or create an issue on GitHub.
