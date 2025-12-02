/**
 * Test Toolkit - Jest test execution
 *
 * Provides: jest, coverage reporting
 */
import { execa } from 'execa';
import { BaseToolkit } from './base-toolkit.js';
export class TestToolkit extends BaseToolkit {
    name = 'test';
    description = 'Test execution and coverage reporting';
    workingDir;
    constructor(workingDir) {
        super();
        this.workingDir = workingDir;
    }
    getTools() {
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
    async executeTool(toolName, params) {
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
        }
        catch (error) {
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
    async testRun(params) {
        const args = [];
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
        const result = await execa('npx', ['jest', ...args], {
            cwd: this.workingDir,
            timeout: 300000, // 5 minutes
            reject: false, // Don't throw on non-zero exit
        });
        const success = result.exitCode === 0;
        return {
            success,
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
    async testCoverage(params) {
        const args = ['--coverage'];
        if (params.threshold) {
            args.push(`--coverageThreshold=${JSON.stringify({ global: { lines: params.threshold } })}`);
        }
        args.push('--ci');
        args.push('--passWithNoTests');
        const result = await execa('npx', ['jest', ...args], {
            cwd: this.workingDir,
            timeout: 300000, // 5 minutes
            reject: false,
        });
        const success = result.exitCode === 0;
        return {
            success,
            output: {
                stdout: result.stdout,
                stderr: result.stderr,
            },
            metadata: {
                duration: result.durationMs,
                threshold: params.threshold,
            },
        };
    }
}
//# sourceMappingURL=test-toolkit.js.map