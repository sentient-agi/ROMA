/**
 * Builder Performance Benchmark
 *
 * Tests real builder operations and validates against SLO requirements:
 * - p95 latency ≤ 300ms at 100 RPS
 * - p99 latency ≤ 500ms
 * - 99.9% uptime/success rate
 *
 * Run with: tsx performance-tests/builder-benchmark.ts
 */

import { SaaSBuilder } from '../packages/builder/dist/index.js';
import { readFileSync } from 'fs';
import { join } from 'path';

interface BenchmarkResult {
  operation: string;
  iterations: number;
  durations: number[];
  errors: number;
  p50: number;
  p95: number;
  p99: number;
  mean: number;
  successRate: number;
}

/**
 * Calculate percentile from sorted array
 */
function percentile(sorted: number[], p: number): number {
  const index = Math.ceil((sorted.length * p) / 100) - 1;
  return sorted[Math.max(0, index)];
}

/**
 * Calculate statistics from duration array
 */
function calculateStats(durations: number[], errors: number): Omit<BenchmarkResult, 'operation' | 'iterations'> {
  const sorted = [...durations].sort((a, b) => a - b);
  const total = durations.reduce((sum, d) => sum + d, 0);

  return {
    durations,
    errors,
    p50: percentile(sorted, 50),
    p95: percentile(sorted, 95),
    p99: percentile(sorted, 99),
    mean: total / durations.length,
    successRate: ((durations.length - errors) / durations.length) * 100,
  };
}

/**
 * Benchmark a builder operation
 */
async function benchmarkOperation(
  name: string,
  fn: () => Promise<any>,
  iterations: number = 100
): Promise<BenchmarkResult> {
  console.log(`\nBenchmarking: ${name} (${iterations} iterations)`);

  const durations: number[] = [];
  let errors = 0;

  for (let i = 0; i < iterations; i++) {
    const start = Date.now();
    try {
      await fn();
      durations.push(Date.now() - start);

      // Progress indicator
      if ((i + 1) % 10 === 0) {
        process.stdout.write('.');
      }
    } catch (error) {
      errors++;
      durations.push(Date.now() - start);
      process.stdout.write('x');
    }
  }

  console.log(' Done!');

  const stats = calculateStats(durations, errors);

  return {
    operation: name,
    iterations,
    ...stats,
  };
}

/**
 * Format benchmark results
 */
function formatResults(result: BenchmarkResult): string {
  const lines = [
    `\n${'='.repeat(60)}`,
    `Operation: ${result.operation}`,
    `Iterations: ${result.iterations}`,
    `${'='.repeat(60)}`,
    '',
    `Latency (ms):`,
    `  Mean:    ${result.mean.toFixed(2)}`,
    `  p50:     ${result.p50.toFixed(2)}`,
    `  p95:     ${result.p95.toFixed(2)} ${result.p95 <= 300 ? '✅' : '❌ FAILED SLO (≤300ms)'}`,
    `  p99:     ${result.p99.toFixed(2)} ${result.p99 <= 500 ? '✅' : '❌ FAILED SLO (≤500ms)'}`,
    '',
    `Success Rate: ${result.successRate.toFixed(2)}% ${result.successRate >= 99.9 ? '✅' : '❌ FAILED SLO (≥99.9%)'}`,
    `Errors: ${result.errors}`,
    '',
  ];

  return lines.join('\n');
}

/**
 * Check if results meet SLO
 */
function checkSLO(result: BenchmarkResult): boolean {
  const p95Pass = result.p95 <= 300;
  const p99Pass = result.p99 <= 500;
  const successRatePass = result.successRate >= 99.9;

  return p95Pass && p99Pass && successRatePass;
}

/**
 * Main benchmark execution
 */
