/**
 * ROMA - Main orchestrator that ties together all components
 */
import { Atomizer, type AtomizationResult } from './atomizer.js';
import { Planner, type PlannerOptions } from './planner.js';
import { Executor, type ExecutorOptions, type ExecutorResult } from './executor.js';
import { Aggregator, type AggregationResult } from './aggregator.js';
import { Verifier, type VerificationResult } from './verifier.js';

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
    try {
      this.log('Starting ROMA solve', { goal });

      // Step 1: Atomization - determine if task is atomic or composite
      const atomization = this.atomizer.atomize(goal, context);
      this.log('Atomization result', atomization);

      if (atomization.isAtomic) {
        // Atomic task - execute directly
        return this.executeAtomic(goal, atomization, context);
      } else {
        // Composite task - plan and execute recursively
        return await this.executeComposite(goal, atomization, context);
      }
    } catch (error) {
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

  /**
   * Execute an atomic task directly
   */
  private executeAtomic(goal: string, atomization: AtomizationResult, context?: Record<string, any>): ROMAResult {
    this.log('Executing atomic task', { goal });

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
    context?: Record<string, any>
  ): Promise<ROMAResult> {
    this.log('Executing composite task', { goal, taskType: atomization.taskType });

    if (!atomization.taskType) {
      throw new Error('Composite task must have a taskType');
    }

    // Step 2: Planning - create task DAG
    const plan = this.planner.plan(goal, {
      taskType: atomization.taskType,
      context,
    });
    this.log('Plan created', { tasks: plan.tasks.length, stages: plan.executionOrder?.length });

    // Validate plan
    if (!plan.validation.isAcyclic) {
      throw new Error(`Plan contains cycles: ${JSON.stringify(plan.validation.hasCycles)}`);
    }

    // Step 3: Execution - execute the plan
    const execution = await this.executor.execute(plan, goal);
    this.log('Execution completed', { success: execution.success, duration: execution.duration });

    // Step 4: Aggregation - combine results
    const aggregation = this.aggregator.aggregate(execution.results, execution.context);
    this.log('Aggregation completed', { artifacts: Object.keys(aggregation.artifacts).length });

    // Step 5: Verification - validate outputs
    const verification = await this.verifier.verifyArtifacts(aggregation.artifacts);
    this.log('Verification completed', { passed: verification.passed });

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
