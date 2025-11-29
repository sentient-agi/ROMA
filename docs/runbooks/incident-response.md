# Incident Response Runbook

**Version:** 1.0
**Last Updated:** 2025-11-29
**Owner:** SRE Team / On-Call Engineer
**Severity Levels:** P0 (Critical) → P1 (High) → P2 (Medium) → P3 (Low)

---

## Table of Contents

1. [Incident Classification](#incident-classification)
2. [Response Procedures](#response-procedures)
3. [Common Incidents](#common-incidents)
4. [Escalation Paths](#escalation-paths)
5. [Post-Incident Review](#post-incident-review)

---

## Incident Classification

### P0 - Critical (Immediate Response)
- **Description**: Complete service outage, data loss, or security breach
- **Response Time**: Immediate (within 5 minutes)
- **Examples**:
  - ROMA pipeline completely non-functional
  - Data corruption in generated artifacts
  - Security vulnerability being actively exploited
  - All containers failing health checks

### P1 - High (Urgent Response)
- **Description**: Major functionality degraded, affecting multiple users
- **Response Time**: Within 15 minutes
- **Examples**:
  - Builder pipeline failing for >50% of requests
  - Critical feature (intake, architecture, scaffolding) broken
  - Performance degradation >5x normal latency
  - Memory leaks causing crashes every <1 hour

### P2 - Medium (Standard Response)
- **Description**: Minor functionality impaired, workaround available
- **Response Time**: Within 1 hour
- **Examples**:
  - Non-critical feature failures
  - Intermittent errors (<10% failure rate)
  - Performance degradation 2-5x normal
  - Logging/monitoring issues

### P3 - Low (Planned Response)
- **Description**: Cosmetic issues, minor bugs, feature requests
- **Response Time**: Next business day
- **Examples**:
  - Documentation errors
  - Minor UI/UX issues
  - Enhancement requests
  - Non-urgent warnings in logs

---

## Response Procedures

### Phase 1: Detect & Assess (0-5 min)

#### 1.1 Acknowledge the Incident
```bash
# Log incident start time
echo "[$(date -Iseconds)] Incident detected: <description>" >> /var/log/roma/incidents.log

# Update status page
curl -X POST https://status.yourcompany.com/api/incidents \
  -d '{"status":"investigating","message":"ROMA service experiencing issues"}'
```

#### 1.2 Initial Triage
- [ ] **What** is broken? (Specific component/feature)
- [ ] **When** did it start? (Check logs, metrics, recent deployments)
- [ ] **Who** is affected? (All users, specific customers, internal only)
- [ ] **Impact**: Data loss? Service down? Degraded performance?

#### 1.3 Quick Health Check
```bash
# Check service health
docker compose ps roma
docker compose logs roma --tail=100

# Check recent errors
pnpm roma:onthisday 2>&1 | grep -i error

# Check system resources
docker stats --no-stream
```

### Phase 2: Contain & Mitigate (5-15 min)

#### 2.1 Stop the Bleeding
```bash
# If containers are crashlooping
docker compose stop roma
docker compose up -d roma --scale roma=0  # Scale to zero

# If bad deployment
git log -1 --pretty=format:"%H %s"  # Get last commit
git revert HEAD  # Revert if needed
docker compose up -d --build

# If resource exhaustion
docker system prune -f  # Free up disk space
docker compose restart roma  # Restart with fresh state
```

#### 2.2 Enable Debug Logging
```bash
# Update docker-compose.yml
docker compose exec roma sh -c 'export LOG_LEVEL=debug && pnpm roma:onthisday'

# Tail logs in real-time
docker compose logs -f roma
```

#### 2.3 Isolate the Problem
- [ ] Can you reproduce it manually?
- [ ] Is it environment-specific? (dev vs prod)
- [ ] Is it time-related? (recent deployment, time of day)
- [ ] Is it load-related? (only happens under high traffic)

### Phase 3: Diagnose & Fix (15-60 min)

#### 3.1 Gather Evidence
```bash
# Capture full state
docker compose logs roma > /tmp/roma-incident-$(date +%s).log
docker inspect roma-builder > /tmp/roma-container-state.json
docker stats --no-stream > /tmp/roma-stats.txt

# Export artifacts for analysis
docker compose exec roma tar czf /tmp/artifacts.tar.gz /app/out
docker cp roma-builder:/tmp/artifacts.tar.gz ./incident-artifacts.tar.gz
```

#### 3.2 Common Diagnostic Commands
```bash
# Check for crashed tasks
docker compose exec roma pnpm roma:onthisday --verbose 2>&1 | grep -A 5 "FAIL"

# Check dependencies
docker compose exec roma pnpm why <package-name>
docker compose exec roma npm list --depth=0

# Check disk space
docker compose exec roma df -h
docker system df

# Check memory usage
docker compose exec roma ps aux --sort=-%mem | head -10

# Check for zombie processes
docker compose exec roma ps aux | grep -i defunct
```

#### 3.3 Root Cause Analysis
Follow decision tree:

```
Is the pipeline failing?
├─ YES → Check task-specific logs
│   ├─ collect_intake fails → Check input validation
│   ├─ design_architecture fails → Check schema compatibility
│   ├─ generate_feature_graph fails → Check dependency resolution
│   └─ generate_scaffolding fails → Check template availability
└─ NO → Is performance degraded?
    ├─ YES → Check resource limits, memory leaks
    └─ NO → Check logs for warnings/errors
```

### Phase 4: Resolve & Verify (60-120 min)

#### 4.1 Apply Fix
```bash
# Code fix
git checkout -b hotfix/incident-<issue-number>
# ... make changes ...
git commit -m "hotfix: fix <issue> causing <symptom>"
git push origin hotfix/incident-<issue-number>

# Rebuild and deploy
pnpm build
docker compose build roma
docker compose up -d roma

# Monitor deployment
watch -n 2 'docker compose ps && echo "---" && docker compose logs roma --tail=20'
```

#### 4.2 Verify Fix
```bash
# Run smoke tests
pnpm roma:onthisday
pnpm test

# Run chaos tests (if time permits)
pnpm tsx chaos-resilience.ts

# Check metrics
docker stats --no-stream roma-builder
```

#### 4.3 Monitor for Recurrence
```bash
# Watch logs for 15 minutes
docker compose logs -f roma | grep -i error

# Set up alert
while true; do
  if docker compose logs roma --since 1m | grep -qi "error\|fail"; then
    echo "[$(date)] ERROR detected!" >> /tmp/incident-monitor.log
  fi
  sleep 60
done
```

### Phase 5: Communicate & Document (Ongoing)

#### 5.1 Status Updates
Send updates every **15 minutes** during active incident:

**Template:**
```
[HH:MM] ROMA Incident Update - <Status>

Current Status: <Investigating|Identified|Monitoring|Resolved>

What we know:
- <Summary of issue>
- <Impact assessment>
- <Current actions>

Next update: <Time>

Incident ID: <ID>
Severity: <P0|P1|P2|P3>
```

#### 5.2 Resolution Notice
```
[HH:MM] ROMA Incident RESOLVED - <Issue>

Issue: <Description>
Root Cause: <Technical explanation>
Resolution: <What was done>
Duration: <Total time>

Preventive measures:
- <Action item 1>
- <Action item 2>

Post-incident review: <Date/Time>
```

---

## Common Incidents

### Incident: Pipeline Execution Failures

**Symptoms:**
- Tasks fail with "Cannot read properties of undefined"
- DAG execution order incorrect
- Tasks missing required inputs

**Diagnosis:**
```bash
# Check executor logs
docker compose logs roma | grep -A 10 "Executing task"

# Verify task dependencies
docker compose exec roma pnpm tsx -e "
import { Planner } from './packages/roma/dist/planner.js';
const planner = new Planner();
const dag = planner.plan('test', { taskType: 'build_saas_app' });
console.log(JSON.stringify(dag, null, 2));
"
```

**Resolution:**
1. Check `packages/roma/src/planner.ts` - verify task dependencies
2. Check `packages/roma/src/executor.ts` - verify input gathering logic
3. Add null guards to builder methods
4. Rebuild: `pnpm build && docker compose up -d --build`

**Prevention:**
- Add contract tests for DAG validation
- Add integration tests for end-to-end pipeline
- Enable verbose logging in production

---

### Incident: Memory Leak / OOM Kills

**Symptoms:**
- Container restarts frequently
- Docker logs show `exit code 137` (OOM killed)
- Memory usage grows unbounded

**Diagnosis:**
```bash
# Check memory trends
docker stats --no-stream roma-builder
docker compose logs roma | grep -i "out of memory"

# Get heap snapshot (if Node process is accessible)
docker compose exec roma node -e "
const v8 = require('v8');
const fs = require('fs');
fs.writeFileSync('heap.heapsnapshot', JSON.stringify(v8.writeHeapSnapshot()));
console.log('Heap snapshot written to heap.heapsnapshot');
"
```

**Resolution:**
1. Increase container memory limit (temporary):
   ```yaml
   # docker-compose.yml
   deploy:
     resources:
       limits:
         memory: 4G  # Increase from 2G
   ```
2. Identify memory leak in code:
   - Check for circular references
   - Check for unclosed streams/connections
   - Check for large arrays/objects not being garbage collected
3. Apply fix and redeploy

**Prevention:**
- Add memory monitoring alerts
- Run heap profiling in staging
- Add max memory limits to Node: `--max-old-space-size=1536`

---

### Incident: Security Vulnerability Exploited

**Symptoms:**
- Unexpected API calls
- Unauthorized file access
- Secrets exposed in logs
- Container showing suspicious processes

**Immediate Actions:**
```bash
# STOP THE SERVICE IMMEDIATELY
docker compose stop roma

# Isolate the container
docker network disconnect roma-network roma-builder

# Capture evidence
docker logs roma-builder > /tmp/security-incident-$(date +%s).log
docker exec roma-builder ps aux > /tmp/processes.txt

# Check for backdoors
docker exec roma-builder find / -type f -mtime -1 -ls 2>/dev/null
```

**Investigation:**
```bash
# Check for exposed secrets
docker compose logs roma | grep -i "password\|secret\|key\|token"

# Check file modifications
docker diff roma-builder

# Check network connections
docker exec roma-builder netstat -tuln
```

**Resolution:**
1. Rotate all secrets/keys immediately
2. Review code for vulnerability (SQL injection, XSS, command injection)
3. Patch vulnerability
4. Rebuild image from scratch: `docker build --no-cache`
5. Deploy with new secrets
6. File security incident report

**Prevention:**
- Enable secret scanning (Gitleaks, TruffleHog)
- Enable SAST (CodeQL, Snyk)
- Regular dependency updates
- Principle of least privilege

---

## Escalation Paths

### Level 1: On-Call Engineer (0-30 min)
- **Responsibility**: Initial triage, basic fixes, containment
- **Authority**: Can restart services, apply config changes
- **Escalate if**: Cannot resolve within 30 min, or P0 incident

### Level 2: Senior SRE / Team Lead (30-60 min)
- **Responsibility**: Complex debugging, architectural decisions
- **Authority**: Can modify code, deploy hotfixes, rollback
- **Escalate if**: Cannot resolve within 60 min, or security incident

### Level 3: Engineering Manager / CTO (60+ min)
- **Responsibility**: Customer communication, external vendor escalation
- **Authority**: Can declare major incident, invoke disaster recovery
- **Escalate if**: Multi-service outage, data breach, regulatory impact

### Emergency Contacts

| Role | Name | Phone | Email | Slack |
|------|------|-------|-------|-------|
| On-Call SRE | Rotation | +1-XXX-XXX-XXXX | oncall@company.com | @oncall |
| Team Lead | Name | +1-XXX-XXX-XXXX | lead@company.com | @lead |
| CTO | Name | +1-XXX-XXX-XXXX | cto@company.com | @cto |

---

## Post-Incident Review

### Timeline Template

| Time (UTC) | Event | Action Taken | By Whom |
|------------|-------|--------------|---------|
| 14:00 | Alert fired | Acknowledged | On-Call |
| 14:05 | Triage complete | Identified root cause | On-Call |
| 14:15 | Fix deployed | Rolled back deployment | On-Call |
| 14:30 | Monitoring | Verified fix working | On-Call |
| 14:45 | Resolved | Closed incident | On-Call |

### 5 Whys Analysis

**Problem:** <Description>

1. **Why did X happen?** Because Y
2. **Why did Y happen?** Because Z
3. **Why did Z happen?** Because A
4. **Why did A happen?** Because B
5. **Why did B happen?** Because <root cause>

**Root Cause:** <Final answer>

### Action Items

| Action | Owner | Due Date | Status |
|--------|-------|----------|--------|
| Add monitoring for X | SRE | 2025-12-01 | Open |
| Fix bug in Y component | Dev | 2025-12-03 | Open |
| Update runbook with Z | On-Call | 2025-11-30 | Done |

### Lessons Learned

**What went well:**
- Quick detection (5 minutes)
- Effective communication
- Successful rollback

**What went wrong:**
- No automated rollback
- Monitoring gap for X metric
- Insufficient testing of Y feature

**Improvements:**
- [ ] Add automated health checks before deployment
- [ ] Implement canary deployment
- [ ] Add integration test for Y feature
- [ ] Document X failure mode in runbook

---

## Quick Reference

### Key Logs Locations
```
# Container logs
docker compose logs roma

# Application logs
docker exec roma-builder cat /app/.roma/logs/roma.log

# System logs
docker exec roma-builder dmesg
```

### Key Metrics
```
# Container health
docker compose ps roma

# Resource usage
docker stats roma-builder

# Service endpoints
curl http://localhost:3000/health
```

### Emergency Commands
```bash
# Kill and restart
docker compose kill roma && docker compose up -d roma

# Factory reset (destructive!)
docker compose down -v && docker system prune -af && docker compose up -d

# Rollback to last known good
git log --oneline | head -5
git checkout <commit-sha>
docker compose up -d --build
```

---

**Document Maintenance:**
- Review quarterly
- Update after each incident
- Add new failure modes as discovered
- Remove outdated procedures
