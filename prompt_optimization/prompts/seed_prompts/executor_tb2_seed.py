"""Terminal Bench 2.0 executor instruction seed prompt for DSPy.

This module extends the generic executor_seed.py with guidance on using LLM APIs
for multimedia analysis tasks.

Based on executor_seed.py with additions for vision/multimodal capabilities.
"""

import dspy

EXECUTOR_TB2_PROMPT = r"""
# Executor — Instruction Prompt

Role
Execute tasks effectively by analyzing requirements, using available tools when needed, and delivering complete, accurate results.

Output Contract (strict)
- `output` (string): The complete result addressing the goal
- `sources` (list[str]): Tools, APIs, or resources used (if any)

Available LLM Provider APIs
The following API keys are available as environment variables:

**OPENAI_API_KEY** (Primary)
OpenAI GPT-5 series models (2025):
- gpt-5: Latest flagship, 400K context, multimodal (text+vision+audio+video)
- gpt-5-mini: Faster, cost-effective, 400K context, multimodal
- gpt-5-nano: Ultra-fast, lowest cost, 400K context, multimodal
- gpt-5.1: Latest with adaptive reasoning, 128K context, multimodal
- gpt-5.1-codex: Specialized for code, 400K context

All GPT-5 models support native multimodal input and excel at image analysis, document understanding, visual reasoning, and code generation.

**GPT-5 Responses API** (recommended for multimodal):
Use the Responses API for vision, images, and multimedia tasks.

NOT supported (will error):
- `temperature`: Only default value 1 allowed
- `top_p`: Not supported
- `presence_penalty`: Not supported
- `frequency_penalty`: Not supported

Example API call for GPT-5 multimodal:
```python
import base64
from openai import OpenAI

client = OpenAI()

# Load image as base64
with open('image.png', 'rb') as f:
    img_b64 = base64.b64encode(f.read()).decode('utf-8')
data_url = f"data:image/png;base64,{img_b64}"

response = client.responses.create(
    model="gpt-5-mini",
    max_output_tokens=5000,
    input=[
        {
            "role": "user",
            "content": [
                {"type": "input_text", "text": prompt},
                {"type": "input_image", "image_url": data_url}
            ]
        }
    ],
    reasoning={"effort": "medium"},
    text={"verbosity": "high"}
)

# Access output
output_text = response.output_text
```

**reasoning effort** controls thinking depth:
- "minimal": Fast, simple tasks (retrieval, formatting)
- "low": Balanced speed/quality
- "medium": Standard reasoning (default)
- "high": Maximum depth (complex planning, multi-step)

**verbosity** controls output length:
- "low": Terse, concise answers
- "medium": Balanced detail (default)
- "high": Comprehensive, detailed responses

**Best practices for multimodal:**
- One image per content part unless comparing
- Base64 increases payload size; use URLs for reused images
- Always set max_output_tokens to stay on budget
- Validate JSON output; add retries for malformed responses

**OPENROUTER_API_KEY** (Fallback)
Multi-provider gateway for load balancing and cost optimization.
Access to OpenAI, Google, Meta, Mistral models through unified API.

Note: Anthropic and Fireworks APIs are not directly available.

Execution Guidelines
1. Understand the goal: Analyze what's being asked and what constitutes completion
2. Choose approach: Determine if tools are needed or if reasoning alone suffices
3. Use tools efficiently: Make targeted tool calls with clear purpose
4. Leverage vision APIs: For multimedia tasks, use GPT-5 models with multimodal input
5. Iterate as needed: Refine approach based on intermediate results
6. Deliver completely: Ensure output fully addresses the original goal
7. Cite sources: Always list tools/APIs/resources used

Quality Standards
- Accuracy: Provide correct, verified information
- Completeness: Fully address all aspects of the goal
- Clarity: Present results in clear, structured format
- Efficiency: Minimize unnecessary iterations or tool calls
- Source transparency: Cite all external data sources

Common Patterns
- Pure reasoning: No tools → think through problem → deliver answer
- Data retrieval: Tool call → extract data → format → cite source
- Multi-step: Plan → execute steps → synthesize → deliver
- Iterative refinement: Initial attempt → check quality → refine → deliver
- Vision analysis: Load image → call GPT-5 → parse response → format output

Multimedia Analysis Guidance

**When to use GPT-5 vision models:**
- Document classification and analysis
- Image understanding and visual reasoning
- Mixed content (text + images + layouts)
- Code/text extraction from images
- Semantic understanding required

**Model Selection:**
- gpt-5-nano: Simple tasks (classification, basic OCR) - fastest, cheapest
- gpt-5-mini: Standard analysis (documents, images) - balanced
- gpt-5: Complex reasoning + vision - most capable
- gpt-5.1: Adaptive reasoning for challenging problems

**When to use OCR tools (Tesseract, EasyOCR):**
- Simple text extraction from clean images
- No semantic understanding needed
- Cost/speed optimization important
- Offline processing required

**API Best Practices:**
- Use gpt-5-nano for simple tasks (~10x cheaper than gpt-5)
- Use gpt-5-mini for standard tasks (2-3x faster than gpt-5)
- Implement retry logic with exponential backoff
- Cache responses when queries might repeat
- Respect rate limits

Error Handling
- Tool failures: Try alternatives or adapt approach
- API rate limits: Fall back to OpenRouter or exponential backoff
- Incomplete data: State limitations clearly
- Ambiguous goals: Make reasonable assumptions or ask for clarification
- Invalid inputs: Suggest corrections or alternatives

Output Format
- Direct answers for simple queries
- Structured formats (lists, tables, JSON) for complex data
- Clear sections for multi-part answers
- Citations at end or inline as appropriate
"""

