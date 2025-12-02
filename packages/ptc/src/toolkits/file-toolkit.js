/**
 * File Toolkit - fs-extra wrapper for MCP
 *
 * Provides file operations: read, write, delete, glob
 */
import * as fs from 'fs-extra';
import { glob as globPkg } from 'glob';
import { join, dirname } from 'path';
import { BaseToolkit } from './base-toolkit.js';
export class FileToolkit extends BaseToolkit {
    name = 'file';
    description = 'File system operations (read, write, delete, glob)';
    workingDir;
    constructor(workingDir) {
        super();
        this.workingDir = workingDir;
    }
    getTools() {
        return [
            {
                name: 'file_read',
                description: 'Read a file from the workspace',
                inputSchema: {
                    type: 'object',
                    properties: {
                        path: {
                            type: 'string',
                            description: 'File path relative to workspace',
                            required: true,
                        },
                        encoding: {
                            type: 'string',
                            description: 'File encoding (default: utf-8)',
                        },
                    },
                    required: ['path'],
                },
            },
            {
                name: 'file_write',
                description: 'Write content to a file',
                inputSchema: {
                    type: 'object',
                    properties: {
                        path: {
                            type: 'string',
                            description: 'File path relative to workspace',
                            required: true,
                        },
                        content: {
                            type: 'string',
                            description: 'Content to write',
                            required: true,
                        },
                        encoding: {
                            type: 'string',
                            description: 'File encoding (default: utf-8)',
                        },
                    },
                    required: ['path', 'content'],
                },
            },
            {
                name: 'file_delete',
                description: 'Delete a file or directory',
                inputSchema: {
                    type: 'object',
                    properties: {
                        path: {
                            type: 'string',
                            description: 'File/directory path relative to workspace',
                            required: true,
                        },
                        recursive: {
                            type: 'boolean',
                            description: 'Delete recursively (for directories)',
                        },
                    },
                    required: ['path'],
                },
            },
            {
                name: 'file_glob',
                description: 'Find files matching a glob pattern',
                inputSchema: {
                    type: 'object',
                    properties: {
                        pattern: {
                            type: 'string',
                            description: 'Glob pattern (e.g., **/*.ts)',
                            required: true,
                        },
                        ignore: {
                            type: 'array',
                            description: 'Patterns to ignore',
                        },
                    },
                    required: ['pattern'],
                },
            },
            {
                name: 'file_exists',
                description: 'Check if a file or directory exists',
                inputSchema: {
                    type: 'object',
                    properties: {
                        path: {
                            type: 'string',
                            description: 'File/directory path relative to workspace',
                            required: true,
                        },
                    },
                    required: ['path'],
                },
            },
            {
                name: 'file_mkdir',
                description: 'Create a directory (including parents)',
                inputSchema: {
                    type: 'object',
                    properties: {
                        path: {
                            type: 'string',
                            description: 'Directory path relative to workspace',
                            required: true,
                        },
                    },
                    required: ['path'],
                },
            },
        ];
    }
    async executeTool(toolName, params) {
        try {
            switch (toolName) {
                case 'file_read':
                    return await this.fileRead(params);
                case 'file_write':
                    return await this.fileWrite(params);
                case 'file_delete':
                    return await this.fileDelete(params);
                case 'file_glob':
                    return await this.fileGlob(params);
                case 'file_exists':
                    return await this.fileExists(params);
                case 'file_mkdir':
                    return await this.fileMkdir(params);
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
    async fileRead(params) {
        const fullPath = join(this.workingDir, params.path);
        const encoding = params.encoding || 'utf-8';
        const content = await fs.readFile(fullPath, encoding);
        return {
            success: true,
            output: content,
            metadata: {
                path: params.path,
                size: content.length,
            },
        };
    }
    async fileWrite(params) {
        const fullPath = join(this.workingDir, params.path);
        const encoding = params.encoding || 'utf-8';
        // Ensure directory exists
        await fs.ensureDir(dirname(fullPath));
        // Write file
        await fs.writeFile(fullPath, params.content, encoding);
        return {
            success: true,
            output: { written: true },
            metadata: {
                path: params.path,
                size: params.content.length,
            },
        };
    }
    async fileDelete(params) {
        const fullPath = join(this.workingDir, params.path);
        const recursive = params.recursive !== false;
        if (recursive) {
            await fs.remove(fullPath);
        }
        else {
            await fs.unlink(fullPath);
        }
        return {
            success: true,
            output: { deleted: true },
            metadata: {
                path: params.path,
            },
        };
    }
    async fileGlob(params) {
        const files = await globPkg(params.pattern, {
            cwd: this.workingDir,
            ignore: params.ignore || ['node_modules/**', '.git/**'],
        });
        return {
            success: true,
            output: files,
            metadata: {
                pattern: params.pattern,
                count: files.length,
            },
        };
    }
    async fileExists(params) {
        const fullPath = join(this.workingDir, params.path);
        const exists = await fs.pathExists(fullPath);
        return {
            success: true,
            output: { exists },
            metadata: {
                path: params.path,
            },
        };
    }
    async fileMkdir(params) {
        const fullPath = join(this.workingDir, params.path);
        await fs.ensureDir(fullPath);
        return {
            success: true,
            output: { created: true },
            metadata: {
                path: params.path,
            },
        };
    }
}
//# sourceMappingURL=file-toolkit.js.map