/**
 * MCP Toolkits - Exports all available toolkits
 */
export { BaseToolkit, type ToolDefinition, type ToolResult } from './base-toolkit.js';
export { FileToolkit } from './file-toolkit.js';
export { GitToolkit } from './git-toolkit.js';
export { BuildToolkit } from './build-toolkit.js';
export { TestToolkit } from './test-toolkit.js';
export { TemplateToolkit } from './template-toolkit.js';
export { LintToolkit } from './lint-toolkit.js';
export { SecretToolkit } from './secret-toolkit.js';
import { BaseToolkit } from './base-toolkit.js';
import { SecretProvider } from '../src/interfaces.js';
/**
 * Create all standard toolkits for a workspace
 */
export declare function createStandardToolkits(workingDir: string, secretProvider: SecretProvider): BaseToolkit[];
/**
 * Get all available tools from toolkits
 */
export declare function getAllToolDefinitions(toolkits: BaseToolkit[]): any[];
/**
 * Execute a tool by name across all toolkits
 */
export declare function executeToolByName(toolName: string, params: any, toolkits: BaseToolkit[]): Promise<import("./base-toolkit.js").ToolResult>;
//# sourceMappingURL=index.d.ts.map