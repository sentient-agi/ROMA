# ROMA-DSPy 测试套件

本目录包含 ROMA-DSPy 的测试套件，按测试类型组织，并使用 pytest 标记进行分类，以实现灵活的测试执行。

## 测试组织

```
tests/
├── unit/              # 快速、隔离的单元测试
├── integration/       # 包含外部服务的集成测试
├── tools/             # 工具箱特定测试
├── validation/        # 验证和确认测试
├── performance/       # 性能基准测试 (未来)
└── fixtures/          # 共享测试固件 (fixtures)
```

## 测试标记 (Markers)

测试使用 pytest 标记进行分类。使用标记来运行特定的测试子集：

### 主要类别
- `unit` - 无外部依赖的快速单元测试
- `integration` - 需要外部服务的集成测试
- `e2e` - 端到端系统测试

### 需求标记
- `requires_db` - 需要 PostgreSQL 数据库
- `requires_llm` - 需要 LLM API 密钥 (OpenAI 等)
- `requires_e2b` - 需要 E2B 沙箱环境

### 功能标记
- `checkpoint` - 检查点/恢复功能测试
- `error_handling` - 错误传播测试
- `tools` - 工具箱集成测试
- `performance` - 性能基准测试
- `slow` - 耗时较长的测试

## 运行测试

### 运行所有测试
```bash
pytest
```

### 仅运行单元测试 (快速)
```bash
pytest -m unit
```

### 运行集成测试 (需要服务)
```bash
pytest -m integration
```

### 运行需要 PostgreSQL 的测试
```bash
# 先启动 Postgres
docker-compose up -d postgres

# 运行数据库测试
pytest -m requires_db

# 清理
docker-compose down
```

### 运行需要 LLM API 的测试
```bash
# 设置 API 密钥
export OPENAI_API_KEY=your_key_here

# 运行 LLM 测试
pytest -m requires_llm
```

### 运行特定测试类别
```bash
# 仅检查点测试
pytest -m checkpoint

# 仅工具箱测试
pytest -m tools

# 不需要数据库的集成测试
pytest -m "integration and not requires_db"

# 包含所有需求的 E2E 测试
pytest -m "e2e and requires_db and requires_llm"
```

### 按目录运行测试
```bash
# 所有单元测试
pytest tests/unit/

# 特定测试文件
pytest tests/unit/test_dag_serialization.py

# 特定测试函数
pytest tests/unit/test_dag_serialization.py::test_serialize_task_node
```

### 测试覆盖率
```bash
# 运行并生成覆盖率报告
pytest --cov=src/roma_dspy --cov-report=html

# 打开覆盖率报告
open htmlcov/index.html
```

## 设置测试环境

### 1. 安装开发依赖
```bash
pip install -e ".[dev]"
```

### 2. 启动 PostgreSQL (用于 DB 测试)
```bash
docker-compose up -d postgres

# 验证是否运行
docker-compose ps

# 检查日志
docker-compose logs postgres
```

### 3. 设置环境变量
```bash
# LLM 测试必需
export OPENAI_API_KEY=sk-...
export FIREWORKS_API_KEY=...

# DB 测试必需 (docker-compose 默认值)
export DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost/roma_dspy_test

# 可选：E2B 沙箱
export E2B_API_KEY=...
```

### 4. 运行数据库迁移 (首次)
```bash
# 将迁移应用到测试数据库
uv run alembic upgrade head
```

## 编写测试

### 测试结构
```python
import pytest

@pytest.mark.unit
def test_my_unit_test():
    """测试描述。"""
    # 无外部依赖的快速测试
    assert True

@pytest.mark.integration
@pytest.mark.requires_db
async def test_my_integration_test(postgres_storage):
    """测试描述。"""
    # 使用 fixtures 的集成测试
    result = await postgres_storage.get_execution("exec_123")
    assert result is not None
```

### 使用标记
```python
# 单个标记
@pytest.mark.unit

# 多个标记
@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.requires_db

# 带条件的跳过
@pytest.mark.skipif(
    not os.getenv("OPENAI_API_KEY"),
    reason="需要 OPENAI_API_KEY 环境变量"
)
```

### Fixtures
常用 fixtures 可在 `tests/conftest.py` 和 `tests/fixtures/` 中找到：

- `postgres_storage` - 初始化的 PostgresStorage 实例
- `postgres_config` - 用于测试的 PostgresConfig
- `temp_checkpoint_dir` - 用于检查点测试的临时目录
- 针对 LM 和外部服务的 Mock fixtures

## 持续集成 (CI)

测试自动运行于：
- Pull requests (单元测试 + 无外部依赖的集成测试)
- Main 分支提交 (带服务的完整套件)

查看 `.github/workflows/ci.yml` 获取 CI 配置。

## 故障排除

### 测试超时
```bash
# 增加慢速测试的超时时间
pytest --timeout=300
```

### 数据库连接错误
```bash
# 检查 Postgres 是否运行
docker-compose ps

# 重置数据库
docker-compose down -v
docker-compose up -d postgres
```

### 导入错误
```bash
# 以可编辑模式重新安装
pip install -e .
```

### 跳过的测试
```bash
# 查看测试被跳过的原因
pytest -v -rs

# 强制运行跳过的测试 (危险!)
pytest --runxfail
```

## 测试最佳实践

1. **保持单元测试快速** - 无 I/O，无网络，无外部服务
2. **使用适当的标记** - 准确标记测试以进行选择性运行
3. **Mock 外部依赖** - 在单元测试中 mock LLM
4. **清理资源** - 使用 fixtures 进行 setup/teardown
5. **测试边缘情况** - 无效输入、错误条件、边界值
6. **记录测试目的** - 清晰的文档字符串解释测试内容

## 性能测试

性能测试计划在未来开发：

```bash
# 运行性能基准测试 (未来)
pytest -m performance --benchmark-only
```

## 测试数据

测试数据和 fixtures 位于：
- `tests/fixtures/` - 可重用的测试数据
- 单个测试文件 - 测试特定的数据

避免将敏感数据（API 密钥、凭证）提交到测试文件中。
