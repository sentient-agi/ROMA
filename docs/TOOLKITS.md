# ROMA-DSPy Toolkits Reference

Complete guide to using toolkits in ROMA-DSPy agents.

## Table of Contents

- [Overview](#overview)
- [Quick Start](#quick-start)
- [Native Toolkits](#native-toolkits)
- [MCP Integration](#mcp-integration)
- [Configuration Guide](#configuration-guide)
- [Examples](#examples)
- [Creating Custom Toolkits](#creating-custom-toolkits)
- [Best Practices](#best-practices)

---

## Overview

ROMA-DSPy provides a powerful toolkit system that enables agents to interact with external systems, execute code, access data, and perform specialized operations. The toolkit architecture supports:

- **10 Built-in Toolkits** for common operations (files, math, web, crypto, code execution)
- **MCP Integration** to connect to any Model Context Protocol server (1000+ available)
- **Smart Data Handling** with optional Parquet storage for large results
- **Execution Isolation** with per-execution file scoping
- **Tool Metrics** tracking invocations, latency, and errors
- **Flexible Configuration** via YAML profiles

### Architecture

```
Agent (Executor)
├── Toolkit Manager
│   ├── Native Toolkits (FileToolkit, CalculatorToolkit, etc.)
│   ├── MCP Toolkits (connects to external MCP servers)
│   └── Custom Toolkits (user-defined)
├── Tool Storage (optional Parquet for large data)
└── Tool Metrics (tracking and observability)
```

Each toolkit:
- Auto-registers tools with DSPy's tool system
- Provides full parameter schemas for LLM tool selection
- Handles errors gracefully with structured responses
- Optionally stores large results to reduce context usage

---

## Quick Start

### 1. Using Built-in Toolkits

```yaml
# config/profiles/my_profile.yaml
agents:
  executor:
    llm:
      model: openai/gpt-4o-mini
      temperature: 0.3
    prediction_strategy: react  # Required for tool usage
    toolkits:
      - class_name: FileToolkit
        enabled: true
      - class_name: CalculatorToolkit
        enabled: true
      - class_name: E2BToolkit
        enabled: true
        toolkit_config:
          timeout: 300
```

**Usage:**
```bash
just solve "Calculate 15% of 2500 and save to results.txt" -c config/profiles/my_profile.yaml
```

### 2. Using MCP Servers

```yaml
agents:
  executor:
    llm:
      model: openai/gpt-4o-mini
    prediction_strategy: react
    toolkits:
      # Public HTTP MCP server (no installation needed)
      - class_name: MCPToolkit
        enabled: true
        toolkit_config:
          server_name: coingecko
          server_type: http
          url: https://mcp.api.coingecko.com/sse
          use_storage: false
```

**Usage:**
```bash
just solve "What is the current price of Bitcoin?" -c config/profiles/my_profile.yaml
```

---

## Native Toolkits

ROMA-DSPy includes 10 built-in toolkits registered in `ToolkitManager.BUILTIN_TOOLKITS`.

### 1. FileToolkit

File operations with execution-scoped isolation.

**Tools:**
- `save_file(file_path: str, content: str, encoding: str = 'utf-8')` - Save content to file
- `read_file(file_path: str, encoding: str = 'utf-8')` - Read file content
- `list_files(directory: str = ".", pattern: str = "*")` - List files matching pattern
- `search_files(query: str, directory: str = ".", extensions: list = None)` - Search file contents
- `create_directory(directory_path: str)` - Create directory
- `delete_file(file_path: str)` - Delete file (requires enable_delete=True)

**Configuration:**
```yaml
- class_name: FileToolkit
  enabled: true
  toolkit_config:
    enable_delete: false  # Safety: disable destructive operations
    max_file_size: 10485760  # 10MB limit
```

**Security:**
- All file paths are scoped to execution-specific directories
- Path traversal attacks prevented
- File size limits enforced
- Delete operations disabled by default

**Example:** See `config/examples/basic/minimal.yaml`

---

### 2. CalculatorToolkit

Mathematical operations with precision control.

**Tools:**
- `add(a: float, b: float)` - Add two numbers
- `subtract(a: float, b: float)` - Subtract b from a
- `multiply(a: float, b: float)` - Multiply two numbers
- `divide(a: float, b: float)` - Divide a by b
- `exponentiate(base: float, exponent: float)` - Calculate base^exponent
- `factorial(n: int)` - Calculate factorial of n
- `is_prime(n: int)` - Check if n is prime
- `square_root(n: float)` - Calculate square root

**Configuration:**
```yaml
- class_name: CalculatorToolkit
  enabled: true
  toolkit_config:
    precision: 10  # Decimal places (default: 10)
```

**Response Format:**
```json
{
  "success": true,
  "operation": "addition",
  "operands": [25, 47],
  "result": 72.0
}
```

**Example:** See `config/examples/basic/minimal.yaml`

---

### 3. E2BToolkit

Secure sandboxed code execution via [E2B](https://e2b.dev).

**Features:**
- Isolated Python/Node.js execution environments
- Automatic sandbox health checks
- Sandbox lifecycle management
- File system access within sandbox
- Network access for data fetching

**Configuration:**
```yaml
- class_name: E2BToolkit
  enabled: true
  toolkit_config:
    timeout: 300  # Execution timeout (seconds)
    max_lifetime_hours: 23.5  # Auto-restart before 24h limit
    template: base  # E2B template ID
    auto_reinitialize: true  # Auto-restart on failure
```

**Environment Variables:**
```bash
export E2B_API_KEY=your_key_here
export E2B_TEMPLATE_ID=base  # Optional: custom template
```

**Example:** See `config/examples/basic/multi_toolkit.yaml`

---

### 4. SerperToolkit

Web search via [Serper.dev](https://serper.dev) API.

**Tools:**
- `search(query: str, num_results: int = 10)` - Search the web

**Configuration:**
```yaml
- class_name: SerperToolkit
  enabled: true
  toolkit_config:
    location: "United States"  # Search location
    language: "en"  # Results language
    num_results: 10  # Number of results
    date_range: null  # Optional: "d" (day), "w" (week), "m" (month), "y" (year)
```

**Environment Variables:**
```bash
export SERPER_API_KEY=your_key_here
```

**Example:** See `config/examples/basic/multi_toolkit.yaml`

---

### 5. WebSearchToolkit

Native web search using DSPy with LLM-powered web search capabilities.

**Features:**
- DSPy-native integration with web search enabled models
- Supports OpenRouter (with plugins) and OpenAI (Responses API)
- Automatic citation extraction
- Expert searcher prompts for comprehensive data retrieval
- Prioritizes reliable sources (Wikipedia, government, academic)
- Configurable search context depth

**Tool:**
- `web_search(query: str, max_results: int = None, search_context_size: str = None)` - Search the web with comprehensive data retrieval

**Configuration:**
```yaml
- class_name: WebSearchToolkit
  enabled: true
  toolkit_config:
    model: openrouter/openai/gpt-5-mini  # Auto-detects provider from prefix
    search_engine: exa  # For OpenRouter (omit for native search)
    max_results: 5  # Number of search results
    search_context_size: medium  # low, medium, or high
    temperature: 1.0  # Model temperature (1.0 required for GPT-5)
    max_tokens: 16000  # Max response tokens (16000+ for GPT-5)
```

**Provider Detection:**
- Models starting with `openrouter/` use OpenRouter plugins API
- Models starting with `openai/` use OpenAI Responses API
- No separate provider parameter needed

**Search Behavior:**
The toolkit uses expert searcher instructions that guide the LLM to:
1. Retrieve COMPLETE datasets (entire tables, all list items, all data points)
2. Prioritize reliable sources (Wikipedia first, then gov/academic/news)
3. Present data EXACTLY as found (no summarization)
4. Include temporal awareness for time-sensitive queries

**Environment Variables:**
```bash
export OPENROUTER_API_KEY=your_key_here  # For OpenRouter models
# OR
export OPENAI_API_KEY=your_key_here  # For OpenAI models
```

**Response Format:**
```json
{
  "success": true,
  "data": "Comprehensive answer with complete data...",
  "citations": [
    {"url": "https://en.wikipedia.org/..."},
    {"url": "https://example.com/..."}
  ],
  "tool": "web_search",
  "model": "openrouter/openai/gpt-5-mini",
  "provider": "openrouter"
}
```

**Example Usage:**
```yaml
# OpenRouter native search (GPT-5-mini)
- class_name: WebSearchToolkit
  toolkit_config:
    model: openrouter/openai/gpt-5-mini
    # No search_engine = native search
    max_results: 5
    search_context_size: medium
    temperature: 1.0
    max_tokens: 16000

# OpenRouter with Exa search engine
- class_name: WebSearchToolkit
  toolkit_config:
    model: openrouter/anthropic/claude-sonnet-4
    search_engine: exa
    max_results: 10
    search_context_size: high

# OpenAI Responses API
- class_name: WebSearchToolkit
  toolkit_config:
    model: openai/gpt-4o
    search_context_size: medium
    max_results: 5
```

**Example:** See `config/profiles/crypto_agent.yaml`

---

### 6. BinanceToolkit

Cryptocurrency market data from Binance.

**Features:**
- Spot, USDT-margined futures, and coin-margined futures
- Real-time prices and ticker stats
- Orderbook depth and recent trades
- OHLCV candlestick data
- Optional statistical analysis

**Tools:**
- `get_current_price(symbol: str, market: str = "spot")` - Current price
- `get_ticker_stats(symbol: str, market: str = "spot")` - 24h ticker statistics
- `get_book_ticker(symbol: str, market: str = "spot")` - Best bid/ask prices
- `get_klines(symbol: str, interval: str, limit: int = 100, market: str = "spot")` - OHLCV data
- `get_order_book(symbol: str, limit: int = 100, market: str = "spot")` - Order book depth
- `get_recent_trades(symbol: str, limit: int = 100, market: str = "spot")` - Recent trades

**Configuration:**
```yaml
- class_name: BinanceToolkit
  enabled: true
  toolkit_config:
    default_market: spot  # spot, usdm, coinm
    enable_analysis: false  # Statistical analysis
```

**No API Key Required** - Uses public Binance endpoints

**Example:** See `config/profiles/crypto_agent.yaml`

---

### 7. CoinGeckoToolkit

Comprehensive cryptocurrency data from [CoinGecko](https://coingecko.com).

**Features:**
- 17,000+ cryptocurrencies
- Real-time prices in 100+ currencies
- Historical price and market data
- OHLCV candlestick data
- Market rankings and statistics
- Contract address lookups
- Global market metrics

**Tools:**
- `get_coin_price(coin_name_or_id: str, vs_currency: str = "usd")` - Current price
- `get_coin_market_chart(coin_name_or_id: str, vs_currency: str = "usd", days: int = 30)` - Historical data
- More tools available - see toolkit implementation

**Configuration:**
```yaml
- class_name: CoinGeckoToolkit
  enabled: true
  toolkit_config:
    coins: null  # Restrict to specific coins (null = all)
    default_vs_currency: usd  # Default quote currency
    use_pro: false  # Use CoinGecko Pro API
    enable_analysis: false  # Statistical analysis
```

**Environment Variables:**
```bash
export COINGECKO_API_KEY=your_key_here  # Optional: for Pro API
```

**No API Key Required** for public endpoints

**Example:** See `config/profiles/crypto_agent.yaml`

---

### 8. DefiLlamaToolkit

DeFi protocol analytics from [DefiLlama](https://defillama.com).

**Features:**
- Protocol TVL (Total Value Locked) tracking
- Daily fees and revenue analysis
- Yield farming pools and APY data (Pro)
- User activity metrics (Pro)
- Cross-chain analytics
- Statistical analysis

**Tools (Public):**
- `get_protocol_fees(protocol_name: str)` - Protocol fees and revenue
- `get_protocol_tvl(protocol_name: str)` - Total Value Locked
- More public tools available

**Tools (Pro - requires API key):**
- `get_yield_pools()` - Yield farming opportunities
- `get_yield_chart(pool_id: str)` - Historical APY data
- `get_active_users(protocol_name: str)` - User activity
- More Pro tools available

**Configuration:**
```yaml
- class_name: DefiLlamaToolkit
  enabled: true
  toolkit_config:
    enable_pro_features: false  # Requires API key
    default_chain: ethereum
    enable_analysis: true
```

**Environment Variables:**
```bash
export DEFILLAMA_API_KEY=your_key_here  # For Pro features
```

**No API Key Required** for public endpoints

**Example:** See `config/profiles/crypto_agent.yaml`

---

### 9. ArkhamToolkit

Blockchain analytics from [Arkham Intelligence](https://arkhamintelligence.com).

**Features:**
- Token analytics (top tokens, holders, flows)
- Transfer tracking with entity attribution
- Wallet balance monitoring across chains
- Statistical analysis of distributions
- Rate limiting (20 req/sec standard, 1 req/sec heavy)

**Tools:**
- Token analytics tools
- Transfer tracking tools
- Wallet balance tools
- More tools available - see toolkit implementation

**Configuration:**
```yaml
- class_name: ArkhamToolkit
  enabled: true
  toolkit_config:
    default_chain: ethereum
    enable_analysis: true
```

**Environment Variables:**
```bash
export ARKHAM_API_KEY=your_key_here  # Required
```

**API Key Required**

---

### 10. CoinglassToolkit

Derivatives market data from [Coinglass](https://coinglass.com).

**Features:**
- Historical funding rates weighted by open interest (OHLC data)
- Real-time funding rates across 20+ exchanges
- Funding rate arbitrage opportunity detection
- Open interest tracking and historical analysis
- Taker buy/sell volume ratios (market sentiment)
- Liquidation data by exchange and position type

**Tools:**
- `get_funding_rates_weighted_by_oi` - Historical funding rate OHLC data
- `get_funding_rates_per_exchange` - Current funding rates across exchanges
- `get_arbitrage_opportunities` - Funding rate arbitrage opportunities
- `get_open_interest_by_exchange` - Current open interest by exchange
- `get_open_interest_history` - Historical open interest data
- `get_taker_buy_sell_volume` - Buy/sell volume ratios
- `get_liquidations_by_exchange` - Liquidation data

**Configuration:**
```yaml
- class_name: CoinglassToolkit
  enabled: true
  toolkit_config:
    symbols: ["BTC", "ETH", "SOL"]  # Restrict to specific symbols (null = all)
    default_symbol: BTC
    storage_threshold_kb: 500  # Auto-store responses > 500KB
```

**Environment Variables:**
```bash
export COINGLASS_API_KEY=your_key_here  # Required
```

**API Key Required** - Get yours at [Coinglass API](https://coinglass.com/api)

**Example:** See `config/profiles/crypto_agent.yaml`

---

### 11. MCPToolkit

Universal connector for Model Context Protocol servers.

**Special Property:** The MCPToolkit can connect to **any** MCP server - there are 1000+ available!

See [MCP Integration](#mcp-integration) section below for complete details.

---

## MCP Integration

The **MCPToolkit** enables ROMA-DSPy agents to use tools from **any** MCP (Model Context Protocol) server. This provides unlimited extensibility beyond the 10 built-in toolkits.

### What is MCP?

MCP is an open protocol for connecting AI applications to data sources and tools. It's like USB-C for AI - a universal connector.

**Resources:**
- **Awesome MCP Servers**: [700+ servers](https://github.com/wong2/awesome-mcp-servers)
- **MCP Documentation**: [modelcontextprotocol.io](https://modelcontextprotocol.io/)
- **Build Your Own**: Any server implementing the MCP protocol

### Connection Types

#### 1. HTTP/SSE Servers (Remote)

**Best for:** Public APIs, cloud services, no installation needed

**Example - CoinGecko Public Server:**
```yaml
- class_name: MCPToolkit
  enabled: true
  toolkit_config:
    server_name: coingecko
    server_type: http
    url: https://mcp.api.coingecko.com/sse
    use_storage: false
```

**Example - Exa Search (with API key):**
```yaml
- class_name: MCPToolkit
  enabled: true
  toolkit_config:
    server_name: exa
    server_type: http
    url: https://mcp.exa.ai/mcp
    headers:
      Authorization: "Bearer ${oc.env:EXA_API_KEY}"
    use_storage: true  # Exa returns large search results
    storage_threshold_kb: 50
```

**No installation required** - connects over HTTP

#### 2. Stdio Servers (Local Subprocess)

**Best for:** Local tools, filesystem access, databases, git operations

**Example - GitHub Operations:**
```yaml
- class_name: MCPToolkit
  enabled: true
  toolkit_config:
    server_name: github
    server_type: stdio
    command: npx
    args:
      - "-y"
      - "@modelcontextprotocol/server-github"
    env:
      GITHUB_PERSONAL_ACCESS_TOKEN: "${oc.env:GITHUB_PERSONAL_ACCESS_TOKEN}"
    use_storage: false
```

**Example - Filesystem Access:**
```yaml
- class_name: MCPToolkit
  enabled: true
  toolkit_config:
    server_name: filesystem
    server_type: stdio
    command: npx
    args:
      - "-y"
      - "@modelcontextprotocol/server-filesystem"
      - "/Users/yourname/Documents"  # Allowed directory
    use_storage: false
```

**Requires installation:**
```bash
npm install -g @modelcontextprotocol/server-github
npm install -g @modelcontextprotocol/server-filesystem
```

### Storage Configuration

MCP tools can return large datasets (search results, database queries, etc.). The toolkit provides smart data handling:

**Small Data (default):**
```yaml
use_storage: false  # Returns raw text/JSON directly
```

**Large Data (with storage):**
```yaml
use_storage: true  # Stores data in Parquet, returns reference
storage_threshold_kb: 100  # Store results > 100KB (default)
```

**How it works:**
1. Tool executes and returns data
2. If data size > threshold, saves to Parquet file
3. Returns file reference instead of full data
4. Reduces context usage for large datasets

### Finding MCP Servers

**Popular Categories:**

| Category | Examples |
|----------|----------|
| **Web Search** | Exa, Brave Search, Google Search |
| **Development** | GitHub, GitLab, Linear, Sentry |
| **Data** | PostgreSQL, SQLite, MongoDB, Redis |
| **Cloud** | AWS, Google Cloud, Kubernetes |
| **Productivity** | Google Drive, Slack, Notion, Confluence |
| **Finance** | Stripe, QuickBooks |
| **AI/ML** | OpenAI, Anthropic, Hugging Face |

**Browse all:**
- [awesome-mcp-servers](https://github.com/wong2/awesome-mcp-servers) - 700+ servers
- [MCP Server Registry](https://modelcontextprotocol.io/servers) - Official registry

### Multiple MCP Servers

You can use **multiple** MCP servers in one agent:

```yaml
agents:
  executor:
    llm:
      model: openai/gpt-4o-mini
    prediction_strategy: react
    toolkits:
      # GitHub for code
      - class_name: MCPToolkit
        toolkit_config:
          server_name: github
          server_type: stdio
          command: npx
          args: ["-y", "@modelcontextprotocol/server-github"]
          env:
            GITHUB_PERSONAL_ACCESS_TOKEN: "${oc.env:GITHUB_TOKEN}"

      # Exa for web search
      - class_name: MCPToolkit
        toolkit_config:
          server_name: exa
          server_type: http
          url: https://mcp.exa.ai/mcp
          headers:
            Authorization: "Bearer ${oc.env:EXA_API_KEY}"
          use_storage: true

      # Filesystem for local files
      - class_name: MCPToolkit
        toolkit_config:
          server_name: filesystem
          server_type: stdio
          command: npx
          args: ["-y", "@modelcontextprotocol/server-filesystem", "/path/to/allowed/dir"]
```

**Example:** See `config/examples/mcp/multi_server.yaml`

---

## Configuration Guide

### Basic Structure

```yaml
agents:
  executor:
    llm:
      model: openai/gpt-4o-mini
      temperature: 0.3
    prediction_strategy: react  # REQUIRED for tool usage
    toolkits:
      - class_name: ToolkitName
        enabled: true
        include_tools: null  # Optional: whitelist specific tools
        exclude_tools: null  # Optional: blacklist specific tools
        toolkit_config:
          # Toolkit-specific settings
```

### Tool Filtering

**Include specific tools only:**
```yaml
- class_name: CalculatorToolkit
  enabled: true
  include_tools:
    - add
    - subtract
    - multiply
  # Only these 3 tools will be available
```

**Exclude specific tools:**
```yaml
- class_name: FileToolkit
  enabled: true
  exclude_tools:
    - delete_file  # Safety: disable deletions
  # All tools except delete_file will be available
```

### Environment Variables

**Via OmegaConf:**
```yaml
toolkit_config:
  api_key: "${oc.env:MY_API_KEY}"  # Reads from environment
  timeout: "${oc.env:TIMEOUT,300}"  # Default value: 300
```

**Via .env file:**
```bash
# .env
E2B_API_KEY=your_key
SERPER_API_KEY=your_key
GITHUB_PERSONAL_ACCESS_TOKEN=your_token
```

### Storage Integration

Some toolkits support optional Parquet storage for large data:

```yaml
- class_name: MCPToolkit
  enabled: true
  toolkit_config:
    server_name: database
    server_type: stdio
    command: npx
    args: ["-y", "@modelcontextprotocol/server-sqlite", "/path/to/db.db"]
    use_storage: true  # Enable storage wrapper
    storage_threshold_kb: 100  # Store results > 100KB
```

**Toolkits with storage support:**
- MCPToolkit
- DefiLlamaToolkit
- ArkhamToolkit
- BinanceToolkit (for large responses)
- CoinGeckoToolkit (for large responses)
- CoinglassToolkit (for large responses)

---

## Examples

All examples available in `config/examples/`. See `config/examples/README.md` for complete guide.

### Example 1: Minimal Configuration

**File:** `config/examples/basic/minimal.yaml`

Simple agent with FileToolkit and CalculatorToolkit.

**Usage:**
```bash
just solve "Calculate 15% of 2500 and save to results.txt" -c config/examples/basic/minimal.yaml
```

---

### Example 2: Multi-Toolkit

**File:** `config/examples/basic/multi_toolkit.yaml`

Combines E2B (code execution), FileToolkit, CalculatorToolkit, and SerperToolkit.

**Usage:**
```bash
just solve "Search for Python fibonacci implementation, execute it, and save results" \
  -c config/examples/basic/multi_toolkit.yaml
```

---

### Example 3: Public HTTP MCP Server

**File:** `config/examples/mcp/http_public_server.yaml`

Uses CoinGecko public MCP server - **no installation or API key required!**

**Usage:**
```bash
just solve "What is the current price of Bitcoin?" \
  -c config/examples/mcp/http_public_server.yaml
```

---

### Example 4: Local Stdio MCP Server

**File:** `config/examples/mcp/stdio_local_server.yaml`

Uses local Exa MCP server for web search.

**Setup:**
```bash
export EXA_API_KEY=your_key
npm install -g @exa-labs/exa-mcp-server
```

**Usage:**
```bash
just solve "Search for latest LLM research papers" \
  -c config/examples/mcp/stdio_local_server.yaml
```

---

### Example 5: Multiple MCP Servers

**File:** `config/examples/mcp/multi_server.yaml`

Combines GitHub, Exa (web search), and CoinGecko MCP servers.

**Usage:**
```bash
just solve "Search recent AI news, check Bitcoin price, and create GitHub issue summary" \
  -c config/examples/mcp/multi_server.yaml
```

---

### Example 6: Crypto Agent (Domain-Specific)

**File:** `config/profiles/crypto_agent.yaml`

Comprehensive crypto analysis with:
- CoinGeckoToolkit (17,000+ coins)
- CoinglassToolkit (derivatives market data)
- BinanceToolkit (spot + futures)
- DefiLlamaToolkit (DeFi protocols)
- ArkhamToolkit (blockchain analytics)
- Exa MCP (web search)

**Usage:**
```bash
just solve "Compare Bitcoin and Ethereum: prices, market caps, 24h volumes, and analyze trends" \
  crypto_agent
```

---

## Creating Custom Toolkits

### Step 1: Create Toolkit Class

```python
# my_custom_toolkit.py
from roma_dspy.tools.base.base import BaseToolkit
from typing import Optional, List

class MyCustomToolkit(BaseToolkit):
    """My custom toolkit for XYZ operations."""

    def __init__(
        self,
        enabled: bool = True,
        include_tools: Optional[List[str]] = None,
        exclude_tools: Optional[List[str]] = None,
        **config,
    ):
        super().__init__(
            enabled=enabled,
            include_tools=include_tools,
            exclude_tools=exclude_tools,
            **config,
        )

        # Your initialization
        self.api_key = config.get("api_key")

    def _setup_dependencies(self) -> None:
        """Setup external dependencies."""
        # Optional: validate API keys, initialize clients
        pass

    def _initialize_tools(self) -> None:
        """Initialize toolkit-specific configuration."""
        # Optional: additional setup
        pass

    # Tool methods (auto-registered by BaseToolkit)

    async def my_tool(self, param1: str, param2: int) -> str:
        """
        Tool description that the LLM will see.

        Args:
            param1: Description of param1
            param2: Description of param2

        Returns:
            Result description
        """
        # Your tool implementation
        result = f"Processed {param1} with {param2}"
        return result

    async def another_tool(self, query: str) -> dict:
        """Another tool that returns structured data."""
        return {
            "success": True,
            "query": query,
            "results": ["result1", "result2"]
        }
```

### Step 2: Register Toolkit

Add to `src/roma_dspy/tools/base/manager.py`:

```python
BUILTIN_TOOLKITS = {
    # ... existing toolkits ...
    "MyCustomToolkit": "path.to.my_custom_toolkit",
}
```

### Step 3: Use in Configuration

```yaml
agents:
  executor:
    llm:
      model: openai/gpt-4o-mini
    prediction_strategy: react
    toolkits:
      - class_name: MyCustomToolkit
        enabled: true
        toolkit_config:
          api_key: "${oc.env:MY_API_KEY}"
```

### Best Practices

1. **Tool Design:**
   - Clear, descriptive tool names
   - Comprehensive docstrings (LLM sees these)
   - Type hints for all parameters
   - Return structured data (JSON dicts or strings)

2. **Error Handling:**
   ```python
   async def my_tool(self, param: str) -> dict:
       try:
           result = await self._do_something(param)
           return {"success": True, "data": result}
       except Exception as e:
           logger.error(f"Tool failed: {e}")
           return {"success": False, "error": str(e)}
   ```

3. **Storage for Large Data:**
   ```python
   class MyToolkit(BaseToolkit):
       REQUIRES_FILE_STORAGE = False  # Optional storage

       def __init__(self, use_storage: bool = False, **config):
           super().__init__(**config)
           self.use_storage = use_storage

       async def big_data_tool(self, query: str) -> str:
           result = await self._fetch_large_dataset(query)

           if self.use_storage and len(result) > threshold:
               # Store to Parquet and return reference
               path = await self.file_storage.save_tool_result(...)
               return f"Data stored at: {path}"

           return result
   ```

4. **Testing:**
   ```python
   # tests/test_my_toolkit.py
   import pytest
   from my_custom_toolkit import MyCustomToolkit

   @pytest.mark.asyncio
   async def test_my_tool():
       toolkit = MyCustomToolkit()
       result = await toolkit.my_tool("test", 42)
       assert "Processed" in result
   ```

---

## Best Practices

### 1. Toolkit Selection

**Choose the right tools for the task:**
```yaml
# For file operations + math
toolkits:
  - class_name: FileToolkit
  - class_name: CalculatorToolkit

# For web research
toolkits:
  - class_name: SerperToolkit  # Native
  # OR
  - class_name: MCPToolkit  # MCP (Exa, Brave, etc.)
    toolkit_config:
      server_name: exa
      server_type: http
      url: https://mcp.exa.ai/mcp

# For code execution
toolkits:
  - class_name: E2BToolkit
```

### 2. Security

**File operations:**
```yaml
- class_name: FileToolkit
  toolkit_config:
    enable_delete: false  # Disable destructive operations
    max_file_size: 10485760  # 10MB limit
```

**MCP servers:**
- Only use trusted MCP servers
- Validate server URLs and signatures
- Use environment variables for sensitive data

### 3. Performance

**Use storage for large data:**
```yaml
- class_name: MCPToolkit
  toolkit_config:
    use_storage: true
    storage_threshold_kb: 50  # Aggressive threshold for faster responses
```

**Limit tool scope:**
```yaml
- class_name: CalculatorToolkit
  include_tools:
    - add
    - multiply
  # Faster tool selection with fewer options
```

### 4. Cost Optimization

**Use task-aware mapping** to assign different toolkits to different task types:

```yaml
agent_mapping:
  executors:
    RETRIEVE:
      # Cheap model + web search
      llm:
        model: openrouter/google/gemini-2.0-flash-exp:free
      toolkits:
        - class_name: SerperToolkit

    CODE_INTERPRET:
      # Powerful model + code execution
      llm:
        model: openrouter/anthropic/claude-sonnet-4
      toolkits:
        - class_name: E2BToolkit
        - class_name: FileToolkit
```

**Example:** See `config/examples/advanced/task_aware_mapping.yaml`

### 5. Observability

**Enable logging:**
```yaml
runtime:
  enable_logging: true
```

**Track tool metrics:**
- Tool invocations logged automatically
- Latency tracking
- Error rates
- View in MLflow (if observability enabled)

### 6. API Key Management

**Never hardcode keys:**
```yaml
# ❌ BAD
toolkit_config:
  api_key: "sk-1234567890abcdef"

# ✅ GOOD
toolkit_config:
  api_key: "${oc.env:MY_API_KEY}"
```

**Use .env file:**
```bash
# .env
E2B_API_KEY=your_key
SERPER_API_KEY=your_key
GITHUB_PERSONAL_ACCESS_TOKEN=your_token
```

---

## Troubleshooting

### "Unknown toolkit class: XYZ"

**Cause:** Toolkit not registered or typo in class_name

**Fix:**
```bash
# Check available toolkits
python -c "from roma_dspy.tools.base.manager import ToolkitManager; print(ToolkitManager.BUILTIN_TOOLKITS.keys())"

# Verify spelling matches exactly (case-sensitive)
```

### "Tools don't support strategy: chain_of_thought"

**Cause:** Chain-of-thought strategy doesn't support tool usage

**Fix:**
```yaml
agents:
  executor:
    prediction_strategy: react  # Use react or codeact for tools
```

### MCP Server Connection Failed

**HTTP servers:**
```bash
# Test connectivity
curl -I https://mcp.api.coingecko.com/sse

# Check headers/auth
curl -H "Authorization: Bearer YOUR_KEY" https://mcp.exa.ai/mcp
```

**Stdio servers:**
```bash
# Verify installation
npx @modelcontextprotocol/server-github --version

# Test manually
npx -y @modelcontextprotocol/server-github
```

### E2B Not Working

```bash
# Verify API key
echo $E2B_API_KEY

# Test connection
python -c "from e2b import Sandbox; s = Sandbox(); print(s.is_running())"

# Check template
export E2B_TEMPLATE_ID=base
```

### Large Data Timeouts

**Enable storage:**
```yaml
toolkit_config:
  use_storage: true
  storage_threshold_kb: 50  # Lower threshold
```

---

## Additional Resources

- **Configuration Guide**: [CONFIGURATION.md](CONFIGURATION.md)
- **MCP Deep Dive**: [MCP.md](MCP.md)
- **Example Configurations**: `config/examples/`
- **Awesome MCP Servers**: https://github.com/wong2/awesome-mcp-servers
- **MCP Documentation**: https://modelcontextprotocol.io/
- **E2B Documentation**: https://e2b.dev/docs

---

**Ready to build?** Start with the examples in `config/examples/` and customize for your use case! 🚀