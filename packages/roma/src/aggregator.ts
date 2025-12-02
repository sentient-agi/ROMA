/**
 * Aggregator - Combines results from subtasks into a coherent answer
 */
import type { TaskResult } from './executor.js';
import type { ROMAExecutionContext } from '@roma/schemas';

export interface AggregationResult {
  summary: string;
  artifacts: Record<string, any>;
  metrics: {
    totalTasks: number;
    successfulTasks: number;
    failedTasks: number;
    totalDuration: number;
    averageTaskDuration: number;
  };
  recommendations?: string[];
}

export class Aggregator {
  /**
   * Aggregates task results into a final result
   */
  aggregate(results: TaskResult[], context: ROMAExecutionContext): AggregationResult {
    const successfulTasks = results.filter((r) => r.success);
    const failedTasks = results.filter((r) => !r.success);
    const totalDuration = results.reduce((sum, r) => sum + r.duration, 0);

    // Collect all artifacts
    const artifacts: Record<string, any> = {
      ...context.artifacts,
    };

    // Extract outputs from successful tasks
    for (const result of successfulTasks) {
      if (result.outputs) {
        Object.assign(artifacts, result.outputs);
      }
    }

    // Generate summary
    const summary = this.generateSummary(results, context, failedTasks.length > 0);

    // Generate recommendations based on results
    const recommendations = this.generateRecommendations(results, artifacts);

    return {
      summary,
      artifacts,
      metrics: {
        totalTasks: results.length,
        successfulTasks: successfulTasks.length,
        failedTasks: failedTasks.length,
        totalDuration,
        averageTaskDuration: results.length > 0 ? totalDuration / results.length : 0,
      },
      recommendations,
    };
  }

  /**
   * Generates a human-readable summary
   */
  private generateSummary(results: TaskResult[], context: ROMAExecutionContext, hasFailures: boolean): string {
    const lines: string[] = [];

    lines.push(`Goal: ${context.goal}`);
    lines.push(`Session ID: ${context.sessionId}`);
    lines.push('');

    if (hasFailures) {
      lines.push('⚠️  Execution completed with errors');
      const failures = results.filter((r) => !r.success);
      lines.push(`Failed tasks (${failures.length}):`);
      for (const failure of failures) {
        lines.push(`  - ${failure.taskId}: ${failure.error}`);
      }
    } else {
      lines.push('✅ Execution completed successfully');
    }

    lines.push('');
    lines.push('Task Execution:');
    for (const result of results) {
      const status = result.success ? '✅' : '❌';
      const duration = `${result.duration}ms`;
      lines.push(`  ${status} ${result.taskId} (${duration})`);
    }

    lines.push('');
    lines.push('Generated Artifacts:');
    const artifactKeys = Object.keys(context.artifacts);
    if (artifactKeys.length === 0) {
      lines.push('  (none)');
    } else {
      for (const key of artifactKeys) {
        lines.push(`  - ${key}`);
      }
    }

    return lines.join('\n');
  }

  /**
   * Generates recommendations based on execution results
   */
  private generateRecommendations(results: TaskResult[], artifacts: Record<string, any>): string[] {
    const recommendations: string[] = [];

    // Check for failures
    const failures = results.filter((r) => !r.success);
    if (failures.length > 0) {
      recommendations.push('Review and fix failed tasks before proceeding');
      recommendations.push('Check logs for detailed error messages');
    }

    // Check for slow tasks
    const slowTasks = results.filter((r) => r.duration > 5000);
    if (slowTasks.length > 0) {
      recommendations.push(`${slowTasks.length} tasks took longer than 5 seconds - consider optimization`);
    }

    // Check for missing artifacts
    if (!artifacts.intake) {
      recommendations.push('Intake artifact is missing - requirements may not be properly captured');
    }
    if (!artifacts.architecture) {
      recommendations.push('Architecture artifact is missing - system design is incomplete');
    }

    // Success recommendations
    if (failures.length === 0) {
      recommendations.push('All tasks completed successfully - ready for deployment');
      if (artifacts.scaffoldingSpecs) {
        recommendations.push('Scaffolding specs generated - ready for execution');
      }
    }

    return recommendations;
  }

  /**
   * Formats aggregation result as JSON
   */
  toJSON(result: AggregationResult): string {
    return JSON.stringify(result, null, 2);
  }

  /**
   * Formats aggregation result as markdown
   */
  toMarkdown(result: AggregationResult): string {
    const lines: string[] = [];

    lines.push('# Execution Summary\n');
    lines.push(result.summary);
    lines.push('\n## Metrics\n');
    lines.push(`- Total Tasks: ${result.metrics.totalTasks}`);
    lines.push(`- Successful: ${result.metrics.successfulTasks}`);
    lines.push(`- Failed: ${result.metrics.failedTasks}`);
    lines.push(`- Total Duration: ${result.metrics.totalDuration}ms`);
    lines.push(`- Average Task Duration: ${result.metrics.averageTaskDuration.toFixed(2)}ms`);

    if (result.recommendations && result.recommendations.length > 0) {
      lines.push('\n## Recommendations\n');
      for (const rec of result.recommendations) {
        lines.push(`- ${rec}`);
      }
    }

    lines.push('\n## Artifacts\n');
    for (const [key, value] of Object.entries(result.artifacts)) {
      lines.push(`### ${key}\n`);
      lines.push('```json');
      lines.push(JSON.stringify(value, null, 2));
      lines.push('```\n');
    }

    return lines.join('\n');
  }
}
