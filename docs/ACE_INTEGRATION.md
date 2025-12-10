# ACE Integration - Learning-Enabled ROMA + PTC

**Status**: ✅ Fully Integrated
**Version**: 1.0
**Date**: 2025-12-08

---

## Overview

This document describes the integration of **ACE (Agentic Context Engine)** with **ROMA + PTC**, enabling the system to **learn from each code generation task** and improve over time.

### What is ACE?

ACE is a learning framework that enables AI agents to improve from experience through a three-stage cycle:

1. **Agent** - Executes task and generates output
2. **Reflector** - Analyzes performance and extracts insights
3. **SkillManager** - Converts insights into reusable skills

**Key Benefits:**
- **20-35% performance improvement** after learning
- **49% token reduction** on similar tasks
- **Continuous improvement** without retraining
- **Persistent knowledge** via skillbooks

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    ACEIntegratedExecutor                     │
│                                                              │
│  ┌──────────────┐     ┌──────────────┐     ┌─────────────┐ │
│  │  PTCExecutor │────▶│  ACE Agent   │────▶│  Reflector  │ │
│  │   (Base)     │     │  (Wrapper)   │     │  (gpt-4o-   │ │
│  └──────────────┘     └──────────────┘     │   mini)     │ │
│         │                     │             └─────────────┘ │
│         │                     │                     │       │
│         ▼                     ▼                     ▼       │
│  ┌──────────────┐     ┌──────────────┐     ┌─────────────┐ │
│  │ PTC Service  │     │ Environment  │     │   Skill     │ │
│  │   (Kimi)     │     │  Evaluator   │     │  Manager    │ │
│  └──────────────┘     └──────────────┘     └─────────────┘ │
│                               │                     │       │
│                               └─────────┬───────────┘       │
│                                         ▼                   │
│                                  ┌─────────────┐            │
│                                  │  Skillbook  │            │
│                                  │   (JSON)    │            │
│                                  └─────────────┘            │
└─────────────────────────────────────────────────────────────┘
```

---

## Components

### 1. ACEIntegratedExecutor

Main class that extends `PTCExecutor` with learning capabilities.

**Location**: `src/roma_dspy/integrations/ace_integration.py`

```python
from roma_dspy.integrations import create_ace_executor

executor = create_ace_executor(
    ptc_base_url="http://localhost:8002",
    skillbook_path="./skillbooks/roma_ptc.json",
    ace_model="gpt-4o-mini",  # Cheap model for reflection
    async_learning=True,  # Non-blocking learning
)

