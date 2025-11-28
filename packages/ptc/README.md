# @roma/ptc - PTC/MCP Integration Layer

This package provides interfaces and stub implementations for integrating with PTC (Programmatic Tool Calling) and MCP (Model Context Protocol).

## Overview

The PTC layer is responsible for:
- Executing scaffolding specifications in a sandboxed environment
- Managing tools and their execution
- Handling secrets securely
- Verifying postconditions
- Providing rollback capabilities

## Architecture

```
┌─────────────────────────────────────────┐
│         Scaffolding Spec                │
│  (what to build, how to verify)         │
└────────────────┬────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────┐
│         PTC Executor                    │
│  (orchestrates execution)               │
└────────────────┬────────────────────────┘
                 │
        ┌────────┴────────┐
        │                 │
        ▼                 ▼
  ┌──────────┐      ┌──────────┐
  │  Tools   │      │ Sandbox  │
  │(file, cmd│      │ (docker, │
  │template) │      │  vm, etc)│
  └──────────┘      └──────────┘
```

## Current Implementation

This package currently provides **stub implementations** for rapid prototyping. The stubs simulate execution without actually running commands or creating files.

### Stub Components

1. **PtcExecutorStub** - Simulates scaffolding execution
2. **EnvSecretProvider** - Reads secrets from environment variables

### Production Implementation

For production use, replace stubs with real implementations that integrate with:

- **Open PTC Agent** - For actual tool execution
- **MCP Servers** - For model-driven execution
- **Docker/E2B** - For sandboxed environments
- **HashiCorp Vault** - For secret management

## Usage

```typescript
import { PtcExecutorStub } from '@roma/ptc';
import type { ScaffoldingSpec } from '@roma/schemas';

const executor = new PtcExecutorStub({ verbose: true });

const result = await executor.execute(scaffoldingSpec);

if (result.success) {
  console.log('Execution completed successfully');
  console.log('Artifacts:', result.artifacts);
} else {
  console.error('Execution failed:', result.error);
}
```

## Interfaces

### PtcExecutor

Main interface for executing scaffolding specs:

```typescript
interface PtcExecutor {
  execute(spec: ScaffoldingSpec): Promise<ExecutionResult>;
  executeStep(step: any, context: ExecutionContext): Promise<StepResult>;
  checkPostconditions(spec: ScaffoldingSpec): Promise<PostconditionResult[]>;
  rollback(log: ExecutionStateLog): Promise<boolean>;
}
```

### Sandbox

Interface for isolated execution environments:

```typescript
interface Sandbox {
  start(): Promise<void>;
  exec(command: string, options?: ExecOptions): Promise<ExecResult>;
  readFile(path: string): Promise<string>;
  writeFile(path: string, content: string): Promise<void>;
  stop(): Promise<void>;
  destroy(): Promise<void>;
}
```

### SecretProvider

Interface for secret management:

```typescript
interface SecretProvider {
  get(key: string): Promise<string | null>;
  set(key: string, value: string): Promise<void>;
  delete(key: string): Promise<void>;
  list(): Promise<string[]>;
}
```

## Extending

To create a real implementation:

1. Implement `PtcExecutor` interface
2. Integrate with your sandbox environment (Docker, E2B, etc.)
3. Implement tool execution with proper error handling
4. Add retry logic and idempotency checks
5. Integrate with secret management system
6. Implement postcondition verification
7. Add rollback support

See the stubs for reference implementations.
