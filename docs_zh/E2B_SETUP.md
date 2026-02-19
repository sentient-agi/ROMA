# E2B 集成设置指南

## 概览

本指南说明如何为 ROMA-DSPy 设置带 S3 存储集成的 E2B 代码执行沙箱。此设置使智能体能够在隔离的沙箱中执行代码，同时通过 goofys 保持对共享 S3 存储的访问权限。

## 架构

```
┌─────────────────────────────────────────────────────────────┐
│                         主机系统                             │
│                                                              │
│  ┌────────────┐         ┌─────────────────────────────┐    │
│  │   智能体    │────────>│   工具箱 (如 DefiLlama)     │    │
│  └────────────┘         └─────────────────────────────┘    │
│         │                         │                          │
│         │                         │                          │
│         │                         ▼                          │
│         │              ┌─────────────────────┐              │
│         │              │   FileStorage       │              │
│         │              │   (S3 via goofys)   │              │
│         │              └─────────────────────┘              │
│         │                         │                          │
│         ▼                         │                          │
│  ┌────────────┐                  │                          │
│  │ E2BToolkit │                  │                          │
│  └────────────┘                  │                          │
│         │                         │                          │
│         │                         │                          │
│         │                         │                          │
│         │                         │                          │
│         │                         │                          │
│         │                         │                          │
│         ▼                         │                          │
│  ┌────────────┐                  │                          │
│  │   E2B API  │──────────────────┘                          │
│  └────────────┘                                             │
└─────────┼───────────────────────────────────────────────────┘
          │
          │     同一个 S3 桶 (Bucket)
          │
┌─────────▼───────────────────────────────────────────────────┐
│                      E2B 沙箱                                │
│                                                               │
│  ┌───────────────────────────────────────────────────┐      │
│  │  start-up.sh: 将 S3 挂载到 /opt/sentient           │      │
│  │  通过 goofys 使用来自主机的环境变量                 │      │
│  └───────────────────────────────────────────────────┘      │
│                                                               │
│  ┌───────────────────────────────────────────────────┐      │
│  │  智能体生成的代码执行                               │      │
│  │  - 读取 /opt/sentient/executions/...              │      │
│  │  - 写入 /opt/sentient/executions/...              │      │
│  └───────────────────────────────────────────────────┘      │
│                                                               │
└───────────────────────────────────────────────────────────────┘
```

## 先决条件

