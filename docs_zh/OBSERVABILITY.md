# 可观察性与监控

ROMA-DSPy 通过 MLflow 集成提供全面的可观察性，支持实验跟踪、指标记录和执行追踪。

## 概览

可观察性系统捕获：
- **执行追踪** - 任务分解和执行流程
- **LLM 指标** - 每次 LLM 调用的 Token 使用量、成本和延迟
- **性能指标** - 任务持续时间、深度和成功率
- **编译工件** - 优化后的提示词和 Few-shot 示例

## MLflow 集成

### 配置

在配置中启用 MLflow 跟踪：

```yaml
# config/defaults/config.yaml
observability:
  mlflow:
    enabled: true
    tracking_uri: "http://127.0.0.1:5000"  # 本地 MLflow 服务器
    experiment_name: "ROMA-DSPy"
    log_traces: true
    log_compiles: true
    log_evals: true
    log_traces_from_compile: false  # 开销较大，默认禁用
```

或通过环境变量：

```bash
export MLFLOW_ENABLED=true
export MLFLOW_TRACKING_URI=http://127.0.0.1:5000
export MLFLOW_EXPERIMENT=ROMA-DSPy
```

### 启动 MLflow 服务器

```bash
# 启动 MLflow UI
mlflow ui --port 5000

# 或指定后端存储
mlflow ui --backend-store-uri sqlite:///mlflow.db --port 5000
```

访问 UI：http://localhost:5000

## 记录内容

### 1. 运行级指标

每次求解器 (Solver) 执行都会创建一个 MLflow 运行，包含：

**参数：**
- `task` - 原始目标/任务
- `max_depth` - 最大分解深度
- `config_version` - 配置版本
- `solver_type` - RecursiveSolver 标识符

**指标：**
- `total_tasks` - 创建的任务总数
- `completed_tasks` - 成功完成的任务数
- `failed_tasks` - 失败的任务数
- `total_cost` - LLM API 总成本 (USD)
- `total_tokens` - 消耗的总 Token 数
- `execution_duration` - 总执行时间 (秒)
- `max_depth_reached` - 实际达到的最大深度

### 2. LLM 追踪

对于每次语言模型调用：

**记录信息：**
- 模块名称 (atomizer, planner, executor 等)
- 模型标识符 (gpt-4, claude-3 等)
- Token 使用量 (prompt, completion, total)
- 成本明细
- 延迟 (毫秒)
- 输入/输出 (如果启用)

**每模块指标：**
- `{module}_calls` - 调用次数
- `{module}_tokens` - 总 Token 数
- `{module}_cost` - 总成本
- `{module}_avg_latency` - 平均延迟

### 3. 编译工件

使用 DSPy 优化时：

- 编译后的预测器签名
- Few-shot 示例
- 优化指标
- 提示词模版

## 使用示例

### 基本用法

```python
from roma_dspy.config.manager import ConfigManager
from roma_dspy.core.engine.solve import RecursiveSolver

# 加载启用 MLflow 的配置
config = ConfigManager(profile="high_quality").get_config()
config.observability.mlflow.enabled = True

# 创建求解器
solver = RecursiveSolver(config=config)

# 解决任务 - 自动记录到 MLflow
result = await solver.async_solve("规划巴塞罗那周末游")
```

### 自定义实验名称

```python
config.observability.mlflow.experiment_name = "Barcelona-Planning-v2"
solver = RecursiveSolver(config=config)
```

### 程序化访问

```python
from roma_dspy.observability.mlflow_manager import MLflowManager

# 初始化
mlflow_mgr = MLflowManager(config.observability.mlflow)
await mlflow_mgr.initialize()

# 开始运行
run_id = await mlflow_mgr.start_run(
    run_name="custom-run",
    tags={"version": "1.0", "experiment_type": "production"}
)

# 记录指标
await mlflow_mgr.log_metric("custom_metric", 42.0)
await mlflow_mgr.log_param("custom_param", "value")

# 结束运行
await mlflow_mgr.end_run(status="FINISHED")
```

## 查询 MLflow 数据

### 使用 MLflow UI

1. 访问 http://localhost:5000
2. 选择您的实验
3. 比较运行、查看指标、下载工件

### 使用 MLflow API

```python
import mlflow

# 设置跟踪 URI
mlflow.set_tracking_uri("http://localhost:5000")

# 搜索运行
runs = mlflow.search_runs(
    experiment_names=["ROMA-DSPy"],
    filter_string="metrics.total_cost < 1.0",
    order_by=["metrics.execution_duration ASC"]
)

# 获取最佳运行
best_run = runs.sort_values("metrics.total_cost").iloc[0]
print(f"最佳运行: {best_run.run_id}")
print(f"成本: ${best_run['metrics.total_cost']:.4f}")
```

