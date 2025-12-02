/**
 * FeatureGraphSchema - Dependency graph of features with execution ordering
 */
import { z } from 'zod';

/** Feature dependency type */
export const DependencyTypeSchema = z.enum([
  'hard',      // Must complete before dependent can start
  'soft',      // Preferred order but not required
  'data',      // Data dependency (output consumed as input)
  'optional',  // Nice to have but not required
]);

/** Feature node in the dependency graph */
export const FeatureNodeSchema = z.object({
  id: z.string(),
  name: z.string(),
  description: z.string(),
  type: z.enum(['infrastructure', 'backend', 'frontend', 'integration', 'testing']),
  priority: z.number().min(0).max(10).default(5),
  estimatedComplexity: z.enum(['low', 'medium', 'high', 'critical']).default('medium'),
  dependencies: z.array(z.object({
    featureId: z.string(),
    type: DependencyTypeSchema,
    reason: z.string().optional(),
  })).default([]),
  outputs: z.array(z.object({
    name: z.string(),
    type: z.string(),
    description: z.string(),
  })).optional(),
  inputs: z.array(z.object({
    name: z.string(),
    type: z.string(),
    source: z.string().optional(), // Which feature provides this
  })).optional(),
  metadata: z.object({
    assignedTo: z.string().optional(),
    estimatedHours: z.number().optional(),
    tags: z.array(z.string()).optional(),
  }).optional(),
});

/** Execution stage grouping */
export const ExecutionStageSchema = z.object({
  stageNumber: z.number(),
  name: z.string(),
  description: z.string().optional(),
  features: z.array(z.string()), // Feature IDs that can run in parallel
  preconditions: z.array(z.string()).optional(), // Required stages
  postconditions: z.array(z.string()).optional(), // Validation rules
});

/** Main feature graph schema */
export const FeatureGraphSchema = z.object({
  metadata: z.object({
    version: z.string().default('1.0.0'),
    generatedAt: z.string().datetime().optional(),
    basedOnArchitecture: z.string().optional(),
  }),
  nodes: z.array(FeatureNodeSchema),
  executionStages: z.array(ExecutionStageSchema),
  validation: z.object({
    isAcyclic: z.boolean(),
    hasCycles: z.array(z.array(z.string())).optional(), // List of cycles if found
    unreachableNodes: z.array(z.string()).optional(),
    criticalPath: z.array(z.string()).optional(), // Longest dependency chain
  }),
  statistics: z.object({
    totalFeatures: z.number(),
    totalStages: z.number(),
    averageComplexity: z.number().optional(),
    estimatedTotalHours: z.number().optional(),
    parallelizationFactor: z.number().optional(), // How much can run in parallel
  }).optional(),
});

/** Utility type for topological sorting result */
export const TopologicalOrderSchema = z.object({
  order: z.array(z.string()), // Feature IDs in execution order
  stages: z.array(z.array(z.string())), // Grouped by parallelizable stages
});

export type FeatureGraph = z.infer<typeof FeatureGraphSchema>;
export type FeatureNode = z.infer<typeof FeatureNodeSchema>;
export type ExecutionStage = z.infer<typeof ExecutionStageSchema>;
export type DependencyType = z.infer<typeof DependencyTypeSchema>;
export type TopologicalOrder = z.infer<typeof TopologicalOrderSchema>;
