/**
 * LlmIntakeBuilder - Convert natural language to IntakeSchema
 */
import type { BaseLlmProvider } from '../providers/base-provider.js';
import { IntakeSchema, type Intake } from '@roma/schemas';
import { scoreConfidence } from '../confidence.js';
import { checkGuardrails, formatGuardrailError } from '../guardrails.js';

export interface LlmIntakeBuilderConfig {
  provider: BaseLlmProvider;
  confidenceThreshold?: number; // Default: 0.85
  maxClarificationTurns?: number; // Default: 10 (hard limit)
  softClarificationLimit?: number; // Default: 5 (warn user)
  verbose?: boolean;
}

export interface IntakeBuilderOptions {
  partialJson?: Partial<Intake>; // Optional pre-filled fields
  skipClarification?: boolean; // Skip clarification even if confidence low
}

export interface ClarificationRequest {
  question: string;
  field: string; // What field needs clarification
  reason: string; // Why clarification needed
}

export interface IntakeBuilderResult {
  intake: Intake;
  clarificationTurns: number;
  clarifications: Array<{ question: string; answer: string }>;
  confidence: number;
}

/**
 * LLM-backed builder that converts natural language to IntakeSchema
 */
export class LlmIntakeBuilder {
  private provider: BaseLlmProvider;
  private confidenceThreshold: number;
  private maxClarificationTurns: number;
  private softClarificationLimit: number;
  private verbose: boolean;

  constructor(config: LlmIntakeBuilderConfig) {
    this.provider = config.provider;
    this.confidenceThreshold = config.confidenceThreshold ?? 0.85;
    this.maxClarificationTurns = config.maxClarificationTurns ?? 10;
    this.softClarificationLimit = config.softClarificationLimit ?? 5;
    this.verbose = config.verbose ?? false;
  }

  /**
   * Build IntakeSchema from natural language description
   */
  async build(
    description: string,
    options: IntakeBuilderOptions = {}
  ): Promise<IntakeBuilderResult> {
    // 1. Safety check
    this.log('🛡️  Running safety guardrails...');
    const guardrailResult = checkGuardrails(description);
    if (!guardrailResult.allowed) {
      throw new Error(formatGuardrailError(guardrailResult));
    }
    this.log(`✅ Domain allowed: ${guardrailResult.domain}`);

    // 2. Generate initial intake
    this.log('\n🤖 Generating intake from description...');
    let currentPrompt = this.buildInitialPrompt(description, options.partialJson);
    let intake: Intake;
    let rawOutput: string;

    try {
      rawOutput = await this.provider.completeText(currentPrompt);

      // Extract and validate JSON
      const jsonText = this.extractJson(rawOutput);
      const parsed = JSON.parse(jsonText);
      intake = IntakeSchema.parse(parsed);
    } catch (error: any) {
      throw new Error(`Failed to generate intake: ${error.message}`);
    }

    // 3. Check confidence
    const initialConfidence = scoreConfidence(rawOutput, {
      threshold: this.confidenceThreshold,
      strictMode: true,
    });

    this.log(`📊 Confidence: ${initialConfidence.score.toFixed(2)}`);
    if (!initialConfidence.confident) {
      this.log(`⚠️  Low confidence: ${initialConfidence.reasons.join(', ')}`);
    }

    // 4. Clarification loop (if needed and not skipped)
    const clarifications: Array<{ question: string; answer: string }> = [];

    if (!initialConfidence.confident && !options.skipClarification) {
      this.log('\n🔄 Entering clarification mode...\n');

      // Identify what needs clarification
      const clarificationRequests = this.identifyClarificationNeeds(intake, initialConfidence.reasons);

      for (let turn = 0; turn < this.maxClarificationTurns && turn < clarificationRequests.length; turn++) {
        if (turn >= this.softClarificationLimit) {
          this.log(`\n⚠️  Soft limit reached (${this.softClarificationLimit} turns). Continuing...`);
        }

        const request = clarificationRequests[turn];
        this.log(`❓ Clarification ${turn + 1}: ${request.question}`);

        // In a real implementation, this would prompt the user for input
        // For now, we'll simulate by adding default values
        const answer = this.generateDefaultAnswer(request);
        this.log(`💬 Answer: ${answer}\n`);

        clarifications.push({ question: request.question, answer });

        // Regenerate with clarification
        currentPrompt = this.buildClarificationPrompt(
          description,
          intake,
          clarifications,
          options.partialJson
        );

        try {
          rawOutput = await this.provider.completeText(currentPrompt);
          const jsonText = this.extractJson(rawOutput);
          const parsed = JSON.parse(jsonText);
          intake = IntakeSchema.parse(parsed);

          // Check if confidence improved
          const newConfidence = scoreConfidence(rawOutput, {
            threshold: this.confidenceThreshold,
          });

          this.log(`📊 Updated confidence: ${newConfidence.score.toFixed(2)}`);

          if (newConfidence.confident) {
            this.log('✅ Confidence threshold met, stopping clarification\n');
            break;
          }
        } catch (error: any) {
          this.log(`❌ Clarification failed: ${error.message}`);
          // Continue with previous intake
        }
      }

      if (clarifications.length >= this.maxClarificationTurns) {
        this.log(`⚠️  Hard limit reached (${this.maxClarificationTurns} turns). Using current result.`);
      }
    }

    // 5. Final confidence check
    const finalConfidence = scoreConfidence(JSON.stringify(intake), {
      threshold: this.confidenceThreshold,
    });

    this.log(`\n✅ Final intake generated with ${clarifications.length} clarification turn(s)`);

    return {
      intake,
      clarificationTurns: clarifications.length,
      clarifications,
      confidence: finalConfidence.score,
    };
  }

