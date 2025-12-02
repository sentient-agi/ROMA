/**
 * LlmArchitectureBuilder - Convert IntakeSchema to ArchitectureSchema
 */
import type { BaseLlmProvider } from '../providers/base-provider.js';
import type { ProviderRouter } from '../providers/provider-router.js';
import { ArchitectureSchema, type Architecture } from '@roma/schemas';
import type { Intake } from '@roma/schemas';
import { scoreConfidence } from '../confidence.js';

export interface LlmArchitectureBuilderConfig {
  provider: BaseLlmProvider | ProviderRouter;
  confidenceThreshold?: number; // Default: 0.85
  verbose?: boolean;
}

export interface ArchitectureBuilderOptions {
  maxRetries?: number; // Default: 2
  temperature?: number; // Default: 0.7
}

export interface ArchitectureBuilderResult {
  architecture: Architecture;
  confidence: number;
  retries: number;
}

/**
 * LLM-backed builder that converts IntakeSchema to ArchitectureSchema
 */
export class LlmArchitectureBuilder {
  private provider: BaseLlmProvider | ProviderRouter;
  private confidenceThreshold: number;
  private verbose: boolean;

  constructor(config: LlmArchitectureBuilderConfig) {
    this.provider = config.provider;
    this.confidenceThreshold = config.confidenceThreshold ?? 0.85;
    this.verbose = config.verbose ?? false;
  }

  /**
   * Build ArchitectureSchema from IntakeSchema
   */
  async build(
    intake: Intake,
    options: ArchitectureBuilderOptions = {}
  ): Promise<ArchitectureBuilderResult> {
    const maxRetries = options.maxRetries ?? 2;
    let retries = 0;

    this.log('🏗️  Generating system architecture...');

    for (let attempt = 0; attempt <= maxRetries; attempt++) {
      try {
        const prompt = this.buildPrompt(intake);

        const rawOutput = await this.provider.completeText(prompt, {
          temperature: options.temperature ?? 0.7,
        });

        // Extract and validate JSON
        const jsonText = this.extractJson(rawOutput);
        const parsed = JSON.parse(jsonText);
        const architecture = ArchitectureSchema.parse(parsed);

        // Check confidence
        const confidence = scoreConfidence(rawOutput, {
          threshold: this.confidenceThreshold,
          strictMode: true,
        });

        this.log(`📊 Confidence: ${confidence.score.toFixed(2)}`);

        if (confidence.confident || attempt === maxRetries) {
          if (!confidence.confident && attempt === maxRetries) {
            this.log(`⚠️  Using result despite low confidence (max retries reached)`);
          }

          this.log(`✅ Architecture generated successfully`);

          return {
            architecture,
            confidence: confidence.score,
            retries: attempt,
          };
        }

        // Low confidence, retry
        this.log(`⚠️  Low confidence, retrying (attempt ${attempt + 1}/${maxRetries})...`);
        retries = attempt + 1;
      } catch (error: any) {
        this.log(`❌ Attempt ${attempt + 1} failed: ${error.message}`);

        if (attempt === maxRetries) {
          throw new Error(`Failed to generate architecture after ${maxRetries + 1} attempts: ${error.message}`);
        }
      }
    }

    throw new Error('Failed to generate architecture');
  }

  /**
   * Build prompt with few-shot example
   */
  private buildPrompt(intake: Intake): string {
    const fewShotExample = this.getFewShotExample();

    return `You are a senior software architect. Convert IntakeSchema into a complete, detailed ArchitectureSchema.

${fewShotExample}

Now generate ArchitectureSchema for this intake:

INTAKE:
${JSON.stringify(intake, null, 2)}

ARCHITECTURE REQUIREMENTS:
1. Analyze the intake's features, security, and technical constraints
2. Design appropriate service architecture (monolith, microservices, serverless)
3. Create database schema with proper tables, columns, indexes, and relationships
4. Define API contracts for all endpoints
5. Specify security implementations (auth, authorization, encryption)
6. Plan deployment strategy and observability
7. Ensure all services have clear responsibilities and dependencies
8. NO placeholders like "TODO", "...", "???"
9. Return ONLY valid JSON conforming to ArchitectureSchema

ARCHITECTURE JSON OUTPUT:`;
  }

