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
export {
  PtcExecutorEnhanced,
  type EnhancedExecutorOptions,
  type FailureScenario,
  type ExecutionMetrics,
} from './executor-enhanced.js';
export {
  PtcExecutorReal,
  type PtcExecutorRealOptions,
} from './ptc-executor-real.js';
export {
  CheckpointManager,
  type CheckpointOptions,
  type ResumeOptions,
  type CanResumeResult,
} from './checkpoint-manager.js';
export {
  EnvSecretProvider,
  type SecretAuditLog,
  type EnvSecretProviderOptions,
} from './secret-provider-env.js';
export {
  SecretSanitizer,
  getGlobalSanitizer,
  setGlobalSanitizer,
  installGlobalSanitization,
  type SanitizationOptions,
  type ValidationResult,
} from './secret-sanitizer.js';

// Re-export types from schemas for convenience
export type { ScaffoldingSpec, ExecutionStateLog } from '@roma/schemas';

// Export MCP Toolkits (ToolResult already exported from interfaces.js)
export {
  BaseToolkit,
  FileToolkit,
  GitToolkit,
  BuildToolkit,
  TestToolkit,
  TemplateToolkit,
  LintToolkit,
  SecretToolkit,
  createStandardToolkits,
  getAllToolDefinitions,
  executeToolByName,
  type ToolDefinition,
} from './toolkits/index.js';
