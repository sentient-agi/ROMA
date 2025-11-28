/**
 * @roma/ptc - PTC/MCP Integration Layer
 *
 * Interfaces and implementations for Programmatic Tool Calling
 * and Model Context Protocol integration
 */

export type {
  Tool,
  ToolResult,
  MCPServer,
  PtcExecutor,
  ExecutionContext,
  ExecutionResult,
  StepResult,
  PostconditionResult,
  SandboxConfig,
  Sandbox,
  ExecOptions,
  ExecResult,
  SecretProvider,
} from './interfaces.js';

export { PtcExecutorStub } from './executor-stub.js';
export { EnvSecretProvider } from './secret-provider-env.js';

// Re-export types from schemas for convenience
export type { ScaffoldingSpec, ExecutionStateLog } from '@roma/schemas';
