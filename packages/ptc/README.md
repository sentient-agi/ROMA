# @roma/ptc - Programmatic Tool Calling & MCP Integration

Real file generation using MCP Toolkits for the ROMA Multi-Agent System.

## Features

### ✅ Phase 2A - PtcExecutorReal (IMPLEMENTED)
- Direct toolkit execution (no Docker overhead)
- Real file generation using fs-extra
- Git operations via simple-git
- npm install/build/test via execa
- Template rendering with EJS

### ✅ Phase 2B - 7 MCP Toolkits (IMPLEMENTED)
1. **FileToolkit** - read/write/delete/glob operations
2. **TemplateToolkit** - EJS template rendering  
3. **GitToolkit** - init/commit/branch/log
4. **BuildToolkit** - npm install/run/build
5. **TestToolkit** - Jest test execution
6. **LintToolkit** - ESLint and TypeScript checking
7. **SecretToolkit** - Secure secret access with sanitization

### 📋 Phase 2C - Docker Sandbox (TODO - Phase 3)
- Isolated execution environment
- Resource limits (CPU/memory)
- Network isolation
- Volume mounting

## External Service Requirements (for Phase 3+)

### Real External Services (Currently Mocked)
- **Stripe**: Test API keys + webhook simulator
- **Resend**: Mock SMTP server for email testing
- **Postgres**: Test container (docker-compose)
- **Redis**: Test instance (optional caching)
- **External APIs**: Wiremock/stub server

### Current Approach
Phase 2 uses **in-process execution** with mocked external services. This is faster for development and testing. Docker sandboxing will be added in Phase 3 for production isolation.

## Usage

```typescript
import { PtcExecutorReal } from '@roma/ptc';

const executor = new PtcExecutorReal({
  workingDir: '/path/to/output',
  verbose: true,
});

const result = await executor.execute(scaffoldingSpec);
```
