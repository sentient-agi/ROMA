/**
 * Secret Sanitizer - Prevents secret leakage in logs, artifacts, and error messages
 */

export interface SanitizationOptions {
  redactionString?: string;
  preserveLength?: boolean;
  patterns?: RegExp[];
}

export class SecretSanitizer {
  private knownSecrets: Set<string> = new Set();
  private secretPatterns: RegExp[] = [];
  private options: Required<SanitizationOptions>;

  constructor(options: SanitizationOptions = {}) {
    this.options = {
      redactionString: options.redactionString || '[REDACTED]',
      preserveLength: options.preserveLength ?? false,
      patterns: options.patterns || this.getDefaultPatterns(),
    };

    this.secretPatterns = this.options.patterns;
  }

  /**
   * Register a secret value to be sanitized
   */
  registerSecret(secret: string): void {
    if (!secret || secret.length < 4) {
      // Don't register very short strings as secrets
      return;
    }
    this.knownSecrets.add(secret);
  }

  /**
   * Unregister a secret (e.g., after rotation)
   */
  unregisterSecret(secret: string): void {
    this.knownSecrets.delete(secret);
  }

  /**
   * Clear all registered secrets
   */
  clearSecrets(): void {
    this.knownSecrets.clear();
  }

  /**
   * Sanitize a string by replacing secrets with redaction string
   */
  sanitizeString(text: string): string {
    if (!text) return text;

    let sanitized = text;

    // Replace known secret values
    for (const secret of this.knownSecrets) {
      const replacement = this.options.preserveLength
        ? this.options.redactionString.repeat(Math.ceil(secret.length / this.options.redactionString.length))
        : this.options.redactionString;

      sanitized = sanitized.replace(new RegExp(this.escapeRegex(secret), 'g'), replacement);
    }

    // Apply pattern-based sanitization
    for (const pattern of this.secretPatterns) {
      sanitized = sanitized.replace(pattern, (match) => {
        return this.options.preserveLength
          ? this.options.redactionString.repeat(Math.ceil(match.length / this.options.redactionString.length))
          : this.options.redactionString;
      });
    }

    return sanitized;
  }

  /**
   * Sanitize an object recursively
   */
  sanitizeObject<T>(obj: T): T {
    if (obj === null || obj === undefined) {
      return obj;
    }

    if (typeof obj === 'string') {
      return this.sanitizeString(obj) as unknown as T;
    }

    if (Array.isArray(obj)) {
      return obj.map((item) => this.sanitizeObject(item)) as unknown as T;
    }

    if (typeof obj === 'object') {
      const sanitized: any = {};
      for (const [key, value] of Object.entries(obj)) {
        // Sanitize both key and value
        const sanitizedKey = this.isSensitiveKey(key) ? key : key;
        sanitized[sanitizedKey] = this.isSensitiveKey(key)
          ? this.options.redactionString
          : this.sanitizeObject(value);
      }
      return sanitized;
    }

    return obj;
  }

  /**
   * Sanitize Error objects
   */
  sanitizeError(error: Error): Error {
    const sanitized = new Error(this.sanitizeString(error.message));
    sanitized.name = error.name;
    if (error.stack) {
      sanitized.stack = this.sanitizeString(error.stack);
    }
    return sanitized;
  }

  /**
   * Check if a value contains secrets
   */
  containsSecrets(text: string): boolean {
    if (!text) return false;

    // Check against known secrets
    for (const secret of this.knownSecrets) {
      if (text.includes(secret)) {
        return true;
      }
    }

    // Check against patterns
    for (const pattern of this.secretPatterns) {
      if (pattern.test(text)) {
        return true;
      }
    }

    return false;
  }

