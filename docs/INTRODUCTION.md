# 🚀 Introduction to ROMA

## 🌟 Universal Task Execution Framework

**ROMA** is a **general-purpose, hierarchical task execution framework** that empowers you to build ANY intelligent system by decomposing complex tasks into fundamental primitives. At the moment, we have the following: **Think 🤔, Write ✍️, and Search 🔍**.

This isn't just another AI tool—it's a **universal scaffold for building high-performance agents** that can handle ANY task that can be broken down using the MECE (Mutually Exclusive, Collectively Exhaustive) principle. From podcast generation to market analysis, from story writing to code generation—if you can imagine it, you can build it.

## 🎯 The MECE Framework

At the heart of SentientResearchAgent lies the **MECE principle** (Mutually Exclusive, Collectively Exhaustive), which provides a universal framework for decomposing ANY task into three fundamental operations.

### What is MECE?

MECE is a problem-solving principle that ensures complete coverage without overlap:
- **Mutually Exclusive**: Each operation type is distinct—there's no ambiguity about whether something is a THINK, WRITE, or SEARCH operation
- **Collectively Exhaustive**: These three operations cover ALL possible tasks—there's nothing you need to do that doesn't fit into one of these categories

### The Three Universal Operations

#### 🤔 THINK - Reasoning & Analysis
Any cognitive operation that processes information without creating new content or retrieving external data:
- **Data Analysis**: Finding patterns, trends, insights
- **Decision Making**: Choosing between options, evaluating trade-offs
- **Planning**: Breaking down problems, creating strategies
- **Evaluation**: Assessing quality, checking correctness
- **Problem Solving**: Finding solutions, debugging issues

#### ✍️ WRITE - Content Generation & Synthesis
Any operation that creates new content or synthesizes existing information:
- **Document Creation**: Reports, articles, documentation
- **Code Generation**: Writing programs, scripts, configurations
- **Creative Content**: Stories, scripts, marketing copy
- **Synthesis**: Combining multiple sources into cohesive output
- **Formatting**: Structuring and presenting information

#### 🔍 SEARCH - Information Retrieval
Any operation that gathers information from external sources:
- **Web Research**: Finding online information
- **Database Queries**: Retrieving structured data
- **API Calls**: Fetching from external services
- **Literature Review**: Academic or technical research
- **Data Collection**: Gathering raw information

### Why MECE Matters

1. **Universal Applicability**: ANY task can be broken down into these three operations
2. **Clear Boundaries**: No confusion about which operation to use
3. **Complete Coverage**: Nothing falls through the cracks
4. **Scalable Complexity**: Simple tasks use few operations, complex tasks use many

### MECE in Action

Consider building a market analysis report:

```
Goal: "Create a comprehensive market analysis for electric vehicles"

Decomposition:
1. SEARCH: Gather market data and statistics
2. SEARCH: Find competitor information
3. SEARCH: Collect regulatory information
4. THINK: Analyze market trends
5. THINK: Identify opportunities and threats
6. WRITE: Create executive summary
7. WRITE: Detailed analysis sections
8. THINK: Review and ensure coherence
9. WRITE: Final report with recommendations
```

Each operation is clearly one type, and together they completely achieve the goal.

## 🔄 Execution Flow Architecture

SentientResearchAgent uses a sophisticated three-directional execution flow that mirrors natural problem-solving:

### 1. **Top-Down Decomposition** ⬇️
Tasks flow from general to specific:
```
"Build a mobile app" (General)
    ↓
"Design UI" + "Build Backend" + "Write Tests" (Specific)
    ↓
"Create login screen" + "Design dashboard" + ... (More Specific)
```

### 2. **Bottom-Up Aggregation** ⬆️
Results flow from specific to general:
```
Individual UI screens (Specific)
    ↑
Complete UI design (Less Specific)
    ↑
Fully functional app (General)
```

### 3. **Left-to-Right Dependencies** ➡️
Tasks can depend on siblings for context:
```
"Research users" → "Design features" → "Build MVP"
     (First)           (Uses research)    (Uses both)
```


### The Recursive Process