### 分析成本

```python
# 获取所有运行
runs = mlflow.search_runs(experiment_names=["ROMA-DSPy"])

# 成本分析
total_cost = runs["metrics.total_cost"].sum()
avg_cost = runs["metrics.total_cost"].mean()
cost_by_depth = runs.groupby("params.max_depth")["metrics.total_cost"].mean()

print(f"总花费: ${total_cost:.2f}")
print(f"平均单次花费: ${avg_cost:.4f}")
print("\n按深度划分的成本:")
print(cost_by_depth)
```

## 成本跟踪

### Token 成本

ROMA-DSPy 跟踪常见 LLM 提供商的成本：

- **OpenAI**: gpt-4, gpt-3.5-turbo 等
- **Anthropic**: claude-3-opus, claude-3-sonnet 等
- **Fireworks AI**: 各种模型
- **OpenRouter**: 透传定价

成本计算公式：
```python
cost = (prompt_tokens * prompt_price_per_1k / 1000) +
       (completion_tokens * completion_price_per_1k / 1000)
```

### 成本优化

监控这些指标以优化成本：

1. **每任务 Token 数** - 识别冗长的模块
2. **失败任务成本** - 浪费在失败上的花费
3. **模型选择** - 比较不同模型的成本
4. **深度 vs 成本** - 找到最佳分解深度

## 性能监控

### 关键指标

**延迟：**
- 总执行时间
- 每模块延迟
- LLM 调用延迟

**吞吐量：**
- 每分钟任务数
- 每次分解的子任务数
- 成功率

**资源使用：**
- Token 消耗率
- 每任务 API 调用数
- 检查点频率

### 告警与阈值

设置告警：

```python
# 高成本运行
if run.metrics.total_cost > 5.0:
    alert("检测到高成本运行")

# 执行缓慢
if run.metrics.execution_duration > 300:
    alert("执行缓慢")

# 高失败率
failure_rate = run.metrics.failed_tasks / run.metrics.total_tasks
if failure_rate > 0.2:
    alert("高失败率")
```

## 与 Postgres 集成

当同时启用 MLflow 和 Postgres 时，您将获得双重可观察性：

**MLflow**: 实验跟踪、可视化、比较
**Postgres**: 详细执行追踪、可查询历史、审计日志

```python
# 查询两个源
import mlflow
from roma_dspy.core.storage.postgres_storage import PostgresStorage

# MLflow - 高级指标
runs = mlflow.search_runs(experiment_names=["ROMA-DSPy"])

# Postgres - 详细追踪
storage = PostgresStorage(config.storage.postgres)
await storage.initialize()

for _, run in runs.iterrows():
    execution_id = run["tags.execution_id"]
    costs = await storage.get_execution_costs(execution_id)
    print(f"Run {execution_id}: ${costs['total_cost']:.4f}")
```

## 最佳实践

1. **使用描述性实验名称** - 按项目/功能组织
2. **适当标记运行** - 添加版本、环境、用户标签
3. **定期监控成本** - 设置成本告警
4. **归档旧实验** - 保持 MLflow 数据库可管理
5. **生产环境禁用昂贵日志** - `log_traces_from_compile: false`
6. **使用远程跟踪服务器** - 用于团队协作
7. **备份 MLflow 数据** - 尤其是工件存储

## 故障排除

### MLflow 连接问题

```bash
# 检查服务器是否运行
curl http://localhost:5000/health

# 检查环境变量
echo $MLFLOW_TRACKING_URI

# 测试连接
python -c "import mlflow; print(mlflow.get_tracking_uri())"
```

### 缺少指标

```python
# 验证日志已启用
print(config.observability.mlflow.enabled)
print(config.observability.mlflow.log_traces)

# 检查 MLflow 管理器初始化
print(solver.mlflow_manager._initialized)
```

### 存储占用高

```bash
# 检查工件存储大小
du -sh ~/.mlflow

# 清理旧运行 (谨慎使用)
mlflow gc --backend-store-uri sqlite:///mlflow.db
```

## 高级主题

### 自定义指标

```python
# 添加自定义指标到 MLflow
async with solver.mlflow_manager.run_context():
    await solver.mlflow_manager.log_metric("custom_score", score)
    await solver.mlflow_manager.log_param("algorithm", "custom")
```

### 分布式跟踪

对于多机设置：

