# Rolling Restart Runbook

**Version:** 1.0
**Last Updated:** 2025-11-29
**Estimated Time:** 5-15 minutes
**Risk Level:** Low

---

## Purpose

Safely restart ROMA services with minimal disruption. Use this runbook for:
- Applying configuration changes
- Clearing memory leaks
- Recovering from degraded state
- Applying security patches
- Routine maintenance

---

## Prerequisites

- [ ] Check current service health
- [ ] Verify no active critical jobs
- [ ] Notify team in Slack/Email if production
- [ ] Have rollback plan ready
- [ ] Backup current state (optional, recommended)

---

## Quick Reference

### Zero-Downtime Restart (Recommended)
```bash
docker compose up -d --no-deps --build roma
```

### Standard Restart
```bash
docker compose restart roma
```

### Full Restart (with rebuild)
```bash
docker compose down
docker compose up -d --build
```

### Emergency Stop
```bash
docker compose stop roma
# OR
docker compose kill roma  # Forceful
```

---

## Procedures

### Procedure 1: Health Check Restart (Most Common)

**When to use:** Service is degraded but still running

**Time:** ~2 minutes
**Downtime:** None (if using --no-deps)

#### Steps

**1. Check current health**
```bash
# Check if containers are running
docker compose ps roma

# Check resource usage
docker stats --no-stream roma-builder

# Check recent logs for errors
docker compose logs roma --tail=100 | grep -i error
```

**2. Capture pre-restart state**
```bash
# Save current logs
docker compose logs roma > /tmp/pre-restart-$(date +%s).log

# Note current resource usage
docker stats --no-stream roma-builder > /tmp/pre-restart-stats.txt
```

**3. Perform restart**
```bash
# Graceful restart (recommended)
docker compose restart roma

# Monitor restart
watch -n 1 'docker compose ps roma'
```

**4. Verify health**
```bash
# Wait 10 seconds for startup
sleep 10

# Check if healthy
docker compose ps roma | grep "Up (healthy)"

# Run smoke test
pnpm roma:onthisday

# Check logs for startup errors
docker compose logs roma --since 1m | grep -i error
```

**Expected outcome:**
- Container status: `Up (healthy)`
- Smoke test: Passes
- No error logs
- Memory usage: Reset to baseline (~200-500MB)

---

### Procedure 2: Configuration Change Restart

**When to use:** Applying changes to docker-compose.yml or .env

**Time:** ~5 minutes
**Downtime:** <10 seconds

#### Steps

**1. Prepare changes**
```bash
# Edit configuration
vim docker-compose.yml
# OR
vim .env

# Validate syntax
docker compose config

# Diff changes
git diff docker-compose.yml
```

**2. Apply changes**
```bash
# Recreate containers with new config
docker compose up -d roma

# This will:
# - Stop old container
# - Create new container with new config
# - Start new container
# - Remove old container
```

**3. Verify**
```bash
# Check new config is applied
docker compose exec roma env | grep YOUR_VARIABLE

# Check logs
docker compose logs roma --since 1m

# Run smoke test
pnpm roma:onthisday
```

---

### Procedure 3: Code Update Restart

**When to use:** Deploying new code version

**Time:** ~10 minutes
**Downtime:** <30 seconds

#### Steps

**1. Pull latest code**
```bash
# Fetch latest
git fetch origin

# Check what's new
git log HEAD..origin/main --oneline

# Pull
git pull origin main
```

**2. Rebuild**
```bash
# Install new dependencies (if package.json changed)
pnpm install

# Build new code
pnpm build

# Rebuild container image
docker compose build roma
```

**3. Deploy**
```bash
# Stop old, start new
docker compose up -d roma

# Monitor startup
docker compose logs -f roma
```

**4. Verify deployment**
```bash
# Check version (if you have version endpoint)
docker compose exec roma pnpm roma --version

# Run tests
pnpm test

# Run smoke test
pnpm roma:onthisday

# Monitor for 5 minutes
docker compose logs roma --since 5m | grep -i error
```

---

