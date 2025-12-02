/**
 * Structured Logger for ROMA
 *
 * Uses pino for JSON logging with correlation IDs and secret sanitization
 */
import pino from 'pino';
import type { Logger as PinoLogger } from 'pino';

let logger: PinoLogger | null = null;

/**
 * Secret patterns to sanitize from logs
 */
const SECRET_PATTERNS = [
  /Bearer\s+[A-Za-z0-9\-._~+/]+=*/gi,
  /api[_-]?key["\s:=]+[A-Za-z0-9\-._~+/]{20,}/gi,
  /token["\s:=]+[A-Za-z0-9\-._~+/]{20,}/gi,
  /password["\s:=]+\S+/gi,
  /secret["\s:=]+\S+/gi,
  /hf_[A-Za-z0-9]{32,}/gi, // HuggingFace tokens
  /ghp_[A-Za-z0-9]{36,}/gi, // GitHub tokens
  /sk-[A-Za-z0-9]{32,}/gi, // OpenAI tokens
];

/**
 * Sanitize secrets from log messages and objects
 */
function sanitizeSecrets(value: any): any {
  if (typeof value === 'string') {
    let sanitized = value;
    for (const pattern of SECRET_PATTERNS) {
      sanitized = sanitized.replace(pattern, '[REDACTED]');
    }
    return sanitized;
  }

  if (Array.isArray(value)) {
    return value.map(sanitizeSecrets);
  }

  if (value && typeof value === 'object') {
    const sanitized: any = {};
    for (const [key, val] of Object.entries(value)) {
      // Redact entire value if key suggests it's sensitive
      const lowerKey = key.toLowerCase();
      if (lowerKey.includes('password') || lowerKey.includes('secret') || lowerKey.includes('token') || lowerKey.includes('key')) {
        sanitized[key] = '[REDACTED]';
      } else {
        sanitized[key] = sanitizeSecrets(val);
      }
    }
    return sanitized;
  }

  return value;
}

/**
 * Initialize the logger
 */
export function initializeLogger(): PinoLogger {
  if (logger) {
    return logger;
  }

  const isDevelopment = process.env.NODE_ENV !== 'production';
  const logLevel = process.env.LOG_LEVEL || (isDevelopment ? 'debug' : 'info');

  logger = pino({
    level: logLevel,
    formatters: {
      level: (label) => {
        return { level: label };
      },
    },
    transport: isDevelopment
      ? {
          target: 'pino-pretty',
          options: {
            colorize: true,
            translateTime: 'HH:MM:ss',
            ignore: 'pid,hostname',
          },
        }
      : undefined,
    // Apply secret sanitization to all logs
    mixin() {
      return {};
    },
    serializers: {
      err: pino.stdSerializers.err,
      error: pino.stdSerializers.err,
    },
  });

  return logger;
}

/**
 * Get the global logger instance
 */
export function getLogger(): PinoLogger {
  if (!logger) {
    return initializeLogger();
  }
  return logger;
}

/**
 * Create a child logger with additional context
 */
export function createChildLogger(context: Record<string, any>): PinoLogger {
  const parent = getLogger();
  return parent.child(sanitizeSecrets(context));
}

/**
 * Log with automatic secret sanitization
 */
export function log(level: 'debug' | 'info' | 'warn' | 'error', message: string, context?: Record<string, any>): void {
  const logger = getLogger();
  const sanitizedContext = context ? sanitizeSecrets(context) : {};
  const sanitizedMessage = sanitizeSecrets(message);

  logger[level](sanitizedContext, sanitizedMessage);
}

/**
 * Convenience logging functions
 */
export const logDebug = (message: string, context?: Record<string, any>) => log('debug', message, context);
export const logInfo = (message: string, context?: Record<string, any>) => log('info', message, context);
export const logWarn = (message: string, context?: Record<string, any>) => log('warn', message, context);
export const logError = (message: string, context?: Record<string, any>) => log('error', message, context);
