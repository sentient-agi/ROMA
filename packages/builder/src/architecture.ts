/**
 * Architecture Mode - Generate system architecture from intake
 */
import type { Intake, Architecture, Service } from '@roma/schemas';
import { ArchitectureSchema } from '@roma/schemas';

export class ArchitectureBuilder {
  /**
   * Generate architecture from intake
   */
  async fromIntake(intake: Intake): Promise<Architecture> {
    // Simplified architecture generation based on intake features
    const services = this.generateServices(intake);
    const database = this.generateDatabaseSchema(intake);

    const architecture: Architecture = {
      metadata: {
        version: '1.0.0',
        generatedAt: new Date().toISOString(),
        basedOnIntake: intake.metadata.appName,
      },
      overview: {
        description: `${intake.metadata.appName} architecture with ${services.length} services`,
        patterns: this.determinePatterns(intake),
        layers: ['presentation', 'api', 'business-logic', 'data-access', 'infrastructure'],
      },
      infrastructure: {
        services,
        database,
        cache: this.shouldUseCache(intake)
          ? {
              enabled: true,
              type: 'redis',
              ttl: 3600,
            }
          : undefined,
      },
      apiContract: this.generateAPIContract(intake),
      security: {
        authentication: {
          strategy: intake.requirements.security.authentication?.methods?.[0]?.toUpperCase() || 'JWT',
          implementation: this.getAuthImplementation(intake.requirements.security.authentication?.methods?.[0]),
        },
        authorization: {
          strategy: intake.requirements.security.authorization?.model?.toUpperCase() || 'RBAC',
          implementation: 'Middleware-based role checking',
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
        containerization: intake.technicalConstraints?.deployment === 'docker',
        orchestration: intake.technicalConstraints?.deployment === 'kubernetes' ? 'kubernetes' : 'docker-compose',
      },
      observability: {
        logging: {
          level: 'info',
          structured: true,
          destination: 'stdout',
        },
      },
    };

    return ArchitectureSchema.parse(architecture);
  }

  private generateServices(intake: Intake): Service[] {
    const services: Service[] = [];

    // Always have an API server
    services.push({
      id: 'api-server',
      name: 'API Server',
      type: 'api',
      description: 'Main REST API server',
      responsibilities: intake.requirements.features.map((f) => f.name),
      exposedAPIs: intake.requirements.features.map((f) => ({
        name: `${f.name} API`,
        endpoint: `/api/${f.id}/*`,
        method: 'GET|POST|PUT|DELETE',
        description: f.description,
      })),
    });

    // Add frontend if specified
    if (intake.technicalConstraints?.framework?.frontend) {
      services.push({
        id: 'frontend',
        name: 'Frontend SPA',
        type: 'static',
        description: `${intake.technicalConstraints.framework.frontend} single-page application`,
        responsibilities: ['User interface rendering', 'Client-side routing'],
        dependencies: ['api-server'],
      });
    }

    return services;
  }

  private generateDatabaseSchema(intake: Intake) {
    const tables = intake.requirements.features
      .filter((f) => f.dataModel?.entities)
      .flatMap((f) =>
        f.dataModel!.entities.map((entity) => ({
          name: entity.name.toLowerCase(),
          columns: entity.fields.map((field) => ({
            name: field.name,
            type: this.mapFieldType(field.type),
            nullable: !field.required,
            primaryKey: field.name === 'id',
            unique: field.unique || false,
            index: field.indexed || false,
          })),
        }))
      );

    return {
      name: `${intake.metadata.appName.toLowerCase().replace(/\s+/g, '_')}_db`,
      type: 'relational' as const,
      tables,
    };
  }

  private generateAPIContract(intake: Intake) {
    const endpoints = intake.requirements.features
      .filter((f) => f.api?.endpoints)
      .flatMap((f) =>
        f.api!.endpoints.map((endpoint) => ({
          path: endpoint.path,
          method: endpoint.method,
          description: endpoint.description,
          response: {
            statusCode: endpoint.method === 'POST' ? 201 : 200,
            schema: {},
          },
          authentication: endpoint.auth !== false,
        }))
      );

    return {
      version: '1.0.0',
      baseUrl: '/api',
      endpoints,
      authentication: {
        type: 'bearer' as const,
        tokenLocation: 'header' as const,
      },
    };
  }

  private determinePatterns(intake: Intake): Array<'microservices' | 'monolith' | 'serverless' | 'event-driven' | 'cqrs' | 'saga'> {
    const patterns: Array<'microservices' | 'monolith' | 'serverless' | 'event-driven' | 'cqrs' | 'saga'> = [];

    // Simple heuristics
    if (intake.requirements.features.length > 5) {
      patterns.push('microservices');
    } else {
      patterns.push('monolith');
    }

    if (intake.integrations && intake.integrations.length > 0) {
      patterns.push('event-driven');
    }

    return patterns.length > 0 ? patterns : ['monolith'];
  }

  private shouldUseCache(intake: Intake): boolean {
    // Use cache if performance requirements are specified
    return !!intake.requirements.performance;
  }

  private getAuthImplementation(method?: string): string {
    const implementations: Record<string, string> = {
      jwt: 'jsonwebtoken library with RS256 algorithm',
      oauth: 'OAuth 2.0 with passport.js',
      api_key: 'API key validation middleware',
      session: 'Express session with secure cookies',
    };
    return implementations[method || 'jwt'] || implementations.jwt;
  }

  private mapFieldType(type: string): string {
    const typeMap: Record<string, string> = {
      string: 'VARCHAR(255)',
      text: 'TEXT',
      integer: 'INTEGER',
      number: 'NUMERIC',
      boolean: 'BOOLEAN',
      timestamp: 'TIMESTAMP',
      date: 'DATE',
      uuid: 'UUID',
    };
    return typeMap[type.toLowerCase()] || 'VARCHAR(255)';
  }
}