  /**
   * Build initial prompt with few-shot example
   */
  private buildInitialPrompt(description: string, partialJson?: Partial<Intake>): string {
    const fewShotExample = this.getFewShotExample();

    return `You are a precise SaaS requirements analyst. Convert user descriptions into complete, valid IntakeSchema JSON.

${fewShotExample}

Now generate IntakeSchema for this request:

USER REQUEST:
${description}

${partialJson ? `PARTIAL DATA (merge with generated output):\n${JSON.stringify(partialJson, null, 2)}\n\n` : ''}

INSTRUCTIONS:
1. Generate valid JSON strictly conforming to IntakeSchema
2. Infer reasonable defaults where not specified
3. NO placeholders like "TODO", "...", "???"
4. Ensure all required fields are populated
5. For features, infer appropriate data models, API endpoints, and UI pages
6. Set sensible security defaults (JWT auth, RBAC, encryption enabled)
7. Return ONLY valid JSON, no explanatory text

JSON OUTPUT:`;
  }

  /**
   * Build clarification prompt
   */
  private buildClarificationPrompt(
    description: string,
    currentIntake: Intake,
    clarifications: Array<{ question: string; answer: string }>,
    partialJson?: Partial<Intake>
  ): string {
    const clarificationText = clarifications
      .map((c, i) => `Q${i + 1}: ${c.question}\nA${i + 1}: ${c.answer}`)
      .join('\n\n');

    return `You are a precise SaaS requirements analyst. The user has provided clarifications. Update the IntakeSchema accordingly.

ORIGINAL REQUEST:
${description}

CURRENT INTAKE:
${JSON.stringify(currentIntake, null, 2)}

CLARIFICATIONS:
${clarificationText}

${partialJson ? `PARTIAL DATA (merge with generated output):\n${JSON.stringify(partialJson, null, 2)}\n\n` : ''}

INSTRUCTIONS:
1. Update the intake JSON based on clarifications
2. Maintain all existing valid data
3. Replace placeholders and incomplete fields
4. Ensure complete, valid IntakeSchema
5. Return ONLY valid JSON, no explanatory text

UPDATED JSON OUTPUT:`;
  }

