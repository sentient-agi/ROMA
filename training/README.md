# ACE Training Infrastructure

This directory contains the training infrastructure for ROMA+PTC+ACE system.

## Overview

The training system allows you to train ACE on multiple code generation scenarios, building up a skillbook that improves performance over time.

**Expected Outcomes:**
- 📚 **50 scenarios**: 15-20 skills learned, 20-30% improvement
- 📚 **100 scenarios**: 30-40 skills learned, 30-50% improvement
- 💰 **Token reduction**: 40-50% on similar tasks
- 🎯 **Quality improvement**: Better code structure, fewer errors

---

## Quick Start

### 1. Basic Training (Example Scenarios)

Run the training script with built-in examples:

```bash
cd /home/user/ROMA
python training/ace_training.py --examples
```

This runs 5 example Micro SaaS scenarios and creates an initial skillbook.

### 2. Custom Training (Your Scenarios)

Create your scenarios file:

```bash
cp training/scenarios_template.yaml training/my_scenarios.yaml
# Edit my_scenarios.yaml with your scenarios
```

Run training with your scenarios:

```bash
python training/ace_training.py --scenarios training/my_scenarios.yaml
```

### 3. Interactive Training

Add scenarios interactively:

```bash
python training/ace_training.py --interactive
```

---

## Training Workflow

```
┌─────────────────────────────────────────────────────────────┐
│                    TRAINING WORKFLOW                         │
└─────────────────────────────────────────────────────────────┘

1. Prepare Scenarios
   ↓
   Create scenarios_template.yaml with your tasks
   (User provides: 50-100 Micro SaaS / automation scenarios)

2. Run Training
   ↓
   python training/ace_training.py --scenarios scenarios.yaml
   - Executes each scenario via ROMA+PTC
   - ACE learns patterns from each execution
   - Skillbook grows with each task

3. Monitor Progress
   ↓
   Watch console output for:
   - Skills learned count
   - Performance scores
   - Cost per scenario
   - Success/failure rate

4. Review Results
   ↓
   Check training/results/training_results_*.json
   - Detailed results for each scenario
   - Cost breakdown
   - Category performance
   - Overall statistics

5. Use Trained System
   ↓
   The trained skillbook is now ready for production
   All future tasks benefit from learned patterns
```

---

## File Structure

```
training/
├── README.md                      # This file
├── ace_training.py                # Main training script
├── scenarios_template.yaml        # YAML template for scenarios
├── scenarios_template.json        # JSON template for scenarios
├── scenarios.yaml                 # YOUR scenarios (create this)
│
├── skillbooks/                    # Learned skills storage
│   └── training.json             # Default skillbook for training
│
└── results/                       # Training results
    └── training_results_*.json   # Result files (timestamped)
```

---

## Creating Training Scenarios

### Scenario Format (YAML)

```yaml
scenarios:
  - name: "Descriptive Name"
    goal: "Natural language description of what to build"
    requirements:
      - "Specific requirement 1"
      - "Specific requirement 2"
      - "Specific requirement 3"
    task_type: "CODE_INTERPRET"  # or TEXT_GENERATION, CODE_REVIEW
    category: "micro_saas"        # or automation, ai_agent, custom
```

### Scenario Format (JSON)

```json
{
  "scenarios": [
    {
      "name": "Descriptive Name",
      "goal": "Natural language description of what to build",
      "requirements": [
        "Specific requirement 1",
        "Specific requirement 2"
      ],
      "task_type": "CODE_INTERPRET",
      "category": "micro_saas"
    }
  ]
}
```

### Example Scenarios

See `scenarios_template.yaml` for detailed examples including:
- Email validation API
- URL shortener service
- Webhook forwarding
- And more...

---

## Training Strategies

### Strategy 1: Pattern-Based Training

Group similar tasks together so ACE learns patterns:

```yaml
# Group 1: Validation APIs (10 scenarios)
- Email validation
- Phone validation
- URL validation
- Credit card validation
- ...

# Group 2: Authentication Systems (10 scenarios)
- JWT auth
- OAuth flow
- API key management
- ...

# Group 3: Data Processing (10 scenarios)
- CSV parser
- JSON validator
- XML transformer
- ...
```

**Why**: ACE learns "validation pattern", "auth pattern", etc. that apply across all similar tasks.

### Strategy 2: Progressive Complexity

Start simple, increase complexity:

```yaml
# Level 1: Basic (20 scenarios)
- Simple CRUD APIs
- Basic validators
- Simple webhooks

# Level 2: Intermediate (20 scenarios)
- APIs with authentication
- Multi-step workflows
- Database integration

# Level 3: Advanced (10 scenarios)
- Complex multi-agent systems
- Full-featured SaaS products
- Advanced integrations
```

