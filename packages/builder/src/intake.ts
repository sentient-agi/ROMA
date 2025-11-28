/**
 * Intake Mode - Collect and normalize requirements as IntakeSchema
 */
import type { Intake } from '@roma/schemas';
import { IntakeSchema } from '@roma/schemas';

export interface IntakeInput {
  goal?: string;
  rawRequirements?: any;
  existingIntake?: Intake;
}

export class IntakeBuilder {
  /**
   * Generate intake from natural language or structured input
   */
  async fromNaturalLanguage(input: IntakeInput): Promise<Intake> {
    // If we already have a valid intake, validate and return it
    if (input.existingIntake) {
      return IntakeSchema.parse(input.existingIntake);
    }

    // If we have raw requirements as JSON, parse them
    if (input.rawRequirements) {
      if (typeof input.rawRequirements === 'string') {
        const parsed = JSON.parse(input.rawRequirements);
        return IntakeSchema.parse(parsed);
      }
      return IntakeSchema.parse(input.rawRequirements);
    }

    // Generate from goal (simplified - in real implementation would use LLM)
    if (input.goal) {
      return this.generateFromGoal(input.goal);
    }

    throw new Error('No valid input provided for intake generation');
  }

  /**
   * Generate intake from a goal string (simplified template-based approach)
   */
  private generateFromGoal(goal: string): Intake {
    // This is a simplified implementation
    // In a real system, this would use an LLM to extract requirements

    const appName = this.extractAppName(goal);

    const intake: Intake = {
      metadata: {
        appName,
        description: goal,
        version: '0.1.0',
        createdAt: new Date().toISOString(),
      },
      requirements: {
        features: [
          {
            id: 'core-feature',
            name: 'Core Feature',
            description: 'Main application feature',
            type: 'custom',
            priority: 'high',
          },
        ],
        security: {
          authentication: {
            methods: ['jwt'],
            mfa: false,
          },
          authorization: {
            model: 'rbac',
          },
          dataProtection: {
            encryption: {
              atRest: true,
              inTransit: true,
              algorithm: 'AES-256-GCM',
            },
            pii: false,
          },
        },
      },
      technicalConstraints: {
        targetRuntime: 'node',
        framework: {
          backend: 'fastify',
          frontend: 'react',
        },
        database: 'postgresql',
        deployment: 'docker',
      },
    };

    return IntakeSchema.parse(intake);
  }

  /**
   * Extract app name from goal (simple heuristic)
   */
  private extractAppName(goal: string): string {
    // Look for quoted strings
    const quoted = goal.match(/"([^"]+)"/);
    if (quoted) return quoted[1];

    // Look for "build X" pattern
    const buildMatch = goal.match(/build\s+(?:a\s+)?(\w+(?:\s+\w+)?)/i);
    if (buildMatch) return buildMatch[1];

    // Default
    return 'MyApp';
  }

  /**
   * Validate an intake object
   */
  validate(intake: any): { valid: boolean; errors?: any } {
    try {
      IntakeSchema.parse(intake);
      return { valid: true };
    } catch (error) {
      return { valid: false, errors: error };
    }
  }

  /**
   * Merge multiple intakes (for iterative refinement)
   */
  merge(base: Intake, updates: Partial<Intake>): Intake {
    const merged = {
      ...base,
      ...updates,
      metadata: {
        ...base.metadata,
        ...updates.metadata,
        updatedAt: new Date().toISOString(),
      },
      requirements: {
        ...base.requirements,
        ...updates.requirements,
      },
    };

    return IntakeSchema.parse(merged);
  }
}
