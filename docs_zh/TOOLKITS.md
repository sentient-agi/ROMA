# ROMA-DSPy 工具箱参考

在 ROMA-DSPy 智能体中使用工具箱的完整指南。

## 目录

- [概览](#概览)
- [快速开始](#快速开始)
- [原生工具箱](#原生工具箱)
- [MCP 集成](#mcp-集成)
- [配置指南](#配置指南)
- [示例](#示例)
- [创建自定义工具箱](#创建自定义工具箱)
- [最佳实践](#最佳实践)

---

## 概览

ROMA-DSPy 提供了一个强大的工具箱系统，使智能体能够与外部系统交互、执行代码、访问数据并执行专门操作。工具箱架构支持：

- **10 个内置工具箱** 用于常见操作（文件、数学、Web、加密货币、代码执行）
- **MCP 集成** 连接到任何模型上下文协议 (Model Context Protocol) 服务器（1000+ 可用）
- **智能数据处理** 可选的 Parquet 存储用于大数据
- **执行隔离** 每个执行的文件作用域隔离
- **工具指标** 跟踪调用、延迟和错误
- **灵活配置** 通过 YAML profiles

### 架构

```
智能体 (Executor)
├── 工具箱管理器 (Toolkit Manager)
│   ├── 原生工具箱 (FileToolkit, CalculatorToolkit 等)
│   ├── MCP 工具箱 (连接外部 MCP 服务器)
│   └── 自定义工具箱 (用户定义)
├── 工具存储 (可选 Parquet 用于大数据)
└── 工具指标 (跟踪与可观察性)
```

每个工具箱：
- 自动向 DSPy 的工具系统注册工具
- 为 LLM 工具选择提供完整的参数模式 (schema)
- 通过结构化响应优雅地处理错误
- 可选地存储大型结果以减少上下文使用

---

## 快速开始

### 1. 使用内置工具箱

```yaml
# config/profiles/my_profile.yaml
agents:
  executor:
    llm:
      model: openai/gpt-4o-mini
      temperature: 0.3
    prediction_strategy: react  # 工具使用必填
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

**用法：**
```bash
just solve "计算 2500 的 15% 并保存到 results.txt" -c config/profiles/my_profile.yaml
```

### 2. 使用 MCP 服务器

```yaml
agents:
  executor:
    llm:
      model: openai/gpt-4o-mini
    prediction_strategy: react
    toolkits:
      # 公共 HTTP MCP 服务器 (无需安装)
      - class_name: MCPToolkit
        enabled: true
        toolkit_config:
          server_name: coingecko
          server_type: http
          url: https://mcp.api.coingecko.com/sse
          use_storage: false
```

**用法：**
```bash
just solve "比特币当前价格是多少？" -c config/profiles/my_profile.yaml
```

---

## 原生工具箱

ROMA-DSPy 包含 10 个内置工具箱，注册在 `ToolkitManager.BUILTIN_TOOLKITS` 中。

### 1. FileToolkit

具有执行范围隔离的文件操作。

**工具：**
- `save_file(file_path: str, content: str, encoding: str = 'utf-8')` - 保存内容到文件
- `read_file(file_path: str, encoding: str = 'utf-8')` - 读取文件内容
- `list_files(directory: str = ".", pattern: str = "*")` - 列出匹配模式的文件
- `search_files(query: str, directory: str = ".", extensions: list = None)` - 搜索文件内容
- `create_directory(directory_path: str)` - 创建目录
- `delete_file(file_path: str)` - 删除文件（需要 enable_delete=True）

**配置：**
```yaml
- class_name: FileToolkit
  enabled: true
  toolkit_config:
    enable_delete: false  # 安全：禁用破坏性操作
    max_file_size: 10485760  # 10MB 限制
```

**安全性：**
- 所有文件路径都限于执行特定的目录
- 防止路径遍历攻击
- 强制文件大小限制
- 默认禁用删除操作

**示例：** 参见 `config/examples/basic/minimal.yaml`

---

### 2. CalculatorToolkit

具有精度控制的数学运算。

**工具：**
- `add(a: float, b: float)` - 加法
- `subtract(a: float, b: float)` - 减法
- `multiply(a: float, b: float)` - 乘法
- `divide(a: float, b: float)` - 除法
- `exponentiate(base: float, exponent: float)` - 幂运算
- `factorial(n: int)` - 阶乘
- `is_prime(n: int)` - 质数检查
- `square_root(n: float)` - 平方根

**配置：**
```yaml
- class_name: CalculatorToolkit
  enabled: true
  toolkit_config:
    precision: 10  # 小数位数 (默认: 10)
```

**响应格式：**
```json
{
  "success": true,
  "operation": "addition",
  "operands": [25, 47],
  "result": 72.0
}
```

**示例：** 参见 `config/examples/basic/minimal.yaml`

---

### 3. E2BToolkit

通过 [E2B](https://e2b.dev) 进行安全的沙箱代码执行。

**特性：**
- 隔离的 Python/Node.js 执行环境
- 自动沙箱健康检查
- 沙箱生命周期管理
- 沙箱内文件系统访问
- 用于数据获取的网络访问

**配置：**
```yaml
- class_name: E2BToolkit
  enabled: true
  toolkit_config:
    timeout: 300  # 执行超时 (秒)
    max_lifetime_hours: 23.5  # 24小时限制前自动重启
    template: base  # E2B 模板 ID
    auto_reinitialize: true  # 失败时自动重启
```

**环境变量：**
```bash
export E2B_API_KEY=your_key_here
export E2B_TEMPLATE_ID=base  # 可选: 自定义模板
```

**示例：** 参见 `config/examples/basic/multi_toolkit.yaml`

---

### 4. SerperToolkit

通过 [Serper.dev](https://serper.dev) API 进行 Web 搜索。

**工具：**
- `search(query: str, num_results: int = 10)` - 搜索网络

**配置：**
```yaml
- class_name: SerperToolkit
  enabled: true
  toolkit_config:
    location: "United States"  # 搜索位置
    language: "en"  # 结果语言
    num_results: 10  # 结果数量
    date_range: null  # 可选: "d" (天), "w" (周), "m" (月), "y" (年)
```

**环境变量：**
```bash
export SERPER_API_KEY=your_key_here
```

**示例：** 参见 `config/examples/basic/multi_toolkit.yaml`

---

### 5. WebSearchToolkit

使用具有 Web 搜索能力的 LLM 进行原生 Web 搜索。

**特性：**
- 与启用了 Web 搜索的模型进行 DSPy 原生集成
- 支持 OpenRouter (带插件) 和 OpenAI (Responses API)
- 自动提取引用
- 专家级搜索提示词，用于全面数据检索
- 优先考虑可靠来源（维基百科、政府、学术）
- 可配置搜索上下文深度

**工具：**
- `web_search(query: str, max_results: int = None, search_context_size: str = None)` - 全面检索数据的 Web 搜索

**配置：**
```yaml
- class_name: WebSearchToolkit
  enabled: true
  toolkit_config:
    model: openrouter/openai/gpt-5-mini  # 根据前缀自动检测提供商
    search_engine: exa  # 用于 OpenRouter (省略则使用原生搜索)
    max_results: 5  # 搜索结果数量
    search_context_size: medium  # low, medium, 或 high
    temperature: 1.0  # 模型温度 (GPT-5 需要 1.0)
    max_tokens: 16000  # 最大响应 Token (GPT-5 建议 16000+)
```

**提供商检测：**
- 以 `openrouter/` 开头的模型使用 OpenRouter 插件 API
- 以 `openai/` 开头的模型使用 OpenAI Responses API
- 无需单独的 provider 参数

**搜索行为：**
工具箱使用专家搜索者指令引导 LLM：
1. 检索完整数据集（整个表格、所有列表项、所有数据点）
2. 优先考虑可靠来源（维基百科优先，然后是政府/学术/新闻）
3. 准确呈现找到的数据（不总结）
4. 包含时间敏感查询的时间意识

**环境变量：**
```bash
export OPENROUTER_API_KEY=your_key_here  # 用于 OpenRouter 模型
# 或
export OPENAI_API_KEY=your_key_here  # 用于 OpenAI 模型
```

**响应格式：**
```json
{
  "success": true,
  "data": "包含完整数据的综合答案...",
  "citations": [
    {"url": "https://en.wikipedia.org/..."},
    {"url": "https://example.com/..."}
  ],
  "tool": "web_search",
  "model": "openrouter/openai/gpt-5-mini",
  "provider": "openrouter"
}
```

**使用示例：**
```yaml
# OpenRouter 原生搜索 (GPT-5-mini)
- class_name: WebSearchToolkit
  toolkit_config:
    model: openrouter/openai/gpt-5-mini
    # 无 search_engine = 原生搜索
    max_results: 5
    search_context_size: medium
    temperature: 1.0
    max_tokens: 16000

# OpenRouter 配合 Exa 搜索引擎
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

**示例：** 参见 `config/profiles/crypto_agent.yaml`

---

### 6. BinanceToolkit

来自 Binance 的加密货币市场数据。

**特性：**
- 现货、USDT 本位合约和币本位合约
- 实时价格和 Ticker 统计
- 订单簿深度和近期成交
- OHLCV K线数据
- 可选统计分析

**工具：**
- `get_current_price(symbol: str, market: str = "spot")` - 当前价格
- `get_ticker_stats(symbol: str, market: str = "spot")` - 24小时统计
- `get_book_ticker(symbol: str, market: str = "spot")` - 最佳买卖价
- `get_klines(symbol: str, interval: str, limit: int = 100, market: str = "spot")` - K线数据
- `get_order_book(symbol: str, limit: int = 100, market: str = "spot")` - 订单簿深度
- `get_recent_trades(symbol: str, limit: int = 100, market: str = "spot")` - 近期成交

**配置：**
```yaml
- class_name: BinanceToolkit
  enabled: true
  toolkit_config:
    default_market: spot  # spot, usdm, coinm
    enable_analysis: false  # 统计分析
```

**无需 API 密钥** - 使用公共 Binance 端点

**示例：** 参见 `config/profiles/crypto_agent.yaml`

---

### 7. CoinGeckoToolkit

来自 [CoinGecko](https://coingecko.com) 的全面加密货币数据。

**特性：**
- 17,000+ 加密货币
- 100+ 货币计价的实时价格
- 历史价格和市场数据
- OHLCV K线数据
- 市场排名和统计
- 合约地址查找
- 全球市场指标

**工具：**
- `get_coin_price(coin_name_or_id: str, vs_currency: str = "usd")` - 当前价格
- `get_coin_market_chart(coin_name_or_id: str, vs_currency: str = "usd", days: int = 30)` - 历史数据
- 更多工具请参阅工具箱实现

**配置：**
```yaml
- class_name: CoinGeckoToolkit
  enabled: true
  toolkit_config:
    coins: null  # 限制特定币种 (null = 全部)
    default_vs_currency: usd  # 默认计价货币
    use_pro: false  # 使用 CoinGecko Pro API
    enable_analysis: false  # 统计分析
```

**环境变量：**
```bash
export COINGECKO_API_KEY=your_key_here  # 可选: 用于 Pro API
```

**无需 API 密钥**（对于公共端点）

**示例：** 参见 `config/profiles/crypto_agent.yaml`

---

### 8. DefiLlamaToolkit

来自 [DefiLlama](https://defillama.com) 的 DeFi 协议分析。

**特性：**
- 协议 TVL (总锁仓价值) 跟踪
- 每日费用和收入分析
- 收益农场池和 APY 数据 (Pro)
- 用户活动指标 (Pro)
- 跨链分析
- 统计分析

**工具 (公共)：**
- `get_protocol_fees(protocol_name: str)` - 协议费用和收入
- `get_protocol_tvl(protocol_name: str)` - 总锁仓价值
- 更多公共工具可用

**工具 (Pro - 需要 API 密钥)：**
- `get_yield_pools()` - 收益农场机会
- `get_yield_chart(pool_id: str)` - 历史 APY 数据
- `get_active_users(protocol_name: str)` - 用户活动
- 更多 Pro 工具可用

**配置：**
```yaml
- class_name: DefiLlamaToolkit
  enabled: true
  toolkit_config:
    enable_pro_features: false  # 需要 API 密钥
    default_chain: ethereum
    enable_analysis: true
```

**环境变量：**
```bash
export DEFILLAMA_API_KEY=your_key_here  # 用于 Pro 功能
```

**无需 API 密钥**（对于公共端点）

**示例：** 参见 `config/profiles/crypto_agent.yaml`

---

### 9. ArkhamToolkit

来自 [Arkham Intelligence](https://arkhamintelligence.com) 的区块链分析。

**特性：**
- 代币分析（热门代币、持有者、流向）
- 实体归属的转账跟踪
- 跨链钱包余额监控
- 分布统计分析
- 速率限制（标准 20 req/sec，重型 1 req/sec）

**工具：**
- 代币分析工具
- 转账跟踪工具
- 钱包余额工具
- 更多工具请参阅工具箱实现

**配置：**
```yaml
- class_name: ArkhamToolkit
  enabled: true
  toolkit_config:
    default_chain: ethereum
    enable_analysis: true
```

**环境变量：**
```bash
export ARKHAM_API_KEY=your_key_here  # 必需
```

**需要 API 密钥**

---

### 10. CoinglassToolkit

来自 [Coinglass](https://coinglass.com) 的衍生品市场数据。

**特性：**
- 持仓量加权的历史资金费率 (OHLC 数据)
- 20+ 交易所的实时资金费率
- 资金费率套利机会检测
- 持仓量跟踪和历史分析
- 主动买入/卖出量比率 (市场情绪)
- 按交易所和仓位类型的清算数据

**工具：**
- `get_funding_rates_weighted_by_oi` - 历史资金费率 OHLC 数据
- `get_funding_rates_per_exchange` - 各交易所当前资金费率
- `get_arbitrage_opportunities` - 资金费率套利机会
- `get_open_interest_by_exchange` - 各交易所当前持仓量
- `get_open_interest_history` - 历史持仓量数据
- `get_taker_buy_sell_volume` - 买/卖量比率
- `get_liquidations_by_exchange` - 清算数据

**配置：**
```yaml
- class_name: CoinglassToolkit
  enabled: true
  toolkit_config:
    symbols: ["BTC", "ETH", "SOL"]  # 限制特定品种 (null = 全部)
    default_symbol: BTC
    storage_threshold_kb: 500  # 自动存储 > 500KB 的响应
```

**环境变量：**
```bash
export COINGLASS_API_KEY=your_key_here  # 必需
```

**需要 API 密钥** - 在 [Coinglass API](https://coinglass.com/api) 获取

**示例：** 参见 `config/profiles/crypto_agent.yaml`

---

### 11. MCPToolkit

模型上下文协议 (Model Context Protocol) 服务器的通用连接器。

**特性：** MCPToolkit 可以连接到 **任何** MCP 服务器 - 有 1000+ 可用！

请参阅下方的 [MCP 集成](#mcp-集成) 部分了解完整详情。

---

## MCP 集成

**MCPToolkit** 使 ROMA-DSPy 智能体能够使用来自 **任何** MCP 服务器的工具。这提供了超越 10 个内置工具箱的无限扩展性。

### 什么是 MCP？

MCP 是用于将 AI 应用程序连接到数据源和工具的开放协议。就像 AI 的 USB-C 接口一样通用。

**资源：**
- **Awesome MCP Servers**: [700+ 服务器](https://github.com/wong2/awesome-mcp-servers)
- **MCP 文档**: [modelcontextprotocol.io](https://modelcontextprotocol.io/)
- **构建您自己的**: 任何实现 MCP 协议的服务器

### 连接类型

#### 1. HTTP/SSE 服务器 (远程)

**最适合：** 公共 API，云服务，无需安装

**示例 - CoinGecko 公共服务器：**
```yaml
- class_name: MCPToolkit
  enabled: true
  toolkit_config:
    server_name: coingecko
    server_type: http
    url: https://mcp.api.coingecko.com/sse
    use_storage: false
```

**示例 - Exa 搜索 (带 API 密钥)：**
```yaml
- class_name: MCPToolkit
  enabled: true
  toolkit_config:
    server_name: exa
    server_type: http
    url: https://mcp.exa.ai/mcp
    headers:
      Authorization: "Bearer ${oc.env:EXA_API_KEY}"
    use_storage: true  # Exa 返回大量搜索结果
    storage_threshold_kb: 50
```

**无需安装** - 通过 HTTP 连接

#### 2. Stdio 服务器 (本地子进程)

**最适合：** 本地工具，文件系统访问，数据库，git 操作

**示例 - GitHub 操作：**
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

**示例 - 文件系统访问：**
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
      - "/Users/yourname/Documents"  # 允许的目录
    use_storage: false
```

**需要安装：**
```bash
npm install -g @modelcontextprotocol/server-github
npm install -g @modelcontextprotocol/server-filesystem
```

### 存储配置

MCP 工具可能会返回大型数据集（搜索结果、数据库查询等）。工具箱提供智能数据处理：

**小数据 (默认)：**
```yaml
use_storage: false  # 直接返回原始文本/JSON
```

**大数据 (带存储)：**
```yaml
use_storage: true  # 数据存入 Parquet，返回引用
storage_threshold_kb: 100  # 存储 > 100KB 的结果 (默认)
```

**工作原理：**
1. 工具执行并返回数据
2. 如果数据大小 > 阈值，保存到 Parquet 文件
3. 返回文件引用而不是完整数据
4. 减少大型数据集的上下文占用

### 查找 MCP 服务器

**热门类别：**

| 类别 | 示例 |
|------|------|
| **Web 搜索** | Exa, Brave Search, Google Search |
| **开发** | GitHub, GitLab, Linear, Sentry |
| **数据** | PostgreSQL, SQLite, MongoDB, Redis |
| **云** | AWS, Google Cloud, Kubernetes |
| **生产力** | Google Drive, Slack, Notion, Confluence |
| **金融** | Stripe, QuickBooks |
| **AI/ML** | OpenAI, Anthropic, Hugging Face |

**浏览全部：**
- [awesome-mcp-servers](https://github.com/wong2/awesome-mcp-servers) - 700+ 服务器
- [MCP Server Registry](https://modelcontextprotocol.io/servers) - 官方注册表

### 多个 MCP 服务器

您可以在一个智能体中使用 **多个** MCP 服务器：

```yaml
agents:
  executor:
    llm:
      model: openai/gpt-4o-mini
    prediction_strategy: react
    toolkits:
      # GitHub 用于代码
      - class_name: MCPToolkit
        toolkit_config:
          server_name: github
          server_type: stdio
          command: npx
          args: ["-y", "@modelcontextprotocol/server-github"]
          env:
            GITHUB_PERSONAL_ACCESS_TOKEN: "${oc.env:GITHUB_TOKEN}"

      # Exa 用于 Web 搜索
      - class_name: MCPToolkit
        toolkit_config:
          server_name: exa
          server_type: http
          url: https://mcp.exa.ai/mcp
          headers:
            Authorization: "Bearer ${oc.env:EXA_API_KEY}"
          use_storage: true

      # Filesystem 用于本地文件
      - class_name: MCPToolkit
        toolkit_config:
          server_name: filesystem
          server_type: stdio
          command: npx
          args: ["-y", "@modelcontextprotocol/server-filesystem", "/path/to/allowed/dir"]
```

**示例：** 参见 `config/examples/mcp/multi_server.yaml`

---

## 配置指南

### 基本结构

```yaml
agents:
  executor:
    llm:
      model: openai/gpt-4o-mini
      temperature: 0.3
    prediction_strategy: react  # 工具使用必需
    toolkits:
      - class_name: ToolkitName
        enabled: true
        include_tools: null  # 可选: 白名单特定工具
        exclude_tools: null  # 可选: 黑名单特定工具
        toolkit_config:
          # 工具箱特定设置
```

### 工具过滤

**仅包含特定工具：**
```yaml
- class_name: CalculatorToolkit
  enabled: true
  include_tools:
    - add
    - subtract
    - multiply
  # 只有这 3 个工具可用
```

**排除特定工具：**
```yaml
- class_name: FileToolkit
  enabled: true
  exclude_tools:
    - delete_file  # 安全：禁用删除
  # 除 delete_file 外的所有工具可用
```

### 环境变量

**通过 OmegaConf：**
```yaml
toolkit_config:
  api_key: "${oc.env:MY_API_KEY}"  # 从环境读取
  timeout: "${oc.env:TIMEOUT,300}"  # 默认值: 300
```

**通过 .env 文件：**
```bash
# .env
E2B_API_KEY=your_key
SERPER_API_KEY=your_key
GITHUB_PERSONAL_ACCESS_TOKEN=your_token
```

### 存储集成

一些工具箱支持可选的 Parquet 存储用于大数据：

```yaml
- class_name: MCPToolkit
  enabled: true
  toolkit_config:
    server_name: database
    server_type: stdio
    command: npx
    args: ["-y", "@modelcontextprotocol/server-sqlite", "/path/to/db.db"]
    use_storage: true  # 启用存储包装器
    storage_threshold_kb: 100  # 存储 > 100KB 的结果
```

**支持存储的工具箱：**
- MCPToolkit
- DefiLlamaToolkit
- ArkhamToolkit
- BinanceToolkit (用于大型响应)
- CoinGeckoToolkit (用于大型响应)
- CoinglassToolkit (用于大型响应)

---

## 示例

所有示例均可在 `config/examples/` 中找到。请参阅 `config/examples/README.md` 获取完整指南。

### 示例 1：极简配置

**文件：** `config/examples/basic/minimal.yaml`

包含 FileToolkit 和 CalculatorToolkit 的简单智能体。

**用法：**
```bash
just solve "计算 2500 的 15% 并保存到 results.txt" -c config/examples/basic/minimal.yaml
```

---

### 示例 2：多工具箱

**文件：** `config/examples/basic/multi_toolkit.yaml`

结合 E2B（代码执行）、FileToolkit、CalculatorToolkit 和 SerperToolkit。

**用法：**
```bash
just solve "搜索 Python 斐波那契实现，执行它，并保存结果" \
  -c config/examples/basic/multi_toolkit.yaml
```

---

### 示例 3：公共 HTTP MCP 服务器

**文件：** `config/examples/mcp/http_public_server.yaml`

使用 CoinGecko 公共 MCP 服务器 - **无需安装或 API 密钥！**

**用法：**
```bash
just solve "比特币当前价格是多少？" \
  -c config/examples/mcp/http_public_server.yaml
```

---

### 示例 4：本地 Stdio MCP 服务器

**文件：** `config/examples/mcp/stdio_local_server.yaml`

使用本地 Exa MCP 服务器进行 Web 搜索。

**设置：**
```bash
export EXA_API_KEY=your_key
npm install -g @exa-labs/exa-mcp-server
```

**用法：**
```bash
just solve "搜索最新的 LLM 研究论文" \
  -c config/examples/mcp/stdio_local_server.yaml
```

---

### 示例 5：多个 MCP 服务器

**文件：** `config/examples/mcp/multi_server.yaml`

结合 GitHub、Exa（Web 搜索）和 CoinGecko MCP 服务器。

**用法：**
```bash
just solve "搜索最近的 AI 新闻，检查比特币价格，并创建 GitHub issue 摘要" \
  -c config/examples/mcp/multi_server.yaml
```

---

### 示例 6：加密货币代理（领域特定）

**文件：** `config/profiles/crypto_agent.yaml`

全面的加密分析，包含：
- CoinGeckoToolkit (17,000+ 币种)
- CoinglassToolkit (衍生品市场数据)
- BinanceToolkit (现货 + 期货)
- DefiLlamaToolkit (DeFi 协议)
- ArkhamToolkit (链上分析)
- Exa MCP (Web 搜索)

**用法：**
```bash
just solve "对比比特币和以太坊：价格、市值、24小时成交量，并分析趋势" \
  crypto_agent
```

---

## 创建自定义工具箱

### 步骤 1：创建工具箱类

```python
# my_custom_toolkit.py
from roma_dspy.tools.base.base import BaseToolkit
from typing import Optional, List

class MyCustomToolkit(BaseToolkit):
    """用于 XYZ 操作的自定义工具箱。"""

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

        # 您的初始化
        self.api_key = config.get("api_key")

    def _setup_dependencies(self) -> None:
        """设置外部依赖。"""
        # 可选：验证 API 密钥，初始化客户端
        pass

    def _initialize_tools(self) -> None:
        """初始化工具箱特定配置。"""
        # 可选：额外设置
        pass

    # 工具方法 (由 BaseToolkit 自动注册)

    async def my_tool(self, param1: str, param2: int) -> str:
        """
        LLM 将看到的工具描述。

        Args:
            param1: param1 的描述
            param2: param2 的描述

        Returns:
            结果描述
        """
        # 您的工具实现
        result = f"Processed {param1} with {param2}"
        return result

    async def another_tool(self, query: str) -> dict:
        """另一个返回结构化数据的工具。"""
        return {
            "success": True,
            "query": query,
            "results": ["result1", "result2"]
        }
```

### 步骤 2：注册工具箱

添加到 `src/roma_dspy/tools/base/manager.py`:

```python
BUILTIN_TOOLKITS = {
    # ... 现有工具箱 ...
    "MyCustomToolkit": "path.to.my_custom_toolkit",
}
```

### 步骤 3：在配置中使用

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

### 最佳实践

1. **工具设计：**
   - 清晰、描述性的工具名称
   - 全面的文档字符串（LLM 会看到这些）
   - 所有参数的类型提示
   - 返回结构化数据（JSON 字典或字符串）

2. **错误处理：**
   ```python
   async def my_tool(self, param: str) -> dict:
       try:
           result = await self._do_something(param)
           return {"success": True, "data": result}
       except Exception as e:
           logger.error(f"Tool failed: {e}")
           return {"success": False, "error": str(e)}
   ```

3. **大型数据存储：**
   ```python
   class MyToolkit(BaseToolkit):
       REQUIRES_FILE_STORAGE = False  # 可选存储

       def __init__(self, use_storage: bool = False, **config):
           super().__init__(**config)
           self.use_storage = use_storage

       async def big_data_tool(self, query: str) -> str:
           result = await self._fetch_large_dataset(query)

           if self.use_storage and len(result) > threshold:
               # 存储到 Parquet 并返回引用
               path = await self.file_storage.save_tool_result(...)
               return f"Data stored at: {path}"

           return result
   ```

4. **测试：**
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

## 最佳实践

### 1. 工具箱选择

**为任务选择正确的工具：**
```yaml
# 用于文件操作 + 数学
toolkits:
  - class_name: FileToolkit
  - class_name: CalculatorToolkit

# 用于 Web 研究
toolkits:
  - class_name: SerperToolkit  # 原生
  # 或
  - class_name: MCPToolkit  # MCP (Exa, Brave 等)
    toolkit_config:
      server_name: exa
      server_type: http
      url: https://mcp.exa.ai/mcp

# 用于代码执行
toolkits:
  - class_name: E2BToolkit
```

### 2. 安全性

**文件操作：**
```yaml
- class_name: FileToolkit
  toolkit_config:
    enable_delete: false  # 禁用破坏性操作
    max_file_size: 10485760  # 10MB 限制
```

**MCP 服务器：**
- 仅使用受信任的 MCP 服务器
- 验证服务器 URL 和签名
- 对敏感数据使用环境变量

### 3. 性能

**对大数据使用存储：**
```yaml
- class_name: MCPToolkit
  toolkit_config:
    use_storage: true
    storage_threshold_kb: 50  # 激进的阈值以加快响应
```

**限制工具范围：**
```yaml
- class_name: CalculatorToolkit
  include_tools:
    - add
    - multiply
  # 更少的选项使工具选择更快
```

### 4. 成本优化

**使用任务感知映射**为不同任务类型分配不同的工具箱：

```yaml
agent_mapping:
  executors:
    RETRIEVE:
      # 便宜的模型 + Web 搜索
      llm:
        model: openrouter/google/gemini-2.0-flash-exp:free
      toolkits:
        - class_name: SerperToolkit

    CODE_INTERPRET:
      # 强大的模型 + 代码执行
      llm:
        model: openrouter/anthropic/claude-sonnet-4
      toolkits:
        - class_name: E2BToolkit
        - class_name: FileToolkit
```

**示例：** 参见 `config/examples/advanced/task_aware_mapping.yaml`

### 5. 可观察性

**启用日志：**
```yaml
runtime:
  enable_logging: true
```

**跟踪工具指标：**
- 自动记录工具调用
- 延迟跟踪
- 错误率
- 在 MLflow 中查看（如果启用了可观察性）

### 6. API 密钥管理

**切勿硬编码密钥：**
```yaml
# ❌ 错误
toolkit_config:
  api_key: "sk-1234567890abcdef"

# ✅ 正确
toolkit_config:
  api_key: "${oc.env:MY_API_KEY}"
```

**使用 .env 文件：**
```bash
# .env
E2B_API_KEY=your_key
SERPER_API_KEY=your_key
GITHUB_PERSONAL_ACCESS_TOKEN=your_token
```

---

## 故障排除

### "Unknown toolkit class: XYZ"

**原因：** 工具箱未注册或 class_name 拼写错误

**修复：**
```bash
# 检查可用工具箱
python -c "from roma_dspy.tools.base.manager import ToolkitManager; print(ToolkitManager.BUILTIN_TOOLKITS.keys())"

# 验证拼写是否完全匹配（区分大小写）
```

### "Tools don't support strategy: chain_of_thought"

**原因：** Chain-of-thought 策略不支持工具使用

**修复：**
```yaml
agents:
  executor:
    prediction_strategy: react  # 使用 react 或 codeact 以支持工具
```

### MCP 服务器连接失败

**HTTP 服务器：**
```bash
# 测试连接
curl -I https://mcp.api.coingecko.com/sse

# 检查 headers/auth
curl -H "Authorization: Bearer YOUR_KEY" https://mcp.exa.ai/mcp
```

**Stdio 服务器：**
```bash
# 验证安装
npx @modelcontextprotocol/server-github --version

# 手动测试
npx -y @modelcontextprotocol/server-github
```

### E2B 不工作

```bash
# 验证 API 密钥
echo $E2B_API_KEY

# 测试连接
python -c "from e2b import Sandbox; s = Sandbox(); print(s.is_running())"

# 检查模板
export E2B_TEMPLATE_ID=base
```

### 大数据超时

**启用存储：**
```yaml
toolkit_config:
  use_storage: true
  storage_threshold_kb: 50  # 降低阈值
```

---

## 额外资源

- **配置指南**: [CONFIGURATION.md](CONFIGURATION.md)
- **MCP 深入解析**: [MCP.md](MCP.md)
- **示例配置**: `config/examples/`
- **Awesome MCP Servers**: https://github.com/wong2/awesome-mcp-servers
- **MCP 文档**: https://modelcontextprotocol.io/
- **E2B 文档**: https://e2b.dev/docs

---

**准备好构建了吗？** 从 `config/examples/` 中的示例开始，并根据您的用例进行定制！ 🚀

