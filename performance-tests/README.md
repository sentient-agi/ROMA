# Performance & Resilience Testing

Comprehensive performance testing and chaos engineering for ROMA Multi-Agent SaaS Builder.

## Overview

This directory contains performance tests, load tests, and chaos engineering scenarios that validate system performance and resilience against defined SLO requirements.

## SLO Requirements

The system MUST meet the following Service Level Objectives (SLOs):

| Metric | Requirement | Status |
|--------|------------|--------|
| **p95 Latency** | ≤ 300ms | Validated in benchmarks |
| **p99 Latency** | ≤ 500ms | Validated in benchmarks |
| **Throughput** | 100 RPS | Validated in load tests |
| **Success Rate** | ≥ 99.9% | Validated in all tests |
| **Uptime** | ≥ 99.9% | Monitored in production |

## Test Suites

### 1. Builder Performance Benchmark (`builder-benchmark.ts`)

**Purpose:** Validates builder operation performance against SLO requirements.

**Operations Tested:**
- Intake generation
- Architecture generation
- Feature graph generation
- End-to-end pipeline

**Metrics Collected:**
- Mean latency
- p50, p95, p99 percentiles
- Success rate
- Error count

**Run Locally:**
```bash
# Build packages first
pnpm build

# Run benchmark
tsx performance-tests/builder-benchmark.ts
```

**Expected Output:**
```
╔════════════════════════════════════════════════════════════╗
║  ROMA Builder Performance Benchmark                        ║
╚════════════════════════════════════════════════════════════╝

Benchmarking: Intake Generation (100 iterations)
..........Done!

============================================================
Operation: Intake Generation
Iterations: 100
============================================================

Latency (ms):
  Mean:    156.32
  p50:     142.00
  p95:     223.00 ✅
  p99:     287.00 ✅

Success Rate: 100.00% ✅
Errors: 0
```

**SLO Validation:**
- ✅ p95 ≤ 300ms
- ✅ p99 ≤ 500ms
- ✅ Success rate ≥ 99.9%

**Failure Handling:**
- Exit code 1 if any SLO requirement fails
- Detailed failure report with specific metrics that failed

### 2. Load Test (`builder-load-test.js`)

**Purpose:** Validates system performance under sustained load using k6.

**Load Profile:**
1. Ramp up to 50 RPS (30s)
2. Sustained 100 RPS (2m)
3. Spike to 150 RPS (30s)
4. Scale down (30s)

**Metrics:**
- `builder_operation_duration`: Latency trend
- `builder_error_rate`: Error percentage
- `builder_success_total`: Success counter
- `builder_failure_total`: Failure counter

**Run Locally:**
```bash
# Install k6: https://k6.io/docs/get-started/installation/

# Run load test
k6 run performance-tests/builder-load-test.js
```

**Thresholds:**
```javascript
thresholds: {
  'builder_operation_duration': ['p(95) <= 300', 'p(99) <= 500'],
  'builder_error_rate': ['rate < 0.001'],
}
```

**Example Output:**
```
     ✓ builder_operation_duration.............: avg=156ms p(95)=223ms p(99)=287ms
     ✓ builder_error_rate.....................: 0.00%
     ✓ builder_success_total..................: 12450
       builder_failure_total..................: 0
```

### 3. Chaos Engineering & Resilience (`chaos-resilience.ts`)

**Purpose:** Validates system resilience under adverse conditions.

**Scenarios Tested:**

**Invalid Input Handling:**
- Empty objects
- Null inputs
- Malformed data

**Resource Exhaustion:**
- Large input (100+ features)
- Deep nesting
- Memory stress

**Concurrent Operations:**
- 10 concurrent intake generations
- 5 concurrent pipeline executions

**Error Recovery:**
- Recovery after single error
- Recovery after multiple sequential errors
- State consistency validation

**Run Locally:**
```bash
pnpm build
tsx performance-tests/chaos-resilience.ts
```

**Expected Output:**
```
╔════════════════════════════════════════════════════════════╗
║  ROMA Chaos Engineering & Resilience Tests                ║
╚════════════════════════════════════════════════════════════╝

🔥 Running chaos scenario: Invalid intake - empty object
   ✅ Passed (15ms)

🔥 Running chaos scenario: Large input - many features
   ✅ Passed (1247ms)

...

============================================================
CHAOS ENGINEERING RESULTS
============================================================

✅ PASS Invalid intake - empty object
   Duration: 15ms

✅ PASS Large input - many features
   Duration: 1247ms

...

Total: 9 scenarios
Passed: 9 ✅
Failed: 0 ❌
Success Rate: 100.0%
============================================================

✅ ALL CHAOS SCENARIOS PASSED - SYSTEM IS RESILIENT
```

## GitHub Actions Integration

### Workflow: `performance-tests.yml`

**Triggers:**
- Push to main/master
- Pull requests (benchmark & chaos only)
- Weekly schedule (Friday 04:00 UTC)
- Manual dispatch

**Jobs:**

1. **performance-benchmark**
   - Runs builder performance benchmarks
   - Validates against SLO requirements
   - Uploads results as artifacts (90 day retention)

2. **chaos-resilience**
   - Runs chaos engineering tests
   - Validates error handling and recovery
   - Uploads results as artifacts

