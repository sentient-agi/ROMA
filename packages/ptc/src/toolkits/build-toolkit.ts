/**
 * Build Toolkit - npm/build operations via execa
 *
 * Provides: npm install, npm build, npm run
 */
import { execa } from 'execa';
import { BaseToolkit, ToolDefinition, ToolResult } from './base-toolkit.js';

export class BuildToolkit extends BaseToolkit {
  readonly name = 'build';
  readonly description = 'Build and package management operations (npm)';

  private workingDir: string;

  constructor(workingDir: string) {
    super();
    this.workingDir = workingDir;
  }

  getTools(): ToolDefinition[] {
    return [
      {
        name: 'npm_install',
        description: 'Install npm dependencies',
        inputSchema: {
          type: 'object',
          properties: {
            packages: {
              type: 'array',
              description: 'Specific packages to install (omit for package.json)',
            },
            dev: {
              type: 'boolean',
              description: 'Install as devDependencies',
            },
            production: {
              type: 'boolean',
              description: 'Production install (no devDependencies)',
            },
          },
        },
      },
      {
        name: 'npm_run',
        description: 'Run an npm script',
        inputSchema: {
          type: 'object',
          properties: {
            script: {
              type: 'string',
              description: 'Script name from package.json',
              required: true,
            },
            args: {
              type: 'array',
              description: 'Additional arguments',
            },
          },
          required: ['script'],
        },
      },
      {
        name: 'npm_build',
        description: 'Run npm build',
        inputSchema: {
          type: 'object',
          properties: {
            production: {
              type: 'boolean',
              description: 'Production build',
            },
          },
        },
      },
      {
        name: 'exec',
        description: 'Execute a shell command',
        inputSchema: {
          type: 'object',
          properties: {
            command: {
              type: 'string',
              description: 'Command to execute',
              required: true,
            },
            args: {
              type: 'array',
              description: 'Command arguments',
            },
            timeout: {
              type: 'number',
              description: 'Timeout in milliseconds',
            },
          },
          required: ['command'],
        },
      },
    ];
  }

  async executeTool(toolName: string, params: any): Promise<ToolResult> {
    try {
      switch (toolName) {
        case 'npm_install':
          return await this.npmInstall(params);
        case 'npm_run':
          return await this.npmRun(params);
        case 'npm_build':
          return await this.npmBuild(params);
        case 'exec':
          return await this.exec(params);
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

  private async npmInstall(params: any): Promise<ToolResult> {
    const args: string[] = ['install'];

    if (params.packages && params.packages.length > 0) {
      args.push(...params.packages);
    }

    if (params.dev) {
      args.push('--save-dev');
    }

    if (params.production) {
      args.push('--production');
    }

    const result = await execa('npm', args, {
      cwd: this.workingDir,
      timeout: 300000, // 5 minutes
    });

    return {
      success: true,
      output: {
        stdout: result.stdout,
        stderr: result.stderr,
      },
      metadata: {
        duration: result.durationMs,
        exitCode: result.exitCode,
      },
    };
  }

  private async npmRun(params: any): Promise<ToolResult> {
    const args: string[] = ['run', params.script];

    if (params.args && params.args.length > 0) {
      args.push('--', ...params.args);
    }

    const result = await execa('npm', args, {
      cwd: this.workingDir,
      timeout: 300000, // 5 minutes
    });

    return {
      success: true,
      output: {
        stdout: result.stdout,
        stderr: result.stderr,
      },
      metadata: {
        duration: result.durationMs,
        script: params.script,
      },
    };
  }

  private async npmBuild(params: any): Promise<ToolResult> {
    const args: string[] = ['run', 'build'];

    if (params.production) {
      args.push('--', '--production');
    }

    const result = await execa('npm', args, {
      cwd: this.workingDir,
      timeout: 600000, // 10 minutes
    });

    return {
      success: true,
      output: {
        stdout: result.stdout,
        stderr: result.stderr,
      },
      metadata: {
        duration: result.durationMs,
      },
    };
  }

  private async exec(params: any): Promise<ToolResult> {
    const args = params.args || [];
    const timeout = params.timeout || 60000; // 1 minute default

    const result = await execa(params.command, args, {
      cwd: this.workingDir,
      timeout,
    });

    return {
      success: true,
      output: {
        stdout: result.stdout,
        stderr: result.stderr,
      },
      metadata: {
        duration: result.durationMs,
        exitCode: result.exitCode,
      },
    };
  }
}
