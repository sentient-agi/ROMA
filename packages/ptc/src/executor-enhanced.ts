/**
 * Enhanced PTC Executor with Failure Simulation and Retry Testing
 *
 * This implementation allows testing of:
 * - Retry logic
 * - Backoff strategies
 * - Failure recovery
 * - Idempotency checks
 * - Partial failures
 */
import type {
  PtcExecutor,
  ExecutionResult,
  ExecutionContext,
  StepResult,
  PostconditionResult,
} from './interfaces.js';
import type { ScaffoldingSpec, ExecutionStateLog } from '@roma/schemas';
import { getGlobalSanitizer } from './secret-sanitizer.js';

export interface FailureScenario {
  stepIndex?: number;
  failureType: 'timeout' | 'error' | 'postcondition' | 'random';
  failureRate?: number; // 0-1, for random failures
  recoverAfterAttempts?: number; // Simulate transient failures
  errorMessage?: string;
}

export interface EnhancedExecutorOptions {
  verbose?: boolean;
  failureScenarios?: FailureScenario[];
  simulateLatency?: boolean;
  minLatency?: number;
  maxLatency?: number;
  trackMetrics?: boolean;
}

export class PtcExecutorEnhanced implements PtcExecutor {
  private verbose: boolean;
  private failureScenarios: FailureScenario[];
  private simulateLatency: boolean;
  private minLatency: number;
  private maxLatency: number;
  private trackMetrics: boolean;
  private attemptCounts: Map<string, number> = new Map();
  private metrics: ExecutionMetrics = {
    totalExecutions: 0,
    successfulExecutions: 0,
    failedExecutions: 0,
    totalSteps: 0,
    retriedSteps: 0,
    averageStepDuration: 0,
    totalDuration: 0,
  };

  constructor(options: EnhancedExecutorOptions = {}) {
    this.verbose = options.verbose || false;
    this.failureScenarios = options.failureScenarios || [];
    this.simulateLatency = options.simulateLatency ?? false;
    this.minLatency = options.minLatency ?? 50;
    this.maxLatency = options.maxLatency ?? 500;
    this.trackMetrics = options.trackMetrics ?? true;
  }