1. **Every task starts at an ATOMIZER**
   - Evaluates task complexity
   - Decides: Can this be executed directly (EXECUTE) or needs planning (PLAN)?

2. **If EXECUTE node**:
   - Task is atomic (can't be broken down further)
   - Appropriate executor agent is called
   - Result is returned

3. **If PLAN node**:
   - Task is complex and needs decomposition
   - Planner agent breaks it into subtasks (THINK, WRITE, or SEARCH)
   - Each subtask goes through its own atomizer
   - Process repeats recursively to any depth

4. **Horizontal Dependencies** (Optional):
   - Tasks can depend on siblings at the same level
   - Dependent tasks wait for predecessors to complete
   - Results flow left-to-right when dependencies exist
   - Independent tasks execute in parallel

5. **AGGREGATOR collects results**:
   - Once all subtasks are complete
   - Combines results intelligently based on context
   - Returns synthesized result to parent
   - Parent may itself be a subtask in a larger tree

## 🎚️ Recursive Depth Control

One of SentientResearchAgent's most powerful features is **customizable recursion depth**, allowing you to control the granularity of task decomposition.

*Note: at the moment, we have found most use-cases work well for depths **<= 3***


### Controlling Depth

```python
# Shallow depth for quick tasks
agent = SentientAgent.create(max_depth=1)
quick_result = await agent.run("Summarize this article")
```

### Depth Guidelines

| Task Complexity | Recommended Depth | Use Cases |
|----------------|-------------------|-----------|
| Simple | 1 | Summaries, quick searches, basic writing |
| Moderate | 2-3 | Blog posts, reports, standard analysis |
| Complex | 3-4 | in-depth reports, comprehensive story generation |

## 🔍 Stage Tracing & Transparency

**Stage Tracing** is what sets ROMA apart—complete visibility into every step of the execution process.

### What is Stage Tracing?

Stage Tracing provides a detailed log of:
- **Inputs**: Exactly what each agent receives
- **Processing**: How the agent interprets and processes the input
- **Outputs**: What the agent produces
- **Context**: The surrounding information used
- **Decisions**: Why certain choices were made

### Benefits of Stage Tracing

1. **Debugging Made Easy**
   - See exactly where issues occur
   - Understand why certain outputs were produced
   - Identify bottlenecks or inefficiencies


2. **Trust Through Transparency**
   - No "black box" mystery
   - Understand the reasoning process
   - Verify correctness at each step

3. **Rapid Iteration**
   - See immediate effects of changes
   - Test different approaches quickly
   - Build confidence in your agents


## 🌳 Hierarchical Task Decomposition

The core principle of SentientResearchAgent is **hierarchical task decomposition** through a recursive atomizer-planner-executor architecture.

### The Concept

The framework mirrors human problem-solving through a recursive process:
1. **Atomizer evaluates** - Is this task atomic or does it need planning?
2. **If atomic** - Execute directly with appropriate agent
3. **If complex** - Plan and decompose into subtasks (THINK, WRITE, SEARCH)
4. **Recursively process** - Each subtask goes through the same evaluation
5. **Aggregate results** - Combine outputs bottom-up through aggregators

### Visual Example with Atomizer Flow

```
"Write a research paper on climate change" 
            │
            ▼ [ATOMIZER: Too complex → PLAN]
├── Research current climate data
│   │
│   ▼ [ATOMIZER: Too complex → PLAN]
│   ├── Search temperature trends
│   │   ▼ [ATOMIZER: Atomic → EXECUTE]
│   ├── Search sea level data
│   │   ▼ [ATOMIZER: Atomic → EXECUTE]
│   └── Search extreme weather patterns
│       ▼ [ATOMIZER: Atomic → EXECUTE]
│   ▲ [AGGREGATOR: Combine search results]
│
├── Analyze environmental impacts
│   │
│   ▼ [ATOMIZER: Too complex → PLAN]
│   ├── Impact on ecosystems
│   │   ▼ [ATOMIZER: Atomic → EXECUTE]
│   ├── Impact on human societies
│   │   ▼ [ATOMIZER: Atomic → EXECUTE]
│   └── Economic consequences
│       ▼ [ATOMIZER: Atomic → EXECUTE]
│   ▲ [AGGREGATOR: Synthesize analysis]
│
└── Write and format paper
    │
    ▼ [ATOMIZER: Too complex → PLAN]
    ├── Create outline
    │   ▼ [ATOMIZER: Atomic → EXECUTE]
    ├── Write sections
    │   ▼ [ATOMIZER: Atomic → EXECUTE]
    └── Add citations
        ▼ [ATOMIZER: Atomic → EXECUTE]
    ▲ [AGGREGATOR: Compile final paper]
```

### Key Components in Action

1. **ATOMIZER** - The gatekeeper that decides task handling:
   - Evaluates complexity
   - Routes to PLAN or EXECUTE
   - Ensures appropriate decomposition depth

2. **PLAN NODE** - The decomposer:
   - Breaks complex tasks into MECE subtasks
   - Assigns task types (THINK, WRITE, SEARCH)
   - Defines dependencies

3. **EXECUTE NODE** - The worker:
   - Handles atomic tasks
   - Uses specialized agents
   - Returns concrete results

4. **AGGREGATOR** - The synthesizer:
   - Collects all subtask results
   - Combines intelligently based on context
   - Returns unified output to parent

### Benefits

- **Intelligent Decomposition**: Atomizer ensures optimal task breakdown
- **Parallelization**: Independent subtasks run concurrently
- **Specialization**: Right agent for each task type
- **Clarity**: Complex goals become traceable execution paths
- **Flexibility**: Recursive depth adapts to task complexity


## 🎭 Node Types

### PLAN Nodes

**Purpose**: Decompose complex tasks into subtasks

```python
# PLAN node example
{
  "node_type": "PLAN",
  "goal": "Analyze market trends",
  "sub_graph_id": "subgraph_123",  # Points to child tasks
  "planned_sub_task_ids": ["root.1", "root.2", "root.3"]
}
```

**Characteristics**:
- Never execute work directly
- Create and manage subtasks
- Aggregate results from children
- Can be nested (plans within plans)

### EXECUTE Nodes

**Purpose**: Perform actual work

```python
# EXECUTE node example
{
  "node_type": "EXECUTE",
  "goal": "Search for latest AI breakthroughs",
  "agent_name": "SearchAgent",
  "result": "Found 15 relevant papers..."
}
```

**Characteristics**:
- Leaf nodes in the task tree
- Use specialized agents
- Produce concrete results
- Cannot have subtasks

## 🏷️ Task Types

Task types in ROMA directly map to the MECE framework operations:

### 1. SEARCH Tasks 🔍

**Purpose**: Information retrieval - gathering data from external sources

```python
TaskType.SEARCH
```

**Key Characteristics**:
- Intended to retrieve information from outside the current context
- Not intended to create new content
- Not intended to analyze or make decisions

**Examples**:
- Web searches for current information
- Database queries for specific data
- API calls to external services

**Typical Agents**: Web searchers, database/KB connectors, API integrators

### 2. WRITE Tasks ✍️

**Purpose**: Content generation - creating new information or synthesizing existing

```python
TaskType.WRITE
```

**Key Characteristics**:
- Creates new content that didn't exist before
- Synthesizes information into new forms

**Examples**:
- Report writing and documentation
- Code generation and implementation
- Formatting and presentation

**Typical Agents**: Writers, coders, synthesizers, formatters, content creators

### 3. THINK Tasks 🤔

**Purpose**: Analysis and reasoning - processing information to make decisions

```python
TaskType.THINK
```

**Key Characteristics**:
- Analyzes existing information
- Makes decisions and evaluations

**Examples**:
- Data analysis and pattern recognition
- Strategic planning and decision making
- Mathematical reasoning

**Typical Agents**: Analyzers, reasoners, consistency checking 


## 🤖 Agent System

Agents are the workers that process tasks. Each agent specializes in specific operations.

### Agent Roles

#### 1. Atomizer Agents

**Purpose**: Determine if a task needs decomposition

```python
Input: "Write a blog post about AI"
Output: {
  "is_atomic": False,  # Too complex, needs planning
  "refined_goal": "Write comprehensive blog post about AI developments"
}
```

#### 2. Planner Agents

**Purpose**: Decompose complex tasks

```python
Input: "Research and compare cloud providers"
Output: {
  "subtasks": [
    {"goal": "Research AWS features and pricing", "type": "SEARCH"},
    {"goal": "Research Azure features and pricing", "type": "SEARCH"},
    {"goal": "Research GCP features and pricing", "type": "SEARCH"},
    {"goal": "Create comparison matrix", "type": "THINK"},
    {"goal": "Write recommendation report", "type": "WRITE"}
  ]
}
```

#### 3. Executor Agents

**Purpose**: Perform actual work

```python
Input: "Search for quantum computing applications"
Output: {
  "result": "Found 5 key applications: cryptography, drug discovery...",
  "sources": ["Nature 2024", "MIT Research"],
  "confidence": 0.88
}
```

#### 4. Aggregator Agents

**Purpose**: Combine results from subtasks

```python
Input: [result1, result2, result3]
Output: {
  "summary": "Comprehensive analysis shows...",
  "key_findings": ["Finding 1", "Finding 2"],
  "conclusion": "Based on all research..."
}
```

## 🔗 Context Propagation

Context ensures information flows intelligently between tasks through well-defined propagation strategies.

### Context Propagation Strategies

#### 1. Parent-to-Child Propagation
Parent goals pass their context to children, ensuring awareness of the broader objective:
```python
{
 "parent_goal": "Write investment report",
 "parent_constraints": ["Focus on 2024 data", "Include ESG factors"],
 "inherited_context": {
   "overall_objective": "Quarterly portfolio review",
   "style_guide": "formal"
 }
}
```

2. Sibling-to-Sibling Propagation (Dependency-Based)
When a node depends on previous nodes, context flows between siblings:

```python
{
  "dependency_context": {
    "depends_on": ["research_task_1", "research_task_2"],
    "sibling_results": [
      {"task_id": "research_task_1", "output": "Company A analysis..."},
      {"task_id": "research_task_2", "output": "Company B analysis..."}
    ]
  }
}
```
```text
Root Task (context: user request)
    ↓ (propagates objective + constraints)
Plan Node (context: parent context + planning constraints)
    ↓ (propagates plan + parent context)
Execute Node 1 (context: plan + parent awareness)
    → (provides results to dependent siblings)
Execute Node 2 (context: plan + parent awareness + Node1 results via dependency)
    → (provides results to dependent siblings)
Execute Node 3 (context: plan + parent awareness + Node1,2 results via dependencies)
    ↑ (all results flow up)
Aggregator (context: all child results + original parent context)
```

**Context Types**
<li>
Lineage Context: Information flowing from parent and ancestor tasks</li>
<li>
Dependency Context: Results from sibling tasks that current task depends on</li>
<li>Execution Context: Runtime information and system state </li>
<li>User Context: Preferences and constraints from the original request</li>


## ⚡ Execution Strategies

### 1. Parallel Execution

Independent tasks run simultaneously:

```
        [Task A] ──┐
Root ──→ [Task B] ──┼──→ Aggregator
        [Task C] ──┘
```


### 2. Sequential Execution

Tasks with dependencies run in order:

```
Root ──→ [Task A] ──→ [Task B] ──→ [Task C] ──→ Result
```

**Use Case**: When each task depends on the previous one

### 3. Mixed Strategy

Combination of parallel and sequential:

```
        ┌─→ [Research A] ─┐
Root ──→│                 ├──→ [Analysis] ──→ [Report]
        └─→ [Research B] ─┘
```

## 🎯 Putting It All Together

Here's how these concepts work in practice:

1. **User submits goal** → Creates root TaskNode
2. **Atomizer checks complexity** → Determines PLAN vs EXECUTE
3. **Planner decomposes** → Creates subtask graph
4. **Scheduler activates tasks** → Based on dependencies
5. **Executors process** → Using specialized agents
6. **Context flows** → Between related tasks
7. **Results aggregate** → Bottom-up synthesis
8. **Final result emerges** → From hierarchical processing
