# 提示词优化 (Prompt Optimization)

基于 GEPA (Generative Expectation-Maximization Prompt Optimization with Adversarial Examples) 的模块化工具包，用于优化 ROMA-DSPy 提示词。

## 目录结构

```
prompt_optimization/
├── config.py              # 配置管理 (dataclasses)
├── datasets.py            # 数据集加载器 (AIMO, AIME)
├── solver_setup.py        # Solver 工厂与指令常量
├── judge.py              # 用于评估组件的 LLM 裁判
├── metrics/              # 指标实现 (基础, 搜索, 数字, 反馈)
│   ├── __init__.py
│   ├── base.py
│   ├── metric_with_feedback.py
│   ├── number_metric.py
│   └── search_metric.py
├── selectors.py          # 组件选择策略
├── optimizer.py          # GEPA 优化器工厂
└── run_optimization.py   # 主 CLI 脚本
```

## 快速开始

### 基本用法

```bash
# 使用默认值运行 (5 训练, 5 验证, 15 测试)
python -m prompt_optimization.run_optimization

# 自定义数据集大小
python -m prompt_optimization.run_optimization --train-size 10 --val-size 10 --test-size 30

# 使用不同的组件选择器
python -m prompt_optimization.run_optimization --selector round_robin

# 保存优化后的程序
python -m prompt_optimization.run_optimization --output optimized_solver.json

# 启用详细日志
python -m prompt_optimization.run_optimization --verbose
```

### 可用选择器 (Selectors)

- `planner_only` (默认) - 仅优化规划器 (planner) 组件
- `atomizer_only` - 仅优化原子化器 (atomizer) 组件
- `executor_only` - 仅优化执行器 (executor) 组件
- `aggregator_only` - 仅优化聚合器 (aggregator) 组件
- `round_robin` - 循环优化所有组件

### 编程方式使用

```python
from prompt_optimization import (
    get_default_config,
    load_aimo_datasets,
    create_solver_module,
    ComponentJudge,
    MetricWithFeedback,
    create_optimizer
)

# 加载配置
config = get_default_config()
config.train_size = 10
config.max_metric_calls = 20

# 加载数据集
train, val, test = load_aimo_datasets(
    train_size=config.train_size,
    val_size=config.val_size,
    test_size=config.test_size
)

# 创建 solver
solver = create_solver_module(config)

# 创建裁判和指标
judge = ComponentJudge(config.judge_lm)
# 包装评分指标 (如果省略，默认为基本整数比较)
metric = MetricWithFeedback(judge)

# 创建优化器
optimizer = create_optimizer(config, metric, component_selector="planner_only")

# 替代方案：插入自定义评分指标 (例如，搜索准确性)
# from prompt_optimization.metrics import NumberMetric
# metric = MetricWithFeedback(judge, scoring_metric=NumberMetric())

# 运行优化
optimized = optimizer.compile(solver, trainset=train, valset=val)
```

### 异步用法

裁判 (judge) 和指标 (metrics) 均支持异步执行以提高性能：

```python
import asyncio
from prompt_optimization import ComponentJudge, MetricWithFeedback, get_default_config

config = get_default_config()

# 创建裁判
judge = ComponentJudge(config.judge_lm)

# 同步用法
feedback = judge(
    component_name="planner",
    component_trace={"subtasks": [...], "dependencies_graph": {...}},
    prediction_trace="完整追踪..."
)

# 异步用法
async def evaluate_async():
    feedback = await judge.__acall__(
        component_name="planner",
        component_trace={"subtasks": [...], "dependencies_graph": {...}},
        prediction_trace="完整追踪..."
    )
    return feedback

# 运行异步
feedback = asyncio.run(evaluate_async())

# 指标也支持异步
metric = MetricWithFeedback(judge)

# 异步指标评估
async def evaluate_metric():
    result = await metric.aforward(
        example=example,
        prediction=prediction,
        pred_name="planner",
        pred_trace=trace
    )
    return result
```

## 配置

所有配置集中在 `config.py` 中。关键参数：

- **LM Configs**: 每个组件的模型名称、温度、最大 token 数
- **Dataset**: 训练/验证/测试集大小，随机种子
- **Execution**: 最大并行执行数，并发限制
- **GEPA**: 最大指标调用数，线程数，反思小批量 (minibatch) 大小
- **Solver**: 最大深度，日志设置

## CLI 选项

```
usage: run_optimization.py [-h] [--train-size TRAIN_SIZE] [--val-size VAL_SIZE]
                           [--test-size TEST_SIZE] [--max-parallel MAX_PARALLEL]
                           [--concurrency CONCURRENCY] [--max-metric-calls MAX_METRIC_CALLS]
                           [--num-threads NUM_THREADS]
                           [--selector {planner_only,atomizer_only,executor_only,aggregator_only,round_robin}]
                           [--output OUTPUT] [--verbose] [--skip-eval]
```

## 核心特性

- ✅ **无全局状态** - 所有组件均正确初始化并作为依赖项传递
- ✅ **使用 AsyncParallelExecutor** - 利用 `roma_dspy.utils` 中现有的异步工具
- ✅ **异步支持** - 裁判和指标支持同步 (`forward`) 和异步 (`aforward`) 执行
- ✅ **完全可配置** - 基于 dataclass 的配置，支持 CLI 覆盖
- ✅ **模块化** - 每个组件都可独立测试和重用
- ✅ **类型安全** - 全程使用正确的类型提示
- ✅ **简洁 CLI** - 可通过 `python -m prompt_optimization.run_optimization` 运行

## 从 Notebook 迁移

重构将 `prompt_optimization.ipynb` 中的所有逻辑提取了出来：

| Notebook 单元格 | 新位置 |
|---------------|--------------|
| LM 配置 | `config.py:LMConfig` |
| 模块初始化 | `solver_setup.py:create_solver_module()` |
| 指令 | `solver_setup.py` (常量) |
| 数据集加载 | `datasets.py:load_aimo_datasets()` |
| 裁判设置 | `judge.py:ComponentJudge` |
| 指标 | `metrics/__init__.py:basic_metric`, `metrics/metric_with_feedback.py:MetricWithFeedback` |
| 选择器 | `selectors.py:*_selector` |
| GEPA 优化器 | `optimizer.py:create_optimizer()` |
| 执行 | `run_optimization.py:main()` |
