/**
 * ArchitectureSchema - System design and technical architecture
 */
import { z } from 'zod';

/** Service/component specification */
export const ServiceSchema = z.object({
  id: z.string(),
  name: z.string(),
  type: z.enum(['api', 'worker', 'cron', 'websocket', 'static']),
  description: z.string(),
  responsibilities: z.array(z.string()),
  dependencies: z.array(z.string()).optional(),
  exposedAPIs: z.array(z.object({
    name: z.string(),
    endpoint: z.string(),
    method: z.string(),
    description: z.string(),
  })).optional(),
  consumedAPIs: z.array(z.string()).optional(),
  resources: z.object({
    cpu: z.string().optional(), // e.g., "1000m"
    memory: z.string().optional(), // e.g., "512Mi"
    storage: z.string().optional(),
  }).optional(),
});

/** Database schema specification */
export const DatabaseSchemaSpec = z.object({
  name: z.string(),
  type: z.enum(['relational', 'document', 'key-value', 'graph']),
  tables: z.array(z.object({
    name: z.string(),
    columns: z.array(z.object({
      name: z.string(),
      type: z.string(),
      nullable: z.boolean().default(false),
      primaryKey: z.boolean().default(false),
      unique: z.boolean().default(false),
      index: z.boolean().default(false),
      references: z.object({
        table: z.string(),
        column: z.string(),
        onDelete: z.enum(['CASCADE', 'SET NULL', 'RESTRICT']).default('CASCADE'),
      }).optional(),
    })),
    indexes: z.array(z.object({
      name: z.string(),
      columns: z.array(z.string()),
      unique: z.boolean().default(false),
    })).optional(),
  })),
  migrations: z.object({
    strategy: z.enum(['automatic', 'manual', 'hybrid']).default('automatic'),
    versioning: z.boolean().default(true),
  }).optional(),
});

/** Infrastructure layer specification */
export const InfrastructureSchema = z.object({
  services: z.array(ServiceSchema),
  database: DatabaseSchemaSpec,
  cache: z.object({
    enabled: z.boolean().default(false),
    type: z.enum(['redis', 'memcached', 'in-memory']).optional(),
    ttl: z.number().optional(), // seconds
  }).optional(),
  messageQueue: z.object({
    enabled: z.boolean().default(false),
    type: z.enum(['rabbitmq', 'kafka', 'sqs', 'redis']).optional(),
    topics: z.array(z.string()).optional(),
  }).optional(),
  storage: z.object({
    type: z.enum(['local', 's3', 'gcs', 'azure-blob']).default('local'),
    buckets: z.array(z.string()).optional(),
  }).optional(),
});

/** API contract specification */
export const APIContractSchema = z.object({
  version: z.string().default('1.0.0'),
  baseUrl: z.string(),
  endpoints: z.array(z.object({
    path: z.string(),
    method: z.enum(['GET', 'POST', 'PUT', 'PATCH', 'DELETE']),
    description: z.string(),
    request: z.object({
      headers: z.record(z.string()).optional(),
      params: z.record(z.string()).optional(),
      query: z.record(z.string()).optional(),
      body: z.any().optional(),
    }).optional(),
    response: z.object({
      statusCode: z.number(),
      schema: z.any(),
    }),
    errors: z.array(z.object({
      code: z.number(),
      message: z.string(),
    })).optional(),
    authentication: z.boolean().default(true),
    rateLimit: z.object({
      requests: z.number(),
      window: z.number(), // seconds
    }).optional(),
  })),
  authentication: z.object({
    type: z.enum(['bearer', 'api-key', 'oauth', 'session']),
    tokenLocation: z.enum(['header', 'query', 'cookie']).default('header'),
  }).optional(),
});

/** Main architecture schema */
export const ArchitectureSchema = z.object({
  metadata: z.object({
    version: z.string().default('1.0.0'),
    generatedAt: z.string().datetime().optional(),
    basedOnIntake: z.string().optional(), // reference to intake ID
  }),
  overview: z.object({
    description: z.string(),
    patterns: z.array(z.enum([
      'microservices',
      'monolith',
      'serverless',
      'event-driven',
      'cqrs',
      'saga',
    ])),
    layers: z.array(z.enum([
      'presentation',
      'api',
      'business-logic',
      'data-access',
      'infrastructure',
    ])),
  }),
  infrastructure: InfrastructureSchema,
  apiContract: APIContractSchema.optional(),
  security: z.object({
    authentication: z.object({
      strategy: z.string(),
      implementation: z.string(),
    }),
    authorization: z.object({
      strategy: z.string(),
      implementation: z.string(),
    }),
    encryption: z.object({
      secrets: z.object({
        provider: z.enum(['env', 'vault', 'aws-secrets', 'azure-keyvault']).default('env'),
        rotation: z.boolean().default(false),
      }),
    }),
  }),
  deployment: z.object({
    strategy: z.enum(['rolling', 'blue-green', 'canary']).default('rolling'),
    containerization: z.boolean().default(true),
    orchestration: z.enum(['docker-compose', 'kubernetes', 'nomad', 'none']).default('docker-compose'),
    ci_cd: z.object({
      enabled: z.boolean().default(false),
      pipeline: z.string().optional(),
    }).optional(),
  }),
  observability: z.object({
    logging: z.object({
      level: z.enum(['debug', 'info', 'warn', 'error']).default('info'),
      structured: z.boolean().default(true),
      destination: z.enum(['stdout', 'file', 'service']).default('stdout'),
    }),
    metrics: z.object({
      enabled: z.boolean().default(false),
      provider: z.enum(['prometheus', 'datadog', 'newrelic', 'cloudwatch']).optional(),
    }).optional(),
    tracing: z.object({
      enabled: z.boolean().default(false),
      provider: z.enum(['jaeger', 'zipkin', 'datadog', 'honeycomb']).optional(),
    }).optional(),
  }),
});

export type Architecture = z.infer<typeof ArchitectureSchema>;
export type Service = z.infer<typeof ServiceSchema>;
export type DatabaseSchemaSpec = z.infer<typeof DatabaseSchemaSpec>;
export type Infrastructure = z.infer<typeof InfrastructureSchema>;
export type APIContract = z.infer<typeof APIContractSchema>;
