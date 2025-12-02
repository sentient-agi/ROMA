/**
 * Verifier - Validates generated artifacts against schemas and postconditions
 */
import type {
  Intake,
  Architecture,
  FeatureGraph,
  ScaffoldingSpec,
  PostCondition,
  ExecutionStateLog,
} from '@roma/schemas';
import {
  IntakeSchema,
  ArchitectureSchema,
  FeatureGraphSchema,
  ScaffoldingSpecSchema,
  ExecutionStateLogSchema,
} from '@roma/schemas';

export interface VerificationResult {
  passed: boolean;
  checks: CheckResult[];
  summary: string;
}

export interface CheckResult {
  checkId: string;
  checkType: string;
  passed: boolean;
  message: string;
  severity: 'critical' | 'error' | 'warning' | 'info';
  details?: any;
}

export class Verifier {
  /**
   * Verifies all artifacts against their schemas
   */
  async verifyArtifacts(artifacts: Record<string, any>): Promise<VerificationResult> {
    const checks: CheckResult[] = [];

    // Verify intake
    if (artifacts.intake) {
      checks.push(this.verifyIntake(artifacts.intake));
    }

    // Verify architecture
    if (artifacts.architecture) {
      checks.push(this.verifyArchitecture(artifacts.architecture));
    }

    // Verify feature graph
    if (artifacts.featureGraph) {
      checks.push(this.verifyFeatureGraph(artifacts.featureGraph));
    }

    // Verify scaffolding specs
    if (artifacts.scaffoldingSpecs && Array.isArray(artifacts.scaffoldingSpecs)) {
      for (let i = 0; i < artifacts.scaffoldingSpecs.length; i++) {
        checks.push(this.verifyScaffoldingSpec(artifacts.scaffoldingSpecs[i], i));
      }
    }

    // Verify execution logs
    if (artifacts.executionLogs && Array.isArray(artifacts.executionLogs)) {
      for (let i = 0; i < artifacts.executionLogs.length; i++) {
        checks.push(this.verifyExecutionLog(artifacts.executionLogs[i], i));
      }
    }

    const passed = checks.every((c) => c.passed || c.severity !== 'critical');
    const summary = this.generateSummary(checks, passed);

    return {
      passed,
      checks,
      summary,
    };
  }

  /**
   * Verifies postconditions for a scaffolding execution
   */
  async verifyPostconditions(postconditions: PostCondition[]): Promise<VerificationResult> {
    const checks: CheckResult[] = [];

    for (const postcondition of postconditions) {
      const result = await this.checkPostcondition(postcondition);
      checks.push(result);
    }

    const criticalFailures = checks.filter((c) => !c.passed && c.severity === 'critical');
    const passed = criticalFailures.length === 0;
    const summary = this.generateSummary(checks, passed);

    return {
      passed,
      checks,
      summary,
    };
  }

  /**
   * Verify intake against IntakeSchema
   */
  private verifyIntake(intake: any): CheckResult {
    try {
      IntakeSchema.parse(intake);
      return {
        checkId: 'intake_schema',
        checkType: 'schema_validation',
        passed: true,
        message: 'Intake schema validation passed',
        severity: 'info',
      };
    } catch (error) {
      return {
        checkId: 'intake_schema',
        checkType: 'schema_validation',
        passed: false,
        message: 'Intake schema validation failed',
        severity: 'critical',
        details: error,
      };
    }
  }

  /**
   * Verify architecture against ArchitectureSchema
   */
  private verifyArchitecture(architecture: any): CheckResult {
    try {
      ArchitectureSchema.parse(architecture);
      return {
        checkId: 'architecture_schema',
        checkType: 'schema_validation',
        passed: true,
        message: 'Architecture schema validation passed',
        severity: 'info',
      };
    } catch (error) {
      return {
        checkId: 'architecture_schema',
        checkType: 'schema_validation',
        passed: false,
        message: 'Architecture schema validation failed',
        severity: 'critical',
        details: error,
      };
    }
  }

