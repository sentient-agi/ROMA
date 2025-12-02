/**
 * Atomizer - Determines if a goal is atomic (directly executable) or composite (requires planning)
 */

export interface AtomizationResult {
  isAtomic: boolean;
  taskType?: 'build_saas_app' | 'custom';
  reasoning: string;
  suggestedPlan?: string[];
}

export class Atomizer {
  /**
   * Determines if a goal can be executed directly or needs planning
   */
  atomize(goal: string, context?: Record<string, any>): AtomizationResult {
    // Normalize goal for analysis
    const normalizedGoal = goal.toLowerCase().trim();

    // Check for SaaS building pattern
    if (this.isSaaSBuildingTask(normalizedGoal)) {
      return {
        isAtomic: false,
        taskType: 'build_saas_app',
        reasoning: 'Building a SaaS application requires multiple phases: intake, architecture, feature graph, scaffolding, execution, and verification',
        suggestedPlan: [
          'collect_intake',
          'design_architecture',
          'generate_feature_graph',
          'generate_scaffolding_per_feature',
          'execute_scaffolding',
          'run_integration_tests',
          'verify_postconditions',
          'summarize_output',
        ],
      };
    }

    // Check for other composite patterns
    if (this.isCompositeTask(normalizedGoal)) {
      return {
        isAtomic: false,
        taskType: 'custom',
        reasoning: 'Task appears to have multiple sub-components that should be planned separately',
        suggestedPlan: ['analyze_goal', 'decompose_into_subtasks', 'execute_subtasks', 'aggregate_results'],
      };
    }

    // Default: treat as atomic
    return {
      isAtomic: true,
      reasoning: 'Task appears simple enough to execute directly without decomposition',
    };
  }

  private isSaaSBuildingTask(goal: string): boolean {
    const saasKeywords = [
      'build',
      'create',
      'generate',
      'scaffold',
      'saas',
      'application',
      'app',
      'micro-saas',
      'service',
    ];

    const architectureKeywords = ['authentication', 'billing', 'database', 'api', 'frontend', 'backend'];

    const hasSaaSIntent = saasKeywords.some((keyword) => goal.includes(keyword));
    const hasArchitecturalConcerns = architectureKeywords.some((keyword) => goal.includes(keyword));

    return hasSaaSIntent && (hasArchitecturalConcerns || goal.split(' ').length > 10);
  }

  private isCompositeTask(goal: string): boolean {
    // Heuristics for composite tasks
    const compositeIndicators = [
      'and then',
      'after that',
      'multiple',
      'several',
      'first.*then',
      'steps:',
      '1.',
      '2.',
    ];

    return compositeIndicators.some((pattern) => new RegExp(pattern).test(goal));
  }

  /**
   * Check if a specific task type is atomic
   */
  isTaskTypeAtomic(taskType: string): boolean {
    const atomicTaskTypes = [
      'collect_intake',
      'design_architecture',
      'generate_feature_graph',
      'generate_scaffolding',
      'execute_scaffolding',
      'run_tests',
      'verify_postconditions',
    ];

    return atomicTaskTypes.includes(taskType);
  }
}
