# AWS Bedrock Configuration Guide

This document describes how to use the ROMA-DSPy framework with AWS Bedrock using the `baizantium` AWS profile.

## ✅ Current Configuration

The application is successfully configured to use:
- **AWS Profile**: `baizantium` (SSO)
- **AWS Region**: `ap-southeast-2` (Sydney)
- **Models**: Claude Haiku 4.5, Claude Sonnet 4.5, Claude Sonnet 4
- **Authentication**: AWS SSO with session tokens

## 🚀 Usage

### Quick Start

```bash
# Start all services
docker-compose up -d

# Run a task with AWS Bedrock
docker exec roma-dspy-api roma-dspy solve \
  --profile baizantium \
  "Your question here"

# Example: Simple question (output defaults to text)
docker exec roma-dspy-api roma-dspy solve \
  --profile baizantium \
  --max-depth 1 \
  "What is machine learning?"

# Example: Complex analysis with explicit output format
docker exec roma-dspy-api roma-dspy solve \
  --profile baizantium \
  --max-depth 3 \
  --output text \
  "Compare the top 3 cloud providers"

# Example: JSON output for programmatic use
docker exec roma-dspy-api roma-dspy solve \
  --profile baizantium \
  --max-depth 1 \
  --output json \
  "Calculate 15 * 23"
```

### Using the Justfile

```bash
# Start services
just docker-up

# Solve a task with baizantium profile
just solve "Your task here" baizantium
```

### Using the REST API

```bash
# Submit a task via API
curl -X POST http://localhost:8000/api/v1/executions \
  -H "Content-Type: application/json" \
  -d '{
    "goal": "Your task here",
    "config_profile": "baizantium",
    "max_depth": 2
  }'

# Get execution details
curl http://localhost:8000/api/v1/executions/<execution_id> | jq .

# List all executions
curl http://localhost:8000/api/v1/executions | jq .
```

### Visualize Executions

```bash
# Launch interactive TUI (Terminal UI)
docker exec -it roma-dspy-api roma-dspy viz-interactive <execution_id>

# With live mode (auto-refresh)
docker exec -it roma-dspy-api roma-dspy viz-interactive <execution_id> --live
```

## 🔧 Model Configuration

The `baizantium` profile uses AWS Bedrock Claude models via **AU/APAC inference profiles**:

| Agent | Model | Inference Profile |
|-------|-------|-------------------|
| **Atomizer** | Claude Haiku 4.5 | `au.anthropic.claude-haiku-4-5-20251001-v1:0` |
| **Planner** | Claude Sonnet 4.5 | `au.anthropic.claude-sonnet-4-5-20250929-v1:0` |
| **Executor (default)** | Claude Sonnet 4.5 | `au.anthropic.claude-sonnet-4-5-20250929-v1:0` |
| **Executor (RETRIEVE)** | Claude Haiku 4.5 | `au.anthropic.claude-haiku-4-5-20251001-v1:0` |
| **Executor (CODE_INTERPRET)** | Claude Sonnet 4.5 | `au.anthropic.claude-sonnet-4-5-20250929-v1:0` |
| **Executor (THINK)** | Claude Sonnet 4 | `apac.anthropic.claude-sonnet-4-20250514-v1:0` |
| **Executor (WRITE)** | Claude Sonnet 4.5 | `au.anthropic.claude-sonnet-4-5-20250929-v1:0` |
| **Aggregator** | Claude Haiku 4.5 | `au.anthropic.claude-haiku-4-5-20251001-v1:0` |
| **Verifier** | Claude Haiku 4.5 | `au.anthropic.claude-haiku-4-5-20251001-v1:0` |

- **Claude Haiku 4.5** (`au.anthropic.claude-haiku-4-5-20251001-v1:0`) - Fast tasks
- **Claude Sonnet 4.5** (`au.anthropic.claude-sonnet-4-5-20250929-v1:0`) - Standard tasks
- **Claude Sonnet 4** (`apac.anthropic.claude-sonnet-4-20250514-v1:0`) - Deep reasoning

### Why Inference Profiles?

AWS Bedrock requires **inference profiles** for on-demand access to newer models. Direct model IDs like `anthropic.claude-haiku-4-5-20251001-v1:0` don't support on-demand throughput - you must use regional profiles like `au.anthropic.claude-haiku-4-5-20251001-v1:0`.

## 🔄 Refreshing SSO Credentials

**Important**: AWS SSO tokens are temporary (typically 1-12 hours). When they expire, you'll see authentication errors.

### Manual Refresh

```bash
# Step 1: Login to AWS SSO
aws sso login --profile baizantium

# Step 2: Extract fresh credentials
CACHE_FILE=$(ls -t ~/.aws/cli/cache/*.json | head -1)
ACCESS_KEY=$(jq -r '.Credentials.AccessKeyId' "$CACHE_FILE")
SECRET_KEY=$(jq -r '.Credentials.SecretAccessKey' "$CACHE_FILE")
SESSION_TOKEN=$(jq -r '.Credentials.SessionToken' "$CACHE_FILE")

# Step 3: Update .env
cd /Users/faizwaris/ROMA
# Update the AWS credential lines in .env with new values

# Step 4: Restart API
docker-compose restart roma-api
```

### Interactive TUI
```bash
# Get execution ID from logs or API
EXEC_ID="66724371-17b0-4cbd-b7ec-794d6d2d7553"

# Launch TUI
docker exec -it roma-dspy-api roma-dspy viz-interactive $EXEC_ID

# With live mode for running tasks
docker exec -it roma-dspy-api roma-dspy viz-interactive $EXEC_ID --live
```
