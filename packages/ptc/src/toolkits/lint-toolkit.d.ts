import { BaseToolkit, ToolDefinition, ToolResult } from './base-toolkit.js';
export declare class LintToolkit extends BaseToolkit {
    readonly name = "lint";
    readonly description = "Linting and type checking";
    private workingDir;
    constructor(workingDir: string);
    getTools(): ToolDefinition[];
    executeTool(toolName: string, params: any): Promise<ToolResult>;
    private eslint;
    private tscCheck;
}
//# sourceMappingURL=lint-toolkit.d.ts.map