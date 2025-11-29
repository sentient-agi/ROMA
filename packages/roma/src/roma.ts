/**
 * ROMA - Main orchestrator that ties together all components
 */
import { Atomizer, type AtomizationResult } from './atomizer.js';
import { Planner, type PlannerOptions } from './planner.js';
import { Executor, type ExecutorOptions, type ExecutorResult } from './executor.js';
import { Aggregator, type AggregationResult } from './aggregator.js';
import { Verifier, type VerificationResult } from './verifier.js';
import { withSpan } from './tracing.js';
import { createChildLogger } from './logger.js';
import {
  recordBuildStarted,
  recordBuildSucceeded,
  recordBuildFailed,
  recordBuildDuration,
} from './metrics.js';
import { randomUUID } from 'crypto';

export interface ROMAOptions {
  verbose?: boolean;
  dryRun?: boolean;
  builderInterface?: any;
}

export interface ROMAResult {
  success: boolean;
  atomization: AtomizationResult;
  execution?: ExecutorResult;
  aggregation?: AggregationResult;
  verification?: VerificationResult;
  error?: string;
}

/**
 * ROMA - Recursive Open Meta-Agent
 *
 * Main entry point that implements the recursive plan-execute loop:
 *
 * ```
 * function solve(goal):
 *   if is_atomic(goal):
 *     return execute(goal)
 *   else:
 *     plan = create_plan(goal)
 *     results = execute_plan(plan)
 *     return aggregate(results)
 * ```
 */
export class ROMA {
  private atomizer: Atomizer;
  private planner: Planner;
  private executor: Executor;
  private aggregator: Aggregator;
  private verifier: Verifier;
  private options: ROMAOptions;

  constructor(options: ROMAOptions = {}) {
    this.options = options;
    this.atomizer = new Atomizer();
    this.planner = new Planner();
    this.executor = new Executor({
      verbose: options.verbose,
      dryRun: options.dryRun,
      builderInterface: options.builderInterface,
    });
    this.aggregator = new Aggregator();
    this.verifier = new Verifier();
  }

  /**
   * Main solve method - implements recursive decomposition
   */
  async solve(goal: string, context?: Record<string, any>): Promise<ROMAResult> {
    const executionId = randomUUID();
    const startTime = Date.now();
    const logger = createChildLogger({ executionId, goal });

    return withSpan(
      'roma.solve',
      { executionId, goal, isAtomic: 'unknown' },
      async (span) => {
        try {
          logger.info('Starting ROMA solve');
          recordBuildStarted({ executionId });

          // Step 1: Atomization - determine if task is atomic or composite
          const atomization = await withSpan(
            'roma.atomize',
            { executionId },
            async () => {
              const result = this.atomizer.atomize(goal, context);
              logger.debug({
                isAtomic: result.isAtomic,
                taskType: result.taskType,
              }, 'Atomization result');
              span.setAttribute('isAtomic', result.isAtomic);
              span.setAttribute('taskType', result.taskType || 'none');
              return result;
            }
          );

          let result: ROMAResult;

          if (atomization.isAtomic) {
            // Atomic task - execute directly
            result = this.executeAtomic(goal, atomization, context, executionId);
          } else {
            // Composite task - plan and execute recursively
            result = await this.executeComposite(goal, atomization, context, executionId);
          }

          // Record metrics
          const duration = Date.now() - startTime;
          recordBuildDuration(duration, { executionId, success: String(result.success) });

          if (result.success) {
            recordBuildSucceeded({ executionId });
            logger.info({ duration }, 'ROMA solve completed successfully');
          } else {
            recordBuildFailed({ executionId });
            logger.warn({ duration, error: result.error }, 'ROMA solve completed with failures');
          }

          return result;
        } catch (error) {
          const duration = Date.now() - startTime;
          recordBuildFailed({ executionId });
          recordBuildDuration(duration, { executionId, success: 'false' });

          logger.error({
            error: error instanceof Error ? error.message : String(error),
            duration,
          }, 'ROMA solve failed with error');

          return {
            success: false,
            atomization: {
              isAtomic: false,
              reasoning: 'Error occurred before atomization',
            },
            error: error instanceof Error ? error.message : String(error),
          };
        }
      }
    );
  }

