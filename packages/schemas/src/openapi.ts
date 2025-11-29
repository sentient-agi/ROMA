/**
 * OpenAPI Schema Generator
 *
 * Generates OpenAPI 3.0 specifications from ROMA schemas
 * for API contract testing and documentation
 */
import { z } from 'zod';
import { IntakeSchema } from './intake.js';
import { ArchitectureSchema } from './architecture.js';
import { FeatureGraphSchema } from './feature-graph.js';
import { ScaffoldingSpecSchema } from './scaffolding.js';

export interface OpenAPISpec {
  openapi: string;
  info: {
    title: string;
    version: string;
    description: string;
  };
  paths: Record<string, any>;
  components: {
    schemas: Record<string, any>;
  };
}

/**
 * Convert Zod schema to JSON Schema (OpenAPI compatible)
 */
function zodToJsonSchema(schema: z.ZodType, name: string): any {
  // Simplified conversion - in production use @anatine/zod-openapi or similar
  return {
    type: 'object',
    description: `${name} schema`,
    // Note: Full conversion would require walking the Zod schema tree
    // For now, we'll use the schemas directly in tests
  };
}

/**
 * Generate OpenAPI specification for ROMA Builder API
 */
export function generateOpenAPISpec(): OpenAPISpec {
  const spec: OpenAPISpec = {
    openapi: '3.0.0',
    info: {
      title: 'ROMA SaaS Builder API',
      version: '0.1.0',
      description: 'Multi-Agent SaaS Builder - Contract Specification',
    },
    paths: {
      '/api/builder/intake': {
        post: {
          summary: 'Generate intake specification',
          operationId: 'generateIntake',
          tags: ['Builder'],
          requestBody: {
            required: true,
            content: {
              'application/json': {
                schema: {
                  type: 'object',
                  properties: {
                    goal: { type: 'string' },
                    rawRequirements: { type: 'object' },
                    existingIntake: { $ref: '#/components/schemas/Intake' },
                  },
                },
              },
            },
          },
          responses: {
            '200': {
              description: 'Intake generated successfully',
              content: {
                'application/json': {
                  schema: { $ref: '#/components/schemas/Intake' },
                },
              },
            },
            '400': {
              description: 'Invalid input',
              content: {
                'application/json': {
                  schema: {
                    type: 'object',
                    properties: {
                      error: { type: 'string' },
                    },
                  },
                },
              },
            },
          },
        },
      },
      '/api/builder/architecture': {
        post: {
          summary: 'Generate architecture specification',
          operationId: 'generateArchitecture',
          tags: ['Builder'],
          requestBody: {
            required: true,
            content: {
              'application/json': {
                schema: { $ref: '#/components/schemas/Intake' },
              },
            },
          },
          responses: {
            '200': {
              description: 'Architecture generated successfully',
              content: {
                'application/json': {
                  schema: { $ref: '#/components/schemas/Architecture' },
                },
              },
            },
            '400': {
              description: 'Invalid intake',
            },
          },
        },
      },
      '/api/builder/feature-graph': {
        post: {
          summary: 'Generate feature graph',
          operationId: 'generateFeatureGraph',
          tags: ['Builder'],
          requestBody: {
            required: true,
            content: {
              'application/json': {
                schema: {
                  type: 'object',
                  required: ['intake', 'architecture'],
                  properties: {
                    intake: { $ref: '#/components/schemas/Intake' },
                    architecture: { $ref: '#/components/schemas/Architecture' },
                  },
                },
              },
            },
          },
          responses: {
            '200': {
              description: 'Feature graph generated successfully',
              content: {
                'application/json': {
                  schema: { $ref: '#/components/schemas/FeatureGraph' },
                },
              },
            },
          },
        },
      },
      '/api/builder/scaffolding': {
        post: {
          summary: 'Generate scaffolding specifications',
          operationId: 'generateScaffolding',
          tags: ['Builder'],
          requestBody: {
            required: true,
            content: {
              'application/json': {
                schema: {
                  type: 'object',
                  required: ['featureGraph', 'architecture'],
                  properties: {
                    featureGraph: { $ref: '#/components/schemas/FeatureGraph' },
                    architecture: { $ref: '#/components/schemas/Architecture' },
                  },
                },
              },
            },
          },
          responses: {
            '200': {
              description: 'Scaffolding specs generated successfully',
              content: {
                'application/json': {
                  schema: {
                    type: 'array',
                    items: { $ref: '#/components/schemas/ScaffoldingSpec' },
                  },
                },
              },
            },
          },
        },
      },
    },
    components: {
      schemas: {
        Intake: zodToJsonSchema(IntakeSchema, 'Intake'),
        Architecture: zodToJsonSchema(ArchitectureSchema, 'Architecture'),
        FeatureGraph: zodToJsonSchema(FeatureGraphSchema, 'FeatureGraph'),
        ScaffoldingSpec: zodToJsonSchema(ScaffoldingSpecSchema, 'ScaffoldingSpec'),
      },
    },
  };

  return spec;
}

/**
 * Export OpenAPI spec to JSON file
 */
export function exportOpenAPISpec(): string {
  const spec = generateOpenAPISpec();
  return JSON.stringify(spec, null, 2);
}
