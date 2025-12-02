/**
 * Evaluation Harness - Tests LLM pipeline with multiple prompts
 */
import type { BaseLlmProvider } from '../providers/base-provider.js';
import type { ProviderRouter } from '../providers/provider-router.js';
import { LlmIntakeBuilder } from '../builders/llm-intake-builder.js';
import { LlmArchitectureBuilder } from '../builders/llm-architecture-builder.js';
import { LlmFeatureGraphBuilder } from '../builders/llm-feature-graph-builder.js';
import { IntakeSchema, ArchitectureSchema, FeatureGraphSchema } from '@roma/schemas';
import type { TestPrompt } from './test-prompts.js';

export interface EvalConfig {
  provider: BaseLlmProvider | ProviderRouter;
  prompts: TestPrompt[];
  verbose?: boolean;
  skipClarification?: boolean;
  confidenceThreshold?: number;
}

export interface PromptEvalResult {
  promptId: string;
  prompt: string;
  category: string;
  difficulty: string;

  // Validity
  intakeValid: boolean;
  architectureValid: boolean;
  featureGraphValid: boolean;

  // Metrics
  clarificationTurns: number;
  totalTokens: number;
  totalLatencyMs: number;

  // Confidence
  intakeConfidence: number;
  architectureConfidence: number;
  featureGraphConfidence: number;

  // Errors
  intakeError?: string;
  architectureError?: string;
  featureGraphError?: string;

  // Timing
  timestamp: string;
  duration: number;
}

export interface EvalSummary {
  totalPrompts: number;

  // Validity rates
  intakeValidityRate: number; // Percentage
  architectureValidityRate: number;
  featureGraphValidityRate: number;
  endToEndValidityRate: number; // All three valid

  // Averages
  avgClarificationTurns: number;
  avgTokensPerPrompt: number;
  avgLatencyMs: number;
  avgConfidence: number;

  // By difficulty
  byDifficulty: Record<string, {
    count: number;
    validityRate: number;
    avgTokens: number;
  }>;

  // By category
  byCategory: Record<string, {
    count: number;
    validityRate: number;
  }>;

  // Overall
  totalTokens: number;
  totalDuration: number;

  // Results
  results: PromptEvalResult[];
}

/**
 * Evaluation harness for testing LLM pipeline
 */
export class EvaluationHarness {
  private config: EvalConfig;
  private intakeBuilder: LlmIntakeBuilder;
  private architectureBuilder: LlmArchitectureBuilder;
  private featureGraphBuilder: LlmFeatureGraphBuilder;

  constructor(config: EvalConfig) {
    this.config = config;

    this.intakeBuilder = new LlmIntakeBuilder({
      provider: config.provider,
      confidenceThreshold: config.confidenceThreshold ?? 0.85,
      maxClarificationTurns: 10,
      softClarificationLimit: 5,
      verbose: config.verbose,
    });

    this.architectureBuilder = new LlmArchitectureBuilder({
      provider: config.provider,
      confidenceThreshold: config.confidenceThreshold ?? 0.85,
      verbose: config.verbose,
    });

    this.featureGraphBuilder = new LlmFeatureGraphBuilder({
      provider: config.provider,
      confidenceThreshold: config.confidenceThreshold ?? 0.85,
      verbose: config.verbose,
    });
  }

  /**
   * Run evaluation on all configured prompts
   */
  async runEvaluation(): Promise<EvalSummary> {
    const results: PromptEvalResult[] = [];
    const startTime = Date.now();

    this.log(`Starting evaluation with ${this.config.prompts.length} prompts...\n`);

    for (let i = 0; i < this.config.prompts.length; i++) {
      const testPrompt = this.config.prompts[i];
      this.log(`[${i + 1}/${this.config.prompts.length}] Evaluating: ${testPrompt.id}`);
      this.log(`   Prompt: "${testPrompt.prompt.substring(0, 60)}..."`);

      const result = await this.evaluatePrompt(testPrompt);
      results.push(result);

      this.log(`   ✓ Intake: ${result.intakeValid ? '✅' : '❌'} | Architecture: ${result.architectureValid ? '✅' : '❌'} | FeatureGraph: ${result.featureGraphValid ? '✅' : '❌'}`);
      this.log(`   Tokens: ${result.totalTokens} | Latency: ${result.totalLatencyMs}ms | Clarifications: ${result.clarificationTurns}\n`);
    }

    const totalDuration = Date.now() - startTime;

    // Calculate summary statistics
    const summary = this.calculateSummary(results, totalDuration);

    this.log('='.repeat(60));
    this.log('EVALUATION COMPLETE');
    this.log('='.repeat(60));

    return summary;
  }

