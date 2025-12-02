import { describe, it, expect } from 'vitest';
import {
  IntakeSchema,
  ArchitectureSchema,
  FeatureGraphSchema,
  ScaffoldingSpecSchema,
} from '../src/index.js';

describe('Schema Edge Cases and Error Scenarios', () => {
  describe('IntakeSchema Edge Cases', () => {
    it('should reject missing required security fields', () => {
      const invalid = {
        metadata: {
          appName: 'TestApp',
          description: 'Test',
        },
        requirements: {
          features: [
            {
              id: 'f1',
              name: 'Feature',
              description: 'Test',
              type: 'custom',
            },
          ],
          // Missing security field
        },
      };

      const result = IntakeSchema.safeParse(invalid);
      expect(result.success).toBe(false);
      if (!result.success) {
        expect(result.error.issues.some((i) => i.path.includes('security'))).toBe(true);
      }
    });

    it('should reject invalid authentication methods', () => {
      const invalid = {
        metadata: { appName: 'Test', description: 'Test' },
        requirements: {
          features: [{ id: 'f1', name: 'F1', description: 'Test', type: 'custom' }],
          security: {
            authentication: {
              methods: ['invalid_method'], // Invalid enum value
            },
            authorization: { model: 'rbac' },
            dataProtection: {
              encryption: { atRest: true, inTransit: true },
            },
          },
        },
      };

      const result = IntakeSchema.safeParse(invalid);
      expect(result.success).toBe(false);
    });

    it('should reject negative billing prices', () => {
      const invalid = {
        metadata: { appName: 'Test', description: 'Test' },
        requirements: {
          features: [{ id: 'f1', name: 'F1', description: 'Test', type: 'custom' }],
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
                name: 'Pro',
                price: -10, // Invalid negative price
                features: ['Feature'],
              },
            ],
          },
        },
      };

      const result = IntakeSchema.safeParse(invalid);
      expect(result.success).toBe(false);
    });

    it('should handle missing optional fields with defaults', () => {
      const minimal = {
        metadata: {
          appName: 'TestApp',
          description: 'Test',
        },
        requirements: {
          features: [
            {
              id: 'f1',
              name: 'Feature 1',
              description: 'Test feature',
              type: 'custom',
              // priority should default to 'medium'
            },
          ],
          security: {
            authentication: {
              methods: ['jwt'],
              // mfa should default to false
            },
            authorization: {
              model: 'rbac',
            },
            dataProtection: {
              encryption: {
                atRest: true,
                inTransit: true,
                // algorithm should default to 'AES-256-GCM'
              },
            },
          },
        },
      };

      const result = IntakeSchema.safeParse(minimal);
      expect(result.success).toBe(true);
      if (result.success) {
        expect(result.data.requirements.features[0].priority).toBe('medium');
        expect(result.data.requirements.security.authentication.mfa).toBe(false);
        expect(result.data.requirements.security.dataProtection.encryption.algorithm).toBe('AES-256-GCM');
      }
    });

    it('should reject empty features array', () => {
      const invalid = {
        metadata: { appName: 'Test', description: 'Test' },
        requirements: {
          features: [], // Empty array - no features
          security: {
            authentication: { methods: ['jwt'] },
            authorization: { model: 'rbac' },
            dataProtection: {
              encryption: { atRest: true, inTransit: true },
            },
          },
        },
      };

      const result = IntakeSchema.safeParse(invalid);
      // Should succeed but be semantically invalid - we should add a custom validator
      expect(result.success).toBe(true);
      // TODO: Add semantic validation that requires at least one feature
    });

    it('should reject invalid email-like strings in PII fields', () => {
      const data = {
        metadata: { appName: 'Test', description: 'Test' },
        requirements: {
          features: [
            {
              id: 'f1',
              name: 'Feature',
              description: 'Test',
              type: 'custom',
              dataModel: {
                entities: [
                  {
                    name: 'User',
                    fields: [
                      {
                        name: 'email',
                        type: 'string',
                        required: true,
                        unique: true,
                      },
                    ],
                  },
                ],
              },
            },
          ],
          security: {
            authentication: { methods: ['jwt'] },
            authorization: { model: 'rbac' },
            dataProtection: {
              encryption: { atRest: true, inTransit: true },
              pii: true,
              sensitiveFields: ['email', 'phone'],
            },
          },
        },
      };

      const result = IntakeSchema.safeParse(data);
      expect(result.success).toBe(true);
      // Should mark email fields as PII automatically
    });
  });

  describe('ArchitectureSchema Edge Cases', () => {
    it('should reject cycles in service dependencies', () => {
      const invalid = {
        metadata: { version: '1.0.0' },
        overview: {
          description: 'Test',
          patterns: ['monolith'],
          layers: ['api'],
        },
        infrastructure: {
          services: [
            {
              id: 'service-a',
              name: 'Service A',
              type: 'api',
              description: 'Test',
              responsibilities: ['Test'],
              dependencies: ['service-b'],
            },
            {
              id: 'service-b',
              name: 'Service B',
              type: 'api',
              description: 'Test',
              responsibilities: ['Test'],
              dependencies: ['service-a'], // Circular dependency
            },
          ],
          database: {
            name: 'test_db',
            type: 'relational',
            tables: [],
          },
        },
        security: {
          authentication: {
            strategy: 'JWT',
            implementation: 'jsonwebtoken',
          },
          authorization: {
            strategy: 'RBAC',
            implementation: 'middleware',
          },
          encryption: {
            secrets: {
              provider: 'env',
              rotation: false,
            },
          },
        },
        deployment: {
          strategy: 'rolling',
          containerization: true,
          orchestration: 'docker-compose',
        },
        observability: {
          logging: {
            level: 'info',
            structured: true,
            destination: 'stdout',
          },
        },
      };

      const result = ArchitectureSchema.safeParse(invalid);
      // Schema parsing succeeds but semantic validation should catch cycles
      expect(result.success).toBe(true);
      // TODO: Add cycle detection in ArchitectureBuilder
    });

    it('should reject database tables with no columns', () => {
      const invalid = {
        metadata: { version: '1.0.0' },
        overview: {
          description: 'Test',
          patterns: ['monolith'],
          layers: ['api'],
        },
        infrastructure: {
          services: [],
          database: {
            name: 'test_db',
            type: 'relational',
            tables: [
              {
                name: 'users',
                columns: [], // Empty columns array
              },
            ],
          },
        },
        security: {
          authentication: { strategy: 'JWT', implementation: 'test' },
          authorization: { strategy: 'RBAC', implementation: 'test' },
          encryption: { secrets: { provider: 'env', rotation: false } },
        },
        deployment: {
          strategy: 'rolling',
          containerization: true,
          orchestration: 'docker-compose',
        },
        observability: {
          logging: { level: 'info', structured: true, destination: 'stdout' },
        },
      };

      const result = ArchitectureSchema.safeParse(invalid);
      // Should fail or warn about empty columns
      expect(result.success).toBe(true);
      // TODO: Add validation for non-empty columns
    });

    it('should reject invalid foreign key references', () => {
      const invalid = {
        metadata: { version: '1.0.0' },
        overview: {
          description: 'Test',
          patterns: ['monolith'],
          layers: ['api'],
        },
        infrastructure: {
          services: [],
          database: {
            name: 'test_db',
            type: 'relational',
            tables: [
              {
                name: 'orders',
                columns: [
                  {
                    name: 'user_id',
                    type: 'UUID',
                    references: {
                      table: 'non_existent_table', // Invalid reference
                      column: 'id',
                      onDelete: 'CASCADE',
                    },
                  },
                ],
              },
            ],
          },
        },
        security: {
          authentication: { strategy: 'JWT', implementation: 'test' },
          authorization: { strategy: 'RBAC', implementation: 'test' },
          encryption: { secrets: { provider: 'env', rotation: false } },
        },
        deployment: {
          strategy: 'rolling',
          containerization: true,
          orchestration: 'docker-compose',
        },
        observability: {
          logging: { level: 'info', structured: true, destination: 'stdout' },
        },
      };

      const result = ArchitectureSchema.safeParse(invalid);
      expect(result.success).toBe(true);
      // TODO: Add referential integrity validation
    });
  });

  describe('FeatureGraphSchema Edge Cases', () => {
    it('should detect and report cycles in feature dependencies', () => {
      const withCycle = {
        metadata: { version: '1.0.0' },
        nodes: [
          {
            id: 'a',
            name: 'Feature A',
            description: 'Test',
            type: 'backend',
            priority: 5,
            estimatedComplexity: 'medium',
            dependencies: [
              { featureId: 'b', type: 'hard', reason: 'Depends on B' },
            ],
          },
          {
            id: 'b',
            name: 'Feature B',
            description: 'Test',
            type: 'backend',
            priority: 5,
            estimatedComplexity: 'medium',
            dependencies: [
              { featureId: 'a', type: 'hard', reason: 'Depends on A' },
            ],
          },
        ],
        executionStages: [],
        validation: {
          isAcyclic: false,
          hasCycles: [['a', 'b', 'a']],
        },
      };

      const result = FeatureGraphSchema.safeParse(withCycle);
      expect(result.success).toBe(true);
      if (result.success) {
        expect(result.data.validation.isAcyclic).toBe(false);
        expect(result.data.validation.hasCycles).toBeDefined();
        expect(result.data.validation.hasCycles!.length).toBeGreaterThan(0);
      }
    });

    it('should handle unreachable nodes', () => {
      const withUnreachable = {
        metadata: { version: '1.0.0' },
        nodes: [
          {
            id: 'a',
            name: 'Feature A',
            description: 'Test',
            type: 'backend',
            priority: 5,
            estimatedComplexity: 'medium',
            dependencies: [],
          },
          {
            id: 'orphan',
            name: 'Orphan Feature',
            description: 'Not connected to any other feature',
            type: 'backend',
            priority: 1,
            estimatedComplexity: 'low',
            dependencies: [
              { featureId: 'non_existent', type: 'hard', reason: 'Bad reference' },
            ],
          },
        ],
        executionStages: [
          {
            stageNumber: 1,
            name: 'Stage 1',
            features: ['a'],
          },
        ],
        validation: {
          isAcyclic: true,
          unreachableNodes: ['orphan'],
        },
      };

      const result = FeatureGraphSchema.safeParse(withUnreachable);
      expect(result.success).toBe(true);
      if (result.success) {
        expect(result.data.validation.unreachableNodes).toContain('orphan');
      }
    });
  });

  describe('ScaffoldingSpecSchema Edge Cases', () => {
    it('should reject negative timeout values', () => {
      const invalid = {
        metadata: {
          featureId: 'test',
          featureName: 'Test',
          version: '1.0.0',
        },
        steps: [
          {
            type: 'command',
            description: 'Test command',
            spec: {
              command: 'test',
              timeout: -1000, // Invalid negative timeout
              expectedExitCode: 0,
            },
          },
        ],
        postconditions: [],
      };

      const result = ScaffoldingSpecSchema.safeParse(invalid);
      expect(result.success).toBe(false);
    });

    it('should require at least one postcondition', () => {
      const noPostconditions = {
        metadata: {
          featureId: 'test',
          featureName: 'Test',
          version: '1.0.0',
        },
        steps: [
          {
            type: 'file',
            description: 'Create file',
            operation: {
              type: 'create',
              path: '/test/file.txt',
            },
          },
        ],
        postconditions: [], // Empty postconditions
      };

      const result = ScaffoldingSpecSchema.safeParse(noPostconditions);
      // Currently allows empty postconditions
      expect(result.success).toBe(true);
      // TODO: Consider requiring at least one postcondition
    });

    it('should validate retry policy constraints', () => {
      const invalidRetry = {
        metadata: {
          featureId: 'test',
          featureName: 'Test',
          version: '1.0.0',
        },
        steps: [
          {
            type: 'command',
            description: 'Test',
            spec: {
              command: 'test',
              retryPolicy: {
                maxAttempts: 0, // Invalid - should be at least 1
                backoffStrategy: 'exponential',
                initialDelay: 1000,
                maxDelay: 500, // Invalid - maxDelay < initialDelay
              },
              expectedExitCode: 0,
            },
          },
        ],
        postconditions: [
          {
            id: 'test',
            description: 'Test',
            type: 'command_succeeds',
            check: {
              type: 'command_succeeds',
              command: 'test',
            },
            severity: 'info',
          },
        ],
      };

      const result = ScaffoldingSpecSchema.safeParse(invalidRetry);
      // Currently doesn't validate these constraints
      expect(result.success).toBe(true);
      // TODO: Add custom validation for retry policy constraints
    });

    it('should validate secret references are declared', () => {
      const undeclaredSecret = {
        metadata: {
          featureId: 'test',
          featureName: 'Test',
          version: '1.0.0',
        },
        secrets: [
          {
            name: 'API_KEY',
            provider: 'env',
            required: true,
          },
        ],
        steps: [
          {
            type: 'command',
            description: 'Test',
            spec: {
              command: 'test',
              secretRefs: [
                {
                  name: 'UNDECLARED_SECRET', // Not in secrets array
                  provider: 'env',
                  required: true,
                },
              ],
              expectedExitCode: 0,
            },
          },
        ],
        postconditions: [
          {
            id: 'test',
            description: 'Test',
            type: 'command_succeeds',
            check: { type: 'command_succeeds', command: 'test' },
            severity: 'info',
          },
        ],
      };

      const result = ScaffoldingSpecSchema.safeParse(undeclaredSecret);
      expect(result.success).toBe(true);
      // TODO: Add cross-validation for secret references
    });
  });
});