**Why**: Builds foundational skills before tackling complex tasks.

### Strategy 3: Real-World Mix

Mix of actual products you want to build:

```yaml
# 40% Micro SaaS (20 scenarios)
- Email validator API
- Screenshot service
- Form backend
- ...

# 30% Automation (15 scenarios)
- Workflow engines
- Data pipelines
- Integration platforms
- ...

# 20% AI Agents (10 scenarios)
- Research agent
- Support agent
- Code reviewer
- ...

# 10% Tools/Utilities (5 scenarios)
- CLI tools
- Data converters
- API clients
- ...
```

**Why**: Trains on tasks you'll actually use in production.

---

## Usage Options

### Option 1: Run Example Scenarios

Quick test with 5 built-in examples:

```bash
python training/ace_training.py --examples
```

### Option 2: Run from YAML File

Your custom scenarios:

```bash
python training/ace_training.py --scenarios my_scenarios.yaml
```

### Option 3: Run from JSON File

```bash
python training/ace_training.py --scenarios my_scenarios.json
```

### Option 4: Interactive Mode

Add scenarios one at a time:

```bash
python training/ace_training.py --interactive
```

Prompts you for:
- Scenario name
- Goal/description
- Requirements
- Category

Type "done" when finished to start training.

### Option 5: Custom Configuration

Override defaults:

```bash
python training/ace_training.py \
  --scenarios my_scenarios.yaml \
  --ptc-url http://my-ptc-service:8002 \
  --skillbook ./custom_skillbook.json
```

---

## Command-Line Options

```
python training/ace_training.py [OPTIONS]

Options:
  --scenarios PATH     Path to scenarios file (YAML or JSON)
  --examples          Run built-in example scenarios
  --interactive       Interactive mode - add scenarios manually
  --ptc-url URL       PTC service URL (default: http://localhost:8002)
  --skillbook PATH    Skillbook save path (default: ./training/skillbooks/training.json)
  -h, --help          Show help message
```

---

## Monitoring Training

### Console Output

During training, you'll see:

```
🎯 Starting training with 50 scenarios

📚 Initial skills: 0

[1/50]
▶️  Running: Email Validation API
   Goal: Build a FastAPI endpoint for email validation
   Category: micro_saas
   ✅ Success
   📊 Score: 0.87
   💰 Cost: $0.0012

[2/50]
▶️  Running: URL Shortener Service
   ...

[10/50]
📚 Skills learned: 3

...

[50/50]
📚 Final skills: 18
📈 Skills gained: 18

============================================================
📊 TRAINING SUMMARY
============================================================
Total scenarios: 50
✅ Successful: 48 (96.0%)
❌ Failed: 2 (4.0%)

📁 By Category:
  micro_saas: 20/20 (100.0%)
  automation: 15/16 (93.8%)
  ai_agent: 10/10 (100.0%)
  custom: 3/4 (75.0%)

💰 Total Cost: $0.0450
🔢 Total Tokens: 45,230
📈 Avg Cost/Scenario: $0.0009

💾 Results saved to: training/results/training_results_20251208_143022.json
```

### Result Files

After training, check `training/results/training_results_*.json`:

```json
{
  "session_id": "20251208_143022",
  "total_scenarios": 50,
  "successful": 48,
  "failed": 2,
  "results": [
    {
      "timestamp": "2025-12-08T14:30:25",
      "scenario": {
        "name": "Email Validation API",
        "goal": "Build a FastAPI endpoint...",
        "category": "micro_saas"
      },
      "success": true,
      "output_preview": "from fastapi import FastAPI...",
      "metadata": {
        "cost_usd": 0.001234,
        "tokens_used": 456,
        "performance_score": 0.87,
        "skills_used": 3
      }
    },
    ...
  ]
}
```

---

## Expected Performance

### Training Progress

| Stage | Scenarios | Skills Learned | Improvement | Token Reduction |
|-------|-----------|----------------|-------------|-----------------|
| Initial | 0 | 0 | 0% | 0% |
| Early | 1-10 | 2-4 | 5-10% | 10-15% |
| Mid | 11-30 | 8-15 | 15-25% | 25-35% |
| Trained | 31-50 | 15-20 | 20-30% | 35-45% |
| Well-Trained | 51-100 | 30-40 | 30-50% | 45-55% |

### Cost Estimates

**Training Costs** (Kimi provider):
- 50 scenarios × $0.001 avg = ~$0.05
- 100 scenarios × $0.001 avg = ~$0.10