1. **E2B 账户**
   - 在 [e2b.dev](https://e2b.dev) 注册
   - 从仪表板获取 API 密钥

2. **AWS S3 存储桶**
   - 创建用于存储的 S3 桶
   - 配置具有 S3 访问权限的 AWS 凭证

3. **E2B CLI** (用于创建模版)
   ```bash
   npm install -g @e2b/cli
   # 或
   yarn global add @e2b/cli
   ```

## 步骤 1：环境配置

### 1.1 配置环境变量

复制 `.env.example` 到 `.env` 并填写：

```bash
# 存储配置
STORAGE_BASE_PATH=/opt/sentient
ROMA_S3_BUCKET=your-s3-bucket-name
AWS_REGION=us-east-1

# AWS 凭证
AWS_ACCESS_KEY_ID=your_aws_access_key
AWS_SECRET_ACCESS_KEY=your_aws_secret_key

# E2B 配置
E2B_API_KEY=your_e2b_api_key
E2B_TEMPLATE_ID=roma-dspy-sandbox
```

### 1.2 验证配置

```python
from roma_dspy.config.manager import ConfigManager
import os

config = ConfigManager().load_config()
print(f"存储路径: {config.storage.base_path}")
print(f"S3 桶: {os.getenv('ROMA_S3_BUCKET')}")
```

## 步骤 2：创建自定义 E2B 模版

E2B 模版定义了沙箱环境。我们需要一个包含 S3 挂载脚本的自定义模版。

### 2.1 初始化模版

```bash
cd /Users/barannama/ROMA-DSPy

# 初始化 E2B 模版
e2b template init roma-dspy-sandbox
```

这会创建一个包含模版配置的 `.e2b/` 目录。

### 2.2 添加启动脚本

将我们的启动脚本复制到模版：

```bash
# 复制 start-up.sh 到模版
cp docker/e2b/start-up.sh .e2b/start-up.sh

# 验证脚本可执行
chmod +x .e2b/start-up.sh
```

`start-up.sh` 脚本：
- 在沙箱中安装 goofys
- 将 S3 桶挂载到 `$STORAGE_BASE_PATH`
- 验证写入权限
- 设置 Python 依赖

### 2.3 构建并发布模版

```bash
# 构建模版 (创建 Docker 镜像)
e2b template build

# 这将输出一个模版 ID，如：
# ✓ Template built successfully
# Template ID: roma-dspy-sandbox-abc123

# 将模版 ID 复制到您的 .env 文件
echo "E2B_TEMPLATE_ID=<your-template-id>" >> .env
```

### 2.4 验证模版

```bash
# 列出您的模版
e2b template list

# 您应该看到 ID 与 .env 匹配的模版
```

## 步骤 3：本地存储设置

### 3.1 运行本地设置脚本

```bash
# 使脚本可执行
chmod +x scripts/setup_local.sh

# 运行设置 (通过 goofys 将 S3 挂载到本地)
./scripts/setup_local.sh
```

此脚本：
1. 安装 goofys (如果不存在)
2. 将 S3 桶挂载到本地路径
3. 如果需要，创建符号链接
4. 验证写入权限

### 3.2 验证本地存储

```bash
# 检查挂载
mount | grep goofys

# 验证目录结构
ls -la /opt/sentient/executions/

# 测试写入权限
echo "test" > /opt/sentient/executions/test.txt
cat /opt/sentient/executions/test.txt
rm /opt/sentient/executions/test.txt
```

## 步骤 4：测试 E2B 集成

### 4.1 基本测试

```python
from roma_dspy.tools.core import E2BToolkit
from roma_dspy.config.manager import ConfigManager
from roma_dspy.core.storage import FileStorage

# 加载配置
config = ConfigManager().load_config()

# 创建存储
storage = FileStorage(
    config=config.storage,
    execution_id="test_e2b_001"
)

# 在主机上写入文件
test_data = b"Hello from host!"
await storage.put("test.txt", test_data)
print(f"写入到: {storage.get_artifacts_path('test.txt')}")

# 创建 E2B 工具箱
e2b = E2BToolkit()

# 在 E2B 沙箱中读取文件
code = f"""
import os
file_path = '{storage.get_artifacts_path('test.txt')}'
print(f'正在读取: {{file_path}}')
with open(file_path, 'r') as f:
    content = f.read()
    print(f'内容: {{content}}')
"""

result = e2b.run_python_code(code)
print(result)
```

预期输出：
```json
{
  "success": true,
  "results": [],
  "stdout": [
    "正在读取: /opt/sentient/executions/test_e2b_001/artifacts/test.txt",
    "内容: Hello from host!"
  ],
  "stderr": [],
  "error": null,
  "sandbox_id": "..."
}
```

### 4.2 运行集成测试

```bash
# 运行 E2B 集成测试
pytest tests/integration/test_e2b_integration.py -v

# 运行 E2E 存储测试
pytest tests/integration/test_e2e_storage.py -v
```

## 步骤 5：生产部署

### 5.1 环境特定配置

**开发环境 (.env.development)**:
```bash
STORAGE_BASE_PATH=/opt/sentient/dev
ROMA_S3_BUCKET=roma-storage-dev
E2B_TEMPLATE_ID=roma-dspy-sandbox-dev
```

**生产环境 (.env.production)**:
```bash
STORAGE_BASE_PATH=/opt/sentient/prod
ROMA_S3_BUCKET=roma-storage-prod
E2B_TEMPLATE_ID=roma-dspy-sandbox-prod
```

### 5.2 更新模版

当更新启动脚本时：

```bash
# 修改 docker/e2b/start-up.sh
# 然后更新模版:

cp docker/e2b/start-up.sh .e2b/start-up.sh
e2b template build
```

## 故障排除

### 问题：沙箱无法访问 S3

**症状**：E2B 代码执行失败，出现文件未找到错误

**解决方案**：
1. 验证环境变量已传递给沙箱：
   ```python
   e2b = E2BToolkit()
   status = e2b.get_sandbox_status()
   print(status)  # 检查环境变量
   ```

2. 在 E2B 仪表板中检查 start-up.sh 日志

3. 验证 AWS 凭证有效：
   ```bash
   aws s3 ls s3://$ROMA_S3_BUCKET
   ```

### 问题：goofys 挂载失败

**症状**：本地设置脚本失败或挂载点为空

**解决方案**：
1. 检查 AWS 凭证：
   ```bash
   aws sts get-caller-identity
   ```

2. 验证 S3 桶存在：
   ```bash
   aws s3 ls | grep $ROMA_S3_BUCKET
   ```

3. 检查 goofys 安装：
   ```bash
   which goofys
   goofys --version
   ```

### 问题：主机和 E2B 之间的路径不匹配

**症状**：主机上写入的文件在 E2B 中不可见

**解决方案**：
1. 验证 `STORAGE_BASE_PATH` 在以下位置一致：
   - `.env` 文件
   - 本地设置脚本输出
   - E2B start-up.sh

2. 检查两个系统是否指向同一个 S3 桶：
   ```bash
   # 本地
   mount | grep goofys

   # E2B (在沙箱中运行)
   mount | grep goofys
   ```

### 问题：未找到模版

**症状**：E2B 工具箱失败，提示模版未找到

**解决方案**：
1. 验证模版存在：
   ```bash
   e2b template list
   ```

2. 检查 `.env` 中的 `E2B_TEMPLATE_ID` 是否与模版 ID 匹配

3. 如果需要，重建模版：
   ```bash
   e2b template build
   ```

## 高级配置

### 自定义 Goofys 选项

编辑 `start-up.sh` 以自定义 goofys 挂载：

```bash
# 在 start-up.sh 中，修改 goofys 命令:
goofys \
    --region "${AWS_REGION}" \
    --stat-cache-ttl 5m \           # 更长的缓存
    --type-cache-ttl 5m \
    --max-idle-handles 1000 \       # 更多文件句柄
    --dir-mode 0755 \
    --file-mode 0644 \
    "${S3_BUCKET}" \
    "${STORAGE_BASE_PATH}"
```

### 多个 E2B 模版

创建特定环境的模版：

```bash
# 开发模版
e2b template init roma-dspy-dev
cp docker/e2b/start-up.sh .e2b/start-up.sh
e2b template build

# 生产模版 (带优化)
e2b template init roma-dspy-prod
# 使用生产设置编辑 .e2b/start-up.sh
e2b template build
```

### 监控存储使用情况

```python
from roma_dspy.core.storage import FileStorage

storage = FileStorage(config=config.storage, execution_id="exec_123")
info = await storage.get_storage_info()

print(f"总大小: {info['total_size_mb']} MB")
print(f"文件数: {info['file_count']}")
```

## 最佳实践

1. **使用 Execution ID**：始终将存储范围限定为 execution ID 以进行隔离

2. **清理临时文件**：执行后使用 `cleanup_temp_files()`：
   ```python
   await storage.cleanup_execution_temp_files()
   ```

3. **监控成本**：跟踪 S3 存储和 E2B 沙箱使用情况

4. **模版版本控制**：在生产中对 E2B 模版进行版本控制：
   ```bash
   e2b template build --name roma-dspy-prod-v1.0.0
   ```

5. **错误处理**：始终检查 E2B 执行结果：
   ```python
   result = e2b.run_python_code(code)
   result_data = json.loads(result)
   if not result_data["success"]:
       logger.error(f"E2B execution failed: {result_data['error']}")
   ```

## 参考

- [E2B 文档](https://e2b.dev/docs)
- [Goofys GitHub](https://github.com/kahing/goofys)
- [AWS S3 文档](https://docs.aws.amazon.com/s3/)
- [ROMA-DSPy 存储架构](/docs/STORAGE_ARCHITECTURE.md)

