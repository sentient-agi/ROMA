import { BaseToolkit, ToolDefinition, ToolResult } from './base-toolkit.js';
export declare class FileToolkit extends BaseToolkit {
    readonly name = "file";
    readonly description = "File system operations (read, write, delete, glob)";
    private workingDir;
    constructor(workingDir: string);
    getTools(): ToolDefinition[];
    executeTool(toolName: string, params: any): Promise<ToolResult>;
    private fileRead;
    private fileWrite;
    private fileDelete;
    private fileGlob;
    private fileExists;
    private fileMkdir;
}
//# sourceMappingURL=file-toolkit.d.ts.map