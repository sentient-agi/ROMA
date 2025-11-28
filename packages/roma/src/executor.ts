/**
 * Executor - Executes tasks from the planner's DAG
 */
import type { ROMATask, ROMATaskDAG, ROMAExecutionContext } from '@roma/schemas';

export interface ExecutorOptions {
  verbose?: boolean;
  dryRun?: boolean;
  builderInterface?: any; // Will be injected by CLI
}

export interface TaskResult {
  taskId: string;
  success: boolean;
  outputs?: Record<string, any>;
  error?: string;
  duration: number;
  startedAt: string;
  completedAt: string;
}

export class Executor {
  private options: ExecutorOptions;
  private context: ROMAExecutionContext;
  private builderInterface: any;

  constructor(options: ExecutorOptions = {}) {
    this.options = options;
    this.builderInterface = options.builderInterface;
    this.context = {
      sessionId: this.generateSessionId(),
      goal: '',
      isComposite: true,
      currentPhase: 'execution',
      artifacts: {},
    };
  }

  /**
   * Executes a task DAG stage by stage
   */
  async execute(dag: ROMATaskDAG, goal: string): Promise<ExecutorResult> {
    this.context.goal = goal;
    const results: TaskResult[] = [];
    const startTime = Date.now();

    if (!dag.executionOrder) {
      throw new Error('DAG must have executionOrder');
    }

    this.log('Starting execution of task DAG', { stages: dag.executionOrder.length });

    // Execute stages sequentially, tasks within a stage in parallel
    for (let stageIdx = 0; stageIdx < dag.executionOrder.length; stageIdx++) {
      const stage = dag.executionOrder[stageIdx];
      this.log(`Executing stage ${stageIdx + 1}/${dag.executionOrder.length}`, {
        tasks: stage.length,
      });

      // Execute all tasks in this stage in parallel
      const stageResults = await Promise.all(
        stage.map((taskId) => {
          const task = dag.tasks.find((t) => t.id === taskId);
          if (!task) {
            throw new Error(`Task ${taskId} not found in DAG`);
          }
          return this.executeTask(task, results);
        })
      );

      results.push(...stageResults);

      // Check if any task in this stage failed
      const failures = stageResults.filter((r) => !r.success);
      if (failures.length > 0) {
        this.log(`Stage ${stageIdx + 1} failed`, { failures: failures.length });
        return {
          success: false,
          results,
          context: this.context,
          duration: Date.now() - startTime,
          error: `Stage ${stageIdx + 1} failed with ${failures.length} task failures`,
        };
      }
    }

    const duration = Date.now() - startTime;
    this.log('Execution completed successfully', { duration, tasks: results.length });

    return {
      success: true,
      results,
      context: this.context,
      duration,
    };
  }

  /**
   * Executes a single task
   */
  private async executeTask(task: ROMATask, previousResults: TaskResult[]): Promise<TaskResult> {
    const startedAt = new Date().toISOString();
    const startTime = Date.now();

    this.log(`Executing task: ${task.id}`, { type: task.type });

    if (this.options.dryRun) {
      // Simulate execution
      await this.sleep(100);
      const duration = Date.now() - startTime;
      return {
        taskId: task.id,
        success: true,
        outputs: { simulated: true },
        duration,
        startedAt,
        completedAt: new Date().toISOString(),
      };
    }

    try {
      // Gather inputs from dependencies
      const inputs = this.gatherInputs(task, previousResults);

      // Execute based on task type
      let outputs: Record<string, any> = {};

      switch (task.type) {
        case 'collect_intake':
          outputs = await this.executeCollectIntake(task, inputs);
          break;
        case 'design_architecture':
          outputs = await this.executeDesignArchitecture(task, inputs);
          break;
        case 'generate_feature_graph':
          outputs = await this.executeGenerateFeatureGraph(task, inputs);
          break;
        case 'generate_scaffolding':
          outputs = await this.executeGenerateScaffolding(task, inputs);
          break;
        case 'execute_scaffolding':
          outputs = await this.executeScaffolding(task, inputs);
          break;
        case 'run_tests':
          outputs = await this.executeRunTests(task, inputs);
          break;
        case 'verify_postconditions':
          outputs = await this.executeVerifyPostconditions(task, inputs);
          break;
        case 'aggregate_results':
          outputs = await this.executeAggregateResults(task, inputs);
          break;
        default:
          outputs = await this.executeCustomTask(task, inputs);
      }

      const duration = Date.now() - startTime;
      return {
        taskId: task.id,
        success: true,
        outputs,
        duration,
        startedAt,
        completedAt: new Date().toISOString(),
      };
    } catch (error) {
      const duration = Date.now() - startTime;
      return {
        taskId: task.id,
        success: false,
        error: error instanceof Error ? error.message : String(error),
        duration,
        startedAt,
        completedAt: new Date().toISOString(),
      };
    }
  }

