# Disaster Recovery Plan

**Version:** 1.0
**Last Updated:** 2025-11-29
**Owner:** SRE Team
**Review Schedule:** Quarterly

---

## Table of Contents

1. [Recovery Objectives](#recovery-objectives)
2. [Backup Strategy](#backup-strategy)
3. [Recovery Procedures](#recovery-procedures)
4. [Disaster Scenarios](#disaster-scenarios)
5. [Testing & Validation](#testing--validation)

---

## Recovery Objectives

### RTO (Recovery Time Objective)

| Component | RTO | Justification |
|-----------|-----|---------------|
| **ROMA Service** | 15 minutes | Critical for customer operations |
| **Generated Artifacts** | 4 hours | Customers can re-generate if needed |
| **Execution History** | 24 hours | Historical data, not critical |
| **Documentation** | 1 week | Stored in git, easily recoverable |

### RPO (Recovery Point Objective)

| Data Type | RPO | Backup Frequency |
|-----------|-----|------------------|
| **Source Code** | 0 (zero data loss) | Continuous (git) |
| **Container Images** | 1 hour | Every deployment |
| **Execution State** | 1 hour | Hourly snapshots |
| **Generated Artifacts** | 24 hours | Daily backups |

### Priority Classification

**P0 - Critical (Restore Immediately)**
- Source code repository
- Container registry
- Service configuration
- Secrets/credentials

**P1 - High (Restore within RTO)**
- Container images (tagged releases)
- Recent execution state (<24h)
- Production logs

**P2 - Medium (Restore within 24h)**
- Historical execution state
- Generated artifacts (can be regenerated)
- Development/staging environments

**P3 - Low (Restore as convenient)**
- Build cache
- Development logs
- Temporary files

---

## Backup Strategy

### What We Back Up

#### 1. Source Code (Git)
**Location:** GitHub/GitLab
**Frequency:** Continuous (every commit)
**Retention:** Forever (git history)
**Backup Method:**
```bash
# Multiple git remotes
git remote add origin https://github.com/company/roma.git
git remote add backup https://backup-git.company.com/roma.git

# Push to both
git push origin main
git push backup main
```

**Recovery:**
```bash
git clone https://github.com/company/roma.git
# Or if primary is down
git clone https://backup-git.company.com/roma.git
```

#### 2. Container Images
**Location:** Docker Registry (ECR/DockerHub/GCR)
**Frequency:** Every deployment
**Retention:** Last 30 images per tag
**Backup Method:**
```bash
# Tag with timestamp
docker tag roma-builder:latest roma-builder:$(date +%Y%m%d-%H%M%S)
docker tag roma-builder:latest roma-builder:1.0.0

# Push to primary registry
docker push company-registry/roma-builder:latest
docker push company-registry/roma-builder:1.0.0

# Mirror to backup registry
docker tag roma-builder:1.0.0 backup-registry/roma-builder:1.0.0
docker push backup-registry/roma-builder:1.0.0
```

**Recovery:**
```bash
# Pull from primary
docker pull company-registry/roma-builder:1.0.0

# Or from backup if primary is down
docker pull backup-registry/roma-builder:1.0.0
```

#### 3. Secrets & Configuration
**Location:** Encrypted vault (HashiCorp Vault / AWS Secrets Manager)
**Frequency:** On every update
**Retention:** Last 10 versions
**Backup Method:**
```bash
# Export secrets to encrypted file
vault kv get -format=json secret/roma > secrets.json
gpg --encrypt --recipient ops@company.com secrets.json

# Store encrypted backup in secure S3 bucket
aws s3 cp secrets.json.gpg s3://company-secrets-backup/roma/$(date +%Y%m%d).gpg
```

**Recovery:**
```bash
# Download encrypted backup
aws s3 cp s3://company-secrets-backup/roma/20251129.gpg secrets.json.gpg

# Decrypt
gpg --decrypt secrets.json.gpg > secrets.json

# Restore to vault
jq -r '.data.data | to_entries[] | .key + "=" + .value' secrets.json | while IFS='=' read key value; do
  vault kv put secret/roma/$key value="$value"
done
```

#### 4. Execution State & Logs
**Location:** Persistent volumes + S3 archive
**Frequency:** Hourly snapshots, daily archives
**Retention:** 7 days (hourly), 90 days (daily)
**Backup Method:**
```bash
# Snapshot execution state
docker compose exec roma tar czf /tmp/state-$(date +%Y%m%d-%H%M%S).tar.gz /app/.roma

# Upload to S3
docker cp roma-builder:/tmp/state-*.tar.gz .
aws s3 sync . s3://company-roma-backups/state/ --exclude "*" --include "state-*.tar.gz"

# Clean old backups (keep 7 days)
aws s3 ls s3://company-roma-backups/state/ | \
  while read -r line; do
    createDate=$(echo $line | awk '{print $1" "$2}')
    createDate=$(date -d "$createDate" +%s)
    olderThan=$(date -d "7 days ago" +%s)
    if [[ $createDate -lt $olderThan ]]; then
      fileName=$(echo $line | awk '{print $4}')
      aws s3 rm s3://company-roma-backups/state/$fileName
    fi
  done
```

**Recovery:**
```bash
# Download latest backup
LATEST=$(aws s3 ls s3://company-roma-backups/state/ | sort | tail -1 | awk '{print $4}')
aws s3 cp s3://company-roma-backups/state/$LATEST state-backup.tar.gz

# Restore to container
docker cp state-backup.tar.gz roma-builder:/tmp/
docker compose exec roma tar xzf /tmp/state-backup.tar.gz -C /app/
```

---

## Recovery Procedures

### Scenario 1: Complete Service Failure (Service Down)

**Symptoms:**
- All containers crashed
- Health checks failing
- No response from service

**Recovery Steps:**

#### Step 1: Assess Damage (0-5 min)
```bash
# Check what's still running
docker compose ps

# Check Docker daemon
systemctl status docker

# Check disk space
df -h

# Check logs for root cause
docker compose logs roma --tail=100
```

#### Step 2: Attempt Quick Recovery (5-10 min)
```bash
# Try simple restart
docker compose restart roma

# If that fails, recreate containers
docker compose down
docker compose up -d

# Monitor restart
watch -n 2 'docker compose ps && echo "---" && docker compose logs roma --tail=10'
```

#### Step 3: If Quick Recovery Fails - Full Rebuild (10-30 min)
```bash
# Pull latest code
git pull origin main

# Clean rebuild
pnpm clean
pnpm install --frozen-lockfile
pnpm build

# Rebuild containers
docker compose down -v
docker compose build --no-cache
docker compose up -d

# Verify health
docker compose ps
pnpm roma:onthisday
```

#### Step 4: Verify Recovery
```bash
# Run smoke tests
pnpm test
pnpm roma:onthisday

# Check all services
docker compose exec roma pnpm roma --version

# Monitor for 15 minutes
docker compose logs -f roma
```

**Expected Recovery Time:** 30 minutes
**Data Loss:** None (if volumes intact)

---

### Scenario 2: Data Corruption (Corrupted Artifacts)

**Symptoms:**
- Generated artifacts are malformed
- Pipeline produces invalid output
- Schema validation fails unexpectedly

**Recovery Steps:**

#### Step 1: Isolate Corruption (0-5 min)
```bash
# Stop generating new artifacts
docker compose stop roma

# Identify corruption
ls -lh out/
cat out/intake.json | jq .  # Check if valid JSON

# Check if it's localized or widespread
find out/ -name "*.json" -exec sh -c 'jq empty {} 2>/dev/null || echo "Corrupted: {}"' \;
```

#### Step 2: Restore from Backup (5-15 min)
```bash
# Download latest clean backup
aws s3 sync s3://company-roma-backups/artifacts/$(date -d "yesterday" +%Y%m%d)/ ./out/

# Verify restored data
for file in out/*.json; do
  jq empty "$file" && echo "✓ $file" || echo "✗ $file"
done
```

#### Step 3: Regenerate (if backup unavailable)
```bash
# Re-run pipeline from known-good source
docker compose start roma
pnpm roma:onthisday

# Verify output
jq . out/intake.json
jq . out/architecture.json
```

**Expected Recovery Time:** 15 minutes
**Data Loss:** Up to 24 hours (RPO)

---

### Scenario 3: Total System Loss (Server Destroyed)

**Symptoms:**
- Server completely lost (hardware failure, cloud zone down, etc.)
- No access to any local data

**Recovery Steps:**

#### Step 1: Provision New Server (0-30 min)
```bash
# AWS example
aws ec2 run-instances \
  --image-id ami-xxxxx \
  --instance-type t3.large \
  --key-name roma-recovery \
  --security-groups roma-sg \
  --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=roma-recovery}]'

# Wait for instance
aws ec2 wait instance-running --instance-ids i-xxxxx

# Get public IP
IP=$(aws ec2 describe-instances --instance-ids i-xxxxx --query 'Reservations[0].Instances[0].PublicIpAddress' --output text)

# SSH in
ssh -i roma-recovery.pem ubuntu@$IP
```

#### Step 2: Install Dependencies (30-45 min)
```bash
# Update system
sudo apt-get update && sudo apt-get upgrade -y

# Install Docker
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
newgrp docker

# Install Node.js & pnpm
curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash -
sudo apt-get install -y nodejs
npm install -g pnpm

# Install Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose
```

#### Step 3: Restore Application (45-60 min)
```bash
# Clone repository
git clone https://github.com/company/roma.git
cd roma

# Restore secrets
aws s3 cp s3://company-secrets-backup/roma/latest.gpg secrets.json.gpg
gpg --decrypt secrets.json.gpg > .env

# Install & build
pnpm install --frozen-lockfile
pnpm build

# Pull container images (faster than rebuilding)
docker pull company-registry/roma-builder:latest

# Start services
docker compose up -d
```

#### Step 4: Restore Data (60-75 min)
```bash
# Restore execution state
aws s3 sync s3://company-roma-backups/state/ ./state-backups/
LATEST=$(ls -t state-backups/ | head -1)
docker cp state-backups/$LATEST roma-builder:/tmp/state.tar.gz
docker compose exec roma tar xzf /tmp/state.tar.gz -C /app/

# Restore artifacts (if needed)
aws s3 sync s3://company-roma-backups/artifacts/latest/ ./out/
```

#### Step 5: Verify & Monitor (75-90 min)
```bash
# Run health checks
docker compose ps
pnpm test
pnpm roma:onthisday

# Verify data integrity
find out/ -name "*.json" -exec jq empty {} \;

# Update DNS (if needed)
aws route53 change-resource-record-sets --hosted-zone-id Z12345 \
  --change-batch file://dns-update.json

# Monitor for 30 minutes
docker compose logs -f roma | tee recovery.log
```

**Expected Recovery Time:** 90 minutes
**Data Loss:** Up to 24 hours (RPO)

---

### Scenario 4: Git Repository Lost/Corrupted

**Symptoms:**
- Cannot clone from primary git remote
- Git history corrupted
- Force-push destroyed history

**Recovery Steps:**

#### Step 1: Check Backup Remotes
```bash
# List all remotes
git remote -v

# Try backup remote
git fetch backup
git checkout backup/main

# If backup is clean
git push origin main --force  # DANGEROUS - only in recovery!
```

#### Step 2: Restore from Developer Machines
```bash
# Find developer with latest code
# Ask team to run:
git log -1 --pretty=format:"%H %ai %s"

# Developer with latest code creates bundle
git bundle create roma-recovery.bundle --all

# Transfer bundle to recovery server
scp roma-recovery.bundle recovery-server:/tmp/

# On recovery server
git clone /tmp/roma-recovery.bundle roma
cd roma
git remote add origin https://github.com/company/roma.git
git push origin --all
git push origin --tags
```

#### Step 3: Verify Recovery
```bash
# Clone fresh
git clone https://github.com/company/roma.git roma-verify
cd roma-verify

# Check commit count matches
git log --oneline | wc -l

# Check last 10 commits match team records
git log --oneline -10

# Verify build works
pnpm install && pnpm build && pnpm test
```

**Expected Recovery Time:** 2-4 hours
**Data Loss:** Minimal (depends on last developer push)

---

## Disaster Scenarios

### Classification Matrix

| Scenario | Likelihood | Impact | RTO | Mitigation |
|----------|-----------|--------|-----|------------|
| Service crash | High | Low | 15 min | Auto-restart, monitoring |
| Data corruption | Medium | Medium | 1 hour | Backups, validation |
| Server failure | Low | High | 90 min | Multi-AZ deployment |
| Git repo loss | Very Low | High | 4 hours | Multiple remotes |
| Region outage | Very Low | Critical | 4 hours | Multi-region |
| Security breach | Low | Critical | Immediate | Security scanning, audits |

### Runbook Links

| Disaster Type | Primary Runbook | Secondary Runbook |
|---------------|-----------------|-------------------|
| Service down | This doc (Scenario 1) | [Incident Response](./runbooks/incident-response.md) |
| Data loss | This doc (Scenario 2) | [Troubleshooting](./troubleshooting.md) |
| Security incident | [Incident Response - Security](./runbooks/incident-response.md#incident-security-vulnerability-exploited) | Contact security team |
| Infrastructure | This doc (Scenario 3) | Cloud provider support |

---

## Testing & Validation

### Recovery Drills Schedule

| Drill Type | Frequency | Next Scheduled |
|------------|-----------|----------------|
| Service restart (Scenario 1) | Monthly | 2025-12-01 |
| Backup restore (Scenario 2) | Quarterly | 2026-01-15 |
| Full disaster recovery (Scenario 3) | Annually | 2026-03-01 |
| Git recovery (Scenario 4) | Annually | 2026-06-01 |

### Drill Checklist

**Pre-Drill:**
- [ ] Notify team of drill schedule
- [ ] Prepare test environment (staging)
- [ ] Document current state
- [ ] Set success criteria
- [ ] Assign roles (coordinator, operator, observer)

**During Drill:**
- [ ] Start timer
- [ ] Follow runbook step-by-step
- [ ] Document deviations
- [ ] Time each phase
- [ ] Test monitoring/alerting

**Post-Drill:**
- [ ] Stop timer, record total time
- [ ] Verify all data recovered correctly
- [ ] Run smoke tests
- [ ] Document lessons learned
- [ ] Update runbook with improvements
- [ ] Schedule fixes for identified gaps

### Drill Report Template

```markdown
## Disaster Recovery Drill Report

**Date:** YYYY-MM-DD
**Scenario:** [Scenario name]
**Operator:** [Name]
**Observer:** [Name]

### Results
- **Objective:** [What we tested]
- **Success:** [Yes/No]
- **RTO Target:** [Target time]
- **RTO Actual:** [Actual time]
- **Data Loss:** [None / Amount]

### Timeline
| Time | Action | Result |
|------|--------|--------|
| 00:00 | Started drill | N/A |
| 00:05 | Step 1 completed | Success |
| ... | ... | ... |
| 01:30 | Drill complete | Success |

### Issues Encountered
1. [Issue description]
2. [Issue description]

### Action Items
- [ ] [Fix/improvement]
- [ ] [Update runbook]
- [ ] [Add monitoring]

### Sign-Off
- Operator: _______________
- Observer: _______________
- Manager: _______________
```

---

## Maintenance

### Backup Verification

**Weekly:**
```bash
#!/bin/bash
# Automated backup verification

# Check latest git backup
git clone https://backup-git.company.com/roma.git /tmp/roma-verify
cd /tmp/roma-verify
git log -1 --pretty=format:"%ai" | while read date; do
  age_seconds=$(( $(date +%s) - $(date -d "$date" +%s) ))
  if [ $age_seconds -gt 86400 ]; then
    echo "⚠️  Git backup is >24h old"
    exit 1
  else
    echo "✅ Git backup is fresh"
  fi
done

# Check S3 backups
latest=$(aws s3 ls s3://company-roma-backups/state/ | sort | tail -1 | awk '{print $1" "$2}')
age_seconds=$(( $(date +%s) - $(date -d "$latest" +%s) ))
if [ $age_seconds -gt 7200 ]; then
  echo "⚠️  S3 backup is >2h old"
else
  echo "✅ S3 backup is fresh"
fi

# Verify backup integrity
aws s3 cp s3://company-roma-backups/state/latest.tar.gz /tmp/
tar tzf /tmp/latest.tar.gz > /dev/null && echo "✅ Backup is valid" || echo "❌ Backup is corrupted"
```

**Monthly:**
- Test restore on staging environment
- Verify all backup types
- Update retention policies
- Review and update this document

**Quarterly:**
- Full disaster recovery drill
- Review RTO/RPO targets
- Update contact information
- Audit access to backups

---

## Emergency Contacts

### Primary Contacts

| Role | Name | Phone | Email |
|------|------|-------|-------|
| SRE On-Call | Rotation | +1-XXX-XXX-XXXX | oncall-sre@company.com |
| Engineering Lead | Name | +1-XXX-XXX-XXXX | eng-lead@company.com |
| CTO | Name | +1-XXX-XXX-XXXX | cto@company.com |

### Vendor Contacts

| Vendor | Support Type | Contact | Account ID |
|--------|-------------|---------|-----------|
| AWS | Infrastructure | +1-XXX-XXX-XXXX | XXXXXXXXXXXX |
| GitHub | Git hosting | support@github.com | org-name |
| Docker | Container registry | support@docker.com | company-name |

---

## Appendix

### Automated Backup Scripts

See: `scripts/backup/`
- `backup-state.sh` - Hourly state snapshots
- `backup-artifacts.sh` - Daily artifact archives
- `backup-verify.sh` - Backup integrity checks

### Recovery Scripts

See: `scripts/recovery/`
- `recover-service.sh` - Quick service recovery
- `recover-data.sh` - Data restoration
- `recover-full.sh` - Full disaster recovery

### Monitoring Dashboards

- **Service Health:** https://monitoring.company.com/roma/health
- **Backup Status:** https://monitoring.company.com/roma/backups
- **Recovery Metrics:** https://monitoring.company.com/roma/recovery

---

**Last Tested:** [Date]
**Next Test:** [Date]
**Document Owner:** SRE Team
**Review Frequency:** Quarterly
