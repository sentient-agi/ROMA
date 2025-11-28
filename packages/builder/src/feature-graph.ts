/**
 * Feature Graph Mode - Build dependency graph from intake and architecture
 */
import type { Intake, Architecture, FeatureGraph, FeatureNode, ExecutionStage } from '@roma/schemas';
import { FeatureGraphSchema } from '@roma/schemas';

export class FeatureGraphBuilder {
  /**
   * Generate feature graph from intake and architecture
   */
  async fromIntakeAndArchitecture(intake: Intake, architecture: Architecture): Promise<FeatureGraph> {
    // Build nodes from features
    const nodes = this.buildNodes(intake, architecture);

    // Compute execution stages
    const executionStages = this.computeExecutionStages(nodes);

    // Validate graph
    const validation = this.validateGraph(nodes);

    // Compute statistics
    const statistics = this.computeStatistics(nodes, executionStages);

    const graph: FeatureGraph = {
      metadata: {
        version: '1.0.0',
        generatedAt: new Date().toISOString(),
        basedOnArchitecture: architecture.metadata.version,
      },
      nodes,
      executionStages,
      validation,
      statistics,
    };

    return FeatureGraphSchema.parse(graph);
  }

  private buildNodes(intake: Intake, architecture: Architecture): FeatureNode[] {
    const nodes: FeatureNode[] = [];

    // Add infrastructure node first
    nodes.push({
      id: 'infrastructure',
      name: 'Base Infrastructure',
      description: 'Database, Docker, and project structure',
      type: 'infrastructure',
      priority: 10,
      estimatedComplexity: 'medium',
      dependencies: [],
      outputs: [
        { name: 'database_schema', type: 'sql', description: 'Database schema and migrations' },
        { name: 'docker_config', type: 'yaml', description: 'Docker configuration' },
      ],
    });

    // Add feature nodes
    for (const feature of intake.requirements.features) {
      const dependencies = this.inferDependencies(feature, intake.requirements.features);

      nodes.push({
        id: feature.id,
        name: feature.name,
        description: feature.description,
        type: this.mapFeatureType(feature.type),
        priority: this.mapPriority(feature.priority),
        estimatedComplexity: this.estimateComplexity(feature),
        dependencies: ['infrastructure', ...dependencies].map((depId) => ({
          featureId: depId,
          type: depId === 'infrastructure' ? 'hard' : 'hard',
          reason: depId === 'infrastructure' ? 'Requires base infrastructure' : 'Feature dependency',
        })),
        outputs: this.inferOutputs(feature),
        inputs: this.inferInputs(feature, dependencies),
      });
    }

    return nodes;
  }

  private inferDependencies(feature: any, allFeatures: any[]): string[] {
    const deps: string[] = [];

    // Check explicit dependencies
    if (feature.dependencies) {
      deps.push(...feature.dependencies);
    }

    // Infer from data model relationships
    if (feature.dataModel?.entities) {
      for (const entity of feature.dataModel.entities) {
        if (entity.relationships) {
          for (const rel of entity.relationships) {
            // Find feature that provides this entity
            const providerFeature = allFeatures.find((f) =>
              f.dataModel?.entities.some((e: any) => e.name === rel.target)
            );
            if (providerFeature && providerFeature.id !== feature.id) {
              deps.push(providerFeature.id);
            }
          }
        }
      }
    }

    return [...new Set(deps)]; // Remove duplicates
  }

  private inferOutputs(feature: any) {
    const outputs: Array<{ name: string; type: string; description: string }> = [];

    if (feature.dataModel?.entities) {
      for (const entity of feature.dataModel.entities) {
        outputs.push({
          name: `${entity.name.toLowerCase()}_model`,
          type: 'model',
          description: `${entity.name} database model`,
        });
      }
    }

    if (feature.api?.endpoints) {
      outputs.push({
        name: `${feature.id}_api`,
        type: 'routes',
        description: `${feature.name} API routes`,
      });
    }

    return outputs.length > 0 ? outputs : undefined;
  }

  private inferInputs(feature: any, dependencies: string[]) {
    if (dependencies.length === 0) return undefined;

    return dependencies.map((depId) => ({
      name: `${depId}_model`,
      type: 'model',
      source: depId,
    }));
  }

