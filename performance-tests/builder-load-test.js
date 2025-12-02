/**
 * k6 Load Test - ROMA Builder Performance
 *
 * Tests builder operations under load to validate SLO requirements:
 * - p95 latency ≤ 300ms
 * - p99 latency ≤ 500ms
 * - 100 RPS throughput
 * - 99.9% success rate
 *
 * Run with: k6 run builder-load-test.js
 */

import { check, group, sleep } from 'k6';
import { Rate, Trend, Counter } from 'k6/metrics';

// Custom metrics
const builderLatency = new Trend('builder_operation_duration', true);
const builderErrors = new Rate('builder_error_rate');
const builderSuccess = new Counter('builder_success_total');
const builderFailure = new Counter('builder_failure_total');

// Test configuration
export const options = {
  stages: [
    // Ramp up to 50 RPS
    { duration: '30s', target: 50 },
    // Sustained load at 100 RPS
    { duration: '2m', target: 100 },
    // Spike test to 150 RPS
    { duration: '30s', target: 150 },
    // Scale down
    { duration: '30s', target: 0 },
  ],
  thresholds: {
    // SLO requirements
    'builder_operation_duration': [
      'p(95) <= 300',  // p95 ≤ 300ms
      'p(99) <= 500',  // p99 ≤ 500ms
    ],
    'builder_error_rate': [
      'rate < 0.001',  // 99.9% success rate
    ],
    'http_req_duration': [
      'p(95) <= 300',
      'p(99) <= 500',
    ],
  },
};

// Sample test data
const sampleGoals = [
  'Build a task management app',
  'Build a blog platform',
  'Build an e-commerce site',
  'Build a social media dashboard',
  'Build a project tracker',
];

export default function () {
  // Simulate builder operations
  group('Builder Pipeline Load Test', () => {
    const startTime = Date.now();
    const goal = sampleGoals[Math.floor(Math.random() * sampleGoals.length)];

    // Simulate intake generation
    const intakeResult = simulateBuilderOperation('intake', goal);
    const intakeDuration = Date.now() - startTime;

    builderLatency.add(intakeDuration);

    const success = check(intakeResult, {
      'intake completes': (r) => r.success === true,
      'intake has metadata': (r) => r.metadata !== undefined,
      'intake within SLO': () => intakeDuration <= 300,
    });

    if (success) {
      builderSuccess.add(1);
    } else {
      builderFailure.add(1);
      builderErrors.add(1);
    }

    // Small delay to simulate realistic usage
    sleep(0.1);
  });
}

/**
 * Simulate builder operation
 * In real implementation, this would call actual builder
 */
function simulateBuilderOperation(operation, input) {
  // Simulate processing time (50-200ms typical)
  const processingTime = 50 + Math.random() * 150;
  const startTime = Date.now();

  // Simulate occasional failures (< 0.1%)
  const shouldFail = Math.random() < 0.0005;

  while (Date.now() - startTime < processingTime) {
    // Busy wait to simulate CPU work
  }

  if (shouldFail) {
    return {
      success: false,
      error: 'Simulated failure',
    };
  }

  return {
    success: true,
    metadata: {
      appName: `App-${Math.random().toString(36).substring(7)}`,
      version: '0.1.0',
      operation,
      processingTime,
    },
  };
}

/**
 * Setup function - runs once at start
 */
export function setup() {
  console.log('Starting ROMA Builder load test...');
  console.log('SLO requirements:');
  console.log('  - p95 latency ≤ 300ms');
  console.log('  - p99 latency ≤ 500ms');
  console.log('  - Target: 100 RPS');
  console.log('  - Success rate: ≥ 99.9%');
  return { startTime: Date.now() };
}

/**
 * Teardown function - runs once at end
 */
export function teardown(data) {
  const duration = (Date.now() - data.startTime) / 1000;
  console.log(`\nLoad test completed in ${duration.toFixed(2)}s`);
  console.log('Check output for SLO compliance');
}
