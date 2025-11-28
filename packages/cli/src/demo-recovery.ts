#!/usr/bin/env node
/**
 * Recovery & Checkpoint Demo
 *
 * Demonstrates:
 * 1. Execution with automatic checkpointing
 * 2. Simulated failure mid-build
 * 3. Resume from checkpoint
 * 4. Secret sanitization
 * 5. Failure scenarios with retry
 */

import { readFileSync } from 'fs';
import { join, dirname } from 'path';
import { fileURLToPath } from 'url';
import {
  PtcExecutorEnhanced,
  CheckpointManager,
  SecretSanitizer,
  getGlobalSanitizer,
} from '@roma/ptc';
import { ScaffoldingSpecSchema } from '@roma/schemas';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

async function main() {
  console.log('╔═══════════════════════════════════════════════════════════════╗');
  console.log('║  ROMA Recovery & Checkpoint Demo                              ║');
  console.log('╚═══════════════════════════════════════════════════════════════╝\n');

  // Demo 1: Secret Sanitization
  console.log('📋 DEMO 1: Secret Sanitization\n');
  await demoSecretSanitization();

  console.log('\n' + '─'.repeat(65) + '\n');

  // Demo 2: Execution with Checkpoint
  console.log('💾 DEMO 2: Execution with Automatic Checkpointing\n');
  const { executionId, spec } = await demoExecutionWithCheckpoint();

  console.log('\n' + '─'.repeat(65) + '\n');

  // Demo 3: Simulated Failure & Resume
  console.log('🔄 DEMO 3: Failure Simulation & Resume\n');
  await demoFailureAndResume(executionId, spec);

  console.log('\n' + '─'.repeat(65) + '\n');

  // Demo 4: Retry Logic with Backoff
  console.log('🔁 DEMO 4: Retry Logic & Backoff Strategies\n');
  await demoRetryLogic();

  console.log('\n╔═══════════════════════════════════════════════════════════════╗');
  console.log('║  All Demos Completed Successfully!                            ║');
  console.log('╚═══════════════════════════════════════════════════════════════╝');
}

async function demoSecretSanitization() {
  const sanitizer = new SecretSanitizer();

  // Register fake secrets
  const realStripeKey = 'sk_live_51abc123def456ghi789jkl';
  const realJWT = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.abc123';
  const realDBPassword = 'MySecretP@ssw0rd!';

  sanitizer.registerSecret(realStripeKey);
  sanitizer.registerSecret(realJWT);
  sanitizer.registerSecret(realDBPassword);

  console.log('✅ Registered 3 secrets\n');

  // Test 1: String sanitization
  const logMessage = `Connecting to database with password: ${realDBPassword}`;
  const sanitized = sanitizer.sanitizeString(logMessage);

  console.log('Original log:');
  console.log(`  "${logMessage}"`);
  console.log('\nSanitized log:');
  console.log(`  "${sanitized}"`);
  console.log('');

  // Test 2: Object sanitization
  const config = {
    stripe: {
      apiKey: realStripeKey,
      webhook: 'https://example.com/webhook',
    },
    database: {
      password: realDBPassword,
      host: 'localhost',
    },
    jwt: {
      secret: realJWT,
      algorithm: 'HS256',
    },
  };

  console.log('Original config object:');
  console.log(JSON.stringify(config, null, 2));

  const sanitizedConfig = sanitizer.sanitizeObject(config);

  console.log('\nSanitized config object:');
  console.log(JSON.stringify(sanitizedConfig, null, 2));
  console.log('');

  // Test 3: Leak detection
  const violations = sanitizer.validateNoSecrets(config);

  console.log(`Secret leak detection: Found ${violations.length} violations`);
  if (violations.length > 0) {
    for (const v of violations.slice(0, 3)) {
      console.log(`  ⚠️  ${v.path}: ${v.message}`);
    }
  }
  console.log('');
}