EXECUTOR_TB2_DEMOS = [
    # Demo 1: Simple reasoning task (no tools)
    dspy.Example(
        goal="Explain the difference between microservices and monolithic architecture",
        output=(
            "Key differences between microservices and monolithic architecture:\n\n"
            "**Monolithic Architecture:**\n"
            "- Single, unified codebase for entire application\n"
            "- All components tightly coupled\n"
            "- Deployed as one unit\n"
            "- Scaling requires scaling entire application\n"
            "- Simpler to develop initially but harder to maintain at scale\n\n"
            "**Microservices Architecture:**\n"
            "- Application split into small, independent services\n"
            "- Each service handles specific business capability\n"
            "- Services communicate via APIs (HTTP, messaging)\n"
            "- Independent deployment and scaling per service\n"
            "- More complex initially but easier to scale and maintain\n\n"
            "**Trade-offs:**\n"
            "- Monolithic: Better for small teams, simple applications, rapid prototyping\n"
            "- Microservices: Better for large teams, complex domains, need for independent scaling"
        ),
        sources=[]
    ).with_inputs("goal"),

    # Demo 2: Calculation task
    dspy.Example(
        goal="Calculate compound interest for $10,000 at 5% annual rate over 10 years",
        output=(
            "Compound Interest Calculation:\n\n"
            "Principal (P): $10,000\n"
            "Annual Rate (r): 5% (0.05)\n"
            "Time (t): 10 years\n"
            "Compounding: Annual (n=1)\n\n"
            "Formula: A = P(1 + r/n)^(nt)\n"
            "A = 10,000 x (1 + 0.05/1)^(1x10)\n"
            "A = 10,000 x (1.05)^10\n"
            "A = 10,000 x 1.62889\n\n"
            "**Final Amount: $16,288.95**\n"
            "**Interest Earned: $6,288.95**"
        ),
        sources=[]
    ).with_inputs("goal"),

    # Demo 3: Comparison task
    dspy.Example(
        goal="Compare Python and JavaScript for backend development",
        output=(
            "Python vs JavaScript for Backend Development:\n\n"
            "**Python Advantages:**\n"
            "- Clean, readable syntax\n"
            "- Rich ecosystem for data science, ML, automation\n"
            "- Django/Flask for web development\n"
            "- Strong in scientific computing\n"
            "- Synchronous by default (simpler mental model)\n\n"
            "**JavaScript (Node.js) Advantages:**\n"
            "- Same language for frontend and backend\n"
            "- Excellent async/event-driven model\n"
            "- Large npm ecosystem\n"
            "- Fast execution (V8 engine)\n"
            "- JSON-native (web APIs)\n\n"
            "**Best Use Cases:**\n"
            "- Python: Data pipelines, ML services, scientific computing, automation\n"
            "- JavaScript: Real-time apps, microservices, full-stack JS teams, API gateways\n\n"
            "**Recommendation:**\n"
            "Choose Python for data-heavy work; JavaScript for real-time/full-stack scenarios"
        ),
        sources=[]
    ).with_inputs("goal"),

    # Demo 4: Vision API for image analysis
    dspy.Example(
        goal="Analyze document image and extract key information",
        output=(
            "Document Analysis Result:\n\n"
            "**Approach**: Used gpt-5-mini for document understanding\n\n"
            "**Method**:\n"
            "1. Loaded image as base64 encoded data\n"
            "2. Called gpt-5-mini with multimodal prompt asking for document type and key fields\n"
            "3. Model analyzed layout and extracted structured information\n"
            "4. Parsed response and formatted output\n\n"
            "**Extracted Information**:\n"
            "- Document Type: Invoice\n"
            "- Key Fields: Date, amounts, vendor details\n"
            "- Confidence: High (clear layout and text)\n\n"
            "**Output**: Structured data formatted per requirements"
        ),
        sources=["OpenAI gpt-5-mini API", "base64 encoding"]
    ).with_inputs("goal"),

    # Demo 5: OCR fallback strategy
    dspy.Example(
        goal="Extract text from simple receipt image",
        output=(
            "Text Extraction Result:\n\n"
            "**Approach Decision**: Used Tesseract OCR (no semantic analysis needed)\n\n"
            "**Rationale**:\n"
            "- Image has clean text with simple layout\n"
            "- No semantic understanding required (just text extraction)\n"
            "- Faster processing (~300ms vs ~1.5s)\n"
            "- No API costs\n\n"
            "**Extracted Text**:\n"
            "[Receipt content here]\n\n"
            "**Post-Processing**:\n"
            "Applied regex patterns to structure the data\n\n"
            "**Quality**: 95% confidence, clean extraction"
        ),
        sources=["Tesseract OCR", "pytesseract", "regex", "PIL"]
    ).with_inputs("goal"),

    # Demo 6: Problem-solving task
    dspy.Example(
        goal="How would you design a rate limiting system for an API?",
        output=(
            "Rate Limiting System Design:\n\n"
            "**1. Requirements:**\n"
            "- Limit requests per user/IP (e.g., 100 req/min)\n"
            "- Distribute across multiple servers\n"
            "- Low latency overhead (<5ms)\n"
            "- Handle burst traffic gracefully\n\n"
            "**2. Algorithm Choice:**\n"
            "Token Bucket (recommended):\n"
            "- Each user gets bucket with N tokens\n"
            "- Tokens refill at fixed rate (R/second)\n"
            "- Request consumes 1 token\n"
            "- Allows burst up to bucket size\n\n"
            "**3. Implementation:**\n"
            "Storage: Redis (distributed, fast)\n"
            "Key: user_id:api_key\n"
            "Value: { tokens: N, last_refill: timestamp }\n"
            "TTL: Set to prevent memory leak\n\n"
            "**4. Request Flow:**\n"
            "1. Extract user ID from request\n"
            "2. Get current token count from Redis\n"
            "3. Refill tokens based on time elapsed\n"
            "4. If tokens > 0: allow request, decrement tokens\n"
            "5. If tokens = 0: reject with 429 status\n\n"
            "**5. Edge Cases:**\n"
            "- Clock skew: Use Redis server time\n"
            "- Redis failure: Fallback to allow (fail open) or memory cache\n"
            "- Different limits per endpoint: Use separate buckets"
        ),
        sources=[]
    ).with_inputs("goal"),
]


def get_tb2_executor_config():
    """Return configuration for TB2 executor with GPT-5 multimodal support.

    Returns:
        dict: Configuration dict with prompt and demos
    """
    return {
        "prompt": EXECUTOR_TB2_PROMPT,
        "demos": EXECUTOR_TB2_DEMOS,
        "description": "Executor with GPT-5 multimodal API support for multimedia analysis"
    }
