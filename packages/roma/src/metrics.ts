/**
 * Metrics Collection for ROMA
 *
 * Provides counters, gauges, and histograms for key operations
 */
import { getMeter } from './tracing.js';

let metricsInitialized = false;

// Counters
let buildsStartedCounter: any;
let buildsSucceededCounter: any;
let buildsFailedCounter: any;
let llmTokensUsedCounter: any;
let ptcExecutionsCounter: any;
let ptcFailuresCounter: any;

// Histograms
let buildDurationHistogram: any;

/**
 * Initialize all metrics
 */
export function initializeMetrics(): void {
  if (metricsInitialized) {
    return;
  }

  const meter = getMeter('roma-metrics');

  // Build counters
  buildsStartedCounter = meter.createCounter('builds_started_total', {
    description: 'Total number of builds started',
  });

  buildsSucceededCounter = meter.createCounter('builds_succeeded_total', {
    description: 'Total number of builds that succeeded',
  });

  buildsFailedCounter = meter.createCounter('builds_failed_total', {
    description: 'Total number of builds that failed',
  });

  // LLM token usage
  llmTokensUsedCounter = meter.createCounter('llm_tokens_used_total', {
    description: 'Total number of LLM tokens consumed',
  });

  // PTC execution counters
  ptcExecutionsCounter = meter.createCounter('ptc_executions_total', {
    description: 'Total number of PTC executions',
  });

  ptcFailuresCounter = meter.createCounter('ptc_failures_total', {
    description: 'Total number of PTC execution failures',
  });

  // Build duration histogram
  buildDurationHistogram = meter.createHistogram('build_duration_seconds', {
    description: 'Duration of builds in seconds',
    unit: 's',
  });

  metricsInitialized = true;
}

/**
 * Record a build start
 */
export function recordBuildStarted(attributes: Record<string, string> = {}): void {
  if (!metricsInitialized) initializeMetrics();
  buildsStartedCounter?.add(1, attributes);
}

/**
 * Record a successful build
 */
export function recordBuildSucceeded(attributes: Record<string, string> = {}): void {
  if (!metricsInitialized) initializeMetrics();
  buildsSucceededCounter?.add(1, attributes);
}

/**
 * Record a failed build
 */
export function recordBuildFailed(attributes: Record<string, string> = {}): void {
  if (!metricsInitialized) initializeMetrics();
  buildsFailedCounter?.add(1, attributes);
}

/**
 * Record build duration
 */
export function recordBuildDuration(durationMs: number, attributes: Record<string, string> = {}): void {
  if (!metricsInitialized) initializeMetrics();
  const durationSeconds = durationMs / 1000;
  buildDurationHistogram?.record(durationSeconds, attributes);
}

/**
 * Record LLM token usage
 */
export function recordLlmTokensUsed(tokens: number, attributes: Record<string, string> = {}): void {
  if (!metricsInitialized) initializeMetrics();
  llmTokensUsedCounter?.add(tokens, attributes);
}

/**
 * Record a PTC execution
 */
export function recordPtcExecution(attributes: Record<string, string> = {}): void {
  if (!metricsInitialized) initializeMetrics();
  ptcExecutionsCounter?.add(1, attributes);
}

/**
 * Record a PTC failure
 */
export function recordPtcFailure(attributes: Record<string, string> = {}): void {
  if (!metricsInitialized) initializeMetrics();
  ptcFailuresCounter?.add(1, attributes);
}
