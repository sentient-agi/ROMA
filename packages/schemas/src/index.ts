/**
 * @roma/schemas - Shared TypeScript interfaces and Zod validators
 *
 * Central schema definitions for ROMA Multi-Agent SaaS Builder
 */

// Intake schemas
export {
  IntakeSchema,
  SecurityRequirementsSchema,
  MultiTenancySchema,
  PerformanceRequirementsSchema,
  BillingSchema,
  FeatureSpecSchema,
  type Intake,
  type FeatureSpec,
  type SecurityRequirements,
  type MultiTenancy,
  type PerformanceRequirements,
  type Billing,
} from './intake.js';

// Architecture schemas
export {
  ArchitectureSchema,
  ServiceSchema,
  DatabaseSchemaSpec,
  InfrastructureSchema,
  APIContractSchema,
  type Architecture,
  type Service,
  type Infrastructure,
  type APIContract,
} from './architecture.js';

// Feature graph schemas
export {
  FeatureGraphSchema,
  FeatureNodeSchema,
  ExecutionStageSchema,
  DependencyTypeSchema,
  TopologicalOrderSchema,
  type FeatureGraph,
  type FeatureNode,
  type ExecutionStage,
  type DependencyType,
  type TopologicalOrder,
} from './feature-graph.js';

// Scaffolding schemas
export {
  ScaffoldingSpecSchema,
  SecretRefSchema,
  FileOperationSchema,
  CommandSpecSchema,
  APICallSpecSchema,
  TestSpecSchema,
  PostConditionSchema,
  RollbackSpecSchema,
  StepExecutionResultSchema,
  ExecutionStateLogSchema,
  type ScaffoldingSpec,
  type SecretRef,
  type FileOperation,
  type CommandSpec,
  type APICallSpec,
  type TestSpec,
  type PostCondition,
  type RollbackSpec,
  type StepExecutionResult,
  type ExecutionStateLog,
} from './scaffolding.js';

// ROMA workflow schemas
export {
  ROMATaskSchema,
  ROMATaskDAGSchema,
  ROMAExecutionContextSchema,
  type ROMATask,
  type ROMATaskDAG,
  type ROMAExecutionContext,
} from './roma-workflow.js';