  /**
   * Extract JSON from LLM output
   */
  private extractJson(text: string): string {
    const codeBlockMatch = text.match(/```(?:json)?\s*\n?([\s\S]*?)\n?```/);
    if (codeBlockMatch) {
      return codeBlockMatch[1].trim();
    }

    const jsonMatch = text.match(/\{[\s\S]*\}/);
    if (jsonMatch) {
      return jsonMatch[0];
    }

    return text.trim();
  }

  /**
   * Get few-shot example (OnThisDay architecture - abbreviated)
   */
  private getFewShotExample(): string {
    return `EXAMPLE INPUT (IntakeSchema):
{
  "metadata": { "appName": "OnThisDay", "description": "Daily history SaaS" },
  "requirements": {
    "features": [
      { "id": "auth", "name": "User Authentication", "type": "custom", "priority": "critical" },
      { "id": "daily_feed", "name": "Daily Events Feed", "type": "custom", "priority": "critical", "dependencies": ["auth"] },
      { "id": "billing", "name": "Subscription Billing", "type": "integration", "priority": "high" }
    ],
    "security": {
      "authentication": { "methods": ["jwt"] },
      "authorization": { "model": "rbac", "roles": ["user", "admin"] }
    }
  },
  "technicalConstraints": {
    "targetRuntime": "node",
    "framework": { "backend": "fastify", "frontend": "react" },
    "database": "postgresql"
  }
}

EXAMPLE OUTPUT (ArchitectureSchema):
{
  "metadata": { "version": "1.0.0" },
  "overview": {
    "description": "Microservices-based SaaS with API server, frontend, and worker",
    "patterns": ["microservices", "event-driven"],
    "layers": ["presentation", "api", "business-logic", "data-access", "infrastructure"]
  },
  "infrastructure": {
    "services": [
      {
        "id": "api-server",
        "name": "API Server",
        "type": "api",
        "description": "Main REST API handling auth, events, favorites, billing",
        "responsibilities": ["User auth", "Event feed", "Billing webhooks"],
        "exposedAPIs": [
          { "name": "Auth API", "endpoint": "/api/auth/*", "method": "POST", "description": "Authentication" },
          { "name": "Events API", "endpoint": "/api/events/*", "method": "GET", "description": "Historical events" }
        ],
        "resources": { "cpu": "500m", "memory": "512Mi" }
      },
      {
        "id": "frontend",
        "name": "Frontend SPA",
        "type": "static",
        "description": "React SPA",
        "responsibilities": ["UI rendering", "Client routing"],
        "dependencies": ["api-server"]
      }
    ],
    "database": {
      "name": "onthisday_db",
      "type": "relational",
      "tables": [
        {
          "name": "users",
          "columns": [
            { "name": "id", "type": "UUID", "primaryKey": true },
            { "name": "email", "type": "VARCHAR(255)", "unique": true, "index": true },
            { "name": "password_hash", "type": "VARCHAR(255)" },
            { "name": "subscription_tier", "type": "VARCHAR(50)" },
            { "name": "created_at", "type": "TIMESTAMP" }
          ]
        },
        {
          "name": "historical_events",
          "columns": [
            { "name": "id", "type": "UUID", "primaryKey": true },
            { "name": "date", "type": "VARCHAR(10)", "index": true },
            { "name": "title", "type": "VARCHAR(500)" },
            { "name": "description", "type": "TEXT" }
          ]
        }
      ]
    }
  },
  "security": {
    "authentication": {
      "strategy": "JWT",
      "implementation": "jsonwebtoken library with bcrypt for password hashing"
    },
    "authorization": {
      "strategy": "RBAC",
      "implementation": "Role-based middleware checking user.role"
    },
    "encryption": {
      "secrets": { "provider": "env", "rotation": false }
    }
  },
  "deployment": {
    "strategy": "rolling",
    "containerization": true,
    "orchestration": "docker-compose"
  },
  "observability": {
    "logging": { "level": "info", "structured": true, "destination": "stdout" },
    "metrics": { "enabled": false },
    "tracing": { "enabled": false }
  }
}`;
  }

  /**
   * Log helper
   */
  private log(message: string): void {
    if (this.verbose) {
      console.log(message);
    }
  }
}