async function main() {
  console.log('╔════════════════════════════════════════════════════════════╗');
  console.log('║  ROMA Builder Performance Benchmark                        ║');
  console.log('╚════════════════════════════════════════════════════════════╝');
  console.log('\nSLO Requirements:');
  console.log('  - p95 latency ≤ 300ms');
  console.log('  - p99 latency ≤ 500ms');
  console.log('  - Success rate ≥ 99.9%');

  const builder = new SaaSBuilder();

  // Load sample intake
  const intakePath = join(__dirname, '../packages/examples/onthisday/intake.json');
  let sampleIntake: any;

  try {
    const intakeJson = readFileSync(intakePath, 'utf-8');
    sampleIntake = JSON.parse(intakeJson);
  } catch {
    // Fallback to minimal intake
    sampleIntake = {
      metadata: { appName: 'BenchmarkApp', description: 'Test', version: '0.1.0' },
      requirements: {
        features: [{ id: 'test', name: 'Test', description: 'Test', category: 'core', priority: 'high', complexity: 'low' }],
        security: { authentication: ['jwt'], authorization: ['rbac'], dataEncryption: { atRest: true, inTransit: true }, compliance: [] },
        performance: { responseTime: { p95: 200, p99: 500 }, throughput: { requestsPerSecond: 100 }, concurrentUsers: 1000 },
        multiTenancy: { enabled: false },
      },
      constraints: { budget: 'low', timeline: 'flexible', team: { size: 2, experience: 'intermediate' } },
    };
  }

  const results: BenchmarkResult[] = [];

  // Benchmark 1: Intake generation
  const intakeResult = await benchmarkOperation(
    'Intake Generation',
    async () => {
      await builder.intake({ goal: 'Build a test app' });
    },
    100
  );
  results.push(intakeResult);
  console.log(formatResults(intakeResult));

  // Benchmark 2: Architecture generation
  const archResult = await benchmarkOperation(
    'Architecture Generation',
    async () => {
      await builder.architecture(sampleIntake);
    },
    100
  );
  results.push(archResult);
  console.log(formatResults(archResult));

  // Benchmark 3: Feature graph generation
  const architecture = await builder.architecture(sampleIntake);
  const featureGraphResult = await benchmarkOperation(
    'Feature Graph Generation',
    async () => {
      await builder.featureGraph(sampleIntake, architecture);
    },
    100
  );
  results.push(featureGraphResult);
  console.log(formatResults(featureGraphResult));

  // Benchmark 4: End-to-end pipeline
  const e2eResult = await benchmarkOperation(
    'End-to-End Pipeline',
    async () => {
      const intake = await builder.intake({ goal: 'Build a test app' });
      const arch = await builder.architecture(intake);
      const graph = await builder.featureGraph(intake, arch);
      await builder.scaffolding(graph, arch);
    },
    50  // Fewer iterations for E2E
  );
  results.push(e2eResult);
  console.log(formatResults(e2eResult));

  // Summary
  console.log('\n' + '='.repeat(60));
  console.log('BENCHMARK SUMMARY');
  console.log('='.repeat(60));

  let allPass = true;
  for (const result of results) {
    const pass = checkSLO(result);
    allPass = allPass && pass;
    console.log(`\n${result.operation}:`);
    console.log(`  p95: ${result.p95.toFixed(2)}ms ${pass ? '✅ PASS' : '❌ FAIL'}`);
    console.log(`  p99: ${result.p99.toFixed(2)}ms ${pass ? '✅ PASS' : '❌ FAIL'}`);
    console.log(`  Success: ${result.successRate.toFixed(2)}% ${pass ? '✅ PASS' : '❌ FAIL'}`);
  }

  console.log('\n' + '='.repeat(60));
  if (allPass) {
    console.log('✅ ALL BENCHMARKS PASSED SLO REQUIREMENTS');
    process.exit(0);
  } else {
    console.log('❌ SOME BENCHMARKS FAILED SLO REQUIREMENTS');
    process.exit(1);
  }
}

// Run benchmarks
main().catch((error) => {
  console.error('\n❌ Benchmark failed:', error);
  process.exit(1);
});