  async execute(spec: ScaffoldingSpec): Promise<ExecutionResult> {
    const executionId = this.generateExecutionId();
    const startTime = Date.now();

    this.log(`Starting execution for feature: ${spec.metadata.featureName}`);

    if (this.trackMetrics) {
      this.metrics.totalExecutions++;
    }

    const context: ExecutionContext = {
      executionId,
      featureId: spec.metadata.featureId,
      workingDirectory: process.cwd(),
      secrets: new Map(),
      variables: new Map(),
      stateLog: {
        executionId,
        featureId: spec.metadata.featureId,
        status: 'running',
        startedAt: new Date().toISOString(),
        steps: [],
      },
    };

    // Load and sanitize secrets
    if (spec.secrets) {
      const sanitizer = getGlobalSanitizer();
      for (const secretRef of spec.secrets) {
        const secretValue = `stub-${secretRef.name}`;
        context.secrets.set(secretRef.name, secretValue);
        sanitizer.registerSecret(secretValue);
      }
    }

    // Check preconditions
    if (spec.preconditions) {
      this.log('Checking preconditions...');
      const preconditionResults = await this.checkPreconditions(spec.preconditions);
      const failedPreconditions = preconditionResults.filter((r) => !r.passed);

      if (failedPreconditions.length > 0) {
        context.stateLog.status = 'failed';
        context.stateLog.completedAt = new Date().toISOString();

        if (this.trackMetrics) {
          this.metrics.failedExecutions++;
        }

        return {
          success: false,
          executionId,
          log: context.stateLog,
          artifacts: [],
          error: `Preconditions failed: ${failedPreconditions.map((r) => r.postconditionId).join(', ')}`,
        };
      }
    }

    // Execute steps with retry logic
    const stepResults: any[] = [];
    for (let i = 0; i < spec.steps.length; i++) {
      const step = spec.steps[i];
      this.log(`Executing step ${i + 1}/${spec.steps.length}: ${step.description}`);

      if (this.trackMetrics) {
        this.metrics.totalSteps++;
      }

      // Simulate retry logic
      const retryPolicy = this.getRetryPolicy(step);
      let stepResult: StepResult | null = null;
      let attempts = 0;

      while (attempts < retryPolicy.maxAttempts) {
        attempts++;
        const attemptKey = `${executionId}-${i}`;
        this.attemptCounts.set(attemptKey, attempts);

        if (attempts > 1 && this.trackMetrics) {
          this.metrics.retriedSteps++;
        }

        if (attempts > 1) {
          // Apply backoff
          const delay = this.calculateBackoff(
            attempts,
            retryPolicy.backoffStrategy,
            retryPolicy.initialDelay,
            retryPolicy.maxDelay
          );
          this.log(`Retry attempt ${attempts} after ${delay}ms delay`);
          await this.sleep(delay);
        }

        try {
          stepResult = await this.executeStep(step, i, context, attempts);

          if (stepResult.success) {
            break; // Success, no need to retry
          }

          if (attempts < retryPolicy.maxAttempts) {
            this.log(`Step ${i} failed, retrying...`);
          }
        } catch (error) {
          if (attempts >= retryPolicy.maxAttempts) {
            stepResult = {
              success: false,
              error: error instanceof Error ? error.message : String(error),
              duration: 0,
            };
          }
        }
      }

      if (!stepResult || !stepResult.success) {
        stepResults.push({
          stepIndex: i,
          success: false,
          startedAt: new Date().toISOString(),
          completedAt: new Date().toISOString(),
          duration: stepResult?.duration || 0,
          error: stepResult?.error || 'Unknown error',
          retryAttempts: attempts - 1,
        });

        context.stateLog.status = 'failed';
        context.stateLog.completedAt = new Date().toISOString();
        context.stateLog.steps = stepResults;

        if (this.trackMetrics) {
          this.metrics.failedExecutions++;
          this.metrics.totalDuration += Date.now() - startTime;
        }

        return {
          success: false,
          executionId,
          log: context.stateLog,
          artifacts: [],
          error: `Step ${i} failed after ${attempts} attempts: ${stepResult?.error}`,
        };
      }

      stepResults.push({
        stepIndex: i,
        success: true,
        startedAt: new Date().toISOString(),
        completedAt: new Date().toISOString(),
        duration: stepResult.duration,
        output: stepResult.output,
        retryAttempts: attempts - 1,
        skipped: stepResult.skipped || false,
      });
    }

    // Check postconditions
    const postconditionResults = await this.checkPostconditions(spec);
    const allPostconditionsPassed = postconditionResults.every((r) => r.passed);

    context.stateLog.status = allPostconditionsPassed ? 'completed' : 'failed';
    context.stateLog.completedAt = new Date().toISOString();
    context.stateLog.steps = stepResults;
    context.stateLog.postconditionResults = postconditionResults;

    const duration = Date.now() - startTime;

    if (this.trackMetrics) {
      if (allPostconditionsPassed) {
        this.metrics.successfulExecutions++;
      } else {
        this.metrics.failedExecutions++;
      }
      this.metrics.totalDuration += duration;
      this.updateAverageStepDuration();
    }

    this.log(`Execution ${allPostconditionsPassed ? 'completed successfully' : 'failed'} in ${duration}ms`);

    return {
      success: allPostconditionsPassed,
      executionId,
      log: context.stateLog,
      artifacts: this.generateArtifacts(spec),
    };
  }

  async executeStep(
    step: any,
    stepIndex: number,
    context: ExecutionContext,
    attempt: number
  ): Promise<StepResult> {
    const startTime = Date.now();

    // Check for failure scenario
    const shouldFail = this.shouldSimulateFailure(stepIndex, attempt);

    if (shouldFail) {
      const scenario = this.getFailureScenario(stepIndex);
      const delay = this.simulateLatency ? this.randomLatency() : 100;
      await this.sleep(delay);

      return {
        success: false,
        error: scenario?.errorMessage || 'Simulated failure',
        duration: Date.now() - startTime,
      };
    }

    // Simulate latency if enabled
    if (this.simulateLatency) {
      await this.sleep(this.randomLatency());
    } else {
      await this.sleep(100);
    }

    // Check idempotency
    if (step.type === 'command' && step.spec?.idempotencyCheck?.enabled) {
      // Simulate idempotency check passing
      this.log(`Idempotency check passed for step ${stepIndex}`);
    }

    return {
      success: true,
      output: `Successfully executed ${step.type} step`,
      duration: Date.now() - startTime,
    };
  }

  async checkPostconditions(spec: ScaffoldingSpec): Promise<PostconditionResult[]> {
    const results: PostconditionResult[] = [];

    for (const postcondition of spec.postconditions) {
      const shouldFail = this.failureScenarios.some(
        (s) => s.failureType === 'postcondition'
      );

      results.push({
        postconditionId: postcondition.id,
        passed: !shouldFail,
        message: shouldFail
          ? 'Simulated postcondition failure'
          : `Postcondition "${postcondition.description}" passed (enhanced stub)`,
        checkedAt: new Date().toISOString(),
      });
    }

    return results;
  }

