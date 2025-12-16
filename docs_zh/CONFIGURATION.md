# ROMA-DSPy 配置指南

ROMA-DSPy 智能体、profiles、工具箱和运行时设置的完整配置参考。

## 目录

- [概览](#概览)
- [配置系统](#配置系统)
- [Profiles](#profiles)
- [智能体配置](#智能体配置)
- [任务感知智能体映射](#任务感知智能体映射)
- [工具箱配置](#工具箱配置)
- [LLM 配置](#llm-配置)
- [运行时设置](#运行时设置)
- [存储配置](#存储配置)
- [可观察性 (MLflow)](#可观察性-mlflow)
- [弹性设置](#弹性设置)
- [日志配置](#日志配置)
- [环境变量](#环境变量)
- [自定义提示词和演示](#自定义提示词和演示)
- [配置示例](#配置示例)
- [最佳实践](#最佳实践)

---

## 概览

ROMA-DSPy 使用**分层配置系统**，结合了：
- **OmegaConf**：灵活的 YAML 配置与插值
- **Pydantic**：类型安全验证和默认值
- **Profiles**：针对不同用例的预配置设置
- **环境变量**：运行时覆盖

### 主要特性

- **分层合并**：合并默认值、profiles 和覆盖
- **类型验证**：尽早捕获配置错误
- **环境插值**：使用 `${oc.env:API_KEY}` 获取机密信息
- **Profile 系统**：针对不同领域的预配置智能体
- **任务感知映射**：针对不同任务类型使用不同的执行器

---

## 配置系统

### 解析顺序

配置按以下顺序加载和合并：

1. **Pydantic 默认值** - 来自模式 (schema) 类的基础默认值
2. **YAML 配置** - 显式配置文件
3. **Profile** - Profile 覆盖（如果指定）
4. **CLI/运行时覆盖** - 命令行参数
5. **环境变量** - `ROMA__*` 变量
6. **验证** - 通过 Pydantic 进行最终验证

后层配置覆盖前层配置。

### 使用配置

#### 通过 CLI
```bash
# 使用 profile
uv run python -m roma_dspy.cli solve "task" --profile crypto_agent

# 使用自定义配置文件
uv run python -m roma_dspy.cli solve "task" --config config/examples/basic/minimal.yaml

# 带覆盖
uv run python -m roma_dspy.cli solve "task" \
  --profile general \
  --override agents.executor.llm.temperature=0.5
```

#### 通过 Docker (Just)
```bash
# 使用 profile
just solve "task" crypto_agent

# 带所有参数
just solve "task" general 2 true json
# 参数: <task> [profile] [max_depth] [verbose] [output]
```

#### 通过 API
```bash
curl -X POST http://localhost:8000/api/v1/executions \
  -H "Content-Type: application/json" \
  -d '{
    "goal": "Your task",
    "config_profile": "general",
    "max_depth": 2
  }'
```

#### 编程方式
```python
from roma_dspy.config.manager import ConfigManager

# 加载 profile
config_mgr = ConfigManager()
config = config_mgr.load_config(profile="general")

# 加载自定义配置
config = config_mgr.load_config(
    config_path="config/custom.yaml",
    overrides=["runtime.max_depth=2"]
)

# 带环境前缀
config = config_mgr.load_config(
    profile="crypto_agent",
    env_prefix="ROMA_"
)
```

---

## Profiles

Profiles 是针对不同用例的预配置智能体设置。位于 `config/profiles/`。

### 可用 Profiles

| Profile | 用途 | 用例 | 模型 |
|---------|------|------|------|
| **general** | 通用智能体 | Web 研究, 代码执行, 文件操作, 计算 | Gemini Flash + Claude Sonnet 4.5 |
| **crypto_agent** | 加密货币分析 | 价格跟踪, DeFi 分析, 链上数据 | 任务感知 (Gemini Flash / Claude Sonnet 4.5) |

### Profile 结构

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

### 创建自定义 Profiles

创建 `config/profiles/my_profile.yaml`:

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
  max_depth: 2  # 推荐: 大多数任务 1-2
  timeout: 120
  enable_logging: true
```

使用它：
```bash
just solve "task" my_profile
```

---

## 智能体配置

ROMA-DSPy 有 5 个核心智能体模块。每个都可以独立配置。

### 智能体类型

| 智能体 | 角色 | 默认策略 | 工具箱 |
|-------|------|---------|--------|
| **Atomizer** | 将任务分类为原子或可分解 | chain_of_thought | 无 |
| **Planner** | 将复杂任务分解为子任务 | chain_of_thought | 无 |
| **Executor** | 执行原子任务 | react | 所有工具箱 |
| **Aggregator** | 综合子任务结果 | chain_of_thought | 无 |
| **Verifier** | 验证输出 | chain_of_thought | 无 |

### 智能体配置模式

```yaml
agents:
  executor:  # 智能体类型: atomizer, planner, executor, aggregator, verifier
    # LLM 配置
    llm:
      model: openrouter/anthropic/claude-sonnet-4.5
      temperature: 0.2
      max_tokens: 32000
      timeout: 30
      num_retries: 3
      cache: true

    # 预测策略 (chain_of_thought 或 react)
    prediction_strategy: react

    # 自定义提示词 (可选)
    signature_instructions: "module.path:VARIABLE_NAME"
    demos: "module.path:DEMOS_LIST"

    # 智能体特定设置
    agent_config:
      max_executions: 10  # executor 的最大迭代次数
      # max_subtasks: 12  # planner 的最大子任务数

    # 策略特定设置
    strategy_config:
      # ReAct 特定设置

    # 工具箱 (仅 executor)
    toolkits:
      - class_name: E2BToolkit
        enabled: true
        toolkit_config:
          timeout: 600
```

### 每智能体默认值

每个智能体都有合理的默认值。仅覆盖您需要的：

```yaml
# 最小 executor 覆盖
agents:
  executor:
    llm:
      temperature: 0.3  # 仅覆盖温度
    # 所有其他设置使用默认值
```

### 智能体特定设置

#### Atomizer
```yaml
atomizer:
  agent_config:
    confidence_threshold: 0.8  # 原子分类的阈值
```

#### Planner
```yaml
planner:
  agent_config:
    max_subtasks: 12  # 生成的最大子任务数
```

#### Executor
```yaml
executor:
  agent_config:
    max_executions: 10  # 最大 ReAct 迭代次数
```

#### Aggregator
```yaml
aggregator:
  agent_config:
    synthesis_strategy: hierarchical  # 如何聚合结果
```

#### Verifier
```yaml
verifier:
  agent_config:
    verification_depth: moderate  # 验证彻底程度
```

---

## 任务感知智能体映射

**高级特性**：为不同任务类型使用不同的执行器配置。

### 任务类型

ROMA-DSPy 将任务分为 5 类：

| 任务类型 | 描述 | 示例任务 |
|---------|------|----------|
| **RETRIEVE** | 数据获取, Web 搜索 | "比特币价格", "查找文档" |
| **CODE_INTERPRET** | 代码执行, 分析 | "运行此脚本", "分析 CSV 数据" |
| **THINK** | 深度推理, 分析 | "比较方法", "分析情绪" |
| **WRITE** | 内容创作 | "写报告", "创建文档" |
| **IMAGE_GENERATION** | 图像生成 | "生成图表", "创建可视化" |

### 映射配置

```yaml
# 默认智能体 (用于 atomizer, planner, aggregator, verifier)
agents:
  executor:
    llm:
      model: openrouter/anthropic/claude-sonnet-4.5
    prediction_strategy: react
    toolkits:
      - class_name: FileToolkit
        enabled: true

# 任务特定执行器配置
agent_mapping:
  executors:
    # RETRIEVE: 快速模型 + Web 搜索
    RETRIEVE:
      llm:
        model: openrouter/google/gemini-2.5-flash  # 快速且便宜
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

    # CODE_INTERPRET: 强大模型 + 代码执行
    CODE_INTERPRET:
      llm:
        model: openrouter/anthropic/claude-sonnet-4.5  # 强大
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

### 优势

- **成本优化**：简单任务使用便宜模型
- **质量优化**：复杂任务使用强大模型
- **工具匹配**：每种任务类型获得适当的工具箱
- **性能**：任务特定配置带来更快的执行速度

### 示例: crypto_agent Profile

`crypto_agent` profile 使用任务感知映射：

- **RETRIEVE**: Gemini Flash (快速, 便宜) + CoinGecko/Binance
- **CODE_INTERPRET**: Claude Sonnet 4.5 (强大) + E2B + 加密数据
- **THINK**: Claude Sonnet 4.5 + 所有工具箱
- **WRITE**: Claude Sonnet 4.5 (创造性) + FileToolkit + 研究

---

## 工具箱配置

工具箱提供智能体可以使用的工具（函数）。按智能体配置。

### 可用工具箱

#### 原生工具箱

ROMA-DSPy 包含这些内置工具箱：

| 工具箱 | 用途 | API 密钥 | 配置选项 |
|-------|------|---------|----------|
| **FileToolkit** | 文件 I/O 操作 | ❌ 无 | `enable_delete`, `max_file_size` |
| **CalculatorToolkit** | 数学运算 | ❌ 无 | 无 |
| **E2BToolkit** | 代码执行沙箱 | ✅ 有 | `timeout`, `auto_reinitialize` |
| **SerperToolkit** | Web 搜索 | ✅ 有 | `num_results`, `search_type` |
| **BinanceToolkit** | 加密市场数据 | ❌ 无 | `default_market`, `enable_analysis` |
| **CoinGeckoToolkit** | 加密价格 | ❌ 无 | `use_pro_api` |
| **DefiLlamaToolkit** | DeFi 协议数据 | ❌ 无 | `enable_pro_features` |
| **ArkhamToolkit** | 区块链分析 | ❌ 无 | `enable_analysis` |

#### MCP 工具箱

**MCPToolkit** 很特殊 - 它可以连接到 **任何** MCP (Model Context Protocol) 服务器，让您能够访问数千个潜在工具。

**两种类型的 MCP 服务器：**

1. **HTTP MCP 服务器** (远程)
   - 公共或私有 HTTP 端点
   - 无需安装
   - 示例：CoinGecko MCP, Exa MCP, 或任何自定义 HTTP MCP 服务器

2. **Stdio MCP 服务器** (本地)
   - 作为本地子进程运行
   - 通常是 npm 包或自定义脚本
   - 示例：Filesystem, GitHub, SQLite, 或任何 npm MCP 服务器

**查找 MCP 服务器：**
- **Awesome MCP Servers**: https://github.com/wong2/awesome-mcp-servers (数百个服务器)
- **MCP 文档**: https://modelcontextprotocol.io/
- **构建您自己的**: 任何实现 MCP 协议的服务器

### 基本工具箱配置

```yaml
agents:
  executor:
    toolkits:
      # 无配置的简单工具箱
      - class_name: CalculatorToolkit
        enabled: true

      # 带基本配置的工具箱
      - class_name: FileToolkit
        enabled: true
        toolkit_config:
          enable_delete: false
          max_file_size: 10485760  # 10MB
```

### E2B 工具箱配置

```yaml
- class_name: E2BToolkit
  enabled: true
  toolkit_config:
    timeout: 600  # 执行超时 (秒)
    max_lifetime_hours: 23.5  # 沙箱生命周期
    auto_reinitialize: true  # 失败自动重启
```

**环境变量**:
```bash
E2B_API_KEY=your_e2b_api_key
E2B_TEMPLATE_ID=roma-dspy-sandbox  # 自定义模板
STORAGE_BASE_PATH=/opt/sentient  # 共享存储
```

### MCP 工具箱配置

#### HTTP MCP 服务器 (公共)

连接到任何公共 HTTP MCP 服务器：

```yaml
- class_name: MCPToolkit
  enabled: true
  toolkit_config:
    server_name: coingecko_mcp
    server_type: http
    url: "https://mcp.api.coingecko.com/sse"
    use_storage: true  # 将大结果存储到 Parquet
    storage_threshold_kb: 10  # > 10KB 时存储
```

#### HTTP MCP 服务器 (带认证)

连接到任何经过身份验证的 HTTP MCP 服务器：

```yaml
- class_name: MCPToolkit
  enabled: true
  toolkit_config:
    server_name: exa
    server_type: http
    url: https://mcp.exa.ai/mcp
    headers:
      Authorization: Bearer ${oc.env:EXA_API_KEY}
      # 添加 MCP 服务器所需的任何自定义头
    transport_type: streamable
    use_storage: false
    tool_timeout: 60
```

#### Stdio MCP 服务器 (本地)

连接到任何 stdio MCP 服务器（npm 包或自定义脚本）：

```yaml
- class_name: MCPToolkit
  enabled: true
  toolkit_config:
    server_name: filesystem
    server_type: stdio
    command: npx  # 或 python, node 等
    args:
      - "-y"
      - "@modelcontextprotocol/server-filesystem"
      - "/Users/yourname/Documents"  # 服务器特定参数
    env:  # 服务器的可选环境变量
      CUSTOM_VAR: value
    use_storage: false
```

**常见 Stdio 示例：**

```yaml
# GitHub MCP 服务器
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

# SQLite MCP 服务器
- class_name: MCPToolkit
  toolkit_config:
    server_name: sqlite
    server_type: stdio
    command: npx
    args:
      - "-y"
      - "@modelcontextprotocol/server-sqlite"
      - "/path/to/database.db"

# 自定义 Python MCP 服务器
- class_name: MCPToolkit
  toolkit_config:
    server_name: my_custom_server
    server_type: stdio
    command: python
    args:
      - "/path/to/my_mcp_server.py"
```

**Stdio 服务器先决条件**:
- npm 包: `npm install -g <package-name>`
- 自定义脚本: 确保可执行并实现 MCP 协议

### 加密工具箱配置

#### Binance

```yaml
- class_name: BinanceToolkit
  enabled: true
  include_tools:  # 可选: 限制特定工具
    - get_current_price
    - get_ticker_stats
    - get_klines
  toolkit_config:
    enable_analysis: true
    default_market: spot  # spot 或 futures
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

### 工具过滤

限制工具箱中可用的工具：

```yaml
- class_name: MCPToolkit
  enabled: true
  include_tools:  # 仅这些工具
    - get_simple_price
    - get_coins_markets
    - get_search
  toolkit_config:
    server_name: coingecko_mcp
    server_type: http
    url: "https://mcp.api.coingecko.com/sse"
```

---

## LLM 配置

为每个智能体配置语言模型。

### 基本 LLM 配置

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

### LLM 参数

| 参数 | 描述 | 范围 | 默认值 |
|------|------|------|--------|
| **model** | 模型标识符 | 提供商特定 | `gpt-4o-mini` |
| **temperature** | 随机性 (0=确定性, 2=创造性) | 0.0 - 2.0 | 0.7 |
| **max_tokens** | 最大输出 Token | 1 - 200000 | 2000 |
| **timeout** | 请求超时 (秒) | > 0 | 30 |
| **num_retries** | 失败重试次数 | 0 - 10 | 3 |
| **cache** | 启用 DSPy 缓存 | true/false | true |
| **adapter_type** | DSPy 适配器类型 | `json` 或 `chat` | `json` |
| **use_native_function_calling** | 启用原生工具调用 | true/false | `true` |

### DSPy 适配器配置

ROMA-DSPy 使用 DSPy 适配器来格式化 LLM 的输入/输出。有两种适配器类型可用：

**JSONAdapter** (默认，推荐)：
- 使用结构化 JSON 进行输入/输出
- 对 Claude 和 Gemini 模型性能更好
- 提示词格式更清晰

**ChatAdapter**：
- 使用聊天消息格式
- 对某些 OpenAI 模型性能更好
- 更具对话风格

**原生函数调用** (默认启用)：
- 利用 LLM 提供商的原生工具调用 API (OpenAI, Anthropic 等)
- 对不支持的模型自动回退到基于文本的解析
- 可靠性无差异，提供商集成更清洁

两个参数都有合理的默认值，在配置中是**可选的**：

```yaml
agents:
  executor:
    llm:
      model: openrouter/anthropic/claude-sonnet-4.5
      temperature: 0.2
      max_tokens: 16000
      # 默认: adapter_type=json, use_native_function_calling=true
      # 取消注释以覆盖:
      # adapter_type: chat
      # use_native_function_calling: false
```

### 模型命名

#### OpenRouter (推荐)

所有模型使用单个 API 密钥：

```yaml
model: openrouter/anthropic/claude-sonnet-4.5
model: openrouter/google/gemini-2.5-flash
model: openrouter/openai/gpt-4o
```

**环境**: `OPENROUTER_API_KEY=your_key`

#### 直接提供商

```yaml
# Anthropic
model: claude-sonnet-4.5
# 需要: ANTHROPIC_API_KEY

# OpenAI
model: gpt-4o
# 需要: OPENAI_API_KEY

# Google
model: gemini-2.5-flash
# 需要: GOOGLE_API_KEY
```

### 温度指南

| 温度 | 用途 | 示例 |
|------|------|------|
| **0.0** | 确定性, 事实性 | 数据检索, 分类 |
| **0.1-0.2** | 轻微创造性 | 代码生成, 分析 |
| **0.3-0.5** | 平衡 | 通用任务, 推理 |
| **0.6-1.0** | 创造性 | 内容写作, 头脑风暴 |
| **1.0+** | 非常创造性 | 诗歌, 实验性 |

### Token 限制

按智能体推荐的 `max_tokens`：

| 智能体 | 推荐值 | 理由 |
|-------|-------|------|
| **Atomizer** | 1000-8000 | 简单分类 |
| **Planner** | 4000-32000 | 复杂任务分解 |
| **Executor** | 16000-32000 | 详细执行 |
| **Aggregator** | 5000-32000 | 结果综合 |
| **Verifier** | 3000-16000 | 验证检查 |

### 提供商特定参数 (`extra_body`)

通过 `extra_body` 参数传递提供商特定的特性。这对 OpenRouter 的高级功能（如 Web 搜索、模型路由和提供商偏好）特别有用。

**安全提示**：切勿在 `extra_body` 中包含敏感密钥 (api_key, secret, token)。请使用 `api_key` 字段。

#### OpenRouter Web 搜索

启用实时 Web 搜索以获取最新信息：

```yaml
agents:
  executor:
    llm:
      model: openrouter/google/gemini-2.5-flash
      temperature: 0.0
      extra_body:
        plugins:
          - id: web
            engine: exa  # 选项: "exa", "native", 或省略以自动选择
            max_results: 3
```

**替代方案**：使用 `:online` 后缀进行快速设置：
```yaml
model: openrouter/anthropic/claude-sonnet-4.5:online
```

#### 带有上下文大小的 OpenRouter 原生搜索

对于带有可自定义上下文的 OpenRouter 原生搜索引擎：

```yaml
extra_body:
  plugins:
    - id: web
      engine: native
  web_search_options:
    search_context_size: high  # 选项: "low", "medium", "high"
```

#### 模型回退数组

自动故障转移到替代模型：

```yaml
extra_body:
  models:
    - anthropic/claude-sonnet-4.5
    - openai/gpt-4o
    - google/gemini-2.5-pro
  route: fallback  # 选项: "fallback", "lowest-cost", "lowest-latency"
```

#### 提供商偏好

控制使用哪些提供商：

```yaml
extra_body:
  provider:
    order:
      - Anthropic
      - OpenAI
    data_collection: deny  # 隐私控制: "allow" 或 "deny"
```

#### 完整 OpenRouter Web 搜索示例

```yaml
agents:
  executor:
    llm:
      model: openrouter/anthropic/claude-sonnet-4.5
      temperature: 0.2
      max_tokens: 16000
      extra_body:
        # 启用带自定义设置的 Web 搜索
        plugins:
          - id: web
            engine: exa
            max_results: 5
            search_prompt: "Relevant information:"
        # 针对可靠性的回退模型
        models:
          - anthropic/claude-sonnet-4.5
          - openai/gpt-4o
        route: fallback
```

**文档**：查看 [OpenRouter Web 搜索文档](https://openrouter.ai/docs/features/web-search) 获取所有可用选项。

**成本警告**：Web 搜索插件可能会显著增加每个请求的 API 成本。

---

## 运行时设置

控制执行行为、超时和日志记录。

### 运行时配置

```yaml
runtime:
  max_depth: 6  # 递归深度 (推荐: 1-2)
  max_concurrency: 5  # 并行任务限制
  timeout: 120  # 全局超时 (秒)
  verbose: true  # 详细输出
  enable_logging: true  # 记录到文件
  log_level: INFO  # DEBUG, INFO, WARNING, ERROR

  # 缓存配置
  cache:
    enabled: true
    enable_disk_cache: true
    enable_memory_cache: true
    disk_cache_dir: .cache/dspy
    disk_size_limit_bytes: 30000000000  # 30GB
    memory_max_entries: 1000000
```

### 运行时参数

| 参数 | 描述 | 范围 | 默认值 | 推荐值 |
|------|------|------|--------|--------|
| **max_depth** | 最大任务分解深度 | 1-20 | 5 | **1-2** |
| **max_concurrency** | 并行子任务数 | 1-50 | 5 | 5-10 |
| **timeout** | 全局执行超时 (秒) | 1-300 | 30 | 120-300 |
| **verbose** | 打印详细输出 | bool | false | true (开发) |
| **enable_logging** | 文件日志 | bool | false | true |
| **log_level** | 日志详细程度 | DEBUG-CRITICAL | INFO | INFO |

### 最大深度指南

**重要**：较低的 max_depth = 更快、更便宜、更可靠的执行。

| max_depth | 用例 | 权衡 |
|-----------|------|------|
| **1** | 简单原子任务 | 快速, 便宜, 有限分解 |
| **2** | 大多数生产用例 | **推荐** - 良好平衡 |
| **3-4** | 复杂多步任务 | 较慢, 较贵 |
| **5+** | 高度复杂的分层任务 | 非常慢, 昂贵, 可能失败 |

**最佳实践**：从 `max_depth=1` 开始，仅在需要时增加。

---

## 存储配置

配置执行数据和工具结果的持久存储。

### 存储配置

```yaml
storage:
  base_path: ${oc.env:STORAGE_BASE_PATH,/opt/sentient}
  max_file_size: 104857600  # 100MB

  # PostgreSQL (执行跟踪)
  postgres:
    enabled: ${oc.env:POSTGRES_ENABLED,true}
    connection_url: ${oc.env:DATABASE_URL,postgresql+asyncpg://localhost/roma_dspy}
    pool_size: 10
    max_overflow: 20
```

### 存储后端

#### 本地文件系统

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

或通过 docker-compose (自动)：

```bash
just docker-up  # 自动启动 postgres
```

### 工具结果存储

MCP 和原生工具箱可以将大结果存储到 Parquet：

```yaml
toolkits:
  - class_name: MCPToolkit
    toolkit_config:
      use_storage: true
      storage_threshold_kb: 10  # 存储 > 10KB 的结果
```

**优势**：
- 减少上下文大小
- 启用大型数据集处理
- 自动压缩
- 可通过 DuckDB 查询

---

## 可观察性 (MLflow)

使用 MLflow 跟踪执行指标、追踪和模型性能。

### MLflow 配置

```yaml
observability:
  mlflow:
    enabled: ${oc.env:MLFLOW_ENABLED,false}
    tracking_uri: ${oc.env:MLFLOW_TRACKING_URI,http://mlflow:5000}
    experiment_name: ROMA-General-Agent
    log_traces: true  # 记录完整执行追踪
    log_compiles: true  # 记录 DSPy 编译
    log_evals: true  # 记录评估
```

### 环境变量

```bash
# .env
MLFLOW_ENABLED=true
MLFLOW_TRACKING_URI=http://mlflow:5000
MLFLOW_EXPERIMENT=ROMA-DSPy
```

### 使用 MLflow

#### 启动 MLflow 服务器

```bash
# 通过 Docker Compose (推荐)
just docker-up-full  # 包含 MLflow

# 访问 UI
open http://localhost:5000
```

#### 跟踪执行

```bash
# 启用 MLflow 运行任务
MLFLOW_ENABLED=true just solve "analyze bitcoin price"

# 在 MLflow UI 中查看追踪
open http://localhost:5000
```

### MLflow 跟踪内容

- **执行指标**：持续时间、深度、Token 使用量
- **LLM 调用**：模型、参数、延迟
- **工具使用**：工具调用、结果、错误
- **追踪**：带 span 的完整执行树
- **参数**：所有配置值
- **工件**：输出、日志、检查点

---

## 弹性设置

自动错误处理、重试和恢复。

### 弹性配置

```yaml
resilience:
  # 重试配置
  retry:
    enabled: true
    max_attempts: 5
    strategy: exponential_backoff
    base_delay: 2.0  # 初始延迟 (秒)
    max_delay: 60.0  # 最大延迟

  # 断路器
  circuit_breaker:
    enabled: true
    failure_threshold: 5  # 打开前的故障数
    recovery_timeout: 120.0  # 重试前秒数
    half_open_max_calls: 3  # 恢复时的测试调用数

  # 检查点
  checkpoint:
    enabled: true
    storage_path: ${oc.env:ROMA_CHECKPOINT_PATH,.checkpoints}
    max_checkpoints: 20
    max_age_hours: 48.0
    compress_checkpoints: true
    verify_integrity: true
```

### 重试策略

| 策略 | 行为 | 用例 |
|------|------|------|
| **exponential_backoff** | 每次重试延迟翻倍 | 大多数情况 (默认) |
| **fixed_delay** | 每次重试延迟相同 | 可预测的时间 |
| **random_backoff** | 随机抖动 | 避免惊群效应 |

### 断路器状态

- **Closed**: 正常运行
- **Open**: 故障中，拒绝新请求
- **Half-Open**: 测试恢复

### 检查点恢复

从故障中自动恢复：

```python
from roma_dspy.core.engine.solve import solve

# 执行将自动创建检查点
result = solve("complex task", max_depth=3)

# 如果中断，从检查点恢复
result = solve("complex task", resume_from_checkpoint=True)
```

---

## 日志配置

使用 loguru 进行结构化日志记录。

### 日志配置

```yaml
logging:
  level: ${oc.env:LOG_LEVEL,INFO}
  log_dir: ${oc.env:LOG_DIR,logs}  # null = 仅控制台
  console_format: detailed  # minimal, default, detailed
  file_format: json  # default, detailed, json
  colorize: true
  serialize: true  # JSON 序列化
  rotation: 500 MB  # 文件轮转大小
  retention: 90 days  # 保留时间
  compression: zip  # 压缩轮转日志
  backtrace: true  # 完整回溯
  diagnose: false  # 变量值 (生产中禁用)
  enqueue: true  # 线程安全
```

### 日志级别

| 级别 | 用途 |
|------|------|
| **DEBUG** | 开发, 详细追踪 |
| **INFO** | 生产, 重要事件 |
| **WARNING** | 潜在问题 |
| **ERROR** | 错误, 异常 |
| **CRITICAL** | 致命错误 |

### 环境变量

```bash
# .env
LOG_LEVEL=INFO
LOG_DIR=logs  # 或 null 用于仅控制台
LOG_CONSOLE_FORMAT=detailed
LOG_FILE_FORMAT=json
```

### 日志格式

#### 控制台格式

- **minimal**: 级别 + 消息
- **default**: 时间, 级别, 模块, 消息 (彩色)
- **detailed**: 包含 execution_id, 行号的完整上下文

#### 文件格式

- **default**: 标准文本格式
- **detailed**: 包含进程/线程信息
- **json**: 机器可解析的结构化日志

---

## 环境变量

环境变量覆盖配置值。

### LLM 提供商密钥

```bash
# OpenRouter (推荐 - 单个 key 用于所有模型)
OPENROUTER_API_KEY=your_key

# 或单独的提供商
OPENAI_API_KEY=your_key
ANTHROPIC_API_KEY=your_key
GOOGLE_API_KEY=your_key
```

### 工具箱密钥

```bash
# 代码执行
E2B_API_KEY=your_key
E2B_TEMPLATE_ID=roma-dspy-sandbox

# Web 搜索
EXA_API_KEY=your_key
SERPER_API_KEY=your_key

# 加密 API (均为可选，公共端点无需 key)
COINGECKO_API_KEY=your_key  # 用于 Pro API
DEFILLAMA_API_KEY=your_key  # 用于 Pro 功能
ARKHAM_API_KEY=your_key
BINANCE_API_KEY=your_key
BINANCE_API_SECRET=your_secret

# GitHub MCP
GITHUB_PERSONAL_ACCESS_TOKEN=your_token

# 任何 MCP 服务器可能需要其自己的环境变量
```

### 存储与数据库

```bash
# 存储
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

### 运行时覆盖

使用带双下划线的 `ROMA__` 前缀：

```bash
# 覆盖 agents.executor.llm.temperature
ROMA__AGENTS__EXECUTOR__LLM__TEMPERATURE=0.5

# 覆盖 runtime.max_depth
ROMA__RUNTIME__MAX_DEPTH=2
```

**格式**: `ROMA__<path>__<to>__<setting>=value`

### Docker Compose

在 docker-compose 中，在 `.env` 中设置：

```bash
# .env
OPENROUTER_API_KEY=your_key
E2B_API_KEY=your_key
POSTGRES_ENABLED=true
MLFLOW_ENABLED=true
```

然后：
```bash
just docker-up  # 自动加载 .env
```

---

## 自定义提示词和演示

使用优化的提示词和 Few-shot 示例增强智能体性能。

### 签名指令

自定义指令指导智能体的行为。

#### 三种格式

**1. 内联字符串**
```yaml
agents:
  executor:
    signature_instructions: "逐步执行任务并提供清晰的推理。"
```

**2. Jinja 模版文件**
```yaml
agents:
  executor:
    signature_instructions: "config/prompts/executor.jinja"
```

**3. Python 模块变量**
```yaml
agents:
  executor:
    signature_instructions: "prompt_optimization.seed_prompts.executor_seed:EXECUTOR_PROMPT"
```

#### 种子提示词

ROMA-DSPy 在 `prompt_optimization/seed_prompts/` 中包含优化的种子提示词：

| 模块 | 变量 | 用途 |
|------|------|------|
| `atomizer_seed` | `ATOMIZER_PROMPT` | 任务分类 |
| `planner_seed` | `PLANNER_PROMPT` | 任务分解 |
| `executor_seed` | `EXECUTOR_PROMPT` | 通用执行 |
| `executor_retrieve_seed` | `EXECUTOR_RETRIEVE_PROMPT` | 数据检索 |
| `executor_code_seed` | `EXECUTOR_CODE_PROMPT` | 代码执行 |
| `executor_think_seed` | `EXECUTOR_THINK_PROMPT` | 深度推理 |
| `executor_write_seed` | `EXECUTOR_WRITE_PROMPT` | 内容创作 |
| `aggregator_seed` | `AGGREGATOR_PROMPT` | 结果综合 |
| `verifier_seed` | `VERIFIER_PROMPT` | 输出验证 |

### 演示 (Few-Shot 示例)

提供示例以指导智能体。

#### 格式

```yaml
agents:
  executor:
    demos: "prompt_optimization.seed_prompts.executor_seed:EXECUTOR_DEMOS"
```

#### 创建自定义演示

```python
# my_prompts/executor_demos.py
import dspy

EXECUTOR_DEMOS = [
    dspy.Example(
        goal="计算 2500 的 15%",
        answer="375"
    ).with_inputs("goal"),
    dspy.Example(
        goal="法国的首都是哪里？",
        answer="巴黎"
    ).with_inputs("goal")
]
```

在配置中使用：
```yaml
agents:
  executor:
    demos: "my_prompts.executor_demos:EXECUTOR_DEMOS"
```

### 自定义签名

覆盖默认 DSPy 签名：

```yaml
agents:
  executor:
    signature: "goal -> answer: str, confidence: float"
```

**注意**：大多数用户不需要此项。请改用 `signature_instructions`。

---

## 配置示例

ROMA-DSPy 在 `config/examples/` 中包含全面的配置示例。这些是真实的、可工作的配置，演示了不同的概念和模式。

### 可用示例

#### 基础示例 (`config/examples/basic/`)

| 示例 | 描述 | 使用方法 |
|------|------|----------|
| **minimal.yaml** | 最简单的可能配置 | `just solve "task" -c config/examples/basic/minimal.yaml` |
| **multi_toolkit.yaml** | 多工具箱 (E2B + File + Calculator) | `just solve "task" -c config/examples/basic/multi_toolkit.yaml` |

**演示**：基础知识、工具箱使用、基本配置模式

#### MCP 示例 (`config/examples/mcp/`)

| 示例 | 描述 | 使用方法 |
|------|------|----------|
| **http_public_server.yaml** | 公共 HTTP MCP 服务器 (CoinGecko) - 无需设置 | `just solve "task" -c config/examples/mcp/http_public_server.yaml` |
| **stdio_local_server.yaml** | 通过 npx 的本地 stdio MCP 服务器 | `just solve "task" -c config/examples/mcp/stdio_local_server.yaml` |
| **multi_server.yaml** | 多个 MCP 服务器 (HTTP + stdio) | `just solve "task" -c config/examples/mcp/multi_server.yaml` |
| **common_servers.yaml** | 常见 MCP 服务器 (GitHub, Filesystem, SQLite) | `just solve "task" -c config/examples/mcp/common_servers.yaml` |

**演示**：HTTP vs stdio MCP 服务器、多服务器编排、存储配置

#### 加密示例 (`config/examples/crypto/`)

| 示例 | 描述 | 使用方法 |
|------|------|----------|
| **crypto_agent.yaml** | 现实世界的加密分析智能体 | `just solve "task" -c config/examples/crypto/crypto_agent.yaml` |

**演示**：特定领域智能体、结合 MCP + 原生工具箱、多源数据聚合

#### 高级示例 (`config/examples/advanced/`)

| 示例 | 描述 | 使用方法 |
|------|------|----------|
| **task_aware_mapping.yaml** | 任务特定执行器配置 | `just solve "task" -c config/examples/advanced/task_aware_mapping.yaml` |
| **custom_prompts.yaml** | 自定义提示词和演示 | `just solve "task" -c config/examples/advanced/custom_prompts.yaml` |

**演示**：任务感知智能体映射、每种任务类型的成本/质量优化、加载自定义签名指令和演示

### 快速参考

```bash
# 使用 profile (推荐)
just solve "task" general

# 使用示例配置
just solve "task" -c config/examples/basic/minimal.yaml

# 带 CLI 参数
uv run python -m roma_dspy.cli solve "task" \
  --config config/examples/basic/minimal.yaml \
  --override runtime.max_depth=1
```

### 示例结构

每个示例包括：
- 解释每个部分的**内联注释**
- **设置要求** (API 密钥, npm 包)
- 展示如何运行的**用法示例**
- 关于示例演示内容的**关键学习点**

### 详细指南

查看 **[config/examples/README.md](../config/examples/README.md)** 获取：
- 完整的示例目录结构
- 每个示例的详细描述
- 设置说明
- 常见问题和解决方案
- 成功技巧

---

## 最佳实践

### 1. 从简单开始

```yaml
# 从最小配置开始
agents:
  executor:
    llm:
      model: openrouter/anthropic/claude-sonnet-4.5
    prediction_strategy: react
    toolkits:
      - class_name: FileToolkit
        enabled: true

runtime:
  max_depth: 1  # 从 1 开始，如果需要则增加
```

仅在需要时增加复杂性。

### 2. 使用 Profiles

不要从头开始创建配置。从 profile 开始：

```bash
# 使用现有 profile
just solve "task" general

# 或复制并自定义
cp config/profiles/general.yaml config/profiles/my_profile.yaml
# 编辑 my_profile.yaml
just solve "task" my_profile
```

### 3. 使用环境变量存储机密

切勿在配置文件中硬编码 API 密钥：

```yaml
# ❌ 错误
headers:
  Authorization: Bearer sk-1234567890

# ✅ 正确
headers:
  Authorization: Bearer ${oc.env:EXA_API_KEY}
```

### 4. 优化 max_depth

**大多数任务需要 max_depth=1 或 2**：

- 从 1 开始
- 如果任务需要分解，增加到 2
- 仅对复杂分层任务使用 3+
- 更高的深度 = 更慢 + 更昂贵

### 5. 用于成本优化的任务感知映射

对简单任务使用便宜模型：

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

### 6. 启用缓存

```yaml
agents:
  executor:
    llm:
      cache: true  # 启用 DSPy 缓存

runtime:
  cache:
    enabled: true
    enable_disk_cache: true
```

省钱并提高速度。

### 7. 对大数据使用存储

```yaml
toolkits:
  - class_name: MCPToolkit
    toolkit_config:
      use_storage: true
      storage_threshold_kb: 10  # 存储 > 10KB 的结果
```

防止上下文溢出。

### 8. 使用 MLflow 监控

```yaml
observability:
  mlflow:
    enabled: true
    log_traces: true
```

跟踪性能、成本和错误。

### 9. 配置弹性

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

从故障中自动恢复。

### 10. 验证配置

```python
from roma_dspy.config.manager import ConfigManager

# 使用前验证
try:
    config = ConfigManager().load_config(profile="my_profile")
    print("✅ 配置有效")
except ValueError as e:
    print(f"❌ 配置无效: {e}")
```

---

## 下一步

- **[QUICKSTART.md](QUICKSTART.md)** - 快速开始
- **[TOOLKITS.md](TOOLKITS.md)** - 完整工具箱参考
- **[MCP.md](MCP.md)** - MCP 集成指南
- **[API.md](API.md)** - REST API 参考
- **[DEPLOYMENT.md](DEPLOYMENT.md)** - 生产部署
- **示例**: `config/examples/` - 真实世界示例

---

**有问题？** 查看 `config/examples/` 中的示例或在 GitHub 上创建 issue。