result = await executor.aforward("Create a FastAPI endpoint")
# ACE learns in background, improves future executions
```

**Features:**
- Wraps standard `PTCExecutor` execution
- Automatic learning after each task
- Skillbook persistence
- Async learning (non-blocking)
- Thread-safe for concurrent use

### 2. CodeGenerationEnvironment

Evaluates code generation quality and provides feedback.

**Evaluation Metrics:**
- ✅ **Success** - Code generated without errors
- 💰 **Cost Efficiency** - Lower cost = higher score
- 📊 **Quality** - Comments, type hints, structure
- 🎯 **Intent Match** - Matches requirements

**Feedback Format:**
```
🎉 Excellent! ✅ Generated code | 💰 Cost: $0.0012 (456 tokens) | 📊 Quality: 90% | ✅ Matches intent
```

### 3. ACEPTCAgent

ACE-compatible wrapper for `PTCExecutor`.

**Key Function:**
- Translates ACE `Sample` format to `PTCExecutor` interface
- Enhances prompts with learned skills from skillbook
- Extracts metadata for performance tracking

### 4. Skillbook

Persistent storage of learned patterns.

**Storage Format**: JSON
**Location**: `./skillbooks/*.json` (configurable)

**Example Skillbook Structure:**
```json
{
  "skills": [
    {
      "name": "efficient-validation-pattern",
      "description": "Use regex with named groups for validation",
      "examples": [...],
      "success_rate": 0.95
    }
  ]
}
```

---

## Usage Examples

### Basic Usage

```python
import asyncio
from roma_dspy.integrations import create_ace_executor
from roma_dspy.types import TaskType

async def main():
    # Create ACE-enabled executor
    executor = create_ace_executor(
        ptc_base_url="http://localhost:8002",
        skillbook_path="./skillbooks/my_skills.json",
    )

    # Execute task (ACE learns automatically)
    result = await executor.aforward(
        goal="Create a user authentication system",
        task_type=TaskType.CODE_INTERPRET,
        requirements=[
            "Use JWT tokens",
            "Include password hashing",
            "Add rate limiting",
        ],
    )

    print(result.output)

    # Check learning stats
    stats = executor.get_learning_stats()
    print(f"Skills learned: {stats['total_skills_learned']}")

asyncio.run(main())
```

### Learning Progression

```python
# Run series of related tasks
tasks = [
    "Create email validator",
    "Create phone validator",
    "Create URL validator",
    "Create credit card validator",
]

for task in tasks:
    result = await executor.aforward(goal=task)
    # ACE learns common validation patterns

# Future validation tasks benefit from learned patterns
result = await executor.aforward("Create IPv6 validator")
# Uses learned patterns → faster + cheaper
```

### Skillbook Reuse

```python
# Session 1: Learn from tasks
executor1 = create_ace_executor(skillbook_path="./skills.json")
await executor1.aforward("Build REST API")
# Skills saved to ./skills.json

# Session 2: Reuse learned skills
executor2 = create_ace_executor(skillbook_path="./skills.json")
await executor2.aforward("Build GraphQL API")
# Loads existing skills → improved performance
```

---

## Learning Cycle

### Stage 1: Agent Execution

```python
# User provides task
task = "Create a FastAPI endpoint for user login"

# PTCExecutor generates code via PTC service
result = await ptc_executor.aforward(goal=task)
```

### Stage 2: Environment Evaluation

```python
# CodeGenerationEnvironment evaluates quality
metrics = {
    "success": 1.0,           # Code generated successfully
    "cost_efficiency": 0.85,  # Good cost/value ratio
    "quality": 0.90,          # Has comments, types
    "intent_match": 1.0,      # Matches requirements
    "overall": 0.94           # Excellent!
}

feedback = "🎉 Excellent! ✅ Generated code | 💰 Cost: $0.0015..."
```

### Stage 3: Reflection & Skill Extraction

```python
# Reflector (GPT-4o-mini) analyzes execution
reflection = """
Pattern identified: When building authentication endpoints,
combining JWT with bcrypt and rate limiting creates secure,
production-ready code.
"""

# SkillManager creates reusable skill
skill = {
    "name": "secure-auth-pattern",
    "description": "JWT + bcrypt + rate limiting for auth",
    "examples": [...],
}

# Skill added to skillbook for future use
skillbook.add_skill(skill)
```

### Stage 4: Future Application

```python
# Next auth task uses learned pattern
result = await executor.aforward("Create password reset endpoint")
# Prompt enhanced with: "Based on previous learnings: secure-auth-pattern..."
# → Better code, faster generation, lower cost
```

---

## Performance Metrics

### Learning Improvements

Based on ACE framework benchmarks:

| Metric | Initial | After 50 Tasks | After 100 Tasks |
|--------|---------|----------------|-----------------|
| **Success Rate** | 85% | 92% | 96% |
| **Token Usage** | 100% | 65% | 51% |
| **Cost per Task** | $0.010 | $0.007 | $0.005 |
| **Quality Score** | 0.75 | 0.88 | 0.93 |

**Note**: These are projected based on ACE's published results (20-35% improvement, 49% token reduction).

### Cost Analysis

**ACE Overhead** (Reflection costs):
- Reflector model: `gpt-4o-mini` (~$0.0001 per reflection)
- Frequency: After each task (async, non-blocking)
- Total overhead: ~1-2% of task cost

**ROI Example**:
- Initial task cost: $0.010
- ACE overhead: $0.0001
- After 50 tasks: Save 35% tokens → $0.0065 per task
- **Break-even**: ~3 tasks
- **Long-term savings**: 30-50% on recurring tasks

---

## Configuration

### Environment Variables

```bash
# PTC Service
PTC_BASE_URL=http://localhost:8002
PTC_ENABLED=true

# ACE Settings
ACE_ENABLED=true
ACE_SKILLBOOK_PATH=./skillbooks/production.json
ACE_MODEL=gpt-4o-mini
ACE_ASYNC_LEARNING=true
```

### Skillbook Management

**Recommended Paths**:
- Development: `./skillbooks/dev.json`
- Testing: `./skillbooks/test.json`
- Production: `./skillbooks/production.json`

**Backup Strategy**:
```bash
# Daily backup
cp ./skillbooks/production.json ./backups/production-$(date +%Y%m%d).json

# Version control (optional)
git add skillbooks/production.json
git commit -m "Update skillbook - 150 skills learned"
```

**Skillbook Merging**:
```python
from ace import Skillbook

# Load multiple skillbooks
sb1 = Skillbook.load("./skillbooks/dev.json")
sb2 = Skillbook.load("./skillbooks/staging.json")

# Merge (handles duplicates)
merged = Skillbook.merge([sb1, sb2])
merged.save("./skillbooks/production.json")
```

---

## Async Learning

ACE supports **non-blocking learning** for production use.

### How It Works

```python
executor = create_ace_executor(
    async_learning=True,  # Learning happens in background
)

# Task executes normally
result = await executor.aforward("Build API")
# ← Returns immediately

# Learning happens in background thread
# ← No blocking, user gets result fast
# ← Skillbook updates asynchronously
```

**Benefits**:
- ✅ No user-facing latency
- ✅ Immediate results
- ✅ Learning continues in background
- ✅ Thread-safe skillbook updates

**Thread Safety**:
```python
# Multiple concurrent executions
tasks = [executor.aforward(f"Task {i}") for i in range(10)]
results = await asyncio.gather(*tasks)
# ThreadSafeSkillbook handles concurrent updates
```

---

## Production Deployment

### Recommended Setup

```python
# production_executor.py
from roma_dspy.integrations import create_ace_executor
from pathlib import Path

# Production configuration
PRODUCTION_CONFIG = {
    "ptc_base_url": "http://ptc-service:8002",
    "skillbook_path": "/data/skillbooks/production.json",
    "ace_model": "gpt-4o-mini",
    "async_learning": True,
}

def get_production_executor():
    """Create production-ready ACE executor."""
    skillbook_path = Path(PRODUCTION_CONFIG["skillbook_path"])
    skillbook_path.parent.mkdir(parents=True, exist_ok=True)

    return create_ace_executor(**PRODUCTION_CONFIG)
```

### Monitoring

```python
# Add monitoring to your application
import logging

logging.basicConfig(level=logging.INFO)

# Execute task
executor = get_production_executor()
result = await executor.aforward(goal=task)

# Log learning stats
stats = executor.get_learning_stats()
logging.info(f"ACE Stats: {stats}")

# Track performance
if hasattr(result, '_metadata'):
    logging.info(f"Performance: {result._metadata.get('performance_score')}")
    logging.info(f"Skills used: {result._metadata.get('skills_used')}")
```

### Health Checks

```python
# health_check.py
def check_ace_health():
    """Verify ACE system is functioning."""
    executor = get_production_executor()

    # Check ACE enabled
    stats = executor.get_learning_stats()
    assert stats['ace_enabled'], "ACE not enabled"

    # Check skillbook accessible
    assert stats['skillbook_path'] is not None, "No skillbook path"

    # Check skills loaded
    print(f"✅ ACE healthy: {stats['total_skills_learned']} skills loaded")

    return True
```

---

## Testing

### Run Test Suite

```bash
cd /home/user/ROMA
python examples/test_ace_integration.py
```

**Test Coverage**:
1. ✅ Basic ACE-enabled execution
2. ✅ Learning progression (multiple tasks)
3. ✅ Skillbook persistence and reuse
4. ✅ Cost efficiency comparison

**Expected Output**:
```
🧪 ACE Integration Test Suite
Testing ROMA + PTC + ACE learning capabilities

============================================================
Test 1: Basic ACE-Enabled Execution
============================================================

Task: Create a Python function that calculates factorial
Executing...

✅ Result:
def factorial(n: int) -> int:
    """Calculate factorial of n."""
    ...

📊 ACE Metadata:
  Skills used: 0
  Feedback: ✅ Good! ✅ Generated code | 💰 Cost: $0.0012...
  Score: 0.87

📚 Learning Stats:
  Total skills learned: 1
  Skillbook: ./skillbooks/test_ace.json

...
```

---

## Migration Guide

### Migrating from PTCExecutor to ACEIntegratedExecutor

**Before (Standard PTCExecutor)**:
```python
from roma_dspy.core.modules import PTCExecutor

executor = PTCExecutor(
    ptc_enabled=True,
    ptc_base_url="http://localhost:8002",
)

result = await executor.aforward(goal="Build API")
```

**After (ACE-Enabled)**:
```python
from roma_dspy.integrations import create_ace_executor

executor = create_ace_executor(
    ptc_base_url="http://localhost:8002",
    skillbook_path="./skillbooks/production.json",
    # All PTCExecutor args still work!
)

result = await executor.aforward(goal="Build API")
# Now learns and improves over time!
```

**Backward Compatibility**: ✅ 100% compatible
All `PTCExecutor` arguments work with `ACEIntegratedExecutor`.

---

## Troubleshooting

### ACE Not Available

**Error**: `ACE not available. Install with: pip install ace-framework`

**Fix**:
```bash
# Install ACE from local repository
pip install /home/user/ace-repo/

# Or from PyPI (when available)
pip install ace-framework
```

### Skillbook Not Saving

**Error**: Skills learned but not persisted

**Possible Causes**:
1. Incorrect path permissions
2. Path doesn't exist
3. Async learning not completing

**Fix**:
```python
# Ensure parent directory exists
from pathlib import Path
skillbook_path = Path("./skillbooks/my_skills.json")
skillbook_path.parent.mkdir(parents=True, exist_ok=True)

# Create executor
executor = create_ace_executor(skillbook_path=str(skillbook_path))
```

### Learning Too Slow

**Issue**: Skills not accumulating as expected

**Diagnosis**:
```python
# Check if ACE is actually enabled
stats = executor.get_learning_stats()
print(stats['ace_enabled'])  # Should be True

# Check async learning
print(stats['async_learning'])  # Should be True for production
```

**Fix**:
```python
# Ensure ACE dependencies installed
pip install ace-framework litellm pydantic

# Verify ACE import
from ace import OnlineACE, Skillbook  # Should not error
```

### High Reflection Costs

**Issue**: ACE reflection costs too high

**Solution**: Use cheaper model
```python
executor = create_ace_executor(
    ace_model="gpt-4o-mini",  # ~$0.0001 per reflection
    # OR even cheaper:
    # ace_model="gpt-3.5-turbo",  # ~$0.00005 per reflection
)
```

---

## Roadmap

### Current (v1.0)
- ✅ ACE integration with PTCExecutor
- ✅ Automatic learning from executions
- ✅ Skillbook persistence
- ✅ Async learning support
- ✅ Production-ready

### Planned (v1.1)
- 🔄 Skill quality scoring
- 🔄 Skill expiration (remove outdated patterns)
- 🔄 Multi-model reflection (use different models)
- 🔄 Skill sharing across teams

### Future (v2.0)
- 📋 Active learning (request examples)
- 📋 Human feedback integration
- 📋 Skill marketplace
- 📋 Cross-project skill transfer

---

## References

- **ACE Framework**: https://github.com/Mtolivepickle/agentic-context-engine
- **ROMA Documentation**: `/home/user/ROMA/docs/`
- **PTC Integration**: `/home/user/ROMA/docs/PTC_INTEGRATION.md`
- **Example Code**: `/home/user/ROMA/examples/test_ace_integration.py`

---

## License

ACE integration follows ROMA's license (MIT).

---

**Last Updated**: 2025-12-08
**Status**: ✅ Production Ready
**Maintainer**: ROMA + PTC + ACE Integration Team
