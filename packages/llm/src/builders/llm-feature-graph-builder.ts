/**
 * LlmFeatureGraphBuilder - Convert IntakeSchema + ArchitectureSchema to FeatureGraphSchema
 */
import type { BaseLlmProvider } from '../providers/base-provider.js';
import { FeatureGraphSchema, type FeatureGraph } from '@roma/schemas';
import type { Intake, Architecture } from '@roma/schemas';
import { scoreConfidence } from '../confidence.js';

export interface LlmFeatureGraphBuilderConfig {
  provider: BaseLlmProvider;
  confidenceThreshold?: number; // Default: 0.85
  verbose?: boolean;
}

export interface FeatureGraphBuilderOptions {
  maxRetries?: number; // Default: 2
  temperature?: number; // Default: 0.6 (more deterministic)
}

export interface FeatureGraphBuilderResult {
  featureGraph: FeatureGraph;
  confidence: number;
  retries: number;
}

/**
 * LLM-backed builder that converts IntakeSchema + ArchitectureSchema to FeatureGraphSchema
 */
export class LlmFeatureGraphBuilder {
  private provider: BaseLlmProvider;
  private confidenceThreshold: number;
  private verbose: boolean;

  constructor(config: LlmFeatureGraphBuilderConfig) {
    this.provider = config.provider;
    this.confidenceThreshold = config.confidenceThreshold ?? 0.85;
    this.verbose = config.verbose ?? false;
  }

  /**
   * Build FeatureGraphSchema from IntakeSchema and ArchitectureSchema
   */
  async build(
    intake: Intake,
    architecture: Architecture,
    options: FeatureGraphBuilderOptions = {}
  ): Promise<FeatureGraphBuilderResult> {
    const maxRetries = options.maxRetries ?? 2;
    let retries = 0;

    this.log('📊 Generating feature dependency graph...');

    for (let attempt = 0; attempt <= maxRetries; attempt++) {
      try {
        const prompt = this.buildPrompt(intake, architecture);

        const rawOutput = await this.provider.completeText(prompt, {
          temperature: options.temperature ?? 0.6,
        });

        // Extract and validate JSON
        const jsonText = this.extractJson(rawOutput);
        const parsed = JSON.parse(jsonText);
        const featureGraph = FeatureGraphSchema.parse(parsed);

        // Validate graph properties
        this.validateGraph(featureGraph);

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

          this.log(`✅ Feature graph generated successfully`);
          this.log(`   Nodes: ${featureGraph.nodes.length}, Stages: ${featureGraph.executionStages.length}`);

          return {
            featureGraph,
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
          throw new Error(`Failed to generate feature graph after ${maxRetries + 1} attempts: ${error.message}`);
        }
      }
    }

    throw new Error('Failed to generate feature graph');
  }

  /**
   * Build prompt with few-shot example
   */
  private buildPrompt(intake: Intake, architecture: Architecture): string {
    const fewShotExample = this.getFewShotExample();

    return `You are an expert software project manager. Convert IntakeSchema and ArchitectureSchema into a detailed FeatureGraphSchema with dependency tracking and execution stages.

${fewShotExample}

Now generate FeatureGraphSchema for this project:

INTAKE:
${JSON.stringify(intake, null, 2)}

ARCHITECTURE:
${JSON.stringify(architecture, null, 2)}

FEATURE GRAPH REQUIREMENTS:
1. Analyze all features from intake and services from architecture
2. Create feature nodes with proper dependency types (hard, soft, data, optional)
3. Identify what each feature produces (outputs) and consumes (inputs)
4. Group features into execution stages (parallelizable groups)
5. Validate graph is acyclic (no circular dependencies)
6. Calculate critical path and statistics
7. Ensure infrastructure/setup features come first
8. Assign realistic complexity estimates and priorities
9. NO placeholders like "TODO", "...", "???"
10. Return ONLY valid JSON conforming to FeatureGraphSchema

FEATURE GRAPH JSON OUTPUT:`;
  }