  private async checkPreconditions(preconditions: any[]): Promise<PostconditionResult[]> {
    return preconditions.map((precondition) => ({
      postconditionId: precondition.id,
      passed: true,
      message: `Precondition "${precondition.description}" passed`,
      checkedAt: new Date().toISOString(),
    }));
  }

  async rollback(log: ExecutionStateLog): Promise<boolean> {
    this.log(`Rolling back execution ${log.executionId}`);

    // Simulate rollback with potential failure
    const shouldFail = this.failureScenarios.some((s) => s.failureType === 'error');

    if (shouldFail) {
      this.log('Rollback failed (simulated)');
      return false;
    }

    await this.sleep(200);
    this.log('Rollback completed successfully');
    return true;
  }

  private shouldSimulateFailure(stepIndex: number, attempt: number): boolean {
    for (const scenario of this.failureScenarios) {
      // Check if this scenario applies to this step
      if (scenario.stepIndex !== undefined && scenario.stepIndex !== stepIndex) {
        continue;
      }

      // Check if should recover after N attempts
      if (scenario.recoverAfterAttempts !== undefined) {
        return attempt <= scenario.recoverAfterAttempts;
      }

      // Random failure
      if (scenario.failureType === 'random') {
        return Math.random() < (scenario.failureRate || 0.1);
      }

      // Other failure types
      if (scenario.failureType === 'error' || scenario.failureType === 'timeout') {
        return true;
      }
    }

    return false;
  }

  private getFailureScenario(stepIndex: number): FailureScenario | undefined {
    return this.failureScenarios.find(
      (s) => s.stepIndex === undefined || s.stepIndex === stepIndex
    );
  }

  private getRetryPolicy(step: any): {
    maxAttempts: number;
    backoffStrategy: 'fixed' | 'exponential' | 'linear';
    initialDelay: number;
    maxDelay: number;
  } {
    if (step.type === 'command' && step.spec?.retryPolicy) {
      return {
        maxAttempts: step.spec.retryPolicy.maxAttempts || 1,
        backoffStrategy: step.spec.retryPolicy.backoffStrategy || 'exponential',
        initialDelay: step.spec.retryPolicy.initialDelay || 1000,
        maxDelay: step.spec.retryPolicy.maxDelay || 30000,
      };
    }

    return {
      maxAttempts: 1,
      backoffStrategy: 'fixed',
      initialDelay: 1000,
      maxDelay: 1000,
    };
  }

  private calculateBackoff(
    attempt: number,
    strategy: 'fixed' | 'exponential' | 'linear',
    initialDelay: number,
    maxDelay: number
  ): number {
    let delay: number;

    switch (strategy) {
      case 'exponential':
        delay = initialDelay * Math.pow(2, attempt - 1);
        break;
      case 'linear':
        delay = initialDelay * attempt;
        break;
      case 'fixed':
      default:
        delay = initialDelay;
        break;
    }

    return Math.min(delay, maxDelay);
  }

  private randomLatency(): number {
    return Math.floor(Math.random() * (this.maxLatency - this.minLatency) + this.minLatency);
  }

  private generateArtifacts(spec: ScaffoldingSpec): string[] {
    return spec.steps
      .filter((s) => s.type === 'file' || s.type === 'template')
      .map((s) => {
        if (s.type === 'template') {
          return s.outputPath;
        }
        if (s.type === 'file') {
          return s.operation.path;
        }
        return '';
      })
      .filter(Boolean);
  }

  private updateAverageStepDuration(): void {
    if (this.metrics.totalSteps > 0) {
      this.metrics.averageStepDuration = this.metrics.totalDuration / this.metrics.totalSteps;
    }
  }

  private generateExecutionId(): string {
    return `exec-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
  }

  private sleep(ms: number): Promise<void> {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }

  private log(message: string): void {
    if (this.verbose) {
      console.log(`[PtcExecutorEnhanced] ${message}`);
    }
  }

  /**
   * Get execution metrics
   */
  getMetrics(): ExecutionMetrics {
    return { ...this.metrics };
  }

  /**
   * Reset metrics
   */
  resetMetrics(): void {
    this.metrics = {
      totalExecutions: 0,
      successfulExecutions: 0,
      failedExecutions: 0,
      totalSteps: 0,
      retriedSteps: 0,
      averageStepDuration: 0,
      totalDuration: 0,
    };
    this.attemptCounts.clear();
  }

  /**
   * Get retry attempt counts
   */
  getAttemptCounts(): Map<string, number> {
    return new Map(this.attemptCounts);
  }
}

export interface ExecutionMetrics {
  totalExecutions: number;
  successfulExecutions: number;
  failedExecutions: number;
  totalSteps: number;
  retriedSteps: number;
  averageStepDuration: number;
  totalDuration: number;
}
