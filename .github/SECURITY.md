# Security Policy

## Overview

This project implements comprehensive security controls as part of Phase 4B - Production Hardening.

## Automated Security Scans

All pull requests must pass the following security checks before merging:

### 1. **SAST (Static Application Security Testing)**
- **Tool**: GitHub CodeQL
- **Workflow**: `.github/workflows/codeql.yml`
- **Scope**: JavaScript/TypeScript code analysis
- **Queries**: `security-extended` and `security-and-quality`
- **Blocking**: High/Critical severity findings
- **Schedule**: Weekly on Mondays + on every PR

### 2. **Dependency Vulnerability Scanning**
- **Tools**:
  - GitHub Dependency Review (PRs only)
  - pnpm audit (daily + on every PR)
- **Workflow**: `.github/workflows/dependency-scan.yml`
- **Blocking**: High/Critical vulnerabilities
- **Denied Licenses**: GPL-3.0, AGPL-3.0
- **Schedule**: Daily at 02:00 UTC + on every PR

### 3. **Secret Scanning**
- **Tools**:
  - Gitleaks (primary)
  - TruffleHog (verified secrets only)
  - Custom pattern matching
- **Workflow**: `.github/workflows/secret-scan.yml`
- **Blocking**: Any detected secrets
- **Patterns**: API keys, tokens, private keys, credentials
- **Exemptions**: Configure in `.gitleaksignore`

### 4. **Container & Filesystem Scanning**
- **Tool**: Trivy
- **Workflows**: `.github/workflows/container-scan.yml`
- **Scans**:
  - Filesystem vulnerabilities
  - IaC misconfigurations
  - Docker images (when applicable)
- **Blocking**: Critical vulnerabilities
- **Warning**: High vulnerabilities (review recommended)
- **Schedule**: Weekly on Wednesdays + on every PR

### 5. **Main CI Pipeline**
- **Workflow**: `.github/workflows/ci.yml`
- **Required Checks**:
  - Build & Lint
  - All tests passing
  - All security scans passing
- **Blocking**: Any failure prevents merge

## Security Requirements for PRs

Before a PR can be merged, it MUST:

1. ✅ **Pass build and linting** - Zero compilation errors
2. ✅ **Pass all tests** - 100% of tests must succeed
3. ✅ **Pass CodeQL SAST** - No high/critical code vulnerabilities
4. ✅ **Pass dependency audit** - No high/critical dependency vulnerabilities
5. ✅ **Pass secret scanning** - No secrets detected in code
6. ✅ **Pass Trivy scan** - No critical filesystem vulnerabilities

## Handling Security Findings

### False Positives

**Secret Scanning:**
Add entries to `.gitleaksignore`:
```
# Example: ignore specific test file
packages/tests/fixtures/fake-keys.ts:abc123hash
```

**Dependency Vulnerabilities:**
1. Check if vulnerability applies to your usage
2. If false positive, document in PR description
3. Consider upgrading or replacing dependency
4. As last resort: `pnpm audit --fix` or accept risk with approval

**SAST Findings:**
1. Review CodeQL alert in GitHub Security tab
2. Fix the vulnerability if valid
3. If false positive, dismiss with justification in Security tab

### Real Vulnerabilities

1. **CRITICAL**: Must be fixed before merge
2. **HIGH**: Should be fixed before merge (may require approval to bypass)
3. **MEDIUM/LOW**: Fix in follow-up PR, track in issue

## Environment Variables & Secrets

**Never commit:**
- API keys (HONEYCOMB_API_KEY, OPENAI_API_KEY, etc.)
- Access tokens (GITHUB_TOKEN, HF_TOKEN, etc.)
- Private keys or certificates
- Passwords or credentials

**Use instead:**
- GitHub Secrets for CI/CD
- Environment variables at runtime
- Secret management services (AWS Secrets Manager, Azure Key Vault, etc.)
- `.env` files (add to `.gitignore`)

## Scanning Schedules

| Scan Type | Trigger | Schedule |
|-----------|---------|----------|
| CodeQL SAST | PR, Push, Schedule | Weekly Monday 00:00 UTC |
| Dependency Scan | PR, Push, Schedule | Daily 02:00 UTC |
| Secret Scan | PR, Push | On-demand |
| Trivy | PR, Push, Schedule | Weekly Wednesday 03:00 UTC |
| Full CI | PR, Push | On every commit |

## Security Contacts

For security vulnerabilities, please:
1. **DO NOT** open a public issue
2. Report via GitHub Security Advisories
3. Or contact the maintainers directly

## Compliance

This project implements security controls for:
- ✅ SAST scanning (CodeQL)
- ✅ Dependency vulnerability management
- ✅ Secret detection and prevention
- ✅ Container/filesystem security scanning
- ✅ Automated PR blocking on security findings

**NOT compliant with:**
- ❌ Healthcare (HIPAA) - Domain guard blocks
- ❌ Finance (PCI-DSS, SOC2) - Domain guard blocks
- ❌ Government (FedRAMP, FISMA) - Domain guard blocks

This is intentional per Phase 4 requirements.

## Configuration

### Required GitHub Settings

For full security coverage, ensure:

1. **Branch Protection Rules** (on `main`/`master`):
   - Require status checks before merging
   - Require "All CI Checks Passed" to pass
   - Require "Security Gate" to pass
   - Require up-to-date branches

2. **GitHub Advanced Security** (if available):
   - Enable Dependabot alerts
   - Enable Dependabot security updates
   - Enable Secret scanning
   - Enable Code scanning (CodeQL)

3. **Repository Settings**:
   - Disable force pushes to protected branches
   - Require signed commits (recommended)
   - Enable vulnerability alerts

## Monitoring

Security scan results are available:

1. **GitHub Security Tab** - View all SAST, dependency, and secret findings
2. **Actions Tab** - View workflow execution logs
3. **PR Checks** - Required status checks show at PR level
4. **Artifacts** - Detailed reports available in workflow artifacts

## Updates

This security policy is reviewed and updated:
- Quarterly or as needed
- When new security tools are added
- When threat landscape changes
- When compliance requirements change

---

**Last Updated**: 2025-11-29
**Phase**: 4B - Security & Scanning