### Procedure 4: Emergency Restart (Service Unresponsive)

**When to use:** Service completely frozen, not responding to signals

**Time:** ~1 minute
**Downtime:** ~30 seconds

#### Steps

**1. Capture state before killing**
```bash
# Get thread dump (if possible)
docker compose exec roma kill -3 1 2>/dev/null

# Save logs
docker compose logs roma > /tmp/emergency-restart-$(date +%s).log

# Get container state
docker inspect roma-builder > /tmp/container-state.json
```

**2. Force kill and restart**
```bash
# Forcefully kill
docker compose kill roma

# Remove stopped container
docker compose rm -f roma

# Start fresh
docker compose up -d roma
```

**3. Investigate root cause**
```bash
# Check logs for what caused freeze
grep -i "error\|exception\|timeout\|deadlock" /tmp/emergency-restart-*.log

# Check if resource exhaustion
grep -i "out of memory\|no space\|too many" /tmp/emergency-restart-*.log

# File incident report
echo "Emergency restart at $(date)" >> incidents.log
```

---

### Procedure 5: Planned Maintenance Restart

**When to use:** Scheduled maintenance window

**Time:** ~15 minutes
**Downtime:** Planned (can be zero with blue-green deployment)

#### Steps

**1. Pre-maintenance announcement** (T-24h)
```bash
# Notify users
curl -X POST https://status.company.com/api/maintenance \
  -d '{
    "scheduled": "2025-12-01T02:00:00Z",
    "duration": "15min",
    "impact": "minimal",
    "reason": "Routine maintenance and updates"
  }'
```

**2. Pre-maintenance checks** (T-1h)
```bash
# Verify backups are current
ls -lh /backups/roma/state-$(date +%Y%m%d)*.tar.gz

# Ensure latest code is tested
git pull origin main
pnpm install && pnpm build && pnpm test

# Verify rollback images exist
docker images | grep roma-builder
```

**3. Perform maintenance** (T-0)
```bash
# Set status to maintenance
curl -X POST https://status.company.com/api/status \
  -d '{"status": "maintenance"}'

# Perform restart with updates
docker compose pull
docker compose up -d --force-recreate --build

# Monitor startup
docker compose logs -f roma
```

**4. Post-maintenance verification** (T+5min)
```bash
# Run full test suite
pnpm test

# Run smoke tests
pnpm roma:onthisday

# Load test (optional)
scripts/load-test.sh

# Update status
curl -X POST https://status.company.com/api/status \
  -d '{"status": "operational"}'
```

**5. Post-maintenance announcement** (T+15min)
```bash
# Close maintenance window
curl -X POST https://status.company.com/api/maintenance/complete \
  -d '{
    "actual_duration": "12min",
    "issues": "none",
    "notes": "Maintenance completed successfully"
  }'
```

---

## Rollback Procedures

### Quick Rollback (Within 5 Minutes)

**If new version has issues:**

```bash
# Option 1: Revert to previous image
docker tag roma-builder:previous roma-builder:latest
docker compose up -d roma

# Option 2: Git revert
git log --oneline | head -5  # Find last good commit
git revert HEAD
pnpm build
docker compose up -d --build roma

# Option 3: Use tagged release
docker pull company-registry/roma-builder:v1.2.3  # Last known good
docker tag company-registry/roma-builder:v1.2.3 roma-builder:latest
docker compose up -d roma
```

### Data Rollback

**If data was corrupted during restart:**

```bash
# Restore from pre-restart backup
docker cp /tmp/state-backup.tar.gz roma-builder:/tmp/
docker compose exec roma tar xzf /tmp/state-backup.tar.gz -C /app/

# Restart with restored data
docker compose restart roma
```

---

## Monitoring During Restart

### Key Metrics to Watch

**1. Container Health**
```bash
# Should transition: Up → Restarting → Up (healthy)
watch -n 1 'docker compose ps roma'
```

**2. Resource Usage**
```bash
# Memory should drop after restart, then stabilize
watch -n 2 'docker stats --no-stream roma-builder'
```