```yaml
observability:
  mlflow:
    tracking_uri: "http://mlflow-server.company.com:5000"
    # 使用 S3/GCS 存储工件
    artifact_location: "s3://my-bucket/mlflow-artifacts"
```

### 与其他工具集成

MLflow 集成：
- **Prometheus** - 运维指标
- **Grafana** - 仪表盘
- **Databricks** - 托管 MLflow
- **Weights & Biases** - 通过导出器

## 工具箱指标与可追溯性

ROMA-DSPy 提供全面的工具箱生命周期和工具调用指标跟踪，能够深入了解工具使用模式、性能和可靠性。

### 概览

工具箱指标系统自动跟踪：
- **工具箱生命周期** - 创建、缓存、清理操作
- **工具调用** - 包含计时和 I/O 指标的单个工具调用
- **性能** - 持续时间、成功率、错误模式
- **归因** - 每个工具箱/工具的成本和使用情况

### 配置

启用工具箱指标跟踪：

```yaml
# config/defaults/config.yaml
observability:
  toolkit_metrics:
    enabled: true                    # 启用/禁用跟踪
    track_lifecycle: true            # 跟踪工具箱操作
    track_invocations: true          # 跟踪工具调用
    sample_rate: 1.0                 # 采样率 (0.0-1.0)
    persist_to_db: true              # 保存到 PostgreSQL
    persist_to_mlflow: false         # 保存到 MLflow
    batch_size: 100                  # 持久化批次大小
    async_persist: true              # 异步持久化
```

或通过环境变量：

```bash
export TOOLKIT_METRICS_ENABLED=true
export TOOLKIT_TRACK_LIFECYCLE=true
export TOOLKIT_TRACK_INVOCATIONS=true
export TOOLKIT_SAMPLE_RATE=1.0
export TOOLKIT_PERSIST_DB=true
```

### 跟踪内容

#### 1. 工具箱生命周期事件

**跟踪的操作：**
- `create` - 工具箱实例化
- `cache_hit` - 从缓存检索
- `cache_miss` - 缓存查找失败
- `cleanup` - 工具箱处置

**捕获数据：**
- 操作时间戳
- 工具箱类名
- 持续时间 (毫秒)
- 成功/失败状态
- 错误详情 (如果失败)
- 自定义元数据

#### 2. 工具调用事件

**每次调用的跟踪：**
- 工具名称和工具箱类
- 调用时间戳
- 持续时间 (毫秒)
- 输入大小 (字节)
- 输出大小 (字节)
- 成功/失败状态
- 错误详情 (如果失败)
- 自定义元数据

### API 端点

通过 REST API 查询工具箱指标：

#### 获取聚合摘要

```bash
curl http://localhost:8000/executions/{execution_id}/toolkit-metrics
```

**响应：**
```json
{
  "execution_id": "exec_123",
  "toolkit_lifecycle": {
    "total_created": 5,
    "cache_hit_rate": 0.75
  },
  "tool_invocations": {
    "total_calls": 50,
    "successful_calls": 48,
    "failed_calls": 2,
    "success_rate": 0.96,
    "avg_duration_ms": 125.5,
    "total_duration_ms": 6275.0
  },
  "by_toolkit": {
    "SerperToolkit": {
      "calls": 20,
      "successful": 20,
      "failed": 0,
      "avg_duration_ms": 150.0
    }
  },
  "by_tool": {
    "SerperToolkit.search_web": {
      "calls": 15,
      "successful": 15,
      "avg_duration_ms": 145.0
    }
  }
}
```

#### 获取原始生命周期追踪

```bash
# 所有生命周期追踪
curl http://localhost:8000/executions/{execution_id}/toolkit-traces

# 按操作过滤
curl http://localhost:8000/executions/{execution_id}/toolkit-traces?operation=create

# 按工具箱类过滤
curl http://localhost:8000/executions/{execution_id}/toolkit-traces?toolkit_class=SerperToolkit

# 限制结果
curl http://localhost:8000/executions/{execution_id}/toolkit-traces?limit=100
```

#### 获取原始工具调用

```bash
# 所有工具调用
curl http://localhost:8000/executions/{execution_id}/tool-invocations

# 按工具箱过滤
curl http://localhost:8000/executions/{execution_id}/tool-invocations?toolkit_class=SerperToolkit

# 按工具名称过滤
curl http://localhost:8000/executions/{execution_id}/tool-invocations?tool_name=search_web

# 组合过滤
curl http://localhost:8000/executions/{execution_id}/tool-invocations?toolkit_class=SerperToolkit&tool_name=search_web
```