  /**
   * Validate graph properties
   */
  private validateGraph(graph: FeatureGraph): void {
    // Check for self-dependencies
    for (const node of graph.nodes) {
      for (const dep of node.dependencies) {
        if (dep.featureId === node.id) {
          throw new Error(`Feature "${node.id}" has self-dependency`);
        }
      }
    }

    // Check all dependency targets exist
    const nodeIds = new Set(graph.nodes.map(n => n.id));
    for (const node of graph.nodes) {
      for (const dep of node.dependencies) {
        if (!nodeIds.has(dep.featureId)) {
          throw new Error(`Feature "${node.id}" depends on non-existent feature "${dep.featureId}"`);
        }
      }
    }

    // Check execution stages reference valid features
    for (const stage of graph.executionStages) {
      for (const featureId of stage.features) {
        if (!nodeIds.has(featureId)) {
          throw new Error(`Stage ${stage.stageNumber} references non-existent feature "${featureId}"`);
        }
      }
    }

    // Warn if graph has cycles (but don't fail - LLM might have set isAcyclic correctly)
    if (!graph.validation.isAcyclic) {
      this.log(`⚠️  Warning: Graph contains cycles: ${JSON.stringify(graph.validation.hasCycles)}`);
    }
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
   * Get few-shot example (OnThisDay feature graph - abbreviated)
   */
  private getFewShotExample(): string {
    return `EXAMPLE INPUT (IntakeSchema + ArchitectureSchema):
IntakeSchema: { "features": ["auth", "daily_feed", "favorites", "billing", "admin"], ... }
ArchitectureSchema: { "services": ["api-server", "frontend", "worker"], "database": {...}, ... }

EXAMPLE OUTPUT (FeatureGraphSchema):
{
  "metadata": { "version": "1.0.0" },
  "nodes": [
    {
      "id": "infrastructure",
      "name": "Base Infrastructure",
      "description": "Set up database, Docker, and project structure",
      "type": "infrastructure",
      "priority": 10,
      "estimatedComplexity": "medium",
      "dependencies": [],
      "outputs": [
        { "name": "database_schema", "type": "sql", "description": "PostgreSQL schema" },
        { "name": "docker_config", "type": "yaml", "description": "Docker Compose config" }
      ],
      "metadata": { "estimatedHours": 4, "tags": ["infrastructure"] }
    },
    {
      "id": "auth",
      "name": "User Authentication",
      "description": "JWT-based auth with registration/login",
      "type": "backend",
      "priority": 9,
      "estimatedComplexity": "high",
      "dependencies": [
        { "featureId": "infrastructure", "type": "hard", "reason": "Requires database schema" }
      ],
      "outputs": [
        { "name": "auth_service", "type": "module", "description": "Auth service" },
        { "name": "jwt_middleware", "type": "middleware", "description": "JWT verification" }
      ],
      "inputs": [
        { "name": "database_schema", "type": "sql", "source": "infrastructure" }
      ],
      "metadata": { "estimatedHours": 8, "tags": ["backend", "security"] }
    },
    {
      "id": "daily_feed",
      "name": "Daily Events Feed",
      "description": "API for historical events",
      "type": "backend",
      "priority": 8,
      "estimatedComplexity": "high",
      "dependencies": [
        { "featureId": "infrastructure", "type": "hard" },
        { "featureId": "auth", "type": "hard", "reason": "Requires auth middleware" }
      ],
      "outputs": [
        { "name": "events_api", "type": "routes", "description": "Events endpoints" }
      ],
      "inputs": [
        { "name": "jwt_middleware", "type": "middleware", "source": "auth" }
      ],
      "metadata": { "estimatedHours": 6, "tags": ["backend"] }
    },
    {
      "id": "frontend_auth",
      "name": "Frontend Authentication UI",
      "description": "Login/register pages",
      "type": "frontend",
      "priority": 7,
      "estimatedComplexity": "medium",
      "dependencies": [
        { "featureId": "auth", "type": "data", "reason": "Consumes auth API" }
      ],
      "metadata": { "estimatedHours": 4, "tags": ["frontend"] }
    }
  ],
  "executionStages": [
    {
      "stageNumber": 1,
      "name": "Foundation",
      "description": "Infrastructure setup",
      "features": ["infrastructure"],
      "preconditions": []
    },
    {
      "stageNumber": 2,
      "name": "Core Backend",
      "description": "Authentication and core services",
      "features": ["auth"],
      "preconditions": ["infrastructure"]
    },
    {
      "stageNumber": 3,
      "name": "Features & UI",
      "description": "Business features and frontend",
      "features": ["daily_feed", "frontend_auth"],
      "preconditions": ["auth"]
    }
  ],
  "validation": {
    "isAcyclic": true,
    "criticalPath": ["infrastructure", "auth", "daily_feed"]
  },
  "statistics": {
    "totalFeatures": 4,
    "totalStages": 3,
    "averageComplexity": 7.5,
    "estimatedTotalHours": 22,
    "parallelizationFactor": 1.3
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