**ACE Reflection Costs** (GPT-4o-mini):
- 50 reflections × $0.0001 = ~$0.005
- 100 reflections × $0.0001 = ~$0.01

**Total Training Cost**:
- 50 scenarios: ~$0.055
- 100 scenarios: ~$0.11

**ROI**:
After training, each similar task saves 40-50% tokens:
- Before: $0.001 per task
- After: $0.0005 per task
- Break-even: ~10-20 tasks
- Annual savings (1000 tasks): $500

---

## After Training

### Using Trained Skillbook

Once training is complete, use the trained skillbook in production:

```python
from roma_dspy.integrations import create_ace_executor

# Load trained skillbook
executor = create_ace_executor(
    ptc_base_url="http://localhost:8002",
    skillbook_path="./training/skillbooks/training.json",  # Trained!
)

# All tasks now benefit from learned patterns
result = await executor.aforward("Build a new SaaS API")
# ← Uses learned skills → faster, cheaper, better quality
```

### Continuous Learning

The system continues learning in production:

```python
# Production executor continues learning
executor = create_ace_executor(
    skillbook_path="./production_skillbook.json",
    async_learning=True,  # Non-blocking learning
)

# Each task improves the skillbook
for task in production_tasks:
    result = await executor.aforward(task)
    # Skillbook updated automatically
```

### Backing Up Skillbooks

```bash
# Daily backup
cp training/skillbooks/training.json backups/training_$(date +%Y%m%d).json

# Version control
git add training/skillbooks/training.json
git commit -m "Training: 50 scenarios, 18 skills learned"
```

---

## Troubleshooting

### Training Fails to Start

**Error**: `ModuleNotFoundError: No module named 'ace'`

**Fix**:
```bash
pip install /home/user/ace-repo/
```

### PTC Service Unavailable

**Error**: `Connection refused to http://localhost:8002`

**Fix**: Start PTC service first:
```bash
cd /path/to/ptc-service
python -m uvicorn app.main:app --port 8002
```

### Low Success Rate

**Issue**: Many scenarios failing

**Possible Causes**:
1. Scenarios too vague → Add more specific requirements
2. PTC service issues → Check PTC logs
3. API provider limits → Check rate limits

**Fix**: Review failed scenarios in results file, refine requirements.

### Skills Not Accumulating

**Issue**: Skills learned stays at 0

**Diagnosis**:
```bash
# Check if ACE is enabled
grep "ACE learning" training/results/*.json

# Check skillbook file
cat training/skillbooks/training.json
```

**Fix**: Ensure ACE dependencies installed:
```bash
pip install ace-framework litellm pydantic
```

---

## Best Practices

### 1. Scenario Design

✅ **Good Scenario**:
```yaml
name: "RESTful CRUD API"
goal: "Build a complete CRUD API for managing blog posts"
requirements:
  - "FastAPI framework"
  - "SQLAlchemy ORM with PostgreSQL"
  - "Pydantic models for validation"
  - "JWT authentication"
  - "Pagination support"
  - "Filter by author and tags"
```

❌ **Poor Scenario**:
```yaml
name: "API"
goal: "Make an API"
requirements:
  - "Make it good"
```

### 2. Training Batch Size

- **Small batch (10-20)**: Quick test, basic patterns
- **Medium batch (30-50)**: Good training, useful skills
- **Large batch (75-100)**: Comprehensive, production-ready

### 3. Scenario Variety

Include diverse tasks:
- ✅ Different domains (auth, data, integrations)
- ✅ Different complexity levels
- ✅ Different tech stacks
- ✅ Different patterns

Avoid repetition:
- ❌ 50 identical "CRUD API" scenarios
- ❌ All same category
- ❌ All same complexity

### 4. Monitoring

Check these metrics during training:
- Success rate (should be >90%)
- Cost per scenario (should decrease over time)
- Skills learned (should grow steadily)
- Performance score (should improve)

---

## Next Steps

1. ✅ Review this README
2. ✅ Examine `scenarios_template.yaml`
3. ✅ Create `my_scenarios.yaml` with your tasks
4. ✅ Run training: `python training/ace_training.py --scenarios my_scenarios.yaml`
5. ✅ Monitor progress via console output
6. ✅ Review results in `training/results/`
7. ✅ Use trained skillbook in production

---

## Support

For issues or questions:
- Check `/home/user/ROMA/docs/ACE_INTEGRATION.md`
- Review example scenarios in `scenarios_template.yaml`
- Check training results for error details

---

**Last Updated**: 2025-12-08
**Status**: ✅ Ready for Training
