import { describe, it, expect } from 'vitest';
import { readFileSync } from 'fs';
import { join, dirname } from 'path';
import { fileURLToPath } from 'url';
import { IntakeSchema } from '../src/intake.js';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

describe('IntakeSchema', () => {
  it('should validate OnThisDay intake.json', () => {
    const examplePath = join(__dirname, '../../examples/onthisday/intake.json');
    const rawData = readFileSync(examplePath, 'utf-8');
    const data = JSON.parse(rawData);

    const result = IntakeSchema.safeParse(data);

    if (!result.success) {
      console.error('Validation errors:', JSON.stringify(result.error.errors, null, 2));
    }

    expect(result.success).toBe(true);
  });

  it('should validate minimal intake', () => {
    const minimal = {
      metadata: {
        appName: 'TestApp',
        description: 'A test application',
      },
      requirements: {
        features: [
          {
            id: 'test-feature',
            name: 'Test Feature',
            description: 'A test feature',
            type: 'custom',
          },
        ],
        security: {
          authentication: {
            methods: ['jwt'],
          },
          authorization: {
            model: 'rbac',
          },
          dataProtection: {
            encryption: {
              atRest: true,
              inTransit: true,
            },
          },
        },
      },
    };

    const result = IntakeSchema.safeParse(minimal);
    expect(result.success).toBe(true);
  });

  it('should reject invalid intake', () => {
    const invalid = {
      metadata: {
        appName: 'TestApp',
        // Missing description
      },
      requirements: {
        features: [],
        // Missing security
      },
    };

    const result = IntakeSchema.safeParse(invalid);
    expect(result.success).toBe(false);
  });

  it('should validate security requirements', () => {
    const data = {
      metadata: {
        appName: 'SecureApp',
        description: 'Secure application',
      },
      requirements: {
        features: [
          {
            id: 'f1',
            name: 'Feature 1',
            description: 'Test',
            type: 'custom',
          },
        ],
        security: {
          authentication: {
            methods: ['oauth', 'jwt'],
            providers: ['google', 'github'],
            mfa: true,
          },
          authorization: {
            model: 'rbac',
            roles: ['admin', 'user', 'guest'],
            permissions: ['read', 'write', 'delete'],
          },
          dataProtection: {
            encryption: {
              atRest: true,
              inTransit: true,
              algorithm: 'AES-256-GCM',
            },
            pii: true,
            sensitiveFields: ['email', 'ssn', 'phone'],
          },
          compliance: {
            standards: ['gdpr', 'hipaa'],
            auditLog: true,
            dataRetention: {
              enabled: true,
              days: 90,
            },
          },
        },
      },
    };

    const result = IntakeSchema.safeParse(data);
    expect(result.success).toBe(true);
    if (result.success) {
      expect(result.data.requirements.security.authentication.mfa).toBe(true);
      expect(result.data.requirements.security.compliance?.standards).toContain('gdpr');
    }
  });

  it('should validate billing configuration', () => {
    const data = {
      metadata: {
        appName: 'BillingApp',
        description: 'App with billing',
      },
      requirements: {
        features: [
          {
            id: 'f1',
            name: 'Feature 1',
            description: 'Test',
            type: 'custom',
          },
        ],
        security: {
          authentication: { methods: ['jwt'] },
          authorization: { model: 'rbac' },
          dataProtection: {
            encryption: { atRest: true, inTransit: true },
          },
        },
        billing: {
          enabled: true,
          provider: 'stripe',
          model: 'subscription',
          tiers: [
            {
              name: 'Free',
              price: 0,
              interval: 'monthly',
              features: ['Basic features'],
            },
            {
              name: 'Pro',
              price: 9.99,
              interval: 'monthly',
              features: ['All features', 'Priority support'],
            },
          ],
          trialPeriod: 14,
        },
      },
    };

    const result = IntakeSchema.safeParse(data);
    expect(result.success).toBe(true);
    if (result.success) {
      expect(result.data.requirements.billing?.tiers).toHaveLength(2);
      expect(result.data.requirements.billing?.trialPeriod).toBe(14);
    }
  });
});
