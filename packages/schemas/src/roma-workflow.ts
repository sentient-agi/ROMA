/**
 * ROMA workflow schemas - Task DAG and execution context
 */
import { z } from 'zod';

/** ROMA task types */
export const ROMATaskTypeSchema = z.enum([
  'collect_intake',
  'design_architecture',
  'generate_feature_graph',
  'generate_scaffolding',
  'execute_scaffolding',
  'run_tests',
  'verify_postconditions',
  'aggregate_results',
  'custom',
]);

/** Individual task in the ROMA workflow */
export const ROMATaskSchema = z.object({
  id: z.string(),
  type: ROMATaskTypeSchema,
  description: z.string(),
  dependencies: z.array(z.string()).default([]), // Task IDs
  inputs: z.record(z.any()).optional(),
  outputs: z.record(z.any()).optional(),
  status: z.enum(['pending', 'running', 'completed', 'failed', 'skipped']).default('pending'),
  metadata: z.object({
    createdAt: z.string().datetime().optional(),
    startedAt: z.string().datetime().optional(),
    completedAt: z.string().datetime().optional(),
    duration: z.number().optional(), // milliseconds
    error: z.string().optional(),
    retryCount: z.number().default(0),
  }).optional(),
});

/** Task DAG (Directed Acyclic Graph) */
export const ROMATaskDAGSchema = z.object({
  tasks: z.array(ROMATaskSchema),
  validation: z.object({
    isAcyclic: z.boolean(),
    hasCycles: z.array(z.array(z.string())).optional(),
  }),
  executionOrder: z.array(z.array(z.string())).optional(), // Stages of parallel tasks
});

/** ROMA execution context */
export const ROMAExecutionContextSchema = z.object({
  sessionId: z.string(),
  goal: z.string(),
  isComposite: z.boolean(),
  currentPhase: z.enum(['atomization', 'planning', 'execution', 'aggregation', 'verification']),
  artifacts: z.object({
    intake: z.any().optional(),
    architecture: z.any().optional(),
    featureGraph: z.any().optional(),
    scaffoldingSpecs: z.array(z.any()).optional(),
    executionLogs: z.array(z.any()).optional(),
  }),
  metadata: z.record(z.any()).optional(),
});

export type ROMATask = z.infer<typeof ROMATaskSchema>;
export type ROMATaskType = z.infer<typeof ROMATaskTypeSchema>;
export type ROMATaskDAG = z.infer<typeof ROMATaskDAGSchema>;
export type ROMAExecutionContext = z.infer<typeof ROMAExecutionContextSchema>;
