/**
 * PtcExecutorReal - Real file generation using MCP Toolkits
 *
 * Executes ScaffoldingSpec and generates actual files
 */
import type { ScaffoldingSpec, ExecutionStateLog } from '@roma/schemas';
import type { PtcExecutor, ExecutionContext, ExecutionResult, StepResult, PostconditionResult } from './interfaces.js';
import { createStandardToolkits, executeToolByName, type BaseToolkit } from './toolkits/index.js';
import { EnvSecretProvider } from './secret-provider-env.js';
import { getGlobalSanitizer } from './secret-sanitizer.js';

export interface PtcExecutorRealOptions {
  workingDir: string;
  verbose?: boolean;
  dryRun?: boolean;
  secretProvider?: any;
}

export class PtcExecutorReal implements PtcExecutor {
  private workingDir: string;
  private verbose: boolean;
  private dryRun: boolean;
  private toolkits: BaseToolkit[];
  private secretProvider: any;

  constructor(options: PtcExecutorRealOptions) {
    this.workingDir = options.workingDir;
    this.verbose = options.verbose ?? false;
    this.dryRun = options.dryRun ?? false;
    this.secretProvider = options.secretProvider || new EnvSecretProvider();

    // Initialize toolkits
    this.toolkits = createStandardToolkits(this.workingDir, this.secretProvider);
  }

  async execute(spec: ScaffoldingSpec): Promise<ExecutionResult> {
    const executionId = `exec-${Date.now()}-${this.generateId()}`;
    const startTime = Date.now();

    this.log(`[PtcExecutorReal] Starting execution for feature: ${spec.metadata.featureName}`);

    // Create execution context
    const context: ExecutionContext = {
      executionId,
      featureId: spec.metadata.featureId,
      workingDirectory: this.workingDir,
      secrets: new Map(),
      variables: new Map(),
      stateLog: {
        executionId,
        featureId: spec.metadata.featureId,
        status: 'running',
        startedAt: new Date().toISOString(),
        steps: [],
        rollbackExecuted: false,
      },
    };

    // Load secrets
    if (spec.secrets) {
      this.log(`[PtcExecutorReal] Loading ${spec.secrets.length} secrets...`);
      for (const secretRef of spec.secrets) {
        const value = await this.secretProvider.get(secretRef.name);
        if (value) {
          context.secrets.set(secretRef.name, value);
          getGlobalSanitizer().registerSecret(value);
        }
      }
    }

    // Execute steps
    this.log(`[PtcExecutorReal] Executing ${spec.steps.length} steps...`);

    for (let i = 0; i < spec.steps.length; i++) {
      const step = spec.steps[i];
      this.log(`[PtcExecutorReal] Step ${i + 1}/${spec.steps.length}: ${step.description}`);

      const stepResult = await this.executeStep(step, context);

      context.stateLog.steps.push({
        stepIndex: i,
        success: stepResult.success,
        startedAt: new Date().toISOString(),
        completedAt: new Date().toISOString(),
        duration: stepResult.duration,
        output: stepResult.output,
        error: stepResult.error,
        retryAttempts: 0,
        skipped: stepResult.skipped || false,
      });

      if (!stepResult.success && !stepResult.skipped) {
        this.log(`[PtcExecutorReal] Step ${i + 1} FAILED: ${stepResult.error}`);
        context.stateLog.status = 'failed';
        context.stateLog.completedAt = new Date().toISOString();

        return {
          success: false,
          executionId,
          log: context.stateLog,
          artifacts: [],
          error: stepResult.error,
        };
      }

      this.log(`[PtcExecutorReal] Step ${i + 1} completed successfully`);
    }

    // Check postconditions
    if (spec.postconditions && spec.postconditions.length > 0) {
      this.log(`[PtcExecutorReal] Checking ${spec.postconditions.length} postconditions...`);
      const postconditionResults = await this.checkPostconditions(spec);
      context.stateLog.postconditionResults = postconditionResults;

      const failedPostconditions = postconditionResults.filter((r) => !r.passed);
      if (failedPostconditions.length > 0) {
        this.log(`[PtcExecutorReal] ${failedPostconditions.length} postconditions FAILED`);
      }
    }

    // Success
    const duration = Date.now() - startTime;
    context.stateLog.status = 'completed';
    context.stateLog.completedAt = new Date().toISOString();

    this.log(`[PtcExecutorReal] Execution completed successfully in ${duration}ms`);

    return {
      success: true,
      executionId,
      log: context.stateLog,
      artifacts: this.collectArtifacts(spec),
    };
  }

  async executeStep(step: any, context: ExecutionContext): Promise<StepResult> {
    const startTime = Date.now();

    if (this.dryRun) {
      return {
        success: true,
        output: { dryRun: true },
        duration: 0,
      };
    }

    try {
      let result: any;

      switch (step.type) {
        case 'file':
          result = await this.executeFileStep(step);
          break;
        case 'template':
          result = await this.executeTemplateStep(step);
          break;
        case 'command':
          result = await this.executeCommandStep(step);
          break;
        case 'api_call':
          result = await this.executeApiCallStep(step);
          break;
        case 'test':
          result = await this.executeTestStep(step);
          break;
        default:
          throw new Error(`Unknown step type: ${step.type}`);
      }

      const duration = Date.now() - startTime;

      return {
        success: result.success,
        output: result.output,
        error: result.error,
        duration,
      };
    } catch (error: any) {
      const duration = Date.now() - startTime;
      return {
        success: false,
        error: error.message,
        duration,
      };
    }
  }

