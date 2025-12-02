/**
 * Test Toolkit - Jest test execution
 *
 * Provides: jest, coverage reporting
 */
import { execa } from 'execa';
import { BaseToolkit, ToolDefinition, ToolResult } from './base-toolkit.js';

export class TestToolkit extends BaseToolkit {
  readonly name = 'test';
  readonly description = 'Test execution and coverage reporting';

  private workingDir: string;

  constructor(workingDir: string) {
    super();
    this.workingDir = workingDir;
  }

  getTools(): ToolDefinition[] {
    return [
      {
        name: 'test_run',
        description: 'Run tests with Jest',
        inputSchema: {
          type: 'object',
          properties: {
            pattern: {
              type: 'string',
              description: 'Test file pattern (e.g., auth.test.ts)',
            },
            coverage: {
              type: 'boolean',
              description: 'Generate coverage report',
            },
            watch: {
              type: 'boolean',
              description: 'Watch mode',
            },
          },
        },
      },
      {
        name: 'test_coverage',
        description: 'Generate test coverage report',
        inputSchema: {
          type: 'object',
          properties: {
            threshold: {
              type: 'number',
              description: 'Coverage threshold percentage',
            },
          },
        },
      },
    ];
  }

  async executeTool(toolName: string, params: any): Promise<ToolResult> {
    try {
      switch (toolName) {
        case 'test_run':
          return await this.testRun(params);
        case 'test_coverage':
          return await this.testCoverage(params);
        default:
          return {
            success: false,
            error: `Unknown tool: ${toolName}`,
          };
      }
    } catch (error: any) {
      return {
        success: false,
        error: error.message,
        metadata: {
          stderr: error.stderr,
          exitCode: error.exitCode,
        },
      };
    }
  }

  private async testRun(params: any): Promise<ToolResult> {
    const args: string[] = [];

    if (params.pattern) {
      args.push(params.pattern);
    }

    if (params.coverage) {
      args.push('--coverage');
    }

    if (params.watch) {
      args.push('--watch');
    }

    // Add CI mode by default (no interactive)
    args.push('--ci');
    args.push('--passWithNoTests');

    const startTime = Date.now();
    const result = await execa('npx', ['jest', ...args], {
      cwd: this.workingDir,
      timeout: 300000, // 5 minutes
      reject: false, // Don't throw on non-zero exit
    });
    const duration = Date.now() - startTime;

    const success = result.exitCode === 0;

    return {
      success,
      output: {
        stdout: result.stdout,
        stderr: result.stderr,
      },
      metadata: {
        duration,
        exitCode: result.exitCode,
      },
    };
  }

  private async testCoverage(params: any): Promise<ToolResult> {
    const args: string[] = ['--coverage'];

    if (params.threshold) {
      args.push(`--coverageThreshold=${JSON.stringify({ global: { lines: params.threshold } })}`);
    }

    args.push('--ci');
    args.push('--passWithNoTests');

    const startTime = Date.now();
    const result = await execa('npx', ['jest', ...args], {
      cwd: this.workingDir,
      timeout: 300000, // 5 minutes
      reject: false,
    });
    const duration = Date.now() - startTime;

    const success = result.exitCode === 0;

    return {
      success,
      output: {
        stdout: result.stdout,
        stderr: result.stderr,
      },
      metadata: {
        duration,
        threshold: params.threshold,
      },
    };
  }
}
