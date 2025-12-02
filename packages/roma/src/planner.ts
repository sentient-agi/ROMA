/**
 * Planner - Builds a DAG (Directed Acyclic Graph) of tasks for composite goals
 */
import type { ROMATask, ROMATaskDAG } from '@roma/schemas';

export interface PlannerOptions {
  taskType: 'build_saas_app' | 'custom';
  context?: Record<string, any>;
}

export class Planner {
  /**
   * Creates a task DAG for a given goal
   */
  plan(goal: string, options: PlannerOptions): ROMATaskDAG {
    if (options.taskType === 'build_saas_app') {
      return this.planSaaSBuild(goal, options.context);
    }

    return this.planCustomTask(goal, options.context);
  }

  /**
   * Creates a standard SaaS build plan
   */
  private planSaaSBuild(goal: string, context?: Record<string, any>): ROMATaskDAG {
    const tasks: ROMATask[] = [
      {
        id: 'collect_intake',
        type: 'collect_intake',
        description: 'Collect and validate requirements as IntakeSchema',
        dependencies: [],
        inputs: { goal, rawRequirements: context?.rawRequirements },
        status: 'pending',
      },
      {
        id: 'design_architecture',
        type: 'design_architecture',
        description: 'Generate system architecture from intake',
        dependencies: ['collect_intake'],
        inputs: {},
        status: 'pending',
      },
      {
        id: 'generate_feature_graph',
        type: 'generate_feature_graph',
        description: 'Build feature dependency graph',
        dependencies: ['collect_intake', 'design_architecture'],
        inputs: {},
        status: 'pending',
      },
      {
        id: 'generate_scaffolding_specs',
        type: 'generate_scaffolding',
        description: 'Generate scaffolding specs for each feature',
        dependencies: ['generate_feature_graph', 'design_architecture'],
        inputs: {},
        status: 'pending',
      },
      {
        id: 'execute_scaffolding',
        type: 'execute_scaffolding',
        description: 'Execute scaffolding specs via PTC/MCP',
        dependencies: ['generate_scaffolding_specs'],
        inputs: {},
        status: 'pending',
      },
      {
        id: 'run_integration_tests',
        type: 'run_tests',
        description: 'Run integration tests',
        dependencies: ['execute_scaffolding'],
        inputs: {},
        status: 'pending',
      },
      {
        id: 'verify_postconditions',
        type: 'verify_postconditions',
        description: 'Verify all postconditions are met',
        dependencies: ['run_integration_tests'],
        inputs: {},
        status: 'pending',
      },
      {
        id: 'aggregate_results',
        type: 'aggregate_results',
        description: 'Summarize execution results and artifacts',
        dependencies: ['verify_postconditions'],
        inputs: {},
        status: 'pending',
      },
    ];

    const validation = this.validateDAG(tasks);
    const executionOrder = this.topologicalSort(tasks);

    return {
      tasks,
      validation,
      executionOrder,
    };
  }

  /**
   * Creates a custom task plan (placeholder for now)
   */
  private planCustomTask(goal: string, context?: Record<string, any>): ROMATaskDAG {
    const tasks: ROMATask[] = [
      {
        id: 'analyze_goal',
        type: 'custom',
        description: 'Analyze the goal and determine steps',
        dependencies: [],
        inputs: { goal },
        status: 'pending',
      },
      {
        id: 'execute_task',
        type: 'custom',
        description: 'Execute the task',
        dependencies: ['analyze_goal'],
        inputs: {},
        status: 'pending',
      },
    ];

    const validation = this.validateDAG(tasks);
    const executionOrder = this.topologicalSort(tasks);

    return {
      tasks,
      validation,
      executionOrder,
    };
  }

  /**
   * Validates that the task graph is acyclic
   */
  private validateDAG(tasks: ROMATask[]): { isAcyclic: boolean; hasCycles?: string[][] } {
    const visited = new Set<string>();
    const recursionStack = new Set<string>();
    const cycles: string[][] = [];

    const taskMap = new Map(tasks.map((t) => [t.id, t]));

    const hasCycle = (taskId: string, path: string[]): boolean => {
      if (recursionStack.has(taskId)) {
        const cycleStart = path.indexOf(taskId);
        cycles.push([...path.slice(cycleStart), taskId]);
        return true;
      }

      if (visited.has(taskId)) {
        return false;
      }

      visited.add(taskId);
      recursionStack.add(taskId);
      path.push(taskId);

      const task = taskMap.get(taskId);
      if (task) {
        for (const depId of task.dependencies) {
          if (hasCycle(depId, [...path])) {
            return true;
          }
        }
      }

      recursionStack.delete(taskId);
      return false;
    };

    let foundCycle = false;
    for (const task of tasks) {
      if (!visited.has(task.id)) {
        if (hasCycle(task.id, [])) {
          foundCycle = true;
        }
      }
    }

    return {
      isAcyclic: !foundCycle,
      hasCycles: cycles.length > 0 ? cycles : undefined,
    };
  }

  /**
   * Performs topological sort to determine execution order
   * Returns stages where tasks in the same stage can run in parallel
   */
  private topologicalSort(tasks: ROMATask[]): string[][] {
    const taskMap = new Map(tasks.map((t) => [t.id, t]));
    const inDegree = new Map<string, number>();
    const stages: string[][] = [];

    // Calculate in-degree (number of dependencies each task has)
    // Tasks with 0 dependencies can run first
    for (const task of tasks) {
      inDegree.set(task.id, task.dependencies.length);
    }

    // Process stages
    while (inDegree.size > 0) {
      const currentStage: string[] = [];

      // Find all tasks with in-degree 0 (can run in parallel)
      for (const [taskId, degree] of inDegree.entries()) {
        if (degree === 0) {
          currentStage.push(taskId);
        }
      }

      if (currentStage.length === 0) {
        break; // Cycle detected or done
      }

      stages.push(currentStage);

      // Remove processed tasks and update in-degrees of dependent tasks
      for (const taskId of currentStage) {
        inDegree.delete(taskId);

        // Find all tasks that depend on this completed task
        // and decrement their in-degree
        for (const [otherTaskId, otherTask] of taskMap.entries()) {
          if (otherTask.dependencies.includes(taskId) && inDegree.has(otherTaskId)) {
            inDegree.set(otherTaskId, inDegree.get(otherTaskId)! - 1);
          }
        }
      }
    }

    return stages;
  }

  /**
   * Estimates total execution time based on task durations
   */
  estimateExecutionTime(dag: ROMATaskDAG): number {
    // Simplified estimation - in reality would use task metadata
    return dag.executionOrder ? dag.executionOrder.length * 1000 : 0;
  }
}