3. **load-test** (main/master only)
   - Runs k6 load tests
   - Skipped on PRs (resource intensive)
   - Validates 100 RPS throughput

4. **performance-report**
   - Aggregates all test results
   - Generates summary report
   - Comments on PRs with performance summary

**Artifacts:**
- `performance-benchmark-results` (90 days)
- `chaos-resilience-results` (90 days)
- `k6-load-test-results` (90 days)
- `performance-test-report` (90 days)

## Performance Monitoring

### Observability Integration

Performance metrics are automatically collected via OpenTelemetry and sent to Honeycomb:

**Metrics:**
- `build_duration_seconds` - Histogram of build durations
- `builds_started_total` - Counter of initiated builds
- `builds_succeeded_total` - Counter of successful builds
- `builds_failed_total` - Counter of failed builds

**Traces:**
- End-to-end build traces with `executionId` correlation
- Per-operation spans (atomize, plan, execute, aggregate, verify)
- Latency breakdown by phase

**Dashboards:**
Set up Honeycomb dashboards to visualize:
- p95/p99 latency over time
- Success rate trends
- Error patterns
- Throughput (builds per minute)

### SLO Monitoring

Create Honeycomb SLO monitors:

```javascript
// p95 latency SLO
QUERY: AVG(duration) WHERE p95 <= 300ms
TARGET: 99.9% of time windows

// Success rate SLO
QUERY: COUNT(success=true) / COUNT(*)
TARGET: >= 99.9%
```

## Interpreting Results

### Benchmark Success Criteria

**✅ PASS if:**
- p95 latency ≤ 300ms for all operations
- p99 latency ≤ 500ms for all operations
- Success rate ≥ 99.9%
- Zero crashes or unhandled exceptions

**❌ FAIL if:**
- Any p95 > 300ms
- Any p99 > 500ms
- Success rate < 99.9%
- Any operation crashes

### Load Test Success Criteria

**✅ PASS if:**
- Sustains 100 RPS without degradation
- All k6 thresholds pass
- Error rate < 0.1%
- No memory leaks

**❌ FAIL if:**
- Cannot sustain 100 RPS
- Latency degrades under load
- Error rate > 0.1%
- Memory usage grows unbounded

### Chaos Test Success Criteria

**✅ PASS if:**
- All scenarios pass
- Errors are graceful with meaningful messages
- System recovers after errors
- No data corruption

**❌ FAIL if:**
- Any scenario fails
- Crashes on invalid input
- State corruption after errors
- Memory leaks

## Performance Optimization

### If SLO Requirements Are Not Met

**High Latency (p95 > 300ms):**
1. Profile with `--prof` flag: `node --prof dist/index.js`
2. Check for synchronous I/O blocking event loop
3. Optimize algorithm complexity
4. Add caching for repeated operations
5. Consider parallelization

**Low Throughput:**
1. Profile with `clinic bubbleprof`
2. Check for CPU bottlenecks
3. Optimize hot paths
4. Consider worker threads for CPU-intensive operations
5. Add request batching

**High Error Rate:**
1. Review logs for error patterns
2. Add retry logic with exponential backoff
3. Improve input validation
4. Add circuit breakers for external dependencies
5. Increase timeout values if appropriate

**Memory Issues:**
1. Profile with `node --inspect`
2. Check for memory leaks with Chrome DevTools
3. Review object retention
4. Add streaming for large datasets
5. Implement pagination

## Continuous Performance Testing

### Local Development

Run before committing:
```bash
# Quick benchmark (essential operations only)
tsx performance-tests/builder-benchmark.ts

# Full chaos test
tsx performance-tests/chaos-resilience.ts
```

### CI/CD

- **Every PR**: Benchmark & chaos tests (fast feedback)
- **Every merge to main**: Full load test with k6
- **Weekly**: Comprehensive performance regression test
- **On-demand**: Manual workflow dispatch for investigation

### Performance Budgets

Set performance budgets to prevent regressions:

| Operation | Budget (p95) | Alert if Exceeded |
|-----------|--------------|-------------------|
| Intake | 200ms | Yes |
| Architecture | 250ms | Yes |
| Feature Graph | 300ms | Yes |
| E2E Pipeline | 500ms | Yes |

Update `.github/workflows/performance-tests.yml` to fail if budgets exceeded.

## Troubleshooting

### Tests Timing Out

**Symptom:** Tests fail with timeout errors

**Solution:**
- Increase timeout in test configuration
- Check for deadlocks or infinite loops
- Profile slow operations

### Inconsistent Results

**Symptom:** Performance varies widely between runs

**Solution:**
- Ensure consistent test environment (no other processes)
- Increase iteration count for statistical significance
- Check for caching effects

### Memory Leaks

**Symptom:** Memory usage grows during tests

**Solution:**
- Run with `--expose-gc` and force GC between iterations
- Profile with `clinic doctor` or Chrome DevTools
- Check for event listener accumulation

## References

- [k6 Documentation](https://k6.io/docs/)
- [Node.js Profiling](https://nodejs.org/en/docs/guides/simple-profiling/)
- [OpenTelemetry Performance](https://opentelemetry.io/docs/concepts/performance/)
- [SLO Best Practices](https://sre.google/workbook/implementing-slos/)

---

**Last Updated:** 2025-11-29
**Phase:** 4D - Performance & Reliability Checks
