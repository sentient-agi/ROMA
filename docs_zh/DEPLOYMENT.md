# ROMA-DSPy 部署指南

ROMA-DSPy 的生产部署指南。

## 目录

- [概览](#概览)
- [快速部署](#快速部署)
- [架构](#架构)
- [环境配置](#环境配置)
- [Docker 部署](#docker-部署)
- [生产检查清单](#生产检查清单)
- [监控与可观察性](#监控与可观察性)
- [扩展](#扩展)
- [安全性](#安全性)
- [故障排除](#故障排除)

---

## 概览

ROMA-DSPy 专为使用 Docker Compose 进行生产部署而设计，提供：

**基础设施：**
- PostgreSQL (执行/检查点持久化)
- MinIO (S3 兼容对象存储，用于 MLflow 工件)
- MLflow (可选，实验跟踪)
- ROMA API (FastAPI 服务器)

**特性：**
- 健康检查与自动重启
- 卷持久化
- 网络隔离
- 多阶段 Docker 构建
- 非 root 容器

---

## 快速部署

### 先决条件

- Docker 24.0+ 和 Docker Compose 2.0+
- 最小 4GB RAM (推荐 8GB)
- 20GB 磁盘空间
- 可用端口：8000 (API), 5432 (Postgres), 9000/9001 (MinIO), 5000 (MLflow)

### 1. 克隆仓库

```bash
git clone https://github.com/your-org/ROMA-DSPy.git
cd ROMA-DSPy
```

### 2. 配置环境

```bash
# 复制环境模版
cp .env.example .env

# 编辑 .env 并设置必需值
nano .env
```

**最低要求：**
```bash
# LLM 提供商
OPENROUTER_API_KEY=your_key_here

# 数据库
POSTGRES_PASSWORD=secure_password_here

# MinIO/S3
MINIO_ROOT_PASSWORD=secure_password_here
```

### 3. 启动服务

```bash
# 基础部署 (API + PostgreSQL + MinIO)
just docker-up

# 完整部署 (包含 MLflow 可观察性)
just docker-up-full

# 验证健康状态
curl http://localhost:8000/health
```

### 4. 测试

```bash
# 通过 API
curl -X POST http://localhost:8000/api/v1/executions \
  -H "Content-Type: application/json" \
  -d '{"goal": "What is 2+2?", "max_depth": 1}' | jq

# 通过 CLI (容器内)
docker exec -it roma-dspy-api roma-dspy solve "What is 2+2?"
```

---

## 架构

### Docker Compose 栈

```
┌──────────────────────────────────────────────────────┐
│                  Docker Network                       │
│                                                       │
│  ┌──────────────┐    ┌──────────────┐               │
│  │   ROMA API   │───▶│  PostgreSQL  │               │
│  │  Port: 8000  │    │  Port: 5432  │               │
│  └──────┬───────┘    └──────────────┘               │
│         │                                             │
│         │            ┌──────────────┐                │
│         └───────────▶│    MinIO     │                │
│                      │ Port: 9000   │                │
│                      │ Console:9001 │                │
│                      └──────┬───────┘                │
│                             │                         │
│                      ┌──────▼───────┐                │
│                      │    MLflow    │ (可选)         │
│                      │  Port: 5000  │                │
│                      └──────────────┘                │
└──────────────────────────────────────────────────────┘
```

### 服务描述

**roma-api:**
- FastAPI 应用服务器
- 处理执行管理
- 暴露 REST API
- 健康检查：`http://localhost:8000/health`

**postgres:**
- PostgreSQL 16 Alpine
- 存储执行元数据、检查点、追踪
- 持久卷：`postgres_data`
- 健康检查：`pg_isready`

**minio:**
- S3 兼容对象存储
- 存储 MLflow 工件
- 持久卷：`minio_data`
- UI: `http://localhost:9001`

**mlflow** (可选):
- 实验跟踪服务器
- 需要 `--profile observability`
- UI: `http://localhost:5000`

---

## 环境配置

### 必需变量

```bash
# LLM 提供商 (至少需要一个)
OPENROUTER_API_KEY=your_key_here        # 推荐
# 或
OPENAI_API_KEY=your_key_here
ANTHROPIC_API_KEY=your_key_here
GOOGLE_API_KEY=your_key_here

# 数据库
POSTGRES_DB=roma_dspy                  # 数据库名称
POSTGRES_USER=postgres                  # 数据库用户
POSTGRES_PASSWORD=CHANGE_ME_IN_PROD    # 数据库密码
POSTGRES_PORT=5432                      # 主机端口

# MinIO/S3
MINIO_ROOT_USER=minioadmin             # MinIO 访问密钥
MINIO_ROOT_PASSWORD=CHANGE_ME_IN_PROD  # MinIO 秘密密钥
MINIO_PORT=9000                         # S3 API 端口
MINIO_CONSOLE_PORT=9001                 # 控制台端口

# API
API_PORT=8000                           # API 端口
POSTGRES_ENABLED=true                   # 启用 PostgreSQL 存储
```

### 可选变量

```bash
# 工具箱 API 密钥
E2B_API_KEY=your_key_here              # 代码执行
EXA_API_KEY=your_key_here              # Web 搜索 (via MCP)
SERPER_API_KEY=your_key_here           # Web 搜索工具箱
GITHUB_PERSONAL_ACCESS_TOKEN=your_token # GitHub MCP 服务器
COINGECKO_API_KEY=your_key_here        # CoinGecko Pro API

# MLflow (用于可观察性 profile)
MLFLOW_PORT=5000
MLFLOW_TRACKING_URI=http://mlflow:5000

# 存储
STORAGE_BASE_PATH=/opt/sentient         # 文件存储基础路径

# 安全性
ALLOWED_ORIGINS=https://yourdomain.com  # CORS 源 (逗号分隔)

# 日志
LOG_LEVEL=INFO                          # DEBUG, INFO, WARNING, ERROR
LOG_DIR=/app/logs                       # 日志目录
```

---

## Docker 部署

### 构建并启动

**从头构建：**
```bash
# 清理构建
just docker-build-clean

# 启动服务
just docker-up
```

**使用现有镜像启动：**
```bash
# 基础 (API + Postgres + MinIO)
just docker-up

# 完整 (包含 MLflow)
just docker-up-full
```

### 验证部署

```bash
# 检查所有服务运行状态
just docker-ps

# 检查健康状态
curl http://localhost:8000/health

# 查看日志
just docker-logs

# 查看特定服务日志
just docker-logs-service roma-api
just docker-logs-service postgres
just docker-logs-service mlflow
```

### 停止服务

```bash
# 停止 (保留数据)
just docker-down

# 停止并移除卷 (数据丢失!)
just docker-down-clean
```

---

## 生产检查清单

### 安全性

- [ ] 更改 `.env` 中的默认密码：
  - `POSTGRES_PASSWORD`
  - `MINIO_ROOT_PASSWORD`

- [ ] 为 CORS 设置 `ALLOWED_ORIGINS` (生产环境中不要使用 `*`)

- [ ] 使用 HTTPS 反向代理 (nginx, Caddy, Traefik)

- [ ] 在 API 上启用认证 (添加中间件)

- [ ] 限制网络访问 (防火墙规则)

- [ ] 使用机密管理 (Docker secrets, Vault, AWS Secrets Manager)

- [ ] 定期更新基础镜像：
  ```bash
  docker-compose pull
  docker-compose up -d
  ```

### 可靠性

- [ ] 配置自动备份：
  ```bash
  # PostgreSQL 备份
  docker exec roma-dspy-postgres pg_dump -U postgres roma_dspy > backup.sql
  ```

- [ ] 在 `docker-compose.yaml` 中设置资源限制：
  ```yaml
  roma-api:
    deploy:
      resources:
        limits:
          cpus: '2.0'
          memory: 4G
        reservations:
          cpus: '1.0'
          memory: 2G
  ```

- [ ] 监控磁盘使用率：
  ```bash
  docker system df
  docker volume ls
  ```

- [ ] 配置日志轮转：
  ```yaml
  roma-api:
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
  ```

### 可观察性

- [ ] 启用 MLflow 跟踪：
  ```bash
  just docker-up-full
  ```

- [ ] 设置健康检查监控 (Prometheus, Datadog 等)

- [ ] 配置日志聚合 (ELK, Grafana Loki, Datadog)

- [ ] 监控资源使用率 (CPU, 内存, 磁盘)

- [ ] 为服务故障设置告警

---

## 监控与可观察性

### 健康检查

**API 健康：**
```bash
curl http://localhost:8000/health
```

**响应：**
```json
{
  "status": "healthy",
  "version": "0.1.0",
  "uptime_seconds": 3600.5,
  "active_executions": 2,
  "storage_connected": true,
  "cache_size": 5,
  "timestamp": "2024-10-21T12:00:00.000Z"
}
```

**PostgreSQL 健康：**
```bash
docker exec roma-dspy-postgres pg_isready -U postgres
```

**MinIO 健康：**
```bash
curl http://localhost:9000/minio/health/live
```

### MLflow UI

访问地址：http://localhost:5000

**特性：**
- 实验跟踪
- 运行比较
- 模型注册
- 工件存储

**查看执行：**
1. 导航至 http://localhost:5000
2. 按实验名称过滤
3. 点击 execution ID 查看详情

### 指标端点

```bash
# 执行指标
curl http://localhost:8000/api/v1/executions/<execution_id>/metrics | jq

# 成本摘要
curl http://localhost:8000/api/v1/executions/<execution_id>/costs | jq

# 工具箱指标
curl http://localhost:8000/api/v1/executions/<execution_id>/toolkit-metrics | jq

# LM 追踪
curl http://localhost:8000/api/v1/executions/<execution_id>/lm-traces | jq
```

### 日志聚合

**查看日志：**
```bash
# 所有服务
just docker-logs

# 特定服务
just docker-logs-service roma-api

# 跟踪日志
docker-compose logs -f roma-api
```

**导出日志：**
```bash
docker-compose logs roma-api > roma-api.log
```

---

## 扩展

### 水平扩展 (多 API 实例)

**docker-compose.yaml:**
```yaml
roma-api:
  # ... 现有配置 ...
  deploy:
    replicas: 3  # 运行 3 个实例

  # 负载均衡器
  labels:
    - "traefik.enable=true"
    - "traefik.http.routers.roma.rule=Host(`api.yourdomain.com`)"
```

**使用 nginx 负载均衡：**
```nginx
upstream roma_api {
    server localhost:8001;
    server localhost:8002;
    server localhost:8003;
}

server {
    listen 80;
    server_name api.yourdomain.com;

    location / {
        proxy_pass http://roma_api;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

### 垂直扩展 (资源限制)

**docker-compose.yaml:**
```yaml
roma-api:
  deploy:
    resources:
      limits:
        cpus: '4.0'
        memory: 8G
      reservations:
        cpus: '2.0'
        memory: 4G

postgres:
  deploy:
    resources:
      limits:
        cpus: '2.0'
        memory: 4G
      reservations:
        cpus: '1.0'
        memory: 2G
```

### 数据库扩展

**PostgreSQL 优化：**
```bash
# 连接到数据库
docker exec -it roma-dspy-postgres psql -U postgres -d roma_dspy

# 分析表
ANALYZE executions;
ANALYZE checkpoints;
ANALYZE lm_traces;

# 真空清理
VACUUM ANALYZE;

# 检查索引
\di
```

**连接池** (如果需要，添加 PgBouncer):
```yaml
pgbouncer:
  image: pgbouncer/pgbouncer:latest
  environment:
    DATABASE_URL: postgres://postgres:password@postgres:5432/roma_dspy
    POOL_MODE: transaction
    MAX_CLIENT_CONN: 1000
    DEFAULT_POOL_SIZE: 20
```

---

## 安全性

### HTTPS/TLS

**选项 1：nginx 反向代理**
```nginx
server {
    listen 443 ssl;
    server_name api.yourdomain.com;

    ssl_certificate /etc/nginx/ssl/cert.pem;
    ssl_certificate_key /etc/nginx/ssl/key.pem;

    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

**选项 2：Caddy (自动 HTTPS)**
```caddy
api.yourdomain.com {
    reverse_proxy localhost:8000
}
```

### 认证

**添加 API 密钥中间件** (示例):
```python
# src/roma_dspy/api/middleware.py
from fastapi import HTTPException, Request
from starlette.middleware.base import BaseHTTPMiddleware

class APIKeyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        api_key = request.headers.get("X-API-Key")
        if not api_key or api_key != os.getenv("API_KEY"):
            raise HTTPException(status_code=401, detail="Invalid API key")
        return await call_next(request)
```

**使用：**
```python
# src/roma_dspy/api/main.py
app.add_middleware(APIKeyMiddleware)
```

### 网络安全

**防火墙规则：**
```bash
# 仅允许特定 IP
sudo ufw allow from 203.0.113.0/24 to any port 8000

# 或使用 Docker 网络策略
```

**仅内部网络：**
```yaml
# docker-compose.yaml
services:
  postgres:
    ports: []  # 不暴露给主机
    networks:
      - roma-network

networks:
  roma-network:
    internal: true  # 无外部访问
```

### 机密管理

**使用 Docker secrets:**
```yaml
secrets:
  postgres_password:
    file: ./secrets/postgres_password.txt
  openrouter_api_key:
    file: ./secrets/openrouter_api_key.txt

services:
  roma-api:
    secrets:
      - postgres_password
      - openrouter_api_key
    environment:
      POSTGRES_PASSWORD_FILE: /run/secrets/postgres_password
      OPENROUTER_API_KEY_FILE: /run/secrets/openrouter_api_key
```

---

## 故障排除

### 服务无法启动

**检查日志：**
```bash
just docker-logs-service roma-api
just docker-logs-service postgres
```

**常见问题：**

1. **端口已被占用：**
   ```bash
   # 查找占用端口的进程
   lsof -i :8000

   # 杀死进程或更改 .env 中的 API_PORT
   ```

2. **数据库连接失败：**
   ```bash
   # 检查 postgres 健康
   docker exec roma-dspy-postgres pg_isready -U postgres

   # 验证 .env 中的 DATABASE_URL
   ```

3. **内存不足：**
   ```bash
   # 检查 Docker 资源
   docker stats

   # 增加 Docker 内存限制
   # Docker Desktop → Settings → Resources → Memory
   ```

### 数据持久化问题

**检查卷：**
```bash
# 列出卷
docker volume ls | grep roma

# 检查卷
docker volume inspect roma-dspy_postgres_data

# 备份卷
docker run --rm -v roma-dspy_postgres_data:/data -v $(pwd):/backup alpine tar czf /backup/postgres_backup.tar.gz /data
```

### 性能问题

**监控资源：**
```bash
# 实时统计
docker stats

# 检查磁盘使用
docker system df

# 清理未使用数据
docker system prune -a
```

**数据库慢查询：**
```bash
# 启用查询日志
docker exec -it roma-dspy-postgres psql -U postgres -d roma_dspy

# 显示慢查询
SELECT query, calls, total_time, mean_time
FROM pg_stat_statements
ORDER BY total_time DESC
LIMIT 10;
```

### MLflow 无法访问

**检查服务：**
```bash
# 确保以 observability profile 启动
just docker-up-full

# 检查日志
docker-compose logs mlflow

# 验证端口
curl http://localhost:5000
```

---

## 额外资源

- **快速开始**: [QUICKSTART.md](QUICKSTART.md)
- **配置**: [CONFIGURATION.md](CONFIGURATION.md)
- **API 参考**: http://localhost:8000/docs
- **Docker Compose 文档**: https://docs.docker.com/compose/
- **FastAPI 部署**: https://fastapi.tiangolo.com/deployment/

---

**生产就绪！** 🚀

如有问题，请先检查日志 (`just docker-logs`)，然后查阅文档或提交 issue。

