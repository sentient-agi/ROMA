/**
 * Secret Toolkit - Secret access with sanitization
 *
 * Provides: getSecret (sanitized in logs)
 */
import { BaseToolkit, ToolDefinition, ToolResult } from './base-toolkit.js';
import { SecretProvider } from '../src/interfaces.js';
export declare class SecretToolkit extends BaseToolkit {
    readonly name = "secret";
    readonly description = "Secure secret access with automatic sanitization";
    private secretProvider;
    constructor(secretProvider: SecretProvider);
    getTools(): ToolDefinition[];
    executeTool(toolName: string, params: any): Promise<ToolResult>;
    private getSecret;
    private listSecrets;
}
//# sourceMappingURL=secret-toolkit.d.ts.map