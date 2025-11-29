/**
 * Lint Toolkit - ESLint and TypeScript type checking
 *
 * Provides: eslint, tsc --noEmit
 */
import { execa } from 'execa';
import { BaseToolkit, ToolDefinition, ToolResult } from './base-toolkit.js';

export class LintToolkit extends BaseToolkit {
  readonly name = 'lint';
  readonly description = 'Linting and type checking';

  private workingDir: string;

  constructor(workingDir: string) {
    super();
    this.workingDir = workingDir;
  }

  getTools(): ToolDefinition[] {
    return [
      {
        name: 'eslint',
        description: 'Run ESLint on files',
        inputSchema: {
          type: 'object',
          properties: {
            files: {
              type: 'array',
              description: 'Files or patterns to lint',
            },
            fix: {
              type: 'boolean',
              description: 'Automatically fix problems',
            },
          },
        },
      },
      {
        name: 'tsc_check',
        description: 'Run TypeScript type checking',
        inputSchema: {
          type: 'object',
          properties: {
            project: {
              type: 'string',
              description: 'Path to tsconfig.json',
            },
          },
        },
      },
    ];
  }

  async executeTool(toolName: string, params: any): Promise<ToolResult> {
    try {
      switch (toolName) {
        case 'eslint':
          return await this.eslint(params);
        case 'tsc_check':
          return await this.tscCheck(params);
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

  private async eslint(params: any): Promise<ToolResult> {
    const args: string[] = [];

    if (params.files && params.files.length > 0) {
      args.push(...params.files);
    } else {
      args.push('.');
    }

    if (params.fix) {
      args.push('--fix');
    }

    const startTime = Date.now();
    const result = await execa('npx', ['eslint', ...args], {
      cwd: this.workingDir,
      timeout: 120000, // 2 minutes
      reject: false, // Don't throw on linting errors
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

  private async tscCheck(params: any): Promise<ToolResult> {
    const args: string[] = ['--noEmit'];

    if (params.project) {
      args.push('--project', params.project);
    }

    const startTime = Date.now();
    const result = await execa('npx', ['tsc', ...args], {
      cwd: this.workingDir,
      timeout: 120000, // 2 minutes
      reject: false, // Don't throw on type errors
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
}
