/**
 * Scaffolding Mode - Generate execution specs for each feature
 */
import type { FeatureGraph, FeatureNode, Architecture, ScaffoldingSpec } from '@roma/schemas';
import { ScaffoldingSpecSchema } from '@roma/schemas';

export class ScaffoldingBuilder {
  /**
   * Generate scaffolding specs for all features in the graph
   */
  async fromFeatureGraph(featureGraph: FeatureGraph, architecture: Architecture): Promise<ScaffoldingSpec[]> {
    const specs: ScaffoldingSpec[] = [];

    for (const node of featureGraph.nodes) {
      const spec = await this.generateSpecForFeature(node, featureGraph, architecture);
      specs.push(spec);
    }

    return specs;
  }

  /**
   * Generate scaffolding spec for a single feature
   */
  async generateSpecForFeature(
    feature: FeatureNode,
    graph: FeatureGraph,
    architecture: Architecture
  ): Promise<ScaffoldingSpec> {
    const spec: ScaffoldingSpec = {
      metadata: {
        featureId: feature.id,
        featureName: feature.name,
        version: '1.0.0',
        generatedAt: new Date().toISOString(),
      },
      secrets: this.generateSecrets(feature, architecture),
      preconditions: this.generatePreconditions(feature, graph),
      steps: this.generateSteps(feature, architecture),
      tests: this.generateTests(feature),
      postconditions: this.generatePostconditions(feature),
      idempotency: {
        enabled: true,
        strategy: 'check_and_skip',
        stateFile: `.roma/execution/${feature.id}.state.json`,
      },
    };

    return ScaffoldingSpecSchema.parse(spec);
  }

  private generateSecrets(feature: FeatureNode, architecture: Architecture) {
    const secrets: any[] = [];

    // Add database secrets for features with data models
    if (feature.outputs?.some((o) => o.type === 'model')) {
      secrets.push({
        name: 'DB_PASSWORD',
        provider: 'env',
        required: true,
        description: 'Database password',
      });
    }

    // Add JWT secret for auth features
    if (feature.id === 'auth' || feature.name.toLowerCase().includes('auth')) {
      secrets.push({
        name: 'JWT_SECRET',
        provider: 'env',
        required: true,
        description: 'JWT signing secret',
      });
    }

    return secrets.length > 0 ? secrets : undefined;
  }

  private generatePreconditions(feature: FeatureNode, graph: FeatureGraph) {
    const preconditions: any[] = [];

    // Check dependencies are completed
    for (const dep of feature.dependencies) {
      if (dep.type === 'hard') {
        preconditions.push({
          id: `${dep.featureId}_completed`,
          description: `Feature ${dep.featureId} must be completed`,
          type: 'file_exists',
          check: {
            type: 'file_exists',
            path: `.roma/execution/${dep.featureId}.state.json`,
          },
          severity: 'critical',
          continueOnFailure: false,
        });
      }
    }

    return preconditions.length > 0 ? preconditions : undefined;
  }

  private generateSteps(feature: FeatureNode, architecture: Architecture) {
    const steps: any[] = [];

    // Create directory structure
    steps.push({
      type: 'file',
      description: `Create ${feature.id} directory structure`,
      operation: {
        type: 'create',
        path: `backend/src/${feature.type === 'frontend' ? '../frontend/src' : `features/${feature.id}`}`,
        idempotent: true,
      },
    });

    // Generate models if feature has data outputs
    if (feature.outputs?.some((o) => o.type === 'model')) {
      for (const output of feature.outputs.filter((o) => o.type === 'model')) {
        steps.push({
          type: 'template',
          description: `Generate ${output.name}`,
          templatePath: `templates/models/model.ts.j2`,
          outputPath: `backend/src/models/${output.name}.ts`,
          variables: {
            modelName: output.name,
            description: output.description,
          },
        });
      }
    }

    // Generate API routes if feature has API outputs
    if (feature.outputs?.some((o) => o.type === 'routes')) {
      steps.push({
        type: 'template',
        description: `Generate ${feature.id} API routes`,
        templatePath: `templates/routes/routes.ts.j2`,
        outputPath: `backend/src/routes/${feature.id}.routes.ts`,
        variables: {
          featureId: feature.id,
          featureName: feature.name,
        },
      });
    }

    // Install dependencies
    steps.push({
      type: 'command',
      description: 'Install required packages',
      spec: {
        command: 'npm',
        args: ['install'],
        workdir: 'backend',
        timeout: 60000,
        retryPolicy: {
          maxAttempts: 3,
          backoffStrategy: 'exponential',
          initialDelay: 2000,
          maxDelay: 10000,
        },
        idempotencyCheck: {
          enabled: true,
          checkCommand: 'npm list',
          expectedExitCode: 0,
        },
        expectedExitCode: 0,
      },
    });

    return steps;
  }

  private generateTests(feature: FeatureNode) {
    return [
      {
        name: `${feature.name} Unit Tests`,
        type: 'unit' as const,
        command: `npm test -- ${feature.id}`,
        workdir: 'backend',
        timeout: 30000,
        required: true,
      },
    ];
  }

  private generatePostconditions(feature: FeatureNode) {
    const postconditions: any[] = [];

    // Check generated files exist
    if (feature.outputs) {
      for (const output of feature.outputs) {
        postconditions.push({
          id: `${output.name}_exists`,
          description: `${output.description} file exists`,
          type: 'file_exists',
          check: {
            type: 'file_exists',
            path: this.getOutputPath(output),
          },
          severity: 'critical',
          continueOnFailure: false,
        });
      }
    }

    // Check tests pass
    postconditions.push({
      id: `${feature.id}_tests_pass`,
      description: `${feature.name} tests pass`,
      type: 'command_succeeds',
      check: {
        type: 'command_succeeds',
        command: `npm test -- ${feature.id}`,
        expectedExitCode: 0,
      },
      severity: 'error',
      continueOnFailure: false,
    });

    return postconditions;
  }

  private getOutputPath(output: any): string {
    if (output.type === 'model') {
      return `backend/src/models/${output.name}.ts`;
    }
    if (output.type === 'routes') {
      return `backend/src/routes/${output.name}.ts`;
    }
    return `backend/src/${output.name}`;
  }
}
