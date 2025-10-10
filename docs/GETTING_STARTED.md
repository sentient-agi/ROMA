# 🔧 Getting Started with SentientResearchAgent

Welcome! This guide will help you get up and running with SentientResearchAgent in minutes. Let's build your first intelligent agent system! 🚀

## 📋 Table of Contents

- [Prerequisites](#-prerequisites)
- [Installation](#-installation)
- [Quick Start](#-quick-start)
- [Your First Task](#-your-first-task)
- [Using the Web Interface](#-using-the-web-interface)
- [Basic API Usage](#-basic-api-usage)
- [Understanding the Output](#-understanding-the-output)
- [Next Steps](#-next-steps)
- [Troubleshooting](#-troubleshooting)

## 📦 Prerequisites

Before you begin, ensure you have:

- **Operating System**: Linux, macOS, or Windows (with WSL)
- **Python**: 3.12 or higher
- **Node.js**: 23.11.0 or higher (for the frontend)
- **Git**: For cloning the repository

## 🚀 Installation

### Option 1: Automated Setup (Recommended)

The easiest way to get started:

```bash
# Clone the repository
git clone https://github.com/yourusername/SentientResearchAgent.git
cd SentientResearchAgent

# Run the setup script
./setup.sh
```

Choose between:
- **Docker Setup** - Isolated environment, perfect for trying out
- **Native Setup** - Direct installation for development

### Option 2: Manual Installation

#### Step 1: Backend Setup

```bash
# Install PDM (Python Dependency Manager)
pip install pdm

# Initialize the project
pdm init --non-interactive --python 3.12 --dist
pdm config use_uv true

# Install dependencies
pdm install

# Activate the virtual environment
eval "$(pdm venv activate)"
```

#### Step 2: Frontend Setup

```bash
# Navigate to frontend directory
cd frontend

# Install dependencies
npm install

# Return to project root
cd ..
```

#### Step 3: Configuration

```bash
# Copy the example environment file
cp .env.example .env

# Edit .env with your API keys
# Required keys:
# - OPENROUTER_API_KEY (or other LLM provider)
# - Optional: EXA_API_KEY (for web search)
```

## 🎯 Quick Start

### 1. Start the Server

```bash
# Simple start
python -m sentientresearchagent

# With custom configuration
python -m sentientresearchagent --config sentient.yaml
```

You should see:
```
🚀 Starting Sentient Research Agent Server on 0.0.0.0:8000
📡 WebSocket: http://localhost:8000
🌐 Frontend: http://localhost:3000
📊 System Info: http://localhost:8000/api/system-info
```

### 2. Open the Web Interface

Navigate to `http://localhost:3000` in your browser. You'll see the task execution interface.

### 3. Try a Simple Task

In the web interface:
1. Click "New Task"
2. Enter a goal: `"What are the benefits of solar energy?"`
3. Click "Execute"
4. Watch as the system breaks down and executes your task!

## 🔍 Your First Task

Let's understand what happens when you submit a task:

### Example: Research Task

```python
# Using the Python API
from sentientresearchagent import SentientAgent

async def main():
    # Create an agent
    agent = SentientAgent.create()
    
    # Execute a research task
    result = await agent.run(
        "Compare the environmental impacts of electric vs hydrogen vehicles"
    )
    
    print(result)

# Run the example
import asyncio
asyncio.run(main())
```

### What Happens Behind the Scenes

1. **Task Analysis** 🔍
   - The system analyzes your goal
   - Determines if it needs to be broken down

2. **Planning** 📋
   - Creates a plan with subtasks:
     - Research electric vehicle impacts
     - Research hydrogen vehicle impacts
     - Compare and synthesize findings

3. **Execution** ⚡
   - Subtasks run in parallel where possible
   - Each task uses specialized agents

4. **Aggregation** 📊
   - Results are combined intelligently
   - Final report is generated

## 🖥️ Using the Web Interface

### Main Features

#### 1. Task Submission
![Task Input](images/task-input.png)
- Enter your goal in natural language
- Select an agent profile (optional)
- Configure execution settings

#### 2. Real-Time Visualization
![Task Graph](images/task-graph.png)
- See tasks decompose in real-time
- Track execution progress
- View task dependencies

#### 3. Result Viewing
![Results](images/results.png)
- Structured output display
- Download results
- View execution traces

### Interface Components

- **Task Tree**: Visual hierarchy of all tasks
- **Status Indicators**: 
  - 🔵 PENDING - Waiting to start
  - 🟡 RUNNING - Currently executing
  - 🟢 DONE - Successfully completed
  - 🔴 FAILED - Encountered an error
- **Detail Panel**: Click any task to see details

## 🔌 Basic API Usage

### REST API

#### Execute a Task

```bash
curl -X POST http://localhost:8000/api/simple/execute \
  -H "Content-Type: application/json" \
  -d '{
    "goal": "Write a blog post about quantum computing",
    "profile": "general_agent"
  }'
```

#### Quick Research

```bash
curl -X POST http://localhost:8000/api/simple/research \
  -H "Content-Type: application/json" \
  -d '{
    "topic": "Latest developments in renewable energy"
  }'
```

### WebSocket API (Real-time)

```javascript
// Connect to WebSocket
const socket = io('http://localhost:8000');

// Listen for updates
socket.on('task_update', (data) => {
  console.log('Task updated:', data);
});

// Execute with streaming
socket.emit('simple_execute_stream', {
  goal: 'Analyze cryptocurrency market trends',
  stream: true
});
```

### Python SDK

```python
from sentientresearchagent import ProfiledSentientAgent

# Use a specific profile
agent = ProfiledSentientAgent.create_with_profile("deep_research_agent")

# Execute with configuration
result = await agent.run(
    goal="Research the history of artificial intelligence",
    config={
        "max_depth": 3,
        "enable_caching": True,
        "timeout": 300
    }
)
```

## 📊 Understanding the Output

### Task Results Structure

```json
{
  "task_id": "root",
  "goal": "Your original goal",
  "status": "DONE",
  "result": {
    "content": "Final synthesized result...",
    "metadata": {
      "sources": ["source1", "source2"],
      "confidence": 0.95,
      "execution_time": 45.2
    }
  },
  "subtasks": [
    {
      "task_id": "root.1",
      "goal": "Subtask 1",
      "result": "..."
    }
  ]
}
```

### Execution Trace

Each execution creates a detailed trace in `runtime/projects/traces/`:
- Task decomposition decisions
- Agent invocations
- Context passed between tasks
- Timing information

## 🎓 Common Use Cases

### 1. Research Tasks

```python
result = await agent.run(
    "Research the latest breakthroughs in cancer treatment from 2023-2024"
)
```

### 2. Content Creation

```python
result = await agent.run(
    "Create a comprehensive guide on sustainable living practices"
)
```

### 3. Analysis Tasks

```python
result = await agent.run(
    "Analyze the pros and cons of remote work for software developers"
)
```

### 4. Complex Queries

```python
result = await agent.run(
    "Design a mobile app for mental health tracking, including features, "
    "user interface mockups, and implementation plan"
)
```

## ⚙️ Configuration Tips

### Basic Configuration

Edit `sentient.yaml`:

```yaml
# Use faster execution for testing
execution:
  max_concurrent_nodes: 5  # Run more tasks in parallel
  enable_hitl: false       # Disable human review for automation

# Choose your LLM provider
llm:
  provider: "openrouter"
  model_id: "anthropic/claude-3-opus"  # Or any supported model
```

### Agent Profiles

Select pre-configured profiles:
- `general_agent` - Balanced for most tasks
- `deep_research_agent` - Thorough research with citations
- `creative_agent` - For creative writing and ideation

## 🚨 Troubleshooting

### Common Issues

#### 1. "Connection Refused" Error
```bash
# Ensure the server is running
python -m sentientresearchagent

# Check if port 8000 is available (or your configured FLASK_PORT)
lsof -i :8000
```

#### 2. "API Key Invalid" Error
```bash
# Verify your .env file
cat .env | grep API_KEY

# Ensure keys are set correctly
export OPENROUTER_API_KEY="your-key-here"
```

#### 3. Frontend Not Loading
```bash
# Rebuild frontend
cd frontend
npm run build
cd ..

# Restart server
python -m sentientresearchagent
```

### Debug Mode

Run with detailed logging:
```bash
python -m sentientresearchagent --debug
```

Check logs in `runtime/logs/sentient.log`

## 🎯 Next Steps

Now that you're up and running:

1. **[Core Concepts](CORE_CONCEPTS.md)** - Understand how the system works
2. **[Agent Guide](AGENTS_GUIDE.md)** - Create custom agents
3. **[Examples](examples/)** - See advanced implementations
4. **[API Reference](API_REFERENCE.md)** - Complete API documentation

## 💡 Pro Tips

1. **Start Simple**: Begin with straightforward tasks before complex ones
2. **Use Profiles**: Leverage pre-configured profiles for better results
3. **Monitor Progress**: Watch the task graph to understand execution
4. **Check Traces**: Execution traces help debug and optimize
5. **Cache Results**: Enable caching for faster repeated queries

## 🤝 Getting Help

- **Documentation**: Check other guides in `/docs`
- **Examples**: Browse `/notebooks` for Jupyter examples
- **Issues**: Report bugs on GitHub
- **Community**: Join discussions in GitHub Discussions

---

Ready to build something amazing? Start experimenting with different tasks and see what SentientResearchAgent can do! 🚀