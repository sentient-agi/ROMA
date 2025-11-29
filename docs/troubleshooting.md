# ROMA Troubleshooting Guide

**Version:** 1.0
**Last Updated:** 2025-11-29

Quick reference for diagnosing and fixing common ROMA issues.

---

## Table of Contents

1. [Quick Diagnostics](#quick-diagnostics)
2. [Pipeline Failures](#pipeline-failures)
3. [Performance Issues](#performance-issues)
4. [Container Issues](#container-issues)
5. [Build & Dependency Issues](#build--dependency-issues)
6. [Common Error Messages](#common-error-messages)

---

## Quick Diagnostics

### Health Check Script

```bash
#!/bin/bash
# Save as: scripts/health-check.sh

echo "=== ROMA Health Check ==="
echo

# Check if Docker is running
echo "[1/7] Checking Docker..."
if docker info &> /dev/null; then
  echo "✅ Docker is running"
else
  echo "❌ Docker is not running"
  exit 1
fi

# Check if containers are up
echo "[2/7] Checking containers..."
if docker compose ps roma | grep -q "Up"; then
  echo "✅ ROMA container is running"
else
  echo "❌ ROMA container is not running"
fi

# Check build status
echo "[3/7] Checking build..."
if [ -d "packages/roma/dist" ]; then
  echo "✅ Packages are built"
else
  echo "❌ Packages not built - run 'pnpm build'"
fi

# Check dependencies
echo "[4/7] Checking dependencies..."
if [ -d "node_modules" ]; then
  echo "✅ Dependencies installed"
else
  echo "❌ Dependencies missing - run 'pnpm install'"
fi

# Test pipeline
echo "[5/7] Testing pipeline..."
if pnpm roma:onthisday &> /dev/null; then
  echo "✅ Pipeline executes successfully"
else
  echo "❌ Pipeline failing - check logs"
fi

# Check disk space
echo "[6/7] Checking disk space..."
DISK_USAGE=$(df -h . | tail -1 | awk '{print $5}' | sed 's/%//')
if [ "$DISK_USAGE" -lt 90 ]; then
  echo "✅ Disk space OK ($DISK_USAGE% used)"
else
  echo "⚠️  Disk space critical ($DISK_USAGE% used)"
fi

# Check memory
echo "[7/7] Checking memory..."
if command -v free &> /dev/null; then
  MEM_USAGE=$(free | grep Mem | awk '{printf "%.0f", $3/$2 * 100}')
  echo "ℹ️  Memory usage: $MEM_USAGE%"
fi

echo
echo "=== Health Check Complete ==="
```

### Quick Debug Commands

```bash
# See what's currently broken
pnpm roma:onthisday 2>&1 | grep -E "(Error|FAIL|✗)"

# Check logs for last 100 lines
docker compose logs roma --tail=100

# See which task is failing
pnpm roma:onthisday --verbose 2>&1 | grep -A 5 "Stage.*failed"

# Check resource usage
docker stats --no-stream

# Validate configuration
pnpm build && echo "Build OK" || echo "Build FAILED"
```

---

## Pipeline Failures

### Problem: "Cannot read properties of undefined (reading 'X')"

**Common Causes:**
1. Task dependencies not declared correctly
2. Previous task didn't return expected outputs
3. Null/undefined values not handled

**Diagnosis:**
```bash
# Enable verbose logging to see task outputs
pnpm roma:onthisday --verbose 2>&1 > pipeline.log

# Check which task fails
grep -A 10 "Cannot read properties" pipeline.log

# Check task dependencies in planner
grep -A 5 "id: 'failing_task_id'" packages/roma/src/planner.ts
```

**Solutions:**

**Solution 1: Add missing dependency**
```typescript
// packages/roma/src/planner.ts
{
  id: 'generate_feature_graph',
  type: 'generate_feature_graph',
  description: 'Build feature dependency graph',
  dependencies: ['collect_intake', 'design_architecture'],  // ✅ Both needed
  // NOT: dependencies: ['design_architecture'],  // ❌ Missing intake
  inputs: {},
  status: 'pending',
}
```

**Solution 2: Add null guards**
```typescript
// packages/builder/src/feature-graph.ts
async fromIntakeAndArchitecture(intake: Intake, architecture: Architecture): Promise<FeatureGraph> {
  // Add guards
  if (!intake) {
    throw new Error('Intake is undefined - ensure collect_intake task completed successfully');
  }

  if (!architecture || !architecture.metadata) {
    throw new Error('Architecture is undefined or malformed');
  }

  // Rest of code...
}
```

**Solution 3: Fix task output**
```typescript
// packages/roma/src/executor.ts
private async executeCollectIntake(task: ROMATask, inputs: Record<string, any>): Promise<Record<string, any>> {
  if (this.builderInterface?.intake) {
    const intake = await this.builderInterface.intake(inputs);
    return { intake };  // ✅ Return with key
    // NOT: return intake;  // ❌ Returns value without key
  }
  throw new Error('Builder interface not available for intake');
}
```

---

### Problem: Tasks executing in wrong order

**Symptom:** aggregate_results runs before collect_intake

**Root Cause:** Topological sort bug or incorrect dependency graph

**Diagnosis:**
```bash
# Print execution order
pnpm tsx -e "
import { Planner } from './packages/roma/dist/planner.js';
const planner = new Planner();
const dag = planner.plan('test', { taskType: 'build_saas_app' });
console.log('Execution order:');
dag.executionOrder?.forEach((stage, i) => {
  console.log(\`Stage \${i + 1}: \${stage.join(', ')}\`);
});
"
```

**Expected Output:**
```
Stage 1: collect_intake
Stage 2: design_architecture
Stage 3: generate_feature_graph
Stage 4: generate_scaffolding_specs
...
```

**If order is wrong, check topological sort:**
```typescript
// packages/roma/src/planner.ts
private topologicalSort(tasks: ROMATask[]): string[][] {
  // Correct: in-degree = number of dependencies
  for (const task of tasks) {
    inDegree.set(task.id, task.dependencies.length);  // ✅
  }

  // Correct: decrement dependents when task completes
  for (const [otherTaskId, otherTask] of taskMap.entries()) {
    if (otherTask.dependencies.includes(taskId) && inDegree.has(otherTaskId)) {
      inDegree.set(otherTaskId, inDegree.get(otherTaskId)! - 1);  // ✅
    }
  }
}
```

---

### Problem: Chaos tests failing

**Common Failures:**
1. Schema validation errors
2. Timeout issues
3. Resource exhaustion under load

**Diagnosis:**
```bash
# Run chaos tests with verbose output
pnpm tsx chaos-resilience.ts 2>&1 | tee chaos-results.log

# Check which scenarios fail
grep -E "(PASS|FAIL)" chaos-results.log

# Check specific failure
grep -A 20 "Large input.*FAIL" chaos-results.log
```

**Solutions:**

**Solution 1: Fix schema validation**
```typescript
// Make sure test data matches schema
const validIntake = {
  metadata: { /* ... */ },
  requirements: {
    features: [ /* ... */ ],
    security: {
      authentication: {
        methods: ['jwt'],  // ✅ Array of strings
        mfa: false,
      },
      authorization: {
        model: 'rbac',  // ✅ String
      },
      // NOT: security: { authentication: ['jwt'], authorization: ['rbac'] }  // ❌ Old format
    }
  }
};
```

**Solution 2: Increase timeouts**
```typescript
// chaos-resilience.ts
const TIMEOUT = 60000;  // Increase from 30000 if needed
```

**Solution 3: Add resource limits handling**
```typescript
// Check if we're hitting resource limits
if (error.message.includes('out of memory')) {
  // Handle OOM gracefully
  logger.warn('Out of memory - reducing batch size');
}
```

---

## Performance Issues

### Problem: Pipeline taking >10 seconds

**Expected:** <100ms for OnThisDay example
**Actual:** >10 seconds

**Diagnosis:**
```bash
# Profile execution with timestamps
pnpm roma:onthisday --verbose 2>&1 | while read line; do
  echo "[$(date +%s.%N)] $line"
done > profiled.log

# Calculate time per stage
grep "Executing stage" profiled.log | while read ts rest; do
  echo "$ts Stage started"
done

# Check for slow tasks
grep "completed" profiled.log | awk '{print $NF}'
```

**Common Bottlenecks:**

**1. Slow disk I/O**
```bash
# Check if disk is slow
time dd if=/dev/zero of=/tmp/test bs=1M count=1000
# Should complete in <1s on SSD

# Fix: Use SSD, or mount tmpfs for temporary data
docker compose run --rm -v tmpfs:/app/.roma roma pnpm roma:onthisday
```

**2. Large intake files**
```bash
# Check intake size
ls -lh examples/onthisday/intake.json

# If >1MB, optimize:
# - Remove unnecessary fields
# - Compress arrays
# - Reduce feature count for testing
```

**3. Synchronous operations**
```bash
# Check if tasks can run in parallel
# Look for stages with multiple tasks
pnpm tsx -e "
const planner = new (require('./packages/roma/dist/planner.js')).Planner();
const dag = planner.plan('test', { taskType: 'build_saas_app' });
dag.executionOrder?.forEach((stage, i) => {
  if (stage.length > 1) {
    console.log(\`Stage \${i + 1} can parallelize: \${stage.length} tasks\`);
  }
});
"
```

---

### Problem: High memory usage (>1GB)

**Diagnosis:**
```bash
# Monitor memory over time
while true; do
  docker stats roma-builder --no-stream --format "{{.MemUsage}}" | tee -a mem.log
  sleep 1
done

# Check for memory leaks
pnpm roma:onthisday &
PID=$!
while kill -0 $PID 2>/dev/null; do
  ps -o rss= -p $PID >> mem-profile.txt
  sleep 0.1
done

# Plot memory growth
gnuplot -e "set terminal dumb; plot 'mem-profile.txt' with lines"
```

**Solutions:**

**1. Limit heap size**
```bash
# Add to package.json scripts
"roma:onthisday": "node --max-old-space-size=512 ..."
```

**2. Clear artifacts between runs**
```typescript
// Add cleanup in executor
async execute(dag: ROMATaskDAG, goal: string): Promise<ExecutorResult> {
  try {
    // ... execution logic
  } finally {
    // Clear large objects
    this.context.artifacts = {};
  }
}
```

**3. Stream large outputs**
```typescript
// Instead of loading entire file into memory
const data = JSON.parse(fs.readFileSync('large.json', 'utf-8'));  // ❌

// Stream and process
const stream = fs.createReadStream('large.json');  // ✅
stream.pipe(parser).on('data', chunk => { /* process */ });
```

---

## Container Issues

### Problem: Container keeps restarting

**Symptoms:**
```bash
$ docker compose ps
NAME            STATUS
roma-builder    Restarting (137) 3 seconds ago
```

**Exit codes:**
- **0**: Normal exit
- **1**: Application error
- **137**: Killed by OOM (Out of Memory)
- **139**: Segmentation fault
- **143**: Terminated by SIGTERM

**Diagnosis:**
```bash
# Check exit code
docker inspect roma-builder --format='{{.State.ExitCode}}'

# Check last 200 lines before crash
docker compose logs roma --tail=200

# Check dmesg for OOM killer
docker compose exec roma dmesg | grep -i "out of memory"
```

**Solutions:**

**For exit code 137 (OOM):**
```yaml
# docker-compose.yml - Increase memory limit
deploy:
  resources:
    limits:
      memory: 4G  # Increase from 2G
```

**For exit code 1 (Application error):**
```bash
# Run with --verbose to see error
docker compose run --rm roma pnpm roma:onthisday --verbose

# Check if it's a startup issue
docker compose run --rm roma pnpm roma --version
```

**For exit code 143 (SIGTERM):**
```bash
# Something is killing the process
# Check if it's a timeout
docker compose logs roma | grep -i timeout

# Check if it's health check failing
docker inspect roma-builder --format='{{json .State.Health}}' | jq
```

---

### Problem: "Permission denied" errors

**Symptoms:**
```
Error: EACCES: permission denied, open '/app/out/artifacts.json'
```

**Diagnosis:**
```bash
# Check file permissions
docker compose exec roma ls -la /app/out

# Check user
docker compose exec roma whoami  # Should be 'roma'
docker compose exec roma id      # Should be uid=1001
```

**Solutions:**

**1. Fix host directory permissions**
```bash
# Make output directory writable
chmod 755 out
chown -R $(id -u):$(id -g) out
```

**2. Run as root (dev only!)**
```yaml
# docker-compose.yml (development only)
services:
  roma-dev:
    user: root
```

**3. Use named volume instead of bind mount**
```yaml
volumes:
  - roma-out:/app/out  # Named volume (better permissions)
  # NOT: - ./out:/app/out  # Bind mount (permission issues)
```

---

## Build & Dependency Issues

### Problem: "Cannot find module '@roma/...'"

**Symptoms:**
```
Error [ERR_MODULE_NOT_FOUND]: Cannot find module '@roma/core'
```

**Diagnosis:**
```bash
# Check if packages are built
ls -la packages/*/dist/

# Check if node_modules are linked
ls -la node_modules/@roma/

# Check workspace configuration
pnpm why @roma/core
```

**Solutions:**

**1. Rebuild everything**
```bash
# Clean and rebuild
pnpm clean
rm -rf node_modules packages/*/node_modules
pnpm install
pnpm build
```

**2. Fix workspace links**
```bash
# Re-link workspaces
pnpm install --force
```

**3. Check tsconfig paths**
```json
// tsconfig.json - Ensure paths are correct
{
  "compilerOptions": {
    "paths": {
      "@roma/*": ["./packages/*/src"]
    }
  }
}
```

---

### Problem: "Version mismatch" or "Lockfile out of sync"

**Symptoms:**
```
 ERR_PNPM_OUTDATED_LOCKFILE  Lockfile is out of sync
```

**Solutions:**
```bash
# Update lockfile
pnpm install --no-frozen-lockfile

# Or regenerate completely
rm pnpm-lock.yaml
pnpm install
```

---

## Common Error Messages

### "Task X failed with no error message"

**Cause:** Task caught error but didn't propagate it

**Fix:**
```typescript
// Ensure errors are thrown, not swallowed
try {
  await someOperation();
} catch (error) {
  // ✅ Throw with context
  throw new Error(`Failed to execute task: ${error.message}`);

  // ❌ Don't swallow
  // console.error(error);
  // return { success: false };
}
```

### "ZodError: Invalid input"

**Cause:** Data doesn't match schema

**Debug:**
```typescript
import { IntakeSchema } from '@roma/schemas';

try {
  IntakeSchema.parse(data);
} catch (error) {
  if (error instanceof ZodError) {
    console.log('Validation errors:');
    error.errors.forEach(err => {
      console.log(`  ${err.path.join('.')}: ${err.message}`);
    });
  }
}
```

**Fix:** Update data to match schema, or update schema if data is correct

### "ENOENT: no such file or directory"

**Cause:** File path is wrong or file doesn't exist

**Debug:**
```bash
# Check what's actually in the container
docker compose exec roma ls -R /app/examples

# Check current working directory
docker compose exec roma pwd

# Check if path is absolute vs relative
docker compose exec roma realpath examples/onthisday/intake.json
```

**Fix:** Use absolute paths or ensure relative paths are from correct directory

---

## Getting More Help

### Enable Debug Logging

```bash
# Environment variable
LOG_LEVEL=debug pnpm roma:onthisday

# Or in Docker
docker compose run --rm -e LOG_LEVEL=debug roma pnpm roma:onthisday
```

### Collect Full Diagnostic Bundle

```bash
#!/bin/bash
# Save as: scripts/collect-diagnostics.sh

BUNDLE_DIR="/tmp/roma-diagnostics-$(date +%s)"
mkdir -p "$BUNDLE_DIR"

echo "Collecting diagnostics in $BUNDLE_DIR..."

# System info
docker version > "$BUNDLE_DIR/docker-version.txt"
docker compose version > "$BUNDLE_DIR/compose-version.txt"
node --version > "$BUNDLE_DIR/node-version.txt"
pnpm --version > "$BUNDLE_DIR/pnpm-version.txt"

# Container state
docker compose ps > "$BUNDLE_DIR/container-status.txt"
docker stats --no-stream > "$BUNDLE_DIR/container-stats.txt"
docker inspect roma-builder > "$BUNDLE_DIR/container-inspect.json"

# Logs
docker compose logs roma > "$BUNDLE_DIR/container-logs.txt"
pnpm roma:onthisday --verbose 2>&1 > "$BUNDLE_DIR/pipeline-verbose.log"

# Configuration
cp docker-compose.yml "$BUNDLE_DIR/"
cp package.json "$BUNDLE_DIR/"
cp pnpm-lock.yaml "$BUNDLE_DIR/"

# Build status
ls -R packages/*/dist > "$BUNDLE_DIR/build-artifacts.txt"

# Create tarball
tar czf "roma-diagnostics-$(date +%s).tar.gz" -C /tmp "$(basename $BUNDLE_DIR)"

echo "Diagnostics collected: roma-diagnostics-*.tar.gz"
echo "Please attach this file when reporting issues"
```

---

## Troubleshooting Checklist

Before reporting an issue, verify:

- [ ] Running latest code (`git pull origin main && pnpm install && pnpm build`)
- [ ] Docker daemon is running
- [ ] Sufficient disk space (>5GB free)
- [ ] Sufficient memory (>2GB available)
- [ ] Clean build (`pnpm clean && pnpm build`)
- [ ] Tests pass (`pnpm test`)
- [ ] OnThisDay example works (`pnpm roma:onthisday`)
- [ ] Logs collected (`docker compose logs roma > logs.txt`)
- [ ] Error message copied exactly
- [ ] Steps to reproduce documented

---

**Document Maintenance:**
- Add new issues as they're discovered
- Update solutions when better fixes are found
- Remove obsolete issues after major refactors
- Review quarterly
