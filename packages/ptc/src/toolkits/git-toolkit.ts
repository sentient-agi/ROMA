/**
 * Git Toolkit - simple-git wrapper for MCP
 *
 * Provides git operations: init, commit, branch, push
 */
import { simpleGit, SimpleGit } from 'simple-git';
import { BaseToolkit, ToolDefinition, ToolResult } from './base-toolkit.js';

export class GitToolkit extends BaseToolkit {
  readonly name = 'git';
  readonly description = 'Git version control operations';

  private git: SimpleGit;
  private workingDir: string;

  constructor(workingDir: string) {
    super();
    this.workingDir = workingDir;
    this.git = simpleGit(workingDir);
  }

  getTools(): ToolDefinition[] {
    return [
      {
        name: 'git_init',
        description: 'Initialize a git repository',
        inputSchema: {
          type: 'object',
          properties: {
            defaultBranch: {
              type: 'string',
              description: 'Default branch name (default: main)',
            },
          },
        },
      },
      {
        name: 'git_add',
        description: 'Stage files for commit',
        inputSchema: {
          type: 'object',
          properties: {
            files: {
              type: 'array',
              description: 'Files to stage (default: ["."])',
            },
          },
        },
      },
      {
        name: 'git_commit',
        description: 'Commit staged changes',
        inputSchema: {
          type: 'object',
          properties: {
            message: {
              type: 'string',
              description: 'Commit message',
              required: true,
            },
            author: {
              type: 'object',
              description: 'Author info (name, email)',
            },
          },
          required: ['message'],
        },
      },
      {
        name: 'git_status',
        description: 'Get git status',
        inputSchema: {
          type: 'object',
          properties: {},
        },
      },
      {
        name: 'git_log',
        description: 'Get git commit history',
        inputSchema: {
          type: 'object',
          properties: {
            maxCount: {
              type: 'number',
              description: 'Max commits to return (default: 10)',
            },
          },
        },
      },
      {
        name: 'git_branch',
        description: 'Create or list branches',
        inputSchema: {
          type: 'object',
          properties: {
            name: {
              type: 'string',
              description: 'Branch name (omit to list)',
            },
            create: {
              type: 'boolean',
              description: 'Create new branch',
            },
          },
        },
      },
    ];
  }

  async executeTool(toolName: string, params: any): Promise<ToolResult> {
    try {
      switch (toolName) {
        case 'git_init':
          return await this.gitInit(params);
        case 'git_add':
          return await this.gitAdd(params);
        case 'git_commit':
          return await this.gitCommit(params);
        case 'git_status':
          return await this.gitStatus(params);
        case 'git_log':
          return await this.gitLog(params);
        case 'git_branch':
          return await this.gitBranch(params);
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
      };
    }
  }

  private async gitInit(params: any): Promise<ToolResult> {
    const defaultBranch = params.defaultBranch || 'main';
    await this.git.init();
    await this.git.raw(['branch', '-M', defaultBranch]);

    return {
      success: true,
      output: { initialized: true, branch: defaultBranch },
      metadata: {
        workingDir: this.workingDir,
      },
    };
  }

  private async gitAdd(params: any): Promise<ToolResult> {
    const files = params.files || ['.'];
    await this.git.add(files);

    return {
      success: true,
      output: { staged: files },
      metadata: {
        filesCount: files.length,
      },
    };
  }

  private async gitCommit(params: any): Promise<ToolResult> {
    let options: any = {};

    if (params.author) {
      options['--author'] = `${params.author.name} <${params.author.email}>`;
    }

    const result = await this.git.commit(params.message, undefined, options);

    return {
      success: true,
      output: {
        commit: result.commit,
        summary: result.summary,
      },
      metadata: {
        branch: result.branch,
      },
    };
  }

  private async gitStatus(params: any): Promise<ToolResult> {
    const status = await this.git.status();

    return {
      success: true,
      output: status,
      metadata: {
        clean: status.isClean(),
      },
    };
  }

  private async gitLog(params: any): Promise<ToolResult> {
    const maxCount = params.maxCount || 10;
    const log = await this.git.log({ maxCount });

    return {
      success: true,
      output: log.all,
      metadata: {
        count: log.all.length,
      },
    };
  }

  private async gitBranch(params: any): Promise<ToolResult> {
    if (params.create && params.name) {
      await this.git.branch([params.name]);
      return {
        success: true,
        output: { created: params.name },
      };
    } else {
      const branches = await this.git.branchLocal();
      return {
        success: true,
        output: branches,
        metadata: {
          current: branches.current,
        },
      };
    }
  }
}
