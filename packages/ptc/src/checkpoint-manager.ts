/**
 * Checkpoint Manager - Handles execution state persistence and recovery
 */
import { writeFileSync, readFileSync, existsSync, mkdirSync, readdirSync, unlinkSync } from 'fs';
import { join, dirname } from 'path';
import type { ExecutionStateLog, StepExecutionResult } from '@roma/schemas';

export interface CheckpointOptions {
  checkpointDir?: string;
  autoSave?: boolean;
  saveInterval?: number; // Save after N steps
}

export interface ResumeOptions {
  validateState?: boolean;
  skipCompleted?: boolean;
}

export class CheckpointManager {
  private checkpointDir: string;
  private autoSave: boolean;
  private saveInterval: number;

  constructor(options: CheckpointOptions = {}) {
    this.checkpointDir = options.checkpointDir || '.roma/checkpoints';
    this.autoSave = options.autoSave ?? true;
    this.saveInterval = options.saveInterval ?? 1; // Save after every step by default

    // Ensure checkpoint directory exists
    if (!existsSync(this.checkpointDir)) {
      mkdirSync(this.checkpointDir, { recursive: true });
    }
  }

  /**
   * Save execution state to checkpoint
   */
  saveCheckpoint(log: ExecutionStateLog): string {
    const checkpointPath = this.getCheckpointPath(log.executionId);

    // Ensure directory exists
    const dir = dirname(checkpointPath);
    if (!existsSync(dir)) {
      mkdirSync(dir, { recursive: true });
    }

    // Add checkpoint metadata
    const checkpoint = {
      ...log,
      checkpointedAt: new Date().toISOString(),
      version: '1.0.0',
    };

    writeFileSync(checkpointPath, JSON.stringify(checkpoint, null, 2));
    return checkpointPath;
  }

  /**
   * Load execution state from checkpoint
   */
  loadCheckpoint(executionId: string): ExecutionStateLog | null {
    const checkpointPath = this.getCheckpointPath(executionId);

    if (!existsSync(checkpointPath)) {
      return null;
    }

    try {
      const data = readFileSync(checkpointPath, 'utf-8');
      const checkpoint = JSON.parse(data);

      // Remove checkpoint metadata
      delete checkpoint.checkpointedAt;
      delete checkpoint.version;

      return checkpoint as ExecutionStateLog;
    } catch (error) {
      console.error(`Failed to load checkpoint ${executionId}:`, error);
      return null;
    }
  }

  /**
   * Check if checkpoint exists
   */
  hasCheckpoint(executionId: string): boolean {
    return existsSync(this.getCheckpointPath(executionId));
  }

  /**
   * Validate checkpoint state integrity
   */
  validateCheckpoint(log: ExecutionStateLog): ValidationResult {
    const errors: string[] = [];
    const warnings: string[] = [];

    // Check required fields
    if (!log.executionId) {
      errors.push('Missing executionId');
    }
    if (!log.featureId) {
      errors.push('Missing featureId');
    }
    if (!log.startedAt) {
      errors.push('Missing startedAt timestamp');
    }
    if (!Array.isArray(log.steps)) {
      errors.push('Missing or invalid steps array');
    }

    // Validate step sequence
    if (log.steps) {
      for (let i = 0; i < log.steps.length; i++) {
        const step = log.steps[i];

        if (step.stepIndex !== i) {
          errors.push(`Step ${i} has incorrect stepIndex: ${step.stepIndex}`);
        }

        if (!step.startedAt) {
          errors.push(`Step ${i} missing startedAt timestamp`);
        }

        // Check for orphaned steps (incomplete steps in the middle)
        if (i < log.steps.length - 1 && !step.completedAt) {
          warnings.push(`Step ${i} is incomplete but not the last step`);
        }
      }
    }

    // Validate status transitions
    if (log.status === 'completed' && !log.completedAt) {
      errors.push('Status is completed but missing completedAt timestamp');
    }

    if (log.status === 'running' && log.completedAt) {
      warnings.push('Status is running but has completedAt timestamp');
    }

    return {
      valid: errors.length === 0,
      errors,
      warnings,
    };
  }

  /**
   * Get next step index to execute (resume point)
   */
  getResumePoint(log: ExecutionStateLog): number {
    if (!log.steps || log.steps.length === 0) {
      return 0;
    }

    // Find first incomplete or failed step
    for (let i = 0; i < log.steps.length; i++) {
      const step = log.steps[i];

      // Step not completed or failed
      if (!step.completedAt || !step.success) {
        return i;
      }
    }

    // All steps completed
    return log.steps.length;
  }

  /**
   * Check if execution can be resumed
   */
  canResume(log: ExecutionStateLog, options: ResumeOptions = {}): CanResumeResult {
    const validation = this.validateCheckpoint(log);

    if (!validation.valid) {
      return {
        canResume: false,
        reason: `Invalid checkpoint: ${validation.errors.join(', ')}`,
        resumeFromStep: -1,
      };
    }

    if (log.status === 'completed') {
      return {
        canResume: false,
        reason: 'Execution already completed',
        resumeFromStep: -1,
      };
    }

    if (log.status === 'rolled_back') {
      return {
        canResume: false,
        reason: 'Execution was rolled back',
        resumeFromStep: -1,
      };
    }

    const resumePoint = this.getResumePoint(log);

    return {
      canResume: true,
      resumeFromStep: resumePoint,
      completedSteps: resumePoint,
      totalSteps: log.steps?.length || 0,
    };
  }

  /**
   * List all checkpoints
   */
  listCheckpoints(): string[] {
    if (!existsSync(this.checkpointDir)) {
      return [];
    }

    const files = readdirSync(this.checkpointDir);
    return files
      .filter((f: string) => f.endsWith('.checkpoint.json'))
      .map((f: string) => f.replace('.checkpoint.json', ''));
  }

  /**
   * Delete checkpoint
   */
  deleteCheckpoint(executionId: string): boolean {
    const checkpointPath = this.getCheckpointPath(executionId);

    if (existsSync(checkpointPath)) {
      unlinkSync(checkpointPath);
      return true;
    }

    return false;
  }

  /**
   * Get checkpoint file path
   */
  private getCheckpointPath(executionId: string): string {
    return join(this.checkpointDir, `${executionId}.checkpoint.json`);
  }
}

export interface ValidationResult {
  valid: boolean;
  errors: string[];
  warnings: string[];
}

export interface CanResumeResult {
  canResume: boolean;
  reason?: string;
  resumeFromStep: number;
  completedSteps?: number;
  totalSteps?: number;
}