### 数据库架构

#### toolkit_traces 表

```sql
CREATE TABLE toolkit_traces (
    trace_id BIGSERIAL PRIMARY KEY,
    execution_id VARCHAR(64) NOT NULL,
    timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
    operation VARCHAR(32) NOT NULL,
    toolkit_class VARCHAR(128),
    duration_ms FLOAT NOT NULL,
    success BOOLEAN NOT NULL,
    error TEXT,
    metadata JSONB NOT NULL DEFAULT '{}',
    FOREIGN KEY (execution_id) REFERENCES executions(execution_id) ON DELETE CASCADE
);

-- Indexes for query performance
CREATE INDEX idx_toolkit_traces_execution ON toolkit_traces (execution_id, timestamp);
CREATE INDEX idx_toolkit_traces_operation ON toolkit_traces (operation);
CREATE INDEX idx_toolkit_traces_toolkit_class ON toolkit_traces (toolkit_class);
CREATE INDEX idx_toolkit_traces_success ON toolkit_traces (success);
```

#### tool_invocation_traces 表

```sql
CREATE TABLE tool_invocation_traces (
    trace_id BIGSERIAL PRIMARY KEY,
    execution_id VARCHAR(64) NOT NULL,
    toolkit_class VARCHAR(128) NOT NULL,
    tool_name VARCHAR(128) NOT NULL,
    invoked_at TIMESTAMP WITH TIME ZONE NOT NULL,
    duration_ms FLOAT NOT NULL,
    input_size_bytes INTEGER NOT NULL,
    output_size_bytes INTEGER NOT NULL,
    success BOOLEAN NOT NULL,
    error TEXT,
    metadata JSONB NOT NULL DEFAULT '{}',
    FOREIGN KEY (execution_id) REFERENCES executions(execution_id) ON DELETE CASCADE
);

-- Indexes for query performance
CREATE INDEX idx_tool_invocations_execution ON tool_invocation_traces (execution_id, invoked_at);
CREATE INDEX idx_tool_invocations_toolkit ON tool_invocation_traces (toolkit_class);
CREATE INDEX idx_tool_invocations_tool ON tool_invocation_traces (tool_name);
CREATE INDEX idx_tool_invocations_toolkit_tool ON tool_invocation_traces (toolkit_class, tool_name);
CREATE INDEX idx_tool_invocations_success ON tool_invocation_traces (success);
```

### 数据库迁移

应用迁移以创建工具箱指标表：

```bash
# 导航到项目根目录
cd /path/to/ROMA-DSPy

# 运行迁移
alembic upgrade head
```

或手动：

```bash
# 检查当前版本
alembic current

# 升级到工具箱指标迁移
alembic upgrade 004_toolkit_metrics

# 如果需要回滚
alembic downgrade 003_add_dag_snapshot
```

### 使用示例

#### 分析工具箱性能

```python
from roma_dspy.core.storage.postgres_storage import PostgresStorage

# 获取工具箱指标摘要
summary = await storage.get_toolkit_metrics_summary("exec_123")

print(f"总工具调用数: {summary['tool_invocations']['total_calls']}")
print(f"成功率: {summary['tool_invocations']['success_rate']:.2%}")
print(f"平均持续时间: {summary['tool_invocations']['avg_duration_ms']:.2f}ms")

# 按工具箱分析
for toolkit, metrics in summary['by_toolkit'].items():
    print(f"\n{toolkit}:")
    print(f"  调用数: {metrics['calls']}")
    print(f"  成功率: {metrics['successful'] / metrics['calls']:.2%}")
    print(f"  平均持续时间: {metrics['avg_duration_ms']:.2f}ms")
```

#### 识别慢速工具

```python
# 获取所有工具调用
invocations = await storage.get_tool_invocation_traces("exec_123")

# 按持续时间排序
slow_tools = sorted(invocations, key=lambda x: x.duration_ms, reverse=True)[:10]

print("最慢的 10 个工具调用:")
for inv in slow_tools:
    print(f"{inv.toolkit_class}.{inv.tool_name}: {inv.duration_ms:.2f}ms")
```

#### 跟踪失败

```python
# 获取失败的工具调用
failed = await storage.get_tool_invocation_traces(
    execution_id="exec_123",
    limit=1000
)
failed = [inv for inv in failed if not inv.success]

# 按错误类型分组
from collections import Counter
error_types = Counter(inv.metadata.get('error_type', 'Unknown') for inv in failed)

print("失败分类:")
for error_type, count in error_types.most_common():
    print(f"  {error_type}: {count}")
```