  /**
   * Validate that an artifact doesn't contain secrets
   */
  validateNoSecrets(artifact: any, path: string = 'root'): ValidationResult[] {
    const violations: ValidationResult[] = [];

    if (typeof artifact === 'string') {
      if (this.containsSecrets(artifact)) {
        violations.push({
          path,
          type: 'secret_in_string',
          severity: 'critical',
          message: 'String value contains secret',
        });
      }
    } else if (Array.isArray(artifact)) {
      artifact.forEach((item, index) => {
        violations.push(...this.validateNoSecrets(item, `${path}[${index}]`));
      });
    } else if (typeof artifact === 'object' && artifact !== null) {
      for (const [key, value] of Object.entries(artifact)) {
        if (this.isSensitiveKey(key)) {
          violations.push({
            path: `${path}.${key}`,
            type: 'sensitive_key',
            severity: 'warning',
            message: `Key "${key}" may contain sensitive data`,
          });
        }
        violations.push(...this.validateNoSecrets(value, `${path}.${key}`));
      }
    }

    return violations;
  }

  /**
   * Get default patterns for common secret formats
   */
  private getDefaultPatterns(): RegExp[] {
    return [
      // API keys
      /\b[A-Za-z0-9]{32,}\b/g,

      // AWS Access Keys
      /AKIA[0-9A-Z]{16}/g,

      // JWT tokens
      /eyJ[A-Za-z0-9-_]+\.eyJ[A-Za-z0-9-_]+\.[A-Za-z0-9-_]+/g,

      // GitHub tokens
      /ghp_[A-Za-z0-9]{36}/g,
      /gho_[A-Za-z0-9]{36}/g,
      /ghu_[A-Za-z0-9]{36}/g,
      /ghs_[A-Za-z0-9]{36}/g,
      /ghr_[A-Za-z0-9]{36}/g,

      // Generic tokens (Bearer)
      /Bearer\s+[A-Za-z0-9\-._~+\/]+=*/g,

      // Private keys
      /-----BEGIN\s+(?:RSA\s+)?PRIVATE\s+KEY-----[\s\S]*?-----END\s+(?:RSA\s+)?PRIVATE\s+KEY-----/g,

      // Connection strings
      /(?:postgres|mysql|mongodb):\/\/[^\s]+:[^\s]+@[^\s]+/g,

      // Basic auth
      /Authorization:\s*Basic\s+[A-Za-z0-9+\/=]+/g,
    ];
  }

  /**
   * Check if a key name is sensitive
   */
  private isSensitiveKey(key: string): boolean {
    const sensitiveKeys = [
      'password',
      'passwd',
      'pwd',
      'secret',
      'token',
      'apikey',
      'api_key',
      'private_key',
      'privatekey',
      'auth',
      'authorization',
      'credentials',
      'credential',
    ];

    const lowerKey = key.toLowerCase();
    return sensitiveKeys.some((sensitive) => lowerKey.includes(sensitive));
  }

  /**
   * Escape special regex characters
   */
  private escapeRegex(str: string): string {
    return str.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  }
}

export interface ValidationResult {
  path: string;
  type: 'secret_in_string' | 'sensitive_key' | 'pattern_match';
  severity: 'critical' | 'warning';
  message: string;
}

/**
 * Global secret sanitizer instance
 */
let globalSanitizer: SecretSanitizer | null = null;

export function getGlobalSanitizer(): SecretSanitizer {
  if (!globalSanitizer) {
    globalSanitizer = new SecretSanitizer();
  }
  return globalSanitizer;
}

export function setGlobalSanitizer(sanitizer: SecretSanitizer): void {
  globalSanitizer = sanitizer;
}

/**
 * Sanitize all console.log, console.error, etc. outputs
 */
export function installGlobalSanitization(): void {
  const sanitizer = getGlobalSanitizer();
  const originalLog = console.log;
  const originalError = console.error;
  const originalWarn = console.warn;
  const originalInfo = console.info;

  console.log = (...args: any[]) => {
    originalLog(...args.map((arg) => sanitizer.sanitizeObject(arg)));
  };

  console.error = (...args: any[]) => {
    originalError(...args.map((arg) => sanitizer.sanitizeObject(arg)));
  };

  console.warn = (...args: any[]) => {
    originalWarn(...args.map((arg) => sanitizer.sanitizeObject(arg)));
  };

  console.info = (...args: any[]) => {
    originalInfo(...args.map((arg) => sanitizer.sanitizeObject(arg)));
  };
}