async function demoExecutionWithCheckpoint() {
  const EXAMPLES_DIR = join(__dirname, '../../examples/onthisday');

  // Load auth scaffolding spec
  const authSpecJson = readFileSync(join(EXAMPLES_DIR, 'scaffolding_auth.json'), 'utf-8');
  const spec = ScaffoldingSpecSchema.parse(JSON.parse(authSpecJson));

  console.log(`Feature: ${spec.metadata.featureName}`);
  console.log(`Steps: ${spec.steps.length}`);
  console.log(`Postconditions: ${spec.postconditions.length}\n`);

  // Create executor with checkpoints enabled
  const executor = new PtcExecutorEnhanced({
    verbose: true,
    enableCheckpoints: true,
    checkpointDir: '.roma/checkpoints-demo',
    trackMetrics: true,
  });

  console.log('Starting execution with automatic checkpointing...\n');

  const result = await executor.execute(spec);

  console.log(`\n✅ Execution ${result.success ? 'SUCCESSFUL' : 'FAILED'}`);
  console.log(`Execution ID: ${result.log.executionId}`);
  console.log(`Steps completed: ${result.log.steps.length}`);
  console.log(`Checkpoint saved after each step\n`);

  // Show metrics
  const metrics = executor.getMetrics();
  console.log('Metrics:');
  console.log(`  Total executions: ${metrics.totalExecutions}`);
  console.log(`  Successful: ${metrics.successfulExecutions}`);
  console.log(`  Total steps: ${metrics.totalSteps}`);
  console.log(`  Average step duration: ${metrics.averageStepDuration.toFixed(2)}ms`);

  return { executionId: result.log.executionId, spec };
}

async function demoFailureAndResume(executionId: string, spec: any) {
  console.log('Simulating build failure at step 3...\n');

  // Create executor with failure scenario
  const executor = new PtcExecutorEnhanced({
    verbose: true,
    enableCheckpoints: true,
    checkpointDir: '.roma/checkpoints-demo',
    failureScenarios: [
      {
        stepIndex: 2, // Fail at step 3 (0-indexed)
        failureType: 'error',
        errorMessage: 'Simulated network timeout',
      },
    ],
  });

  // Execute with failure
  console.log('Executing with failure injection...\n');
  const failedResult = await executor.execute(spec);

  console.log(`❌ Execution FAILED at step ${failedResult.log.steps.length}`);
  console.log(`Error: ${failedResult.error}\n`);

  // Check checkpoint
  const checkpointManager = new CheckpointManager({
    checkpointDir: '.roma/checkpoints-demo',
  });

  const checkpoint = checkpointManager.loadCheckpoint(failedResult.log.executionId);
  if (!checkpoint) {
    console.log('❌ No checkpoint found!');
    return;
  }

  console.log('✅ Checkpoint loaded');

  const resumeCheck = checkpointManager.canResume(checkpoint);

  console.log(`Resume available: ${resumeCheck.canResume}`);
  console.log(`Resume from step: ${resumeCheck.resumeFromStep}`);
  console.log(`Completed steps: ${resumeCheck.completedSteps}/${resumeCheck.totalSteps}\n`);

  // Resume without failure scenario
  console.log('Resuming execution from checkpoint...\n');

  const resumeExecutor = new PtcExecutorEnhanced({
    verbose: true,
    enableCheckpoints: true,
    checkpointDir: '.roma/checkpoints-demo',
    failureScenarios: [], // No failures this time
  });

  const resumedResult = await resumeExecutor.resume(failedResult.log.executionId, spec);

  console.log(`\n✅ Resume ${resumedResult.success ? 'SUCCESSFUL' : 'FAILED'}`);
  console.log(`Total steps completed: ${resumedResult.log.steps.length}`);
  console.log(`Final status: ${resumedResult.log.status}`);
}

async function demoRetryLogic() {
  const EXAMPLES_DIR = join(__dirname, '../../examples/onthisday');
  const authSpecJson = readFileSync(join(EXAMPLES_DIR, 'scaffolding_auth.json'), 'utf-8');
  const spec = ScaffoldingSpecSchema.parse(JSON.parse(authSpecJson));

  console.log('Testing transient failure with retry...\n');

  const executor = new PtcExecutorEnhanced({
    verbose: true,
    enableCheckpoints: false,
    trackMetrics: true,
    failureScenarios: [
      {
        stepIndex: 1,
        failureType: 'error',
        recoverAfterAttempts: 2, // Fail twice, then succeed
        errorMessage: 'Transient network error',
      },
    ],
  });

  const result = await executor.execute(spec);

  console.log(`\n✅ Execution ${result.success ? 'SUCCESSFUL' : 'FAILED'}`);

  // Check retry counts
  const attemptCounts = executor.getAttemptCounts();
  console.log(`\nRetry statistics:`);

  for (const [key, count] of attemptCounts.entries()) {
    if (count > 1) {
      console.log(`  Step required ${count} attempts (${count - 1} retries)`);
    }
  }

  const metrics = executor.getMetrics();
  console.log(`\nTotal retried steps: ${metrics.retriedSteps}`);
  console.log(`Success rate: ${(metrics.successfulExecutions / metrics.totalExecutions * 100).toFixed(1)}%`);
}

// Run if executed directly
if (import.meta.url === `file://${process.argv[1]}`) {
  main().catch((error) => {
    console.error('Fatal error:', error);
    process.exit(1);
  });
}