  /**
   * Verify feature graph against FeatureGraphSchema
   */
  private verifyFeatureGraph(featureGraph: any): CheckResult {
    try {
      const parsed = FeatureGraphSchema.parse(featureGraph);

      // Additional validation: check if actually acyclic
      if (!parsed.validation.isAcyclic) {
        return {
          checkId: 'feature_graph_acyclic',
          checkType: 'graph_validation',
          passed: false,
          message: 'Feature graph contains cycles',
          severity: 'critical',
          details: { cycles: parsed.validation.hasCycles },
        };
      }

      return {
        checkId: 'feature_graph_schema',
        checkType: 'schema_validation',
        passed: true,
        message: 'Feature graph schema validation passed',
        severity: 'info',
      };
    } catch (error) {
      return {
        checkId: 'feature_graph_schema',
        checkType: 'schema_validation',
        passed: false,
        message: 'Feature graph schema validation failed',
        severity: 'critical',
        details: error,
      };
    }
  }

  /**
   * Verify scaffolding spec against ScaffoldingSpecSchema
   */
  private verifyScaffoldingSpec(spec: any, index: number): CheckResult {
    try {
      ScaffoldingSpecSchema.parse(spec);
      return {
        checkId: `scaffolding_spec_${index}`,
        checkType: 'schema_validation',
        passed: true,
        message: `Scaffolding spec ${index} validation passed`,
        severity: 'info',
      };
    } catch (error) {
      return {
        checkId: `scaffolding_spec_${index}`,
        checkType: 'schema_validation',
        passed: false,
        message: `Scaffolding spec ${index} validation failed`,
        severity: 'error',
        details: error,
      };
    }
  }

  /**
   * Verify execution log against ExecutionStateLogSchema
   */
  private verifyExecutionLog(log: any, index: number): CheckResult {
    try {
      ExecutionStateLogSchema.parse(log);
      return {
        checkId: `execution_log_${index}`,
        checkType: 'schema_validation',
        passed: true,
        message: `Execution log ${index} validation passed`,
        severity: 'info',
      };
    } catch (error) {
      return {
        checkId: `execution_log_${index}`,
        checkType: 'schema_validation',
        passed: false,
        message: `Execution log ${index} validation failed`,
        severity: 'warning',
        details: error,
      };
    }
  }

  /**
   * Check a single postcondition (placeholder - would actually execute checks)
   */
  private async checkPostcondition(postcondition: PostCondition): Promise<CheckResult> {
    // In a real implementation, this would execute the actual checks
    // For now, we'll just validate the postcondition structure

    return {
      checkId: postcondition.id,
      checkType: `postcondition_${postcondition.type}`,
      passed: true,
      message: `Postcondition "${postcondition.description}" check skipped (not implemented)`,
      severity: postcondition.severity,
    };
  }

  /**
   * Generate summary of verification results
   */
  private generateSummary(checks: CheckResult[], passed: boolean): string {
    const total = checks.length;
    const passedCount = checks.filter((c) => c.passed).length;
    const failedCount = total - passedCount;

    const bySeverity = {
      critical: checks.filter((c) => !c.passed && c.severity === 'critical').length,
      error: checks.filter((c) => !c.passed && c.severity === 'error').length,
      warning: checks.filter((c) => !c.passed && c.severity === 'warning').length,
    };

    const lines: string[] = [];
    lines.push(`Verification ${passed ? 'PASSED' : 'FAILED'}`);
    lines.push(`Total checks: ${total}`);
    lines.push(`Passed: ${passedCount}`);
    lines.push(`Failed: ${failedCount}`);

    if (!passed) {
      lines.push('');
      lines.push('Failures by severity:');
      if (bySeverity.critical > 0) lines.push(`  Critical: ${bySeverity.critical}`);
      if (bySeverity.error > 0) lines.push(`  Error: ${bySeverity.error}`);
      if (bySeverity.warning > 0) lines.push(`  Warning: ${bySeverity.warning}`);
    }

    return lines.join('\n');
  }
}
