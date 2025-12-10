# Quick Start: Testing ROMA + PTC with Kimi

## Option 1: Test on Your Local Machine (Recommended)

### 1. Copy PTC Service to Your Machine

From Claude Code environment:
```bash
# Package the PTC service
cd /home/user
tar -czf ptc-service.tar.gz ptc-service/
```

Transfer `ptc-service.tar.gz` to your local machine, then:

```bash
# Extract
tar -xzf ptc-service.tar.gz
cd ptc-service

# Set up Python environment
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -e .
```

### 2. Configure Environment

Edit `.env` file:
```bash
# Your Kimi API key (already set)
KIMI_API_KEY=sk-CkVXe7heymTJVlE6kfaKxfl0sn6oWmTDMtXVhwUytzXhaUXU

# Provider selection
LLM_PROVIDER=kimi

# Daytona API key (already set)
DAYTONA_API_KEY=dtn_fee7f751e8e48c1a44bdd405464e157a0efe4d8f8a9ff0d1f78fb8ded99b2a84
DAYTONA_API_URL=https://api.daytona.io/v1
```

### 3. Start Service

```bash
cd ptc-service
source .venv/bin/activate
uvicorn src.ptc.service:app --host 0.0.0.0 --port 8001 --reload
```

You should see:
```
INFO: Uvicorn running on http://0.0.0.0:8001
INFO: Kimi (Moonshot AI) client initialized
INFO: PTC Agent initialized successfully
```

### 4. Test the Service

In a new terminal:
```bash
curl http://localhost:8001/health
```

Should return:
```json
{"status":"healthy","service":"ptc","version":"0.1.0","schemas_available":true}
```

### 5. Run Integration Test

```python
import asyncio
import httpx
from pathlib import Path
import sys

# If you have ROMA locally, add it to path
sys.path.insert(0, str(Path("path/to/ROMA/src")))

from roma_dspy.ptc.schemas import PTCExecutionPlan, ScaffoldingSpec

async def test():
    plan = PTCExecutionPlan(
        execution_id="test-001",
        scaffolding=ScaffoldingSpec(
            task_description="Create a Python function to check if a number is prime",
            requirements=[
                "Function named 'is_prime'",
                "Handle edge cases (0, 1, negative)"
            ],
            dependencies=[]
        ),
        enable_testing=True
    )
    
    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(
            "http://localhost:8001/execute",
            json=plan.model_dump(mode='json')
        )
        result = response.json()
        print(f"Status: {result['status']}")
        print(f"Artifacts: {len(result['artifacts'])}")
        print(f"Cost: ${result.get('llm_usage', [{}])[0].get('cost_usd', 0):.4f}")

asyncio.run(test())
```

---

## Option 2: Quick Cloud Deployment

### Using Google Cloud (Free Tier)

```bash
# 1. Create VM
gcloud compute instances create ptc-service \
  --machine-type=e2-micro \
  --zone=us-central1-a \
  --image-family=ubuntu-2204-lts \
  --image-project=ubuntu-os-cloud

# 2. SSH into VM
gcloud compute ssh ptc-service

# 3. Install Python and dependencies
sudo apt update
sudo apt install python3-pip python3-venv -y

# 4. Upload and extract ptc-service.tar.gz (use gcloud scp)

# 5. Follow steps 2-3 from Option 1
```

### Using DigitalOcean

1. Create Droplet (Ubuntu 22.04, $6/month)
2. SSH into droplet
3. Upload ptc-service.tar.gz
4. Follow steps 2-3 from Option 1

---

## Expected Output (When Working)

```
🚀 Testing ROMA + PTC Integration with Kimi
============================================================
📝 Task: Create a Python function to check if a number is prime
🔧 Requirements: 2
🧪 Testing Enabled: True

⏳ Calling PTC service...

============================================================
📊 RESULTS
============================================================

✅ Status: ExecutionStatus.SUCCESS
⏱️  Duration: 8.43s
🔄 Iterations: 1

📦 Artifacts Generated: 2
   1. prime_checker.py (source_code) - 542 chars
      Preview: def is_prime(n: int) -> bool:...
   2. test_prime_checker.py (test) - 387 chars

💰 LLM Usage:
   Provider: kimi
   Model: moonshot-v1-32k
   Tokens: 1,247 (prompt: 523, completion: 724)
   Cost: $0.0041

💵 Total Cost: $0.0041

🧪 Test Execution (Daytona Sandbox):
   Command: pytest -v --tb=short --color=no
   Exit Code: 0
   Tests Passed: 5
   Tests Failed: 0
   Duration: 2.14s

============================================================
✅ SUCCESS! Full integration working:
   ✓ Kimi code generation
   ✓ Code parsing and classification
   ✓ Daytona sandbox test execution

🎉 ROMA + PTC + Kimi integration is operational!
```

---

## Troubleshooting

### "Connection refused" on localhost:8001
- Service not started yet - wait a few seconds
- Check if service is running: `ps aux | grep uvicorn`

### "403 Forbidden" / "Connection error"
- You're behind a proxy (like in Claude Code)
- Deploy to a machine without proxy restrictions

### "Invalid API key"
- Double check your Kimi API key in `.env`
- Get a key from https://platform.moonshot.cn/

### Tests failing in Daytona
- Check Daytona API key is valid
- Ensure service has internet access to reach api.daytona.io

---

## Cost Monitoring

Each successful code generation with Kimi costs approximately:
- Simple function: $0.002-0.004
- Medium complexity: $0.01-0.02
- Complex feature: $0.03-0.05

100 simple functions ≈ $0.40 with Kimi vs $0.60 with Claude

---

## Next Steps

Once working:
1. Run the full test suite: `pytest tests/test_live_integration.py -v`
2. Try more complex tasks
3. Monitor costs and quality
4. Scale as needed
5. Integrate with your ROMA workflows

Enjoy your cost-effective AI code generation! 🎉
