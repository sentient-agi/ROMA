/**
 * PTC/MCP Integration Interfaces
 *
 * Defines the contract for Programmatic Tool Calling and Model Context Protocol
 */
import type { ScaffoldingSpec, ExecutionStateLog, StepExecutionResult } from '@roma/schemas';

/**
 * Tool definition for PTC
 */
export interface Tool {
  name: string;
  description: string;
  inputSchema: Record<string, any>;
  execute: (params: any) => Promise<ToolResult>;
}

/**
 * Result from tool execution
 */
export interface ToolResult {
  success: boolean;
  output?: any;
  error?: string;
  metadata?: Record<string, any>;
}

/**
 * MCP Server interface
 */
export interface MCPServer {
  name: string;
  version: string;
  capabilities: string[];
  tools: Tool[];
  initialize: () => Promise<void>;
  shutdown: () => Promise<void>;
}

/**
 * PTC Executor - executes scaffolding specs using tools
 */
export interface PtcExecutor {
  /**
   * Execute a scaffolding spec
   */
  execute(spec: ScaffoldingSpec): Promise<ExecutionResult>;

  /**
   * Execute a single step
   */
  executeStep(step: any, context: ExecutionContext): Promise<StepResult>;

  /**
   * Check postconditions
   */
  checkPostconditions(spec: ScaffoldingSpec): Promise<PostconditionResult[]>;

  /**
   * Rollback execution
   */
  rollback(log: ExecutionStateLog): Promise<boolean>;
}

/**
 * Execution context - maintains state during execution
 */
export interface ExecutionContext {
  executionId: string;
  featureId: string;
  workingDirectory: string;
  secrets: Map<string, string>;
  variables: Map<string, any>;
  stateLog: ExecutionStateLog;
}

/**
 * Result of executing a scaffolding spec
 */
export interface ExecutionResult {
  success: boolean;
  executionId: string;
  log: ExecutionStateLog;
  artifacts: string[];
  error?: string;
}

/**
 * Result of executing a single step
 */
export interface StepResult {
  success: boolean;
  output?: any;
  error?: string;
  skipped?: boolean;
  duration: number;
}

/**
 * Postcondition check result
 */
export interface PostconditionResult {
  postconditionId: string;
  passed: boolean;
  message: string;
  checkedAt: string;
}

/**
 * Sandbox configuration
 */
export interface SandboxConfig {
  type: 'docker' | 'vm' | 'process';
  image?: string;
  timeout?: number;
  resources?: {
    cpu?: string;
    memory?: string;
    storage?: string;
  };
  network?: {
    enabled: boolean;
    allowedHosts?: string[];
  };
}

/**
 * Sandbox interface for isolated execution
 */
export interface Sandbox {
  id: string;
  status: 'created' | 'running' | 'stopped' | 'error';

  /**
   * Start the sandbox
   */
  start(): Promise<void>;

  /**
   * Execute a command in the sandbox
   */
  exec(command: string, options?: ExecOptions): Promise<ExecResult>;

  /**
   * Read a file from the sandbox
   */
  readFile(path: string): Promise<string>;

  /**
   * Write a file to the sandbox
   */
  writeFile(path: string, content: string): Promise<void>;

  /**
   * Stop the sandbox
   */
  stop(): Promise<void>;

  /**
   * Destroy the sandbox and clean up resources
   */
  destroy(): Promise<void>;
}

export interface ExecOptions {
  workdir?: string;
  env?: Record<string, string>;
  timeout?: number;
  stdin?: string;
}

export interface ExecResult {
  exitCode: number;
  stdout: string;
  stderr: string;
  duration: number;
}

/**
 * Secret provider interface
 */
export interface SecretProvider {
  name: string;

  /**
   * Get a secret value
   */
  get(key: string): Promise<string | null>;

  /**
   * Set a secret value
   */
  set(key: string, value: string): Promise<void>;

  /**
   * Delete a secret
   */
  delete(key: string): Promise<void>;

  /**
   * List all secret keys
   */
  list(): Promise<string[]>;
}
