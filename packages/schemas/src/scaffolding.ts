/**
 * ScaffoldingSpec - Execution specifications with idempotency, secrets, and postconditions
 */
import { z } from 'zod';

/** Secret reference (not the actual value) */
export const SecretRefSchema = z.object({
  name: z.string(),
  provider: z.enum(['env', 'vault', 'aws-secrets', 'azure-keyvault', 'file']).default('env'),
  path: z.string().optional(), // Path within secret provider
  required: z.boolean().default(true),
  description: z.string().optional(),
});

/** File operation specification */
export const FileOperationSchema = z.object({
  type: z.enum(['create', 'update', 'delete', 'copy', 'move', 'template']),
  path: z.string(),
  content: z.string().optional(),
  templatePath: z.string().optional(),
  templateVars: z.record(z.any()).optional(),
  permissions: z.string().optional(), // e.g., "0644"
  owner: z.string().optional(),
  idempotent: z.boolean().default(true),
  backup: z.boolean().default(false),
});

/** Command execution specification with retry logic */
export const CommandSpecSchema = z.object({
  command: z.string(),
  args: z.array(z.string()).optional(),
  workdir: z.string().optional(),
  env: z.record(z.string()).optional(),
  secretRefs: z.array(SecretRefSchema).optional(),
  timeout: z.number().optional(), // milliseconds
  retryPolicy: z.object({
    maxAttempts: z.number().default(1),
    backoffStrategy: z.enum(['fixed', 'exponential', 'linear']).default('exponential'),
    initialDelay: z.number().default(1000), // milliseconds
    maxDelay: z.number().default(30000),
  }).optional(),
  idempotencyCheck: z.object({
    enabled: z.boolean().default(false),
    checkCommand: z.string().optional(),
    expectedOutput: z.string().optional(),
    expectedExitCode: z.number().optional(),
  }).optional(),
  expectedExitCode: z.number().default(0),
  continueOnError: z.boolean().default(false),
});

/** API call specification */
export const APICallSpecSchema = z.object({
  method: z.enum(['GET', 'POST', 'PUT', 'PATCH', 'DELETE']),
  url: z.string(),
  headers: z.record(z.string()).optional(),
  body: z.any().optional(),
  secretRefs: z.array(SecretRefSchema).optional(),
  timeout: z.number().default(30000),
  retryPolicy: z.object({
    maxAttempts: z.number().default(3),
    retryableStatusCodes: z.array(z.number()).default([408, 429, 500, 502, 503, 504]),
    backoffStrategy: z.enum(['fixed', 'exponential']).default('exponential'),
  }).optional(),
  expectedStatusCodes: z.array(z.number()).default([200, 201, 204]),
  idempotencyKey: z.string().optional(),
});

/** Test specification */
export const TestSpecSchema = z.object({
  name: z.string(),
  type: z.enum(['unit', 'integration', 'e2e', 'contract', 'smoke']),
  command: z.string(),
  workdir: z.string().optional(),
  env: z.record(z.string()).optional(),
  timeout: z.number().default(30000),
  required: z.boolean().default(true), // If false, failure is warning only
  coverage: z.object({
    enabled: z.boolean().default(false),
    threshold: z.number().optional(), // percentage
  }).optional(),
});

/** Postcondition verification */
export const PostConditionSchema = z.object({
  id: z.string(),
  description: z.string(),
  type: z.enum([
    'file_exists',
    'file_contains',
    'command_succeeds',
    'api_responds',
    'service_running',
    'custom',
  ]),
  check: z.union([
    // File existence check
    z.object({
      type: z.literal('file_exists'),
      path: z.string(),
    }),
    // File content check
    z.object({
      type: z.literal('file_contains'),
      path: z.string(),
      pattern: z.string(), // regex or literal
      isRegex: z.boolean().default(false),
    }),
    // Command execution check
    z.object({
      type: z.literal('command_succeeds'),
      command: z.string(),
      expectedExitCode: z.number().default(0),
      expectedOutput: z.string().optional(),
    }),
    // API health check
    z.object({
      type: z.literal('api_responds'),
      url: z.string(),
      method: z.enum(['GET', 'POST']).default('GET'),
      expectedStatus: z.number().default(200),
      timeout: z.number().default(5000),
    }),
    // Service status check
    z.object({
      type: z.literal('service_running'),
      serviceName: z.string(),
      port: z.number().optional(),
    }),
    // Custom verification function
    z.object({
      type: z.literal('custom'),
      script: z.string(),
      language: z.enum(['bash', 'python', 'node']).default('bash'),
    }),
  ]),
  severity: z.enum(['critical', 'error', 'warning', 'info']).default('error'),
  continueOnFailure: z.boolean().default(false),
});

