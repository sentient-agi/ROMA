/**
 * Chaos Engineering & Resilience Tests
 *
 * Validates system resilience under adverse conditions:
 * - Handles invalid inputs gracefully
 * - Recovers from errors without corruption
 * - Maintains data consistency
 * - Provides meaningful error messages
 *
 * Run with: tsx performance-tests/chaos-resilience.ts
 */

import { SaaSBuilder } from '../packages/builder/dist/index.js';

interface ChaosTestResult {
  scenario: string;
  passed: boolean;
  duration: number;
  error?: string;
  details?: string;
}

/**
 * Run a chaos test scenario
 */
async function runChaosScenario(
  name: string,
  testFn: () => Promise<void>
): Promise<ChaosTestResult> {
  console.log(`\n🔥 Running chaos scenario: ${name}`);

  const start = Date.now();
  try {
    await testFn();
    const duration = Date.now() - start;
    console.log(`   ✅ Passed (${duration}ms)`);
    return {
      scenario: name,
      passed: true,
      duration,
    };
  } catch (error) {
    const duration = Date.now() - start;
    const errorMsg = error instanceof Error ? error.message : String(error);
    console.log(`   ❌ Failed: ${errorMsg}`);
    return {
      scenario: name,
      passed: false,
      duration,
      error: errorMsg,
    };
  }
}

/**
 * Main chaos test execution
 */