  /**
   * Gather inputs from completed dependencies
   */
  private gatherInputs(task: ROMATask, previousResults: TaskResult[]): Record<string, any> {
    const inputs = { ...task.inputs };

    for (const depId of task.dependencies) {
      const depResult = previousResults.find((r) => r.taskId === depId);
      if (depResult && depResult.outputs) {
        Object.assign(inputs, depResult.outputs);
      }
    }

    return inputs;
  }

  // Task execution methods - These are placeholders that will be filled by builder interface
  private async executeCollectIntake(task: ROMATask, inputs: Record<string, any>): Promise<Record<string, any>> {
    if (this.builderInterface?.intake) {
      return { intake: await this.builderInterface.intake(inputs) };
    }
    throw new Error('Builder interface not available for intake');
  }

  private async executeDesignArchitecture(task: ROMATask, inputs: Record<string, any>): Promise<Record<string, any>> {
    if (this.builderInterface?.architecture) {
      return { architecture: await this.builderInterface.architecture(inputs.intake) };
    }
    throw new Error('Builder interface not available for architecture');
  }

  private async executeGenerateFeatureGraph(
    task: ROMATask,
    inputs: Record<string, any>
  ): Promise<Record<string, any>> {
    if (this.builderInterface?.featureGraph) {
      return {
        featureGraph: await this.builderInterface.featureGraph(inputs.intake, inputs.architecture),
      };
    }
    throw new Error('Builder interface not available for feature graph');
  }

  private async executeGenerateScaffolding(task: ROMATask, inputs: Record<string, any>): Promise<Record<string, any>> {
    if (this.builderInterface?.scaffolding) {
      return {
        scaffoldingSpecs: await this.builderInterface.scaffolding(inputs.featureGraph, inputs.architecture),
      };
    }
    throw new Error('Builder interface not available for scaffolding');
  }

  private async executeScaffolding(task: ROMATask, inputs: Record<string, any>): Promise<Record<string, any>> {
    // This would call PTC/MCP
    return { executionLogs: [] };
  }

  private async executeRunTests(task: ROMATask, inputs: Record<string, any>): Promise<Record<string, any>> {
    return { testResults: [] };
  }

  private async executeVerifyPostconditions(task: ROMATask, inputs: Record<string, any>): Promise<Record<string, any>> {
    return { verified: true };
  }

  private async executeAggregateResults(task: ROMATask, inputs: Record<string, any>): Promise<Record<string, any>> {
    return { summary: inputs };
  }

  private async executeCustomTask(task: ROMATask, inputs: Record<string, any>): Promise<Record<string, any>> {
    return { result: 'custom task executed' };
  }

  private sleep(ms: number): Promise<void> {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }

  private log(message: string, meta?: Record<string, any>): void {
    if (this.options.verbose) {
      console.log(`[Executor] ${message}`, meta || '');
    }
  }

  private generateSessionId(): string {
    return `session-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
  }
}

export interface ExecutorResult {
  success: boolean;
  results: TaskResult[];
  context: ROMAExecutionContext;
  duration: number;
  error?: string;
}