  /**
   * Identify what needs clarification based on confidence issues
   */
  private identifyClarificationNeeds(
    intake: Intake,
    reasons: string[]
  ): ClarificationRequest[] {
    const requests: ClarificationRequest[] = [];

    // Check for placeholder patterns in features
    for (const feature of intake.requirements.features) {
      if (!feature.description || feature.description.length < 10) {
        requests.push({
          question: `Can you provide more details about the "${feature.name}" feature?`,
          field: `features.${feature.id}.description`,
          reason: 'Feature description is too short or missing',
        });
      }

      if (feature.type === 'custom' && !feature.dataModel) {
        requests.push({
          question: `What data does the "${feature.name}" feature need to store?`,
          field: `features.${feature.id}.dataModel`,
          reason: 'Custom feature missing data model',
        });
      }
    }

    // Check billing details
    if (intake.requirements.billing?.enabled && !intake.requirements.billing.tiers) {
      requests.push({
        question: 'What subscription tiers and pricing do you want?',
        field: 'requirements.billing.tiers',
        reason: 'Billing enabled but no tiers defined',
      });
    }

    // Limit to 5 most important questions
    return requests.slice(0, 5);
  }

  /**
   * Generate default answer for clarification (placeholder - real implementation would prompt user)
   */
  private generateDefaultAnswer(request: ClarificationRequest): string {
    // In a real implementation, this would use a clarification agent or prompt the user
    // For now, return a generic answer
    return 'Use reasonable defaults based on common SaaS patterns';
  }

  /**
   * Extract JSON from LLM output (handle markdown code blocks)
   */
  private extractJson(text: string): string {
    // Try code block first
    const codeBlockMatch = text.match(/```(?:json)?\s*\n?([\s\S]*?)\n?```/);
    if (codeBlockMatch) {
      return codeBlockMatch[1].trim();
    }

    // Try to find raw JSON object
    const jsonMatch = text.match(/\{[\s\S]*\}/);
    if (jsonMatch) {
      return jsonMatch[0];
    }

    return text.trim();
  }

  /**
   * Get few-shot example (OnThisDay)
   */
  private getFewShotExample(): string {
    return `EXAMPLE INPUT:
"Build a daily history SaaS with auth, subscription billing, favorites, and admin panel"

EXAMPLE OUTPUT:
{
  "metadata": {
    "appName": "OnThisDay",
    "description": "Micro-SaaS that displays historical events that happened on the current day",
    "version": "0.1.0"
  },
  "requirements": {
    "features": [
      {
        "id": "auth",
        "name": "User Authentication",
        "description": "User registration, login, and session management",
        "type": "custom",
        "priority": "critical"
      },
      {
        "id": "daily_feed",
        "name": "Daily Historical Events Feed",
        "description": "Display events that happened on the current day in history",
        "type": "custom",
        "priority": "critical",
        "dependencies": ["auth"]
      },
      {
        "id": "favorites",
        "name": "Favorite Events",
        "description": "Users can mark events as favorites",
        "type": "crud",
        "priority": "high",
        "dependencies": ["auth", "daily_feed"]
      },
      {
        "id": "billing",
        "name": "Subscription Billing",
        "description": "Stripe integration for subscriptions",
        "type": "integration",
        "priority": "high",
        "dependencies": ["auth"]
      },
      {
        "id": "admin",
        "name": "Admin Dashboard",
        "description": "Admin interface for managing users and events",
        "type": "custom",
        "priority": "medium",
        "dependencies": ["auth"]
      }
    ],
    "security": {
      "authentication": { "methods": ["jwt"], "mfa": false },
      "authorization": { "model": "rbac", "roles": ["user", "admin"] },
      "dataProtection": {
        "encryption": { "atRest": true, "inTransit": true, "algorithm": "AES-256-GCM" },
        "pii": true
      }
    },
    "billing": {
      "enabled": true,
      "provider": "stripe",
      "model": "subscription",
      "tiers": [
        { "name": "free", "price": 0, "interval": "monthly", "features": ["5 favorites", "Daily feed"] },
        { "name": "pro", "price": 4.99, "interval": "monthly", "features": ["Unlimited favorites", "Ad-free"] }
      ]
    }
  },
  "technicalConstraints": {
    "targetRuntime": "node",
    "framework": { "backend": "fastify", "frontend": "react" },
    "database": "postgresql",
    "deployment": "docker"
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
