/**
 * @roma/core - ROMA orchestrator
 *
 * Recursive Open Meta-Agent for SaaS building
 */

export { Atomizer, type AtomizationResult } from './atomizer.js';
export { Planner, type PlannerOptions } from './planner.js';
export { Executor, type ExecutorOptions, type ExecutorResult, type TaskResult } from './executor.js';
export { Aggregator, type AggregationResult } from './aggregator.js';
export { Verifier, type VerificationResult, type CheckResult } from './verifier.js';
export { ROMA } from './roma.js';

// Observability
export {
  initializeTracing,
  getTracer,
  getMeter,
  startSpan,
  withSpan,
  shutdownTracing,
} from './tracing.js';

export {
  initializeLogger,
  getLogger,
  createChildLogger,
  log,
  logDebug,
  logInfo,
  logWarn,
  logError,
} from './logger.js';

export {
  initializeMetrics,
  recordBuildStarted,
  recordBuildSucceeded,
  recordBuildFailed,
  recordBuildDuration,
  recordLlmTokensUsed,
  recordPtcExecution,
  recordPtcFailure,
} from './metrics.js';
