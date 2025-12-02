import { BaseToolkit, ToolDefinition, ToolResult } from './base-toolkit.js';
export declare class GitToolkit extends BaseToolkit {
    readonly name = "git";
    readonly description = "Git version control operations";
    private git;
    private workingDir;
    constructor(workingDir: string);
    getTools(): ToolDefinition[];
    executeTool(toolName: string, params: any): Promise<ToolResult>;
    private gitInit;
    private gitAdd;
    private gitCommit;
    private gitStatus;
    private gitLog;
    private gitBranch;
}
//# sourceMappingURL=git-toolkit.d.ts.map