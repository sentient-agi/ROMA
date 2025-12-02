/**
 * IntakeSchema - Requirements specification with security, multi-tenancy, and compliance
 */
import { z } from 'zod';

/** Security requirements */
export const SecurityRequirementsSchema = z.object({
  authentication: z.object({
    methods: z.array(z.enum(['oauth', 'jwt', 'api_key', 'session', 'passwordless'])),
    providers: z.array(z.string()).optional(),
    mfa: z.boolean().default(false),
  }),
  authorization: z.object({
    model: z.enum(['rbac', 'abac', 'acl']).default('rbac'),
    roles: z.array(z.string()).optional(),
    permissions: z.array(z.string()).optional(),
  }),
  dataProtection: z.object({
    encryption: z.object({
      atRest: z.boolean().default(true),
      inTransit: z.boolean().default(true),
      algorithm: z.string().default('AES-256-GCM'),
    }),
    pii: z.boolean().default(false),
    sensitiveFields: z.array(z.string()).optional(),
  }),
  compliance: z.object({
    standards: z.array(z.enum(['gdpr', 'hipaa', 'pci-dss', 'sox', 'ccpa'])).optional(),
    auditLog: z.boolean().default(true),
    dataRetention: z.object({
      enabled: z.boolean().default(false),
      days: z.number().optional(),
    }).optional(),
  }).optional(),
});

/** Multi-tenancy configuration */
export const MultiTenancySchema = z.object({
  enabled: z.boolean().default(false),
  isolation: z.enum(['database', 'schema', 'row']).default('row'),
  tenantIdentifier: z.string().default('tenant_id'),
  allowCrossTenant: z.boolean().default(false),
});

/** Performance requirements */
export const PerformanceRequirementsSchema = z.object({
  latency: z.object({
    p50: z.number().optional(), // milliseconds
    p95: z.number().optional(),
    p99: z.number().optional(),
  }).optional(),
  throughput: z.object({
    requestsPerSecond: z.number().optional(),
    concurrentUsers: z.number().optional(),
  }).optional(),
  scaling: z.object({
    horizontal: z.boolean().default(true),
    vertical: z.boolean().default(false),
    autoScale: z.boolean().default(false),
  }).optional(),
});

/** Billing and monetization */
export const BillingSchema = z.object({
  enabled: z.boolean().default(false),
  provider: z.enum(['stripe', 'paddle', 'chargebee', 'custom']).optional(),
  model: z.enum(['subscription', 'usage-based', 'one-time', 'hybrid']).optional(),
  tiers: z.array(z.object({
    name: z.string(),
    price: z.number().nonnegative('Price cannot be negative'),
    interval: z.enum(['monthly', 'yearly', 'lifetime']).optional(),
    features: z.array(z.string()),
  })).optional(),
  trialPeriod: z.number().optional(), // days
});

/** Feature specification */
export const FeatureSpecSchema = z.object({
  id: z.string(),
  name: z.string(),
  description: z.string(),
  type: z.enum(['crud', 'workflow', 'integration', 'analytics', 'custom']),
  priority: z.enum(['critical', 'high', 'medium', 'low']).default('medium'),
  dataModel: z.object({
    entities: z.array(z.object({
      name: z.string(),
      fields: z.array(z.object({
        name: z.string(),
        type: z.string(),
        required: z.boolean().default(false),
        unique: z.boolean().default(false),
        indexed: z.boolean().default(false),
      })),
      relationships: z.array(z.object({
        type: z.enum(['one-to-one', 'one-to-many', 'many-to-many']),
        target: z.string(),
        foreignKey: z.string().optional(),
      })).optional(),
    })),
  }).optional(),
  api: z.object({
    endpoints: z.array(z.object({
      method: z.enum(['GET', 'POST', 'PUT', 'PATCH', 'DELETE']),
      path: z.string(),
      description: z.string(),
      auth: z.boolean().default(true),
    })),
  }).optional(),
  ui: z.object({
    pages: z.array(z.object({
      name: z.string(),
      route: z.string(),
      components: z.array(z.string()),
    })),
  }).optional(),
  dependencies: z.array(z.string()).optional(),
});

/** Main intake schema */
export const IntakeSchema = z.object({
  metadata: z.object({
    appName: z.string(),
    description: z.string(),
    version: z.string().default('0.1.0'),
    createdAt: z.string().datetime().optional(),
    updatedAt: z.string().datetime().optional(),
  }),
  requirements: z.object({
    features: z.array(FeatureSpecSchema),
    security: SecurityRequirementsSchema,
    multiTenancy: MultiTenancySchema.optional(),
    performance: PerformanceRequirementsSchema.optional(),
    billing: BillingSchema.optional(),
  }),
  technicalConstraints: z.object({
    targetRuntime: z.enum(['node', 'deno', 'bun', 'browser']).default('node'),
    framework: z.object({
      backend: z.string().optional(), // e.g., "fastify", "express", "hono"
      frontend: z.string().optional(), // e.g., "react", "vue", "svelte"
    }).optional(),
    database: z.enum(['postgresql', 'mysql', 'mongodb', 'sqlite']).default('postgresql'),
    deployment: z.enum(['docker', 'kubernetes', 'serverless', 'vm']).default('docker'),
  }).optional(),
  integrations: z.array(z.object({
    name: z.string(),
    type: z.enum(['payment', 'email', 'sms', 'storage', 'api', 'auth']),
    provider: z.string(),
    config: z.record(z.any()).optional(),
  })).optional(),
});

export type Intake = z.infer<typeof IntakeSchema>;
export type FeatureSpec = z.infer<typeof FeatureSpecSchema>;
export type SecurityRequirements = z.infer<typeof SecurityRequirementsSchema>;
export type MultiTenancy = z.infer<typeof MultiTenancySchema>;
export type PerformanceRequirements = z.infer<typeof PerformanceRequirementsSchema>;
export type Billing = z.infer<typeof BillingSchema>;
