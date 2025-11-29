/**
 * Secret Toolkit - Secret access with sanitization
 *
 * Provides: getSecret (sanitized in logs)
 */
import { BaseToolkit } from './base-toolkit.js';
import { getGlobalSanitizer } from '../src/secret-sanitizer.js';
export class SecretToolkit extends BaseToolkit {
    name = 'secret';
    description = 'Secure secret access with automatic sanitization';
    secretProvider;
    constructor(secretProvider) {
        super();
        this.secretProvider = secretProvider;
    }
    getTools() {
        return [
            {
                name: 'get_secret',
                description: 'Retrieve a secret value (automatically sanitized in logs)',
                inputSchema: {
                    type: 'object',
                    properties: {
                        key: {
                            type: 'string',
                            description: 'Secret key/name',
                            required: true,
                        },
                    },
                    required: ['key'],
                },
            },
            {
                name: 'list_secrets',
                description: 'List available secret keys (values not shown)',
                inputSchema: {
                    type: 'object',
                    properties: {},
                },
            },
        ];
    }
    async executeTool(toolName, params) {
        try {
            switch (toolName) {
                case 'get_secret':
                    return await this.getSecret(params);
                case 'list_secrets':
                    return await this.listSecrets(params);
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
            };
        }
    }
    async getSecret(params) {
        const value = await this.secretProvider.get(params.key);
        if (value === null) {
            return {
                success: false,
                error: `Secret not found: ${params.key}`,
            };
        }
        // Register secret with global sanitizer
        const sanitizer = getGlobalSanitizer();
        sanitizer.registerSecret(value);
        return {
            success: true,
            output: value, // Actual secret value (will be sanitized in logs)
            metadata: {
                key: params.key,
                length: value.length,
            },
        };
    }
    async listSecrets(params) {
        const keys = await this.secretProvider.list();
        return {
            success: true,
            output: keys,
            metadata: {
                count: keys.length,
            },
        };
    }
}
//# sourceMappingURL=secret-toolkit.js.map