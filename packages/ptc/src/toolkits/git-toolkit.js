/**
 * Git Toolkit - simple-git wrapper for MCP
 *
 * Provides git operations: init, commit, branch, push
 */
import { simpleGit } from 'simple-git';
import { BaseToolkit } from './base-toolkit.js';
export class GitToolkit extends BaseToolkit {
    name = 'git';
    description = 'Git version control operations';
    git;
    workingDir;
    constructor(workingDir) {
        super();
        this.workingDir = workingDir;
        this.git = simpleGit(workingDir);
    }
    getTools() {
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
    async executeTool(toolName, params) {
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
        }
        catch (error) {
            return {
                success: false,
                error: error.message,
            };
        }
    }
    async gitInit(params) {
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
    async gitAdd(params) {
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
    async gitCommit(params) {
        let options = {};
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
    async gitStatus(params) {
        const status = await this.git.status();
        return {
            success: true,
            output: status,
            metadata: {
                clean: status.isClean(),
            },
        };
    }
    async gitLog(params) {
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
    async gitBranch(params) {
        if (params.create && params.name) {
            await this.git.branch([params.name]);
            return {
                success: true,
                output: { created: params.name },
            };
        }
        else {
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
//# sourceMappingURL=git-toolkit.js.map