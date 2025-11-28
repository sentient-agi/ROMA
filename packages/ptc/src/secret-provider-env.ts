/**
 * Environment-based secret provider
 *
 * Reads secrets from environment variables or .env files
 */
import type { SecretProvider } from './interfaces.js';

export class EnvSecretProvider implements SecretProvider {
  readonly name = 'env';
  private secrets: Map<string, string>;

  constructor() {
    this.secrets = new Map();
    this.loadFromEnv();
  }

  private loadFromEnv(): void {
    // Load from process.env
    for (const [key, value] of Object.entries(process.env)) {
      if (value !== undefined) {
        this.secrets.set(key, value);
      }
    }
  }

  async get(key: string): Promise<string | null> {
    return this.secrets.get(key) || null;
  }

  async set(key: string, value: string): Promise<void> {
    this.secrets.set(key, value);
    process.env[key] = value;
  }

  async delete(key: string): Promise<void> {
    this.secrets.delete(key);
    delete process.env[key];
  }

  async list(): Promise<string[]> {
    return Array.from(this.secrets.keys());
  }

  /**
   * Get a secret or throw if not found
   */
  async getRequired(key: string): Promise<string> {
    const value = await this.get(key);
    if (value === null) {
      throw new Error(`Required secret not found: ${key}`);
    }
    return value;
  }

  /**
   * Get a secret with a default value
   */
  async getWithDefault(key: string, defaultValue: string): Promise<string> {
    const value = await this.get(key);
    return value !== null ? value : defaultValue;
  }
}
