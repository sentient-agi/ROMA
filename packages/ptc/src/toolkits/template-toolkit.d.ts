import { BaseToolkit, ToolDefinition, ToolResult } from './base-toolkit.js';
export declare class TemplateToolkit extends BaseToolkit {
    readonly name = "template";
    readonly description = "Template rendering with EJS";
    private workingDir;
    constructor(workingDir: string);
    getTools(): ToolDefinition[];
    executeTool(toolName: string, params: any): Promise<ToolResult>;
    private templateRender;
    private templateRenderFile;
}
//# sourceMappingURL=template-toolkit.d.ts.map