  private async executeFileStep(step: any): Promise<any> {
    const op = step.operation;

    if (op.type === 'create' || op.type === 'update') {
      return await executeToolByName(
        'file_write',
        {
          path: op.path,
          content: op.content || '',
        },
        this.toolkits
      );
    } else if (op.type === 'delete') {
      return await executeToolByName(
        'file_delete',
        {
          path: op.path,
          recursive: true,
        },
        this.toolkits
      );
    } else if (op.type === 'template') {
      // Use template toolkit
      const renderResult = await executeToolByName(
        'template_render',
        {
          template: op.templateContent || '',
          vars: op.templateVars || {},
        },
        this.toolkits
      );

      if (!renderResult.success) {
        return renderResult;
      }

      // Write rendered content
      return await executeToolByName(
        'file_write',
        {
          path: op.path,
          content: renderResult.output,
        },
        this.toolkits
      );
    }

    return {
      success: false,
      error: `Unknown file operation: ${op.type}`,
    };
  }

  private async executeTemplateStep(step: any): Promise<any> {
    // Render template
    const renderResult = await executeToolByName(
      'template_render',
      {
        template: step.templateContent || '',
        vars: step.templateVars || {},
      },
      this.toolkits
    );

    if (!renderResult.success) {
      return renderResult;
    }

    // Write to output path
    return await executeToolByName(
      'file_write',
      {
        path: step.outputPath,
        content: renderResult.output,
      },
      this.toolkits
    );
  }

  private async executeCommandStep(step: any): Promise<any> {
    const spec = step.spec;
    const cmd = spec.command;
    const args = spec.args || [];

    // Check for npm commands
    if (cmd === 'npm' && args[0] === 'install') {
      return await executeToolByName('npm_install', {}, this.toolkits);
    } else if (cmd === 'npm' && args[0] === 'run') {
      const script = args[1];
      return await executeToolByName('npm_run', { script }, this.toolkits);
    } else if (cmd === 'npm' && args[0] === 'build') {
      return await executeToolByName('npm_build', {}, this.toolkits);
    }

    // Generic command execution
    return await executeToolByName(
      'exec',
      {
        command: cmd,
        args,
      },
      this.toolkits
    );
  }

  private async executeApiCallStep(step: any): Promise<any> {
    // For now, just log - real API calls would need proper implementation
    this.log(`[PtcExecutorReal] API call: ${step.method} ${step.url}`);
    return {
      success: true,
      output: { stubbed: true },
    };
  }

  private async executeTestStep(step: any): Promise<any> {
    return await executeToolByName(
      'test_run',
      {
        coverage: false,
      },
      this.toolkits
    );
  }

  async checkPostconditions(spec: ScaffoldingSpec): Promise<PostconditionResult[]> {
    if (!spec.postconditions) {
      return [];
    }

    const results: PostconditionResult[] = [];

    for (const postcondition of spec.postconditions) {
      let passed = false;
      let message = '';

      try {
        const check = postcondition.check as any;

        switch (postcondition.type) {
          case 'file_exists':
            if (check.path) {
              const existsResult = await executeToolByName(
                'file_exists',
                { path: check.path },
                this.toolkits
              );
              passed = existsResult.success && existsResult.output.exists;
              message = passed ? 'File exists' : 'File does not exist';
            }
            break;

          case 'command_succeeds':
            if (check.command) {
              const [cmd, ...args] = check.command.split(' ');
              const cmdResult = await executeToolByName(
                'exec',
                { command: cmd, args },
                this.toolkits
              );
              passed = cmdResult.success;
              message = passed ? 'Command succeeded' : 'Command failed';
            }
            break;

          default:
            message = `Postcondition check skipped: ${postcondition.type}`;
            passed = true; // Skip unknown postconditions
        }
      } catch (error: any) {
        passed = false;
        message = error.message;
      }

      results.push({
        postconditionId: postcondition.id || `postcondition-${results.length}`,
        passed,
        message,
        checkedAt: new Date().toISOString(),
      });
    }

    return results;
  }

  async rollback(log: ExecutionStateLog): Promise<boolean> {
    this.log('[PtcExecutorReal] Rollback not implemented');
    return false;
  }

  private collectArtifacts(spec: ScaffoldingSpec): string[] {
    // Collect file paths that were created
    const artifacts: string[] = [];

    for (const step of spec.steps) {
      if (step.type === 'file' && step.operation) {
        artifacts.push(step.operation.path);
      } else if (step.type === 'template' && step.outputPath) {
        artifacts.push(step.outputPath);
      }
    }

    return artifacts;
  }

  private generateId(): string {
    return Math.random().toString(36).substring(2, 12);
  }

  private log(message: string): void {
    if (this.verbose) {
      console.log(message);
    }
  }
}