  /**
   * Evaluate a single prompt through the entire pipeline
   */
  private async evaluatePrompt(testPrompt: TestPrompt): Promise<PromptEvalResult> {
    const startTime = Date.now();
    const timestamp = new Date().toISOString();

    let intakeValid = false;
    let architectureValid = false;
    let featureGraphValid = false;

    let intakeConfidence = 0;
    let architectureConfidence = 0;
    let featureGraphConfidence = 0;

    let clarificationTurns = 0;
    let totalTokens = 0;
    let totalLatencyMs = 0;

    let intakeError: string | undefined;
    let architectureError: string | undefined;
    let featureGraphError: string | undefined;

    let intake: any;
    let architecture: any;

    // Step 1: Generate intake
    try {
      const intakeResult = await this.intakeBuilder.build(testPrompt.prompt, {
        skipClarification: this.config.skipClarification,
      });

      intake = intakeResult.intake;
      intakeValid = true;
      intakeConfidence = intakeResult.confidence;
      clarificationTurns = intakeResult.clarificationTurns;

      // Validate against schema
      IntakeSchema.parse(intake);
    } catch (error: any) {
      intakeError = error.message;
    }

    // Step 2: Generate architecture (if intake succeeded)
    if (intakeValid && intake) {
      try {
        const architectureResult = await this.architectureBuilder.build(intake);

        architecture = architectureResult.architecture;
        architectureValid = true;
        architectureConfidence = architectureResult.confidence;

        // Validate against schema
        ArchitectureSchema.parse(architecture);
      } catch (error: any) {
        architectureError = error.message;
      }
    }

    // Step 3: Generate feature graph (if architecture succeeded)
    if (architectureValid && intake && architecture) {
      try {
        const featureGraphResult = await this.featureGraphBuilder.build(intake, architecture);

        featureGraphValid = true;
        featureGraphConfidence = featureGraphResult.confidence;

        // Validate against schema
        FeatureGraphSchema.parse(featureGraphResult.featureGraph);
      } catch (error: any) {
        featureGraphError = error.message;
      }
    }

    // Get token and latency metrics from provider
    if ('getMetricsSummary' in this.config.provider) {
      const metrics = (this.config.provider as any).getMetricsSummary();
      totalTokens = metrics.totalTokens;
      totalLatencyMs = Math.round(metrics.averageLatencyMs * metrics.totalCalls);
    }

    const duration = Date.now() - startTime;

    return {
      promptId: testPrompt.id,
      prompt: testPrompt.prompt,
      category: testPrompt.category,
      difficulty: testPrompt.difficulty,
      intakeValid,
      architectureValid,
      featureGraphValid,
      clarificationTurns,
      totalTokens,
      totalLatencyMs,
      intakeConfidence,
      architectureConfidence,
      featureGraphConfidence,
      intakeError,
      architectureError,
      featureGraphError,
      timestamp,
      duration,
    };
  }

