/**
 * Builder Contract Tests
 *
 * Validates that SaaSBuilder conforms to its API contract:
 * - Input/output schema validation
 * - Method signatures
 * - Error handling
 * - State transitions
 *
 * These tests BLOCK PRs if they fail - they define the contract
 * that all builder implementations must satisfy.
 */
import { describe, it, expect, beforeEach } from 'vitest';
import { SaaSBuilder } from '../../index.js';
import {
  IntakeSchema,
  ArchitectureSchema,
  FeatureGraphSchema,
  ScaffoldingSpecSchema,
} from '@roma/schemas';
import { readFileSync } from 'fs';
import { join } from 'path';

describe('Builder Contract Tests', () => {
  let builder: SaaSBuilder;
  let sampleIntake: any;

  beforeEach(() => {
    builder = new SaaSBuilder();

    // Load sample intake for testing
    const intakePath = join(__dirname, '../../../../examples/onthisday/intake.json');
    try {
      const intakeJson = readFileSync(intakePath, 'utf-8');
      sampleIntake = JSON.parse(intakeJson);
    } catch (error) {
      // Fallback to minimal intake if file not found
      sampleIntake = {
        metadata: {
          appName: 'TestApp',
          description: 'Test application',
          version: '0.1.0',
        },
        requirements: {
          features: [
            {
              id: 'auth',
              name: 'Authentication',
              description: 'User authentication',
              category: 'core',
              priority: 'high',
              complexity: 'medium',
            },
          ],
          security: {
            authentication: ['jwt'],
            authorization: ['rbac'],
            dataEncryption: { atRest: true, inTransit: true },
            compliance: [],
          },
          performance: {
            responseTime: { p95: 200, p99: 500 },
            throughput: { requestsPerSecond: 100 },
            concurrentUsers: 1000,
          },
          multiTenancy: {
            enabled: false,
          },
        },
        constraints: {
          budget: 'low',
          timeline: 'flexible',
          team: { size: 2, experience: 'intermediate' },
        },
      };
    }
  });

  describe('Contract: intake()', () => {
    it('MUST accept goal string and return valid Intake', async () => {
      const result = await builder.intake({
        goal: 'Build a simple task management app',
      });

      // Contract: Output must be valid Intake schema
      expect(() => IntakeSchema.parse(result)).not.toThrow();

      // Contract: Must have required metadata fields
      expect(result.metadata).toBeDefined();
      expect(result.metadata.appName).toBeDefined();
      expect(typeof result.metadata.appName).toBe('string');
      expect(result.metadata.appName.length).toBeGreaterThan(0);
    });

    it('MUST accept existingIntake and return validated Intake', async () => {
      const result = await builder.intake({
        existingIntake: sampleIntake,
      });

      // Contract: Must validate and return intake
      expect(() => IntakeSchema.parse(result)).not.toThrow();
      expect(result.metadata.appName).toBe(sampleIntake.metadata.appName);
    });

    it('MUST reject invalid input with clear error', async () => {
      // Contract: Must handle invalid input gracefully
      await expect(
        builder.intake({} as any)
      ).rejects.toThrow();
    });

    it('MUST return consistent schema version', async () => {
      const result = await builder.intake({
        goal: 'Test app',
      });

      // Contract: Schema version must be consistent
      expect(result.metadata.version).toBeDefined();
      expect(typeof result.metadata.version).toBe('string');
    });
  });

  describe('Contract: architecture()', () => {
    it('MUST accept valid Intake and return valid Architecture', async () => {
      const result = await builder.architecture(sampleIntake);

      // Contract: Output must be valid Architecture schema
      expect(() => ArchitectureSchema.parse(result)).not.toThrow();

      // Contract: Must have required fields
      expect(result.metadata).toBeDefined();
      expect(result.overview).toBeDefined();
      expect(result.overview.patterns).toBeDefined();
      expect(Array.isArray(result.overview.patterns)).toBe(true);
    });

    it('MUST include infrastructure configuration', async () => {
      const result = await builder.architecture(sampleIntake);

      // Contract: Must define infrastructure
      expect(result.infrastructure).toBeDefined();
      expect(typeof result.infrastructure).toBe('object');
    });

    it('MUST include security configuration', async () => {
      const result = await builder.architecture(sampleIntake);

      // Contract: Must have security configuration
      expect(result.security).toBeDefined();
      expect(result.security.authentication).toBeDefined();
      expect(result.security.authorization).toBeDefined();
    });

    it('MUST reject invalid intake', async () => {
      const invalidIntake = { invalid: 'data' };

      // Contract: Must validate input
      await expect(
        builder.architecture(invalidIntake as any)
      ).rejects.toThrow();
    });
  });

  describe('Contract: featureGraph()', () => {
    it('MUST accept Intake and Architecture and return valid FeatureGraph', async () => {
      const architecture = await builder.architecture(sampleIntake);
      const result = await builder.featureGraph(sampleIntake, architecture);

      // Contract: Output must be valid FeatureGraph schema
      expect(() => FeatureGraphSchema.parse(result)).not.toThrow();

      // Contract: Must have nodes and validation
      expect(result.nodes).toBeDefined();
      expect(Array.isArray(result.nodes)).toBe(true);
      expect(result.validation).toBeDefined();
      expect(result.validation.isAcyclic).toBeDefined();
    });

    it('MUST create nodes for all features', async () => {
      const architecture = await builder.architecture(sampleIntake);
      const result = await builder.featureGraph(sampleIntake, architecture);

      // Contract: Must have at least as many nodes as features
      const featureCount = sampleIntake.requirements.features.length;
      expect(result.nodes.length).toBeGreaterThanOrEqual(featureCount);
    });

    it('MUST ensure graph is acyclic', async () => {
      const architecture = await builder.architecture(sampleIntake);
      const result = await builder.featureGraph(sampleIntake, architecture);

      // Contract: Graph MUST be acyclic (critical for execution)
      expect(result.validation.isAcyclic).toBe(true);
      expect(result.validation.hasCycles).toBeUndefined();
    });

    it('MUST provide execution stages', async () => {
      const architecture = await builder.architecture(sampleIntake);
      const result = await builder.featureGraph(sampleIntake, architecture);

      // Contract: Must define execution order
      expect(result.executionStages).toBeDefined();
      expect(Array.isArray(result.executionStages)).toBe(true);
      expect(result.executionStages.length).toBeGreaterThan(0);
    });
  });

  describe('Contract: scaffolding()', () => {
    it('MUST accept FeatureGraph and Architecture and return ScaffoldingSpec array', async () => {
      const architecture = await builder.architecture(sampleIntake);
      const featureGraph = await builder.featureGraph(sampleIntake, architecture);
      const result = await builder.scaffolding(featureGraph, architecture);

      // Contract: Output must be array of valid ScaffoldingSpec
      expect(Array.isArray(result)).toBe(true);
      expect(result.length).toBeGreaterThan(0);

      result.forEach((spec: any) => {
        expect(() => ScaffoldingSpecSchema.parse(spec)).not.toThrow();
      });
    });

    it('MUST create specs for all features', async () => {
      const architecture = await builder.architecture(sampleIntake);
      const featureGraph = await builder.featureGraph(sampleIntake, architecture);
      const result = await builder.scaffolding(featureGraph, architecture);

      // Contract: Must have spec for each feature node
      expect(result.length).toBe(featureGraph.nodes.length);
    });

    it('MUST include execution steps in each spec', async () => {
      const architecture = await builder.architecture(sampleIntake);
      const featureGraph = await builder.featureGraph(sampleIntake, architecture);
      const result = await builder.scaffolding(featureGraph, architecture);

      // Contract: Each spec must have steps
      result.forEach((spec: any) => {
        expect(spec.steps).toBeDefined();
        expect(Array.isArray(spec.steps)).toBe(true);
        expect(spec.steps.length).toBeGreaterThan(0);
      });
    });

    it('MUST include metadata in each spec', async () => {
      const architecture = await builder.architecture(sampleIntake);
      const featureGraph = await builder.featureGraph(sampleIntake, architecture);
      const result = await builder.scaffolding(featureGraph, architecture);

      // Contract: Each spec must have valid metadata
      result.forEach((spec: any) => {
        expect(spec.metadata).toBeDefined();
        expect(spec.metadata.featureId).toBeDefined();
        expect(spec.metadata.featureName).toBeDefined();
        expect(spec.metadata.version).toBeDefined();
      });
    });
  });

  describe('Contract: End-to-End Pipeline', () => {
    it('MUST execute complete pipeline: intake → architecture → featureGraph → scaffolding', async () => {
      // Contract: Complete builder pipeline must work
      const intake = await builder.intake({
        goal: 'Build a blog platform',
      });

      expect(() => IntakeSchema.parse(intake)).not.toThrow();

      const architecture = await builder.architecture(intake);
      expect(() => ArchitectureSchema.parse(architecture)).not.toThrow();

      const featureGraph = await builder.featureGraph(intake, architecture);
      expect(() => FeatureGraphSchema.parse(featureGraph)).not.toThrow();

      const scaffolding = await builder.scaffolding(featureGraph, architecture);
      expect(Array.isArray(scaffolding)).toBe(true);
      scaffolding.forEach((spec: any) => {
        expect(() => ScaffoldingSpecSchema.parse(spec)).not.toThrow();
      });
    });

    it('MUST maintain data consistency across pipeline stages', async () => {
      const intake = await builder.intake({
        goal: 'Build a todo app',
      });

      const architecture = await builder.architecture(intake);
      const featureGraph = await builder.featureGraph(intake, architecture);
      const scaffolding = await builder.scaffolding(featureGraph, architecture);

      // Contract: Feature IDs must be consistent
      const featureIds = new Set(featureGraph.nodes.map((n: any) => n.id));
      const specIds = new Set(scaffolding.map((s: any) => s.metadata.featureId));

      expect(featureIds.size).toBe(specIds.size);
      specIds.forEach(id => {
        expect(featureIds.has(id)).toBe(true);
      });
    });
  });

  describe('Contract: Error Handling', () => {
    it('MUST provide meaningful errors for invalid inputs', async () => {
      // Contract: Errors must be actionable
      try {
        await builder.intake({ invalid: 'data' } as any);
        expect.fail('Should have thrown an error');
      } catch (error) {
        expect(error).toBeDefined();
        expect(error instanceof Error).toBe(true);
        expect((error as Error).message.length).toBeGreaterThan(0);
      }
    });

    it('MUST handle missing required fields', async () => {
      const incompleteIntake = {
        metadata: {
          appName: 'Test',
          // missing description and version
        },
      };

      // Contract: Must validate required fields
      await expect(
        builder.architecture(incompleteIntake as any)
      ).rejects.toThrow();
    });
  });
});
