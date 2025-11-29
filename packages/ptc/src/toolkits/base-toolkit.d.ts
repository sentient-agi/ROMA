/**
 * Base MCP Toolkit Interface
 *
 * All toolkits must implement this interface to be MCP-compatible
 */
export interface ToolDefinition {
    name: string;
    description: string;
    inputSchema: {
        type: 'object';
        properties: Record<string, {
            type: string;
            description: string;
            required?: boolean;
        }>;
        required?: string[];
    };
}
export interface ToolResult {
    success: boolean;
    output?: any;
    error?: string;
    metadata?: Record<string, any>;
}
export declare abstract class BaseToolkit {
    abstract readonly name: string;
    abstract readonly description: string;
    /**
     * Get all tool definitions provided by this toolkit
     */
    abstract getTools(): ToolDefinition[];
    /**
     * Execute a tool by name
     */
    abstract executeTool(toolName: string, params: any): Promise<ToolResult>;
    /**
     * Initialize the toolkit (optional)
     */
    initialize(): Promise<void>;
    /**
     * Cleanup resources (optional)
     */
    cleanup(): Promise<void>;
}
//# sourceMappingURL=base-toolkit.d.ts.map