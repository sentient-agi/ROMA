# ROMA-DSPy 快速入门指南

无需任何基础设施，**30秒内**即可开始！

## ROMA-DSPy 是什么？

ROMA-DSPy 是一个使用 [DSPy](https://github.com/stanfordnlp/dspy) 构建生产级 AI 智能体的框架。它提供：

- **分层任务分解** - 将复杂任务拆解为可管理的子任务
- **模块化智能体架构** - Atomizer（原子化器）、Planner（规划器）、Executor（执行器）、Aggregator（聚合器）、Verifier（验证器）
- **丰富的工具箱系统** - 文件操作、代码执行、Web 搜索、加密数据等
- **MCP 集成** - 连接任何模型上下文协议 (Model Context Protocol) 服务器
- **可选的生产特性** - REST API、PostgreSQL 持久化、MLflow 可观察性、Docker 部署

## 先决条件

### 极简安装（推荐）
- **Python 3.12+**
- 来自 OpenRouter, OpenAI, Anthropic, 或 Fireworks 的 **API 密钥**

### 完整安装（可选）
- **Docker & Docker Compose**（用于生产特性）
- **Just** 命令运行器（可选但推荐）

---

## 快速开始（3条路径）

选择您首选的设置方法：

### 路径 A：极简安装（推荐 - 30秒启动）

**最适合**：快速评估、开发、测试 - 无需基础设施

**您将获得：**
- ✅ 核心智能体框架（所有模块）
- ✅ 所有 DSPy 预测策略
- ✅ 文件存储（无需数据库）
- ✅ 内置工具箱（计算器、文件操作）
- ✅ 支持任何 LLM 提供商

**您不需要：**
- ❌ Docker
- ❌ PostgreSQL
- ❌ MLflow
- ❌ 基础设施设置

**30秒内安装：**

```bash
# 使用 uv 安装 (推荐，速度快 10-100 倍)
uv pip install roma-dspy

# 或使用 pip
pip install roma-dspy

# 设置您的 API 密钥
export OPENROUTER_API_KEY="sk-or-v1-..."

# 立即开始解决任务
python -c "from roma_dspy.core.engine.solve import solve; print(solve('2+2 是多少？'))"
```

**Python 使用示例：**

```python
from roma_dspy.core.engine.solve import solve

# 简单任务
result = solve("25 * 47 是多少？")
print(result)

# 更复杂的任务
result = solve("分析电动汽车的优缺点")
print(result)
```

**安装时间**：< 30秒  
**包大小**：~15 个核心依赖  
**就绪状态**：立即使用

---

### 路径 B：Docker 完整安装（生产特性）

**最适合**：具有持久化、可观察性和 REST API 的生产部署

**额外特性：**
- ✅ REST API 服务器
- ✅ PostgreSQL 持久化
- ✅ MLflow 可观察性
- ✅ S3 存储集成
- ✅ E2B 代码执行沙箱
- ✅ 交互式 TUI 可视化

1. **克隆并配置**
   ```bash
   git clone https://github.com/your-org/ROMA-DSPy.git
   cd ROMA-DSPy

   # 复制环境模版
   cp .env.example .env
   ```

2. **配置环境**
   编辑 `.env` 并添加您的 API 密钥：
   ```bash
   # 必填
   OPENROUTER_API_KEY=your_key_here

   # 可选（用于特定功能）
   E2B_API_KEY=your_key_here
   EXA_API_KEY=your_key_here
   ```

3. **启动服务**
   ```bash
   # 构建并启动所有服务
   just docker-up

   # 或者带 MLflow 可观察性启动
   just docker-up-full

   # 检查健康状态
   curl http://localhost:8000/health
   ```

4. **运行您的第一个任务**
   ```bash
   # 通过 Docker CLI
   just solve "法国的首都是哪里？"

   # 或通过 REST API
   curl -X POST http://localhost:8000/api/v1/executions \
     -H "Content-Type: application/json" \
     -d '{"goal": "法国的首都是哪里？"}'
   ```

**运行的服务：**
- API: http://localhost:8000
- PostgreSQL: localhost:5432
- MinIO: http://localhost:9001
- MLflow: http://localhost:5000 (使用 `--profile observability`)

---

### 路径 C：加密货币代理（领域特定示例）

**最适合**：加密货币分析用例

1. **快速设置**
   ```bash
   just docker-up
   ```

2. **运行加密分析**
   ```bash
   # 获取比特币价格
   just solve "比特币当前价格是多少？" crypto_agent

   # 复杂分析
   just solve "对比比特币和以太坊的价格，分析7天趋势" crypto_agent

   # DeFi 分析
   just solve "显示按 TVL 排名的前 10 个 DeFi 协议" crypto_agent
   ```

**加密货币代理包含：**
- CoinGecko (15,000+ 加密货币)
- Binance (现货/期货市场)
- DefiLlama (DeFi 协议数据)
- Arkham (链上分析)
- Exa (Web 搜索)

---

## 安装对比

| 特性 | 极简安装 | Docker 完整版 |
|------|---------|-------------|
| **安装时间** | < 30 秒 | 2-5 分钟 |
| **先决条件** | Python 3.12+ | Docker + Docker Compose |
| **基础设施** | 无需 | PostgreSQL, MinIO, MLflow (自动部署) |
| **包大小** | ~15 依赖 | 所有功能 |
| **用例** | 快速评估, 开发, 测试 | 生产部署 |
| **核心框架** | ✅ | ✅ |
| **DSPy 策略** | ✅ | ✅ |
| **文件存储** | ✅ | ✅ |
| **内置工具箱** | ✅ | ✅ |
| **REST API** | ❌ | ✅ |
| **PostgreSQL 持久化** | ❌ | ✅ |
| **MLflow 跟踪** | ❌ | ✅ |
| **S3 存储** | ❌ | ✅ |
| **E2B 沙箱** | ❌ | ✅ |
| **TUI 可视化** | ❌ | ✅ |

**关键区别**：
- **极简** = 仅 Python 包（无 Docker，无服务）
- **Docker** = 完整生产栈（PostgreSQL, MLflow, API，通过 docker-compose 提供所有功能）

---

## 为极简安装添加功能

您可以安装 Python 依赖以获取可选功能：

```bash
# 为特定功能安装依赖
uv pip install roma-dspy[api]          # REST API 依赖
uv pip install roma-dspy[persistence]  # PostgreSQL 客户端依赖
uv pip install roma-dspy[observability] # MLflow 客户端依赖
uv pip install roma-dspy[e2b]          # E2B 代码执行
uv pip install roma-dspy[tui]          # TUI 可视化
uv pip install roma-dspy[dev]          # 开发工具

# 安装所有 Python 依赖
uv pip install roma-dspy[all]
```

**重要**：安装 extras 仅添加 Python 依赖。PostgreSQL、MLflow 和 API 服务器等服务需要 Docker 或单独部署。

**如需使用所有功能的生产环境，请使用 Docker (路径 B)**。

---

## Just 命令速查表

### 基本用法
```bash
just                      # 列出所有命令
just solve "task"         # 使用 Docker 解决任务
just viz <execution_id>   # 可视化执行 DAG
```

### Docker 管理
```bash
just docker-up            # 启动服务
just docker-up-full       # 启动并开启 MLflow
just docker-down          # 停止服务
just docker-logs          # 查看日志
just docker-ps            # 检查状态
just docker-shell         # 在容器中打开 shell
```

### 开发
```bash
just install              # 安装依赖
just test                 # 运行测试
just lint                 # 检查代码质量
just format               # 格式化代码
just clean                # 清理缓存
```

### 列出可用 Profiles
```bash
just list-profiles
# 输出:
#   - crypto_agent
#   - general
```

---

## 验证安装

### 1. 检查健康状态
```bash
curl http://localhost:8000/health
```

预期响应：
```json
{
  "status": "healthy",
  "version": "1.0.0",
  "storage_connected": true,
  "active_executions": 0,
  "uptime_seconds": 123.45
}
```

### 2. 通过 CLI 测试
```bash
# 简单计算
just solve "计算 2500 的 15%"

# 从输出中获取 execution ID，然后可视化
just viz <execution_id>
```

### 3. 通过 API 测试
```bash
# 创建执行 (建议 max_depth=1 或 2)
curl -X POST http://localhost:8000/api/v1/executions \
  -H "Content-Type: application/json" \
  -d '{
    "goal": "1 到 20 之间的质数有哪些？",
    "max_depth": 2
  }' | jq

# 轮询状态 (使用响应中的 execution_id)
curl http://localhost:8000/api/v1/executions/<execution_id>/status | jq
```

---

## 配置 Profiles

ROMA-DSPy 使用 profiles 为不同用例预配置智能体。

### 可用 Profiles

| Profile | 用途 | 模型 | 工具箱 |
|---------|------|------|--------|
| **general** | 通用任务 | Gemini Flash + Claude Sonnet | E2B, FileToolkit, CalculatorToolkit, Exa MCP |
| **crypto_agent** | 加密货币分析 | 多种 (任务感知) | CoinGecko, Binance, DefiLlama, Arkham, E2B |

### 使用 Profile

```bash
# 通过 CLI (如未指定默认为 'general')
just solve "你的任务"
just solve "加密任务" crypto_agent

# 通过 API
curl -X POST http://localhost:8000/api/v1/executions \
  -H "Content-Type: application/json" \
  -d '{
    "goal": "你的任务",
    "config_profile": "general"
  }'
```

### 自定义 Profile

创建 `config/profiles/my_profile.yaml`:
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
  max_depth: 2  # 大多数任务建议 1-2
```

使用它：
```bash
just solve "task" my_profile
```

查看 [CONFIGURATION.md](CONFIGURATION.md) 获取完整指南。

---

## 环境变量

### 必填
```bash
# LLM 提供商 (选择一个或使用 OpenRouter 处理所有)
OPENROUTER_API_KEY=xxx        # 推荐 (所有模型共用一个 key)
# 或单独的提供商:
OPENAI_API_KEY=xxx
ANTHROPIC_API_KEY=xxx
GOOGLE_API_KEY=xxx
```

### 可选特性
```bash
# 代码执行 (E2B)
E2B_API_KEY=xxx

# Web 搜索 (Exa MCP)
EXA_API_KEY=xxx

# Web 搜索 (Serper Toolkit)
SERPER_API_KEY=xxx

# 加密 API (均为公开，无需 key)
# CoinGecko, Binance, DefiLlama, Arkham 无需 key 即可工作
```

### 存储与数据库
```bash
# PostgreSQL (Docker 中自动配置)
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/roma_dspy
POSTGRES_ENABLED=true

# S3 存储 (可选)
STORAGE_BASE_PATH=/opt/sentient
ROMA_S3_BUCKET=your-bucket
AWS_ACCESS_KEY_ID=xxx
AWS_SECRET_ACCESS_KEY=xxx
```

---

## 常见任务

### 1. 解决任务
```bash
# 简单 (默认使用 'general' profile)
just solve "2+2 是多少？"

# 使用特定 profile
just solve "分析比特币" crypto_agent

# 使用所有选项
just solve "复杂任务" crypto_agent 5 true json
# 参数: <task> [profile] [max_depth] [verbose] [output_format]
```

### 2. 检查执行
```bash
# 列出所有执行
curl http://localhost:8000/api/v1/executions | jq

# 获取特定执行
curl http://localhost:8000/api/v1/executions/<id> | jq

# 获取执行状态
curl http://localhost:8000/api/v1/executions/<id>/status | jq
```

### 3. 查看日志
```bash
# 所有服务
just docker-logs

# 特定服务
just docker-logs-service roma-api
just docker-logs-service postgres
just docker-logs-service mlflow
```

### 4. 交互式可视化
```bash
# 解决任务后，获取 execution_id
just solve "Complex task"

# 可视化执行树
just viz <execution_id>
```

---

## 示例

### 示例 1：简单计算
```bash
just solve "计算 10,000 美元本金、5% 年利率、10 年期的复利"
```

### 示例 2：Web 研究
```bash
just solve "研究量子计算的最新进展并总结为 3 个要点"
```

### 示例 3：代码执行
```bash
just solve "生成一个生成斐波那契数列至 100 的 Python 脚本，执行它并显示结果"
```

### 示例 4：加密分析
```bash
just solve "对比比特币和以太坊的市值、24小时交易量和价格变化" crypto_agent
```

### 示例 5：文件操作
```bash
just solve "创建一个包含前 5 种编程语言及其用例数据的 JSON 文件"
```

---

## 故障排除

### Docker 未启动
```bash
# 检查 Docker 是否运行
docker ps

# 重建镜像
just docker-down
just docker-build-clean
just docker-up

# 检查日志
just docker-logs
```

### API 无响应
```bash
# 检查健康
curl http://localhost:8000/health

# 检查容器状态
just docker-ps

# 查看日志
just docker-logs-service roma-api
```

### 数据库连接错误
```bash
# 检查 postgres 是否运行
docker ps | grep postgres

# 检查连接
docker exec -it roma-dspy-postgres psql -U postgres -d roma_dspy -c "SELECT 1"

# 验证 .env 中的 DATABASE_URL 是否匹配 docker-compose.yaml
```

### 缺少 API 密钥
```bash
# 验证密钥已设置
docker exec -it roma-dspy-api env | grep API_KEY

# 修改 .env 后重启
just docker-restart
```

### E2B 不工作
```bash
# 检查 E2B key 已设置
echo $E2B_API_KEY

# 测试 E2B 连接
just e2b-test

# 构建自定义模板 (如使用 S3 挂载)
just e2b-build
```

---

## 下一步

### 了解更多
- **[配置指南](CONFIGURATION.md)** - Profiles, agents, settings
- **[工具箱参考](TOOLKITS.md)** - 所有可用工具箱
- **[MCP 集成](MCP.md)** - 使用 MCP 服务器
- **[API 参考](API.md)** - REST API 端点
- **[部署指南](DEPLOYMENT.md)** - 生产部署
- **[可观察性](OBSERVABILITY.md)** - MLflow 跟踪

### 探索示例
```bash
# 查看所有示例配置
ls config/examples/*/

# 尝试不同示例
just solve "task" -c config/examples/basic/minimal.yaml
```

### 自定义
1. 在 `config/profiles/` 中创建自定义 profiles
2. 添加自定义工具箱 (参见 [TOOLKITS.md](TOOLKITS.md))
3. 按任务类型配置智能体 (参见 [CONFIGURATION.md](CONFIGURATION.md))

### 部署
```bash
# 生产部署
just deploy-full

# 检查部署
just health-check
```

---

## REST API

ROMA-DSPy 包含一个用于程序化访问的生产级 REST API。

### 快速开始

```bash
# 启动 API 服务器 (通过 Docker)
just docker-up

# 验证服务器运行
curl http://localhost:8000/health
```

### API 文档

FastAPI 提供交互式 API 文档：

- **Swagger UI** (交互式测试): http://localhost:8000/docs
- **ReDoc** (简洁参考): http://localhost:8000/redoc
- **OpenAPI JSON**: http://localhost:8000/openapi.json

### 示例用法

```bash
# 开始执行
curl -X POST http://localhost:8000/api/v1/executions \
  -H "Content-Type: application/json" \
  -d '{"goal": "2+2 是多少？", "max_depth": 1}' | jq

# 获取状态 (使用响应中的 execution_id)
curl http://localhost:8000/api/v1/executions/<execution_id>/status | jq

# 获取指标
curl http://localhost:8000/api/v1/executions/<execution_id>/metrics | jq
```

**访问 http://localhost:8000/docs 获取包含所有端点、模式和交互式测试的完整 API 参考。**

---

## 获取帮助

- **文档**: `docs/` 目录
- **示例**: `config/examples/`
- **Issues**: GitHub Issues
- **Just 命令**: 运行 `just` 查看所有可用命令

---

**一切就绪！** 开始使用 ROMA-DSPy 构建吧 🚀