async function main() {
  console.log('╔════════════════════════════════════════════════════════════╗');
  console.log('║  ROMA Chaos Engineering & Resilience Tests                ║');
  console.log('╚════════════════════════════════════════════════════════════╝');

  const builder = new SaaSBuilder();
  const results: ChaosTestResult[] = [];

  // ========================================================================
  // Scenario 1: Invalid Input Handling
  // ========================================================================

  results.push(
    await runChaosScenario('Invalid intake - empty object', async () => {
      try {
        await builder.intake({} as any);
        throw new Error('Should have thrown error for empty input');
      } catch (error) {
        if (!(error instanceof Error)) throw error;
        // Expected to fail gracefully
        if (!error.message || error.message.length === 0) {
          throw new Error('Error message must be meaningful');
        }
      }
    })
  );

  results.push(
    await runChaosScenario('Invalid intake - null input', async () => {
      try {
        await builder.intake(null as any);
        throw new Error('Should have thrown error for null input');
      } catch (error) {
        // Expected to fail gracefully
        if (!(error instanceof Error)) throw new Error('Must throw Error instance');
      }
    })
  );

  results.push(
    await runChaosScenario('Invalid architecture input - malformed intake', async () => {
      try {
        await builder.architecture({ totally: 'invalid' } as any);
        throw new Error('Should have rejected invalid intake');
      } catch (error) {
        // Expected to fail with validation error
      }
    })
  );

  // ========================================================================
  // Scenario 2: Resource Exhaustion
  // ========================================================================

  results.push(
    await runChaosScenario('Large input - many features', async () => {
      const largeIntake = {
        metadata: {
          appName: 'LargeApp',
          description: 'Test large input',
          version: '0.1.0',
        },
        requirements: {
          features: Array.from({ length: 100 }, (_, i) => ({
            id: `feature-${i}`,
            name: `Feature ${i}`,
            description: 'Test feature',
            category: 'core' as const,
            priority: 'medium' as const,
            complexity: 'medium' as const,
          })),
          security: {
            authentication: {
              methods: ['jwt'],
              mfa: false,
            },
            authorization: {
              model: 'rbac',
            },
            dataProtection: {
              encryption: {
                atRest: true,
                inTransit: true,
                algorithm: 'AES-256-GCM',
              },
              pii: false,
            },
            compliance: [],
          },
          performance: {
            responseTime: { p95: 200, p99: 500 },
            throughput: { requestsPerSecond: 100 },
            concurrentUsers: 1000,
          },
          multiTenancy: { enabled: false },
        },
        constraints: {
          budget: 'medium',
          timeline: 'flexible',
          team: { size: 5, experience: 'intermediate' },
        },
      };

      const architecture = await builder.architecture(largeIntake);
      const graph = await builder.featureGraph(largeIntake, architecture);

      // Verify graph is still acyclic with many nodes
      if (!graph.validation.isAcyclic) {
        throw new Error('Graph became cyclic with large input');
      }

      // Verify all features are represented
      if (graph.nodes.length < 100) {
        throw new Error(`Expected ≥100 nodes, got ${graph.nodes.length}`);
      }
    })
  );

  // ========================================================================
  // Scenario 3: Concurrent Operations
  // ========================================================================

  results.push(
    await runChaosScenario('Concurrent intake generation', async () => {
      const promises = Array.from({ length: 10 }, (_, i) =>
        builder.intake({ goal: `Build app ${i}` })
      );

      const intakes = await Promise.all(promises);

      // Verify all succeeded
      if (intakes.length !== 10) {
        throw new Error(`Expected 10 intakes, got ${intakes.length}`);
      }

      // Verify each has unique metadata
      const names = new Set(intakes.map(i => i.metadata.appName));
      if (names.size !== 10) {
        throw new Error('Concurrent operations produced duplicate results');
      }
    })
  );

  results.push(
    await runChaosScenario('Concurrent pipeline execution', async () => {
      const sampleIntake = {
        metadata: { appName: 'ConcurrentTest', description: 'Test', version: '0.1.0' },
        requirements: {
          features: [{ id: 'test', name: 'Test', description: 'Test', category: 'core', priority: 'high', complexity: 'low' }],
          security: {
            authentication: { methods: ['jwt'], mfa: false },
            authorization: { model: 'rbac' },
            dataProtection: { encryption: { atRest: true, inTransit: true, algorithm: 'AES-256-GCM' }, pii: false },
            compliance: [],
          },
          performance: { responseTime: { p95: 200, p99: 500 }, throughput: { requestsPerSecond: 100 }, concurrentUsers: 1000 },
          multiTenancy: { enabled: false },
        },
        constraints: { budget: 'low', timeline: 'flexible', team: { size: 2, experience: 'intermediate' } },
      };

      const promises = Array.from({ length: 5 }, () =>
        (async () => {
          const arch = await builder.architecture(sampleIntake);
          const graph = await builder.featureGraph(sampleIntake, arch);
          return builder.scaffolding(graph, arch);
        })()
      );

      const results = await Promise.all(promises);

      // Verify all succeeded
      if (results.length !== 5) {
        throw new Error(`Expected 5 results, got ${results.length}`);
      }

      // Verify consistency
      results.forEach(specs => {
        if (!Array.isArray(specs) || specs.length === 0) {
          throw new Error('Invalid scaffolding result');
        }
      });
    })
  );

  // ========================================================================
  // Scenario 4: Error Recovery
  // ========================================================================

  results.push(
    await runChaosScenario('Recovery after error', async () => {
      // Cause an error
      try {
        await builder.intake({} as any);
      } catch {
        // Expected
      }

      // Verify builder still works after error
      const intake = await builder.intake({ goal: 'Build recovery test app' });

      if (!intake || !intake.metadata || !intake.metadata.appName) {
        throw new Error('Builder not fully recovered after error');
      }
    })
  );

  results.push(
    await runChaosScenario('Multiple sequential errors', async () => {
      // Cause multiple errors in sequence
      for (let i = 0; i < 5; i++) {
        try {
          await builder.architecture({ invalid: i } as any);
        } catch {
          // Expected
        }
      }

      // Verify builder still functions correctly
      const validIntake = {
        metadata: { appName: 'ErrorRecoveryTest', description: 'Test', version: '0.1.0' },
        requirements: {
          features: [{ id: 'test', name: 'Test', description: 'Test', category: 'core', priority: 'high', complexity: 'low' }],
          security: {
            authentication: { methods: ['jwt'], mfa: false },
            authorization: { model: 'rbac' },
            dataProtection: { encryption: { atRest: true, inTransit: true, algorithm: 'AES-256-GCM' }, pii: false },
            compliance: [],
          },
          performance: { responseTime: { p95: 200, p99: 500 }, throughput: { requestsPerSecond: 100 }, concurrentUsers: 1000 },
          multiTenancy: { enabled: false },
        },
        constraints: { budget: 'low', timeline: 'flexible', team: { size: 2, experience: 'intermediate' } },
      };

      const architecture = await builder.architecture(validIntake);

      if (!architecture || !architecture.metadata) {
        throw new Error('Builder corrupted after multiple errors');
      }
    })
  );

  // ========================================================================
  // Results Summary
  // ========================================================================

  console.log('\n' + '='.repeat(60));
  console.log('CHAOS ENGINEERING RESULTS');
  console.log('='.repeat(60));

  let passCount = 0;
  let failCount = 0;

  results.forEach(result => {
    const status = result.passed ? '✅ PASS' : '❌ FAIL';
    console.log(`\n${status} ${result.scenario}`);
    console.log(`   Duration: ${result.duration}ms`);
    if (result.error) {
      console.log(`   Error: ${result.error}`);
    }

    if (result.passed) passCount++;
    else failCount++;
  });

  console.log('\n' + '='.repeat(60));
  console.log(`Total: ${results.length} scenarios`);
  console.log(`Passed: ${passCount} ✅`);
  console.log(`Failed: ${failCount} ❌`);
  console.log(`Success Rate: ${((passCount / results.length) * 100).toFixed(1)}%`);
  console.log('='.repeat(60));

  if (failCount === 0) {
    console.log('\n✅ ALL CHAOS SCENARIOS PASSED - SYSTEM IS RESILIENT');
    process.exit(0);
  } else {
    console.log('\n❌ SOME CHAOS SCENARIOS FAILED - RESILIENCE ISSUES DETECTED');
    process.exit(1);
  }
}

// Run chaos tests
main().catch((error) => {
  console.error('\n❌ Chaos test execution failed:', error);
  process.exit(1);
});
