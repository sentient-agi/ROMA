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
    return this.intakeBuilder.fromNaturalLanguage(input);
  }

  /**
   * Mode 2: Generate architecture from intake
   */
  async architecture(intake: any) {
    return this.architectureBuilder.fromIntake(intake);
  }

  /**
   * Mode 3: Generate feature graph from intake and architecture
   */
  async featureGraph(intake: any, architecture: any) {
    return this.featureGraphBuilder.fromIntakeAndArchitecture(intake, architecture);
  }

  /**
   * Mode 4: Generate scaffolding specs from feature graph
   */
  async scaffolding(featureGraph: any, architecture: any) {
    return this.scaffoldingBuilder.fromFeatureGraph(featureGraph, architecture);
  }
}