#### 缓存性能分析

```python
# 获取生命周期追踪
traces = await storage.get_toolkit_traces("exec_123")

# 计算缓存指标
cache_hits = sum(1 for t in traces if t.operation == "cache_hit")
cache_misses = sum(1 for t in traces if t.operation == "cache_miss")
total = cache_hits + cache_misses

if total > 0:
    hit_rate = cache_hits / total
    print(f"缓存命中率: {hit_rate:.2%}")
    print(f"缓存命中: {cache_hits}")
    print(f"缓存未命中: {cache_misses}")
```

### 监控与告警

#### 需监控的关键指标

1. **成功率** - 低于 95% 时告警
2. **平均持续时间** - 显著增加时告警
3. **错误率** - 激增时告警
4. **缓存命中率** - 显著下降时告警

#### Prometheus 查询示例

```promql
# 按工具箱的成功率
sum(rate(tool_invocations_success_total[5m])) by (toolkit_class)
/
sum(rate(tool_invocations_total[5m])) by (toolkit_class)

# P95 延迟
histogram_quantile(0.95, sum(rate(tool_duration_ms_bucket[5m])) by (le, tool_name))

# 错误率
sum(rate(tool_invocations_failed_total[5m])) by (toolkit_class, error_type)
```

### 性能调优

#### 减少存储开销

```yaml
# 在高容量环境中仅采样 10% 的调用
observability:
  toolkit_metrics:
    sample_rate: 0.1
```

#### 批量持久化

```yaml
# 增加批量大小以提高写入性能
observability:
  toolkit_metrics:
    batch_size: 500
    async_persist: true
```

#### 禁用特定跟踪

```yaml
# 仅跟踪生命周期，跳过调用
observability:
  toolkit_metrics:
    track_lifecycle: true
    track_invocations: false
```

### 故障排除

#### 指标未出现

1. **检查 PostgreSQL 是否启用:**
   ```yaml
   storage:
     postgres:
       enabled: true
   ```

2. **验证迁移已应用:**
   ```bash
   alembic current
   # 应显示: 004_toolkit_metrics (head)
   ```

3. **检查配置:**
   ```python
   print(config.observability.toolkit_metrics.enabled)
   print(config.observability.toolkit_metrics.persist_to_db)
   ```

#### 高存储使用率

```sql
-- 检查表大小
SELECT
    schemaname,
    tablename,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size
FROM pg_tables
WHERE tablename LIKE '%trace%'
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;

-- 清理旧执行 (小心!)
DELETE FROM executions WHERE created_at < NOW() - INTERVAL '30 days';
```

#### 缺少追踪

```python
# 检查 context 是否正确设置
from roma_dspy.core.context import ExecutionContext

ctx = ExecutionContext.get()
if ctx:
    print(f"Execution ID: {ctx.execution_id}")
    print(f"Toolkit events: {len(ctx.toolkit_events)}")
    print(f"Tool invocations: {len(ctx.tool_invocations)}")
else:
    print("No ExecutionContext found!")
```

### 最佳实践

1. **开发环境启用** - 使用全量跟踪 (sample_rate=1.0)
2. **生产环境采样** - 对于高容量系统使用较低的采样率
3. **监控关键指标** - 设置成功率和延迟告警
4. **定期清理** - 归档或删除旧的执行数据
5. **索引管理** - 监控索引大小和查询性能
6. **关联 LM 追踪** - 结合 LM 指标进行成本归因

### 与 MLflow 集成

```python
# 将工具箱指标记录到 MLflow
from roma_dspy.core.observability import MLflowManager

async with mlflow_manager.run_context():
    summary = await storage.get_toolkit_metrics_summary(execution_id)

    # 记录聚合指标
    await mlflow_manager.log_metric(
        "toolkit_success_rate",
        summary["tool_invocations"]["success_rate"]
    )
    await mlflow_manager.log_metric(
        "avg_tool_duration_ms",
        summary["tool_invocations"]["avg_duration_ms"]
    )

    # 记录每工具箱指标
    for toolkit, metrics in summary["by_toolkit"].items():
        await mlflow_manager.log_metric(
            f"{toolkit}_calls",
            metrics["calls"]
        )
```

## 延伸阅读

- [MLflow 文档](https://mlflow.org/docs/latest/index.html)
- [MLflow 跟踪指南](https://mlflow.org/docs/latest/tracking.html)
- [DSPy 可观察性](https://dspy-docs.vercel.app/)
- [PostgreSQL 性能调优](https://www.postgresql.org/docs/current/performance-tips.html)