  /**
   * Calculate summary statistics from results
   */
  private calculateSummary(results: PromptEvalResult[], totalDuration: number): EvalSummary {
    const totalPrompts = results.length;

    // Validity rates
    const intakeValid = results.filter(r => r.intakeValid).length;
    const architectureValid = results.filter(r => r.architectureValid).length;
    const featureGraphValid = results.filter(r => r.featureGraphValid).length;
    const endToEndValid = results.filter(r => r.intakeValid && r.architectureValid && r.featureGraphValid).length;

    const intakeValidityRate = (intakeValid / totalPrompts) * 100;
    const architectureValidityRate = (architectureValid / totalPrompts) * 100;
    const featureGraphValidityRate = (featureGraphValid / totalPrompts) * 100;
    const endToEndValidityRate = (endToEndValid / totalPrompts) * 100;

    // Averages
    const avgClarificationTurns = results.reduce((sum, r) => sum + r.clarificationTurns, 0) / totalPrompts;
    const avgTokensPerPrompt = results.reduce((sum, r) => sum + r.totalTokens, 0) / totalPrompts;
    const avgLatencyMs = results.reduce((sum, r) => sum + r.totalLatencyMs, 0) / totalPrompts;
    const avgConfidence = results.reduce((sum, r) => sum + (r.intakeConfidence + r.architectureConfidence + r.featureGraphConfidence) / 3, 0) / totalPrompts;

    // By difficulty
    const byDifficulty: Record<string, any> = {};
    for (const difficulty of ['simple', 'medium', 'complex']) {
      const filtered = results.filter(r => r.difficulty === difficulty);
      if (filtered.length > 0) {
        const valid = filtered.filter(r => r.intakeValid && r.architectureValid && r.featureGraphValid).length;
        byDifficulty[difficulty] = {
          count: filtered.length,
          validityRate: (valid / filtered.length) * 100,
          avgTokens: filtered.reduce((sum, r) => sum + r.totalTokens, 0) / filtered.length,
        };
      }
    }

    // By category
    const byCategory: Record<string, any> = {};
    const categories = [...new Set(results.map(r => r.category))];
    for (const category of categories) {
      const filtered = results.filter(r => r.category === category);
      const valid = filtered.filter(r => r.intakeValid && r.architectureValid && r.featureGraphValid).length;
      byCategory[category] = {
        count: filtered.length,
        validityRate: (valid / filtered.length) * 100,
      };
    }

    // Totals
    const totalTokens = results.reduce((sum, r) => sum + r.totalTokens, 0);

    return {
      totalPrompts,
      intakeValidityRate,
      architectureValidityRate,
      featureGraphValidityRate,
      endToEndValidityRate,
      avgClarificationTurns,
      avgTokensPerPrompt,
      avgLatencyMs,
      avgConfidence,
      byDifficulty,
      byCategory,
      totalTokens,
      totalDuration,
      results,
    };
  }

  private log(message: string): void {
    if (this.config.verbose) {
      console.log(message);
    }
  }
}

/**
 * Format evaluation summary as text
 */
export function formatEvalSummary(summary: EvalSummary): string {
  const lines: string[] = [];

  lines.push('\n' + '='.repeat(60));
  lines.push('EVALUATION SUMMARY');
  lines.push('='.repeat(60) + '\n');

  lines.push(`Total Prompts: ${summary.totalPrompts}`);
  lines.push(`Total Duration: ${Math.round(summary.totalDuration / 1000)}s`);
  lines.push(`Total Tokens: ${summary.totalTokens.toLocaleString()}\n`);

  lines.push('VALIDITY RATES:');
  lines.push(`  Intake:         ${summary.intakeValidityRate.toFixed(1)}% (${Math.round(summary.totalPrompts * summary.intakeValidityRate / 100)}/${summary.totalPrompts})`);
  lines.push(`  Architecture:   ${summary.architectureValidityRate.toFixed(1)}% (${Math.round(summary.totalPrompts * summary.architectureValidityRate / 100)}/${summary.totalPrompts})`);
  lines.push(`  Feature Graph:  ${summary.featureGraphValidityRate.toFixed(1)}% (${Math.round(summary.totalPrompts * summary.featureGraphValidityRate / 100)}/${summary.totalPrompts})`);
  lines.push(`  End-to-End:     ${summary.endToEndValidityRate.toFixed(1)}% (${Math.round(summary.totalPrompts * summary.endToEndValidityRate / 100)}/${summary.totalPrompts})\n`);

  lines.push('AVERAGES:');
  lines.push(`  Clarifications: ${summary.avgClarificationTurns.toFixed(2)} turns`);
  lines.push(`  Tokens/Prompt:  ${Math.round(summary.avgTokensPerPrompt).toLocaleString()}`);
  lines.push(`  Latency:        ${Math.round(summary.avgLatencyMs)}ms`);
  lines.push(`  Confidence:     ${summary.avgConfidence.toFixed(2)}\n`);

  lines.push('BY DIFFICULTY:');
  for (const [difficulty, stats] of Object.entries(summary.byDifficulty)) {
    lines.push(`  ${difficulty.padEnd(10)}: ${stats.validityRate.toFixed(1)}% valid | ${Math.round(stats.avgTokens).toLocaleString()} tokens | ${stats.count} prompts`);
  }
  lines.push('');

  lines.push('BY CATEGORY:');
  for (const [category, stats] of Object.entries(summary.byCategory)) {
    lines.push(`  ${category.padEnd(15)}: ${stats.validityRate.toFixed(1)}% valid | ${stats.count} prompts`);
  }

  lines.push('\n' + '='.repeat(60));

  return lines.join('\n');
}
