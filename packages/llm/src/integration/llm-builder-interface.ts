/**
 * LLM Builder Integration - Wires LLM-backed builders into ROMA pipeline
 */
import type { BaseLlmProvider } from '../providers/base-provider.js';
import type { ProviderRouter } from '../providers/provider-router.js';
import { LlmIntakeBuilder, type IntakeBuilderOptions } from '../builders/llm-intake-builder.js';
import { LlmArchitectureBuilder } from '../builders/llm-architecture-builder.js';
import { LlmFeatureGraphBuilder } from '../builders/llm-feature-graph-builder.js';
import type { Intake, Architecture, FeatureGraph } from '@roma/schemas';

export interface LlmBuilderInterfaceConfig {
  provider: BaseLlmProvider | ProviderRouter;
  verbose?: boolean;
  confidenceThreshold?: number;
  maxClarificationTurns?: number;
}

/**
 * Builder interface that uses LLM-backed builders for natural language input
 */
export class LlmBuilderInterface {
  private intakeBuilder: LlmIntakeBuilder;
  private architectureBuilder: LlmArchitectureBuilder;
  private featureGraphBuilder: LlmFeatureGraphBuilder;
  private verbose: boolean;

  constructor(config: LlmBuilderInterfaceConfig) {
    this.verbose = config.verbose ?? false;

    this.intakeBuilder = new LlmIntakeBuilder({
      provider: config.provider,
      confidenceThreshold: config.confidenceThreshold ?? 0.85,
      maxClarificationTurns: config.maxClarificationTurns ?? 10,
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
   * Intake builder - Handles both natural language and pre-made JSON
   */
  async intake(inputs: Record<string, any>): Promise<Intake> {
    this.log('🔍 Intake phase starting...');

    // Check if we have a natural language goal
    if (inputs.goal && typeof inputs.goal === 'string') {
      this.log('📝 Generating intake from natural language...');

      const options: IntakeBuilderOptions = {
        partialJson: inputs.rawRequirements,
        skipClarification: inputs.skipClarification || false,
      };

      const result = await this.intakeBuilder.build(inputs.goal, options);

      this.log(`✅ Intake generated (${result.clarificationTurns} clarification turns)`);
      this.log(`   Confidence: ${result.confidence.toFixed(2)}`);

      // Store intake in context for subsequent tasks
      return result.intake;
    }

    // Check if we already have a pre-made intake
    if (inputs.rawRequirements) {
      this.log('📥 Using pre-made intake from rawRequirements');
      return inputs.rawRequirements as Intake;
    }

    throw new Error('Intake requires either a natural language goal or rawRequirements');
  }

  /**
   * Architecture builder
   */
  async architecture(intake: Intake): Promise<Architecture> {
    this.log('🏗️  Architecture phase starting...');

    const result = await this.architectureBuilder.build(intake);

    this.log(`✅ Architecture generated (${result.retries} retries)`);
    this.log(`   Confidence: ${result.confidence.toFixed(2)}`);

    return result.architecture;
  }

  /**
   * Feature graph builder
   */
  async featureGraph(intake: Intake, architecture: Architecture): Promise<FeatureGraph> {
    this.log('📊 Feature graph phase starting...');

    const result = await this.featureGraphBuilder.build(intake, architecture);

    this.log(`✅ Feature graph generated (${result.retries} retries)`);
    this.log(`   Nodes: ${result.featureGraph.nodes.length}`);
    this.log(`   Stages: ${result.featureGraph.executionStages.length}`);
    this.log(`   Confidence: ${result.confidence.toFixed(2)}`);

    return result.featureGraph;
  }

  /**
   * Scaffolding builder (placeholder - uses existing implementation)
   */
  async scaffolding(featureGraph: FeatureGraph, architecture: Architecture): Promise<any> {
    this.log('🔧 Scaffolding phase (using existing builder)...');
    // This would call the existing SaaSBuilder.scaffolding method
    // For now, return a placeholder
    return {
      message: 'Scaffolding generation would be called here',
      featureCount: featureGraph.nodes.length,
    };
  }

  private log(message: string): void {
    if (this.verbose) {
      console.log(`[LlmBuilder] ${message}`);
    }
  }
}

/**
 * Helper to create ROMA-compatible builder interface from LLM builder
 */
export function createLlmBuilderInterface(config: LlmBuilderInterfaceConfig): {
  intake: (inputs: any) => Promise<Intake>;
  architecture: (intake: Intake) => Promise<Architecture>;
  featureGraph: (intake: Intake, architecture: Architecture) => Promise<FeatureGraph>;
  scaffolding: (featureGraph: FeatureGraph, architecture: Architecture) => Promise<any>;
} {
  const builder = new LlmBuilderInterface(config);

  return {
    intake: builder.intake.bind(builder),
    architecture: builder.architecture.bind(builder),
    featureGraph: builder.featureGraph.bind(builder),
    scaffolding: builder.scaffolding.bind(builder),
  };
}
