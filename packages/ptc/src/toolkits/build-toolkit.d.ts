import { BaseToolkit, ToolDefinition, ToolResult } from './base-toolkit.js';
export declare class BuildToolkit extends BaseToolkit {
    readonly name = "build";
    readonly description = "Build and package management operations (npm)";
    private workingDir;
    constructor(workingDir: string);
    getTools(): ToolDefinition[];
    executeTool(toolName: string, params: any): Promise<ToolResult>;
    private npmInstall;
    private npmRun;
    private npmBuild;
    private exec;
}
//# sourceMappingURL=build-toolkit.d.ts.map