  /**
   * Execute an atomic task directly
   */
  private executeAtomic(
    goal: string,
    atomization: AtomizationResult,
    context: Record<string, any> | undefined,
    executionId: string
  ): ROMAResult {
    const logger = createChildLogger({ executionId, phase: 'atomic' });
    logger.debug({ goal }, 'Executing atomic task');

    // For now, atomic tasks just return success
    // In a real implementation, this would call an executor
    return {
      success: true,
      atomization,
      aggregation: {
        summary: `Atomic task completed: ${goal}`,
        artifacts: {},
        metrics: {
          totalTasks: 1,
          successfulTasks: 1,
          failedTasks: 0,
          totalDuration: 0,
          averageTaskDuration: 0,
        },
      },
    };
  }

  /**
   * Execute a composite task by planning and recursive execution
   */
  private async executeComposite(
    goal: string,
    atomization: AtomizationResult,
    context: Record<string, any> | undefined,
    executionId: string
  ): Promise<ROMAResult> {
    const logger = createChildLogger({ executionId, phase: 'composite' });
    logger.info({ goal, taskType: atomization.taskType }, 'Executing composite task');

    if (!atomization.taskType) {
      throw new Error('Composite task must have a taskType');
    }

    // Step 2: Planning - create task DAG
    const plan = await withSpan('roma.plan', { executionId, taskType: atomization.taskType || 'unknown' }, async (span) => {
      const result = this.planner.plan(goal, {
        taskType: atomization.taskType!,
        context,
      });
      logger.info({
        tasks: result.tasks.length,
        stages: result.executionOrder?.length,
      }, 'Plan created');
      span.setAttribute('taskCount', result.tasks.length);
      span.setAttribute('stageCount', result.executionOrder?.length || 0);
      return result;
    });

    // Validate plan
    if (!plan.validation.isAcyclic) {
      throw new Error(`Plan contains cycles: ${JSON.stringify(plan.validation.hasCycles)}`);
    }

    // Step 3: Execution - execute the plan
    const execution = await withSpan('roma.execute', { executionId }, async (span) => {
      const result = await this.executor.execute(plan, goal);
      logger.info({
        success: result.success,
        duration: result.duration,
        taskCount: result.results.length,
      }, 'Execution completed');
      span.setAttribute('success', result.success);
      span.setAttribute('duration', result.duration);
      return result;
    });

    // Step 4: Aggregation - combine results
    const aggregation = await withSpan('roma.aggregate', { executionId }, async (span) => {
      const result = this.aggregator.aggregate(execution.results, execution.context);
      logger.info({
        artifactCount: Object.keys(result.artifacts).length,
      }, 'Aggregation completed');
      span.setAttribute('artifactCount', Object.keys(result.artifacts).length);
      return result;
    });

    // Step 5: Verification - validate outputs
    const verification = await withSpan('roma.verify', { executionId }, async (span) => {
      const result = await this.verifier.verifyArtifacts(aggregation.artifacts);
      logger.info({
        passed: result.passed,
        checkCount: result.checks.length,
      }, 'Verification completed');
      span.setAttribute('passed', result.passed);
      span.setAttribute('checkCount', result.checks.length);
      return result;
    });

    return {
      success: execution.success && verification.passed,
      atomization,
      execution,
      aggregation,
      verification,
    };
  }

  /**
   * Get a formatted report of the last execution
   */
  formatResult(result: ROMAResult, format: 'text' | 'json' | 'markdown' = 'text'): string {
    if (format === 'json') {
      return JSON.stringify(result, null, 2);
    }

    if (format === 'markdown' && result.aggregation) {
      return this.aggregator.toMarkdown(result.aggregation);
    }

    // Text format
    const lines: string[] = [];
    lines.push('=== ROMA Execution Result ===\n');
    lines.push(`Success: ${result.success ? '✅' : '❌'}`);
    lines.push(`\nAtomization: ${result.atomization.isAtomic ? 'Atomic' : 'Composite'}`);
    lines.push(`Reasoning: ${result.atomization.reasoning}`);

    if (result.execution) {
      lines.push(`\nExecution Duration: ${result.execution.duration}ms`);
      lines.push(`Tasks Completed: ${result.execution.results.length}`);
    }

    if (result.aggregation) {
      lines.push(`\n${result.aggregation.summary}`);
    }

    if (result.verification) {
      lines.push(`\n${result.verification.summary}`);
    }

    if (result.error) {
      lines.push(`\n❌ Error: ${result.error}`);
    }

    return lines.join('\n');
  }

  private log(message: string, meta?: any): void {
    if (this.options.verbose) {
      console.log(`[ROMA] ${message}`, meta || '');
    }
  }
}