**3. Error Logs**
```bash
# Should be minimal/zero errors
docker compose logs -f roma | grep -i error
```

**4. Response Time**
```bash
# Should be <100ms
time pnpm roma:onthisday
```

### Warning Signs

| Sign | Severity | Action |
|------|----------|--------|
| Container keeps restarting | High | Check logs, consider rollback |
| Memory >1.5GB after 5min | Medium | Investigate memory leak |
| Errors in logs | Medium-High | Check error type, may need rollback |
| Startup >60 seconds | Low | Normal for first start, investigate if consistent |

---

## Troubleshooting

### Container Won't Start

**Symptoms:** Status shows `Restarting` or `Exited`

**Diagnosis:**
```bash
# Check exit code
docker inspect roma-builder --format='{{.State.ExitCode}}'

# Check logs
docker compose logs roma --tail=100

# Check if port conflict
netstat -tuln | grep 3000
```

**Solutions:**
```bash
# If port conflict
docker compose down
lsof -ti:3000 | xargs kill
docker compose up -d

# If bad configuration
docker compose config  # Validate
vim docker-compose.yml  # Fix
docker compose up -d

# If dependency issue
pnpm install --frozen-lockfile
pnpm build
docker compose up -d --build
```

---

### Restart Hangs

**Symptoms:** Docker compose restart command never completes

**Diagnosis:**
```bash
# Check if process is stuck
ps aux | grep "docker compose"

# Check Docker daemon
systemctl status docker

# Check container state
docker ps -a | grep roma
```

**Solutions:**
```bash
# Force kill and retry
pkill -9 "docker compose"
docker compose kill roma
docker compose rm -f roma
docker compose up -d roma

# If Docker daemon is stuck
systemctl restart docker
docker compose up -d
```

---

### Health Check Fails After Restart

**Symptoms:** Container shows `unhealthy` status

**Diagnosis:**
```bash
# Check health check logs
docker inspect roma-builder --format='{{json .State.Health}}' | jq

# Test health check manually
docker compose exec roma node -e "console.log('healthy')"
```

**Solutions:**
```bash
# Increase health check timeout if needed
# docker-compose.yml:
healthcheck:
  interval: 30s
  timeout: 10s  # Increase from 3s
  start_period: 30s  # Increase from 5s
  retries: 5  # Increase from 3

# Apply changes
docker compose up -d roma
```

---

## Best Practices

### Do's ✅

- **Always** check service health before restarting
- **Always** save logs before major restarts
- **Always** test in staging first (if available)
- **Always** have rollback plan ready
- **Always** monitor for at least 5 minutes after restart
- **Always** notify team for production restarts

### Don'ts ❌

- **Never** restart during peak usage (if avoidable)
- **Never** restart without checking for active jobs
- **Never** use `kill -9` unless absolutely necessary
- **Never** skip post-restart verification
- **Never** restart multiple services simultaneously (do one at a time)
- **Never** ignore warning signs after restart

---

## Checklists

### Pre-Restart Checklist

- [ ] Verified service health
- [ ] Checked for active jobs
- [ ] Saved current logs
- [ ] Backed up state (if needed)
- [ ] Notified team
- [ ] Prepared rollback plan
- [ ] Read relevant procedures

### Post-Restart Checklist

- [ ] Container status is `Up (healthy)`
- [ ] No errors in logs
- [ ] Smoke tests pass
- [ ] Resource usage is normal
- [ ] Monitored for 5+ minutes
- [ ] Updated status page
- [ ] Documented any issues

---

## Metrics & SLOs

### Restart Performance Targets

| Metric | Target | Actual | Last Measured |
|--------|--------|--------|---------------|
| Restart time | <30s | - | - |
| Memory after restart | <500MB | - | - |
| Error rate post-restart | 0% | - | - |
| Health check pass time | <10s | - | - |

Track these in your monitoring dashboard and review monthly.

---

## Document History

| Date | Version | Changes | Author |
|------|---------|---------|--------|
| 2025-11-29 | 1.0 | Initial version | SRE Team |

**Next Review:** 2026-02-28
