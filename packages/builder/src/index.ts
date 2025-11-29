/**
 * @roma/builder - SaaS Builder v2
 *
 * Domain-specific SaaS decomposition and scaffolding
 */

export { IntakeBuilder, type IntakeInput } from './intake.js';
export { ArchitectureBuilder } from './architecture.js';
export { FeatureGraphBuilder } from './feature-graph.js';
export { ScaffoldingBuilder } from './scaffolding.js';

import { IntakeBuilder } from './intake.js';
import { ArchitectureBuilder } from './architecture.js';
import { FeatureGraphBuilder } from './feature-graph.js';
import { ScaffoldingBuilder } from './scaffolding.js';
import { withSpan, createChildLogger } from '@roma/core';
import type { Span } from '@opentelemetry/api';

/**
 * Main Builder interface that combines all modes
 */
export class SaaSBuilder {
  private intakeBuilder: IntakeBuilder;
  private architectureBuilder: ArchitectureBuilder;
  private featureGraphBuilder: FeatureGraphBuilder;
  private scaffoldingBuilder: ScaffoldingBuilder;

  constructor() {
    this.intakeBuilder = new IntakeBuilder();
    this.architectureBuilder = new ArchitectureBuilder();
    this.featureGraphBuilder = new FeatureGraphBuilder();
    this.scaffoldingBuilder = new ScaffoldingBuilder();
  }

  /**
   * Mode 1: Generate intake from natural language or structured input
   */
  async intake(input: any) {
    const logger = createChildLogger({ mode: 'intake' });
    return withSpan('builder.intake', { hasGoal: Boolean(input.goal) }, async (span: Span) => {
      logger.debug({ inputKeys: Object.keys(input) }, 'Building intake');
      const result = await this.intakeBuilder.fromNaturalLanguage(input);
      logger.info({ appName: result.metadata.appName }, 'Intake built successfully');
      span.setAttribute('appName', result.metadata.appName);
      return result;
    });
  }

  /**
   * Mode 2: Generate architecture from intake
   */
  async architecture(intake: any) {
    const logger = createChildLogger({ mode: 'architecture', appName: intake.metadata?.appName });
    return withSpan('builder.architecture', { appName: intake.metadata?.appName || 'unknown' }, async (span: Span) => {
      logger.debug({}, 'Building architecture');
      const result = await this.architectureBuilder.fromIntake(intake);
      const patterns = result.overview?.patterns?.join(',') || 'none';
      logger.info({ patterns }, 'Architecture built successfully');
      span.setAttribute('patterns', patterns);
      return result;
    });
  }

  /**
   * Mode 3: Generate feature graph from intake and architecture
   */
  async featureGraph(intake: any, architecture: any) {
    const logger = createChildLogger({ mode: 'featureGraph', appName: intake.metadata?.appName });
    return withSpan('builder.featureGraph', { appName: intake.metadata?.appName || 'unknown' }, async (span: Span) => {
      logger.debug({}, 'Building feature graph');
      const result = await this.featureGraphBuilder.fromIntakeAndArchitecture(intake, architecture);
      const nodeCount = result.nodes?.length || 0;
      logger.info({ nodeCount }, 'Feature graph built successfully');
      span.setAttribute('nodeCount', nodeCount);
      return result;
    });
  }

  /**
   * Mode 4: Generate scaffolding specs from feature graph
   */
  async scaffolding(featureGraph: any, architecture: any) {
    const logger = createChildLogger({ mode: 'scaffolding' });
    return withSpan('builder.scaffolding', {}, async (span: Span) => {
      logger.debug({}, 'Building scaffolding');
      const result = await this.scaffoldingBuilder.fromFeatureGraph(featureGraph, architecture);
      const specCount = result.length || 0;
      logger.info({ specCount }, 'Scaffolding built successfully');
      span.setAttribute('specCount', specCount);
      return result;
    });
  }
}