  private computeExecutionStages(nodes: FeatureNode[]): ExecutionStage[] {
    const stages: ExecutionStage[] = [];
    const processed = new Set<string>();
    let stageNumber = 1;

    while (processed.size < nodes.length) {
      const currentStage: string[] = [];

      // Find nodes whose dependencies are all processed
      for (const node of nodes) {
        if (processed.has(node.id)) continue;

        const allDepsProcessed = node.dependencies.every((dep) => processed.has(dep.featureId));

        if (allDepsProcessed) {
          currentStage.push(node.id);
        }
      }

      if (currentStage.length === 0) {
        break; // Cycle or error
      }

      stages.push({
        stageNumber,
        name: `Stage ${stageNumber}`,
        description: this.getStageDescription(currentStage, nodes),
        features: currentStage,
      });

      currentStage.forEach((id) => processed.add(id));
      stageNumber++;
    }

    return stages;
  }

  private getStageDescription(featureIds: string[], nodes: FeatureNode[]): string {
    const features = nodes.filter((n) => featureIds.includes(n.id));
    if (features.every((f) => f.type === 'infrastructure')) return 'Infrastructure setup';
    if (features.every((f) => f.type === 'backend')) return 'Backend services';
    if (features.every((f) => f.type === 'frontend')) return 'Frontend application';
    return 'Feature implementation';
  }

  private validateGraph(nodes: FeatureNode[]) {
    const visited = new Set<string>();
    const recursionStack = new Set<string>();
    const cycles: string[][] = [];

    const hasCycle = (nodeId: string, path: string[]): boolean => {
      if (recursionStack.has(nodeId)) {
        const cycleStart = path.indexOf(nodeId);
        cycles.push([...path.slice(cycleStart), nodeId]);
        return true;
      }

      if (visited.has(nodeId)) return false;

      visited.add(nodeId);
      recursionStack.add(nodeId);
      path.push(nodeId);

      const node = nodes.find((n) => n.id === nodeId);
      if (node) {
        for (const dep of node.dependencies) {
          if (hasCycle(dep.featureId, [...path])) {
            return true;
          }
        }
      }

      recursionStack.delete(nodeId);
      return false;
    };

    for (const node of nodes) {
      if (!visited.has(node.id)) {
        hasCycle(node.id, []);
      }
    }

    return {
      isAcyclic: cycles.length === 0,
      hasCycles: cycles.length > 0 ? cycles : undefined,
      unreachableNodes: undefined,
      criticalPath: this.findCriticalPath(nodes),
    };
  }

  private findCriticalPath(nodes: FeatureNode[]): string[] {
    // Simple longest path algorithm
    const paths: string[][] = [];

    const findPaths = (nodeId: string, currentPath: string[]) => {
      currentPath.push(nodeId);

      const node = nodes.find((n) => n.id === nodeId);
      if (!node || node.dependencies.length === 0) {
        paths.push([...currentPath]);
      } else {
        for (const dep of node.dependencies) {
          findPaths(dep.featureId, [...currentPath]);
        }
      }
    };

    for (const node of nodes) {
      findPaths(node.id, []);
    }

    // Return longest path
    return paths.reduce((longest, current) => (current.length > longest.length ? current : longest), []);
  }

  private computeStatistics(nodes: FeatureNode[], stages: ExecutionStage[]) {
    const totalHours = nodes
      .map((n) => n.metadata?.estimatedHours || 0)
      .reduce((sum, hours) => sum + hours, 0);

    return {
      totalFeatures: nodes.length,
      totalStages: stages.length,
      estimatedTotalHours: totalHours || undefined,
      parallelizationFactor: stages.length > 0 ? nodes.length / stages.length : 1,
    };
  }

  private mapFeatureType(type: string): 'infrastructure' | 'backend' | 'frontend' | 'integration' | 'testing' {
    const typeMap: Record<string, 'infrastructure' | 'backend' | 'frontend' | 'integration' | 'testing'> = {
      crud: 'backend',
      workflow: 'backend',
      integration: 'integration',
      analytics: 'backend',
      custom: 'backend',
    };
    return typeMap[type] || 'backend';
  }

  private mapPriority(priority: string): number {
    const priorityMap: Record<string, number> = {
      critical: 10,
      high: 8,
      medium: 5,
      low: 2,
    };
    return priorityMap[priority] || 5;
  }

  private estimateComplexity(feature: any): 'low' | 'medium' | 'high' | 'critical' {
    let score = 0;

    if (feature.dataModel?.entities) {
      score += feature.dataModel.entities.length * 2;
    }

    if (feature.api?.endpoints) {
      score += feature.api.endpoints.length;
    }

    if (feature.ui?.pages) {
      score += feature.ui.pages.length * 3;
    }

    if (score >= 15) return 'critical';
    if (score >= 10) return 'high';
    if (score >= 5) return 'medium';
    return 'low';
  }
}
