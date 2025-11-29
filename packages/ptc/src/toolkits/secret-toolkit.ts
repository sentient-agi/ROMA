/**
 * Secret Toolkit - Secret access with sanitization
 *
 * Provides: getSecret (sanitized in logs)
 */
import { BaseToolkit, ToolDefinition, ToolResult } from './base-toolkit.js';
import { SecretProvider } from '../src/interfaces.js';
import { getGlobalSanitizer } from '../src/secret-sanitizer.js';

export class SecretToolkit extends BaseToolkit {
  readonly name = 'secret';
  readonly description = 'Secure secret access with automatic sanitization';

  private secretProvider: SecretProvider;

  constructor(secretProvider: SecretProvider) {
    super();
    this.secretProvider = secretProvider;
  }

  getTools(): ToolDefinition[] {
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

  async executeTool(toolName: string, params: any): Promise<ToolResult> {
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
    } catch (error: any) {
      return {
        success: false,
        error: error.message,
      };
    }
  }

  private async getSecret(params: any): Promise<ToolResult> {
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

  private async listSecrets(params: any): Promise<ToolResult> {
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
