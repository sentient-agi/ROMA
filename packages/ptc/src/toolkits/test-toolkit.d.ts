import { BaseToolkit, ToolDefinition, ToolResult } from './base-toolkit.js';
export declare class TestToolkit extends BaseToolkit {
    readonly name = "test";
    readonly description = "Test execution and coverage reporting";
    private workingDir;
    constructor(workingDir: string);
    getTools(): ToolDefinition[];
    executeTool(toolName: string, params: any): Promise<ToolResult>;
    private testRun;
    private testCoverage;
}
//# sourceMappingURL=test-toolkit.d.ts.map