/** Rollback specification */
export const RollbackSpecSchema = z.object({
  enabled: z.boolean().default(false),
  strategy: z.enum(['automatic', 'manual', 'checkpoint']).default('automatic'),
  steps: z.array(z.object({
    description: z.string(),
    type: z.enum(['command', 'file_restore', 'api_call', 'custom']),
    spec: z.any(), // Can be CommandSpec, FileOperation, or APICallSpec
  })).optional(),
  checkpointInterval: z.number().optional(), // For checkpoint strategy
});

/** Main scaffolding specification */
export const ScaffoldingSpecSchema = z.object({
  metadata: z.object({
    featureId: z.string(),
    featureName: z.string(),
    version: z.string().default('1.0.0'),
    generatedAt: z.string().datetime().optional(),
  }),
  secrets: z.array(SecretRefSchema).optional(),
  preconditions: z.array(PostConditionSchema).optional(),
  steps: z.array(z.discriminatedUnion('type', [
    z.object({
      type: z.literal('file'),
      description: z.string(),
      operation: FileOperationSchema,
    }),
    z.object({
      type: z.literal('command'),
      description: z.string(),
      spec: CommandSpecSchema,
    }),
    z.object({
      type: z.literal('api_call'),
      description: z.string(),
      spec: APICallSpecSchema,
    }),
    z.object({
      type: z.literal('template'),
      description: z.string(),
      templatePath: z.string(),
      outputPath: z.string(),
      variables: z.record(z.any()),
    }),
  ])),
  tests: z.array(TestSpecSchema).optional(),
  postconditions: z.array(PostConditionSchema),
  rollback: RollbackSpecSchema.optional(),
  idempotency: z.object({
    enabled: z.boolean().default(true),
    strategy: z.enum(['skip_if_exists', 'check_and_skip', 'force_rerun']).default('check_and_skip'),
    stateFile: z.string().optional(), // Path to store execution state
  }).optional(),
});

/** Execution result for a single step */
export const StepExecutionResultSchema = z.object({
  stepIndex: z.number(),
  success: z.boolean(),
  startedAt: z.string().datetime(),
  completedAt: z.string().datetime(),
  duration: z.number(), // milliseconds
  output: z.string().optional(),
  error: z.string().optional(),
  retryAttempts: z.number().default(0),
  skipped: z.boolean().default(false),
  skipReason: z.string().optional(),
});

/** Execution state log */
export const ExecutionStateLogSchema = z.object({
  executionId: z.string(),
  featureId: z.string(),
  status: z.enum(['pending', 'running', 'completed', 'failed', 'rolled_back']),
  startedAt: z.string().datetime(),
  completedAt: z.string().datetime().optional(),
  steps: z.array(StepExecutionResultSchema),
  postconditionResults: z.array(z.object({
    postconditionId: z.string(),
    passed: z.boolean(),
    message: z.string().optional(),
    checkedAt: z.string().datetime(),
  })).optional(),
  testResults: z.array(z.object({
    testName: z.string(),
    passed: z.boolean(),
    duration: z.number(),
    output: z.string().optional(),
  })).optional(),
  rollbackExecuted: z.boolean().default(false),
  rollbackSuccess: z.boolean().optional(),
  metadata: z.record(z.any()).optional(),
});

export type ScaffoldingSpec = z.infer<typeof ScaffoldingSpecSchema>;
export type SecretRef = z.infer<typeof SecretRefSchema>;
export type FileOperation = z.infer<typeof FileOperationSchema>;
export type CommandSpec = z.infer<typeof CommandSpecSchema>;
export type APICallSpec = z.infer<typeof APICallSpecSchema>;
export type TestSpec = z.infer<typeof TestSpecSchema>;
export type PostCondition = z.infer<typeof PostConditionSchema>;
export type RollbackSpec = z.infer<typeof RollbackSpecSchema>;
export type StepExecutionResult = z.infer<typeof StepExecutionResultSchema>;
export type ExecutionStateLog = z.infer<typeof ExecutionStateLogSchema>;
