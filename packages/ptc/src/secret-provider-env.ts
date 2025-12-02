/**
 * Environment-based secret provider with security enhancements
 *
 * Reads secrets from environment variables or .env files with:
 * - Audit logging
 * - Secret sanitization
 * - Access tracking
 * - Rotation support
 */
import type { SecretProvider } from './interfaces.js';
import { getGlobalSanitizer } from './secret-sanitizer.js';

export interface SecretAuditLog {
  timestamp: string;
  operation: 'get' | 'set' | 'delete' | 'list';
  key: string;
  success: boolean;
  error?: string;
  metadata?: Record<string, any>;
}

export interface EnvSecretProviderOptions {
  enableAudit?: boolean;
  auditCallback?: (log: SecretAuditLog) => void;
  allowedKeys?: string[]; // Whitelist of allowed secret keys
  deniedKeys?: string[]; // Blacklist of denied secret keys
  autoRegisterWithSanitizer?: boolean;
}

export class EnvSecretProvider implements SecretProvider {
  readonly name = 'env';
  private secrets: Map<string, string>;
  private auditLogs: SecretAuditLog[] = [];
  private accessCounts: Map<string, number> = new Map();
  private options: Required<EnvSecretProviderOptions>;

  constructor(options: EnvSecretProviderOptions = {}) {
    this.options = {
      enableAudit: options.enableAudit ?? true,
      auditCallback: options.auditCallback ?? (() => {}),
      allowedKeys: options.allowedKeys ?? [],
      deniedKeys: options.deniedKeys ?? [],
      autoRegisterWithSanitizer: options.autoRegisterWithSanitizer ?? true,
    };

    this.secrets = new Map();
    this.loadFromEnv();
  }

  private loadFromEnv(): void {
    // Load from process.env
    for (const [key, value] of Object.entries(process.env)) {
      if (value !== undefined && this.isKeyAllowed(key)) {
        this.secrets.set(key, value);

        // Register with global sanitizer to prevent leakage
        if (this.options.autoRegisterWithSanitizer) {
          getGlobalSanitizer().registerSecret(value);
        }
      }
    }
  }

  async get(key: string): Promise<string | null> {
    const startTime = Date.now();

    try {
      if (!this.isKeyAllowed(key)) {
        this.audit('get', key, false, 'Key not allowed');
        return null;
      }

      const value = this.secrets.get(key) || null;

      // Track access
      this.accessCounts.set(key, (this.accessCounts.get(key) || 0) + 1);

      this.audit('get', key, value !== null, undefined, {
        duration: Date.now() - startTime,
        accessCount: this.accessCounts.get(key),
      });

      return value;
    } catch (error) {
      this.audit('get', key, false, error instanceof Error ? error.message : String(error));
      throw error;
    }
  }

  async set(key: string, value: string): Promise<void> {
    try {
      if (!this.isKeyAllowed(key)) {
        this.audit('set', key, false, 'Key not allowed');
        throw new Error(`Secret key "${key}" is not allowed`);
      }

      this.secrets.set(key, value);
      process.env[key] = value;

      // Register with sanitizer
      if (this.options.autoRegisterWithSanitizer) {
        getGlobalSanitizer().registerSecret(value);
      }

      this.audit('set', key, true);
    } catch (error) {
      this.audit('set', key, false, error instanceof Error ? error.message : String(error));
      throw error;
    }
  }

  async delete(key: string): Promise<void> {
    try {
      const value = this.secrets.get(key);

      this.secrets.delete(key);
      delete process.env[key];

      // Unregister from sanitizer
      if (value && this.options.autoRegisterWithSanitizer) {
        getGlobalSanitizer().unregisterSecret(value);
      }

      // Clear access count
      this.accessCounts.delete(key);

      this.audit('delete', key, true);
    } catch (error) {
      this.audit('delete', key, false, error instanceof Error ? error.message : String(error));
      throw error;
    }
  }

  async list(): Promise<string[]> {
    try {
      const keys = Array.from(this.secrets.keys());
      this.audit('list', '*', true, undefined, { count: keys.length });
      return keys;
    } catch (error) {
      this.audit('list', '*', false, error instanceof Error ? error.message : String(error));
      throw error;
    }
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

  /**
   * Rotate a secret (delete old, set new)
   */
  async rotate(key: string, newValue: string): Promise<void> {
    const oldValue = await this.get(key);
    if (oldValue) {
      // Unregister old value from sanitizer
      if (this.options.autoRegisterWithSanitizer) {
        getGlobalSanitizer().unregisterSecret(oldValue);
      }
    }

    await this.set(key, newValue);

    this.audit('set', key, true, undefined, { operation: 'rotation' });
  }

  /**
   * Get audit logs
   */
  getAuditLogs(): SecretAuditLog[] {
    return [...this.auditLogs];
  }

  /**
   * Clear audit logs
   */
  clearAuditLogs(): void {
    this.auditLogs = [];
  }

  /**
   * Get access statistics
   */
  getAccessStats(): Map<string, number> {
    return new Map(this.accessCounts);
  }

  /**
   * Verify no secrets have leaked into artifacts
   */
  async verifyNoLeaks(artifact: any): Promise<boolean> {
    const sanitizer = getGlobalSanitizer();

    for (const value of this.secrets.values()) {
      const artifactStr = JSON.stringify(artifact);
      if (artifactStr.includes(value)) {
        this.audit('get', '*', false, 'Secret leak detected in artifact');
        return false;
      }
    }

    return true;
  }

  private isKeyAllowed(key: string): boolean {
    // Check denied list first
    if (this.options.deniedKeys.length > 0 && this.options.deniedKeys.includes(key)) {
      return false;
    }

    // If allowed list is specified, key must be in it
    if (this.options.allowedKeys.length > 0) {
      return this.options.allowedKeys.includes(key);
    }

    return true;
  }

  private audit(
    operation: SecretAuditLog['operation'],
    key: string,
    success: boolean,
    error?: string,
    metadata?: Record<string, any>
  ): void {
    if (!this.options.enableAudit) {
      return;
    }

    const log: SecretAuditLog = {
      timestamp: new Date().toISOString(),
      operation,
      key,
      success,
      error,
      metadata,
    };

    this.auditLogs.push(log);
    this.options.auditCallback(log);

    // Keep only last 1000 logs to prevent memory issues
    if (this.auditLogs.length > 1000) {
      this.auditLogs.shift();
    }
  }
}
