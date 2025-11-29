# @roma/llm

LLM Integration Layer for ROMA - Natural language to structured SaaS specifications.

## Overview

`@roma/llm` provides the foundational LLM abstraction layer for ROMA's natural language capabilities. It enables converting natural language prompts into validated, structured SaaS specifications (IntakeSchema, ArchitectureSchema, FeatureGraphSchema).

## Features

- 🔌 **Provider Abstraction** - Unified interface for multiple LLM providers
- 🔄 **Automatic Fallback** - Router with multi-provider failover
- 📊 **Structured Output** - Zod schema validation for generated JSON
- 🎯 **Confidence Scoring** - Heuristic-based quality assessment
- 🛡️ **Safety Guardrails** - Domain filtering and content safety
- 📈 **Metrics Tracking** - Token usage, latency, and provider breakdown

## Supported Providers

### HuggingFace Inference API (Default)

- **Primary:** DeepSeek-R1 (recommended)
- **Fallback:** Grok-1 or other HF models
- **Zero local GPU** - Uses serverless HF Inference API

## Setup

### 1. Get HuggingFace API Key

1. Go to [https://huggingface.co/settings/tokens](https://huggingface.co/settings/tokens)
2. Click "New token"
3. Set permissions to **Read** (inference only)
4. Copy your token (format: `hf_xxxxxxxxxxxxxxxxxxxxx`)

### 2. Configure Environment

Create or update `.env` in your project root:

```bash
# HuggingFace Inference API
HUGGINGFACE_API_KEY=hf_xxxxxxxxxxxxxxxxxxxxx

# Model IDs (optional - defaults shown)
HUGGINGFACE_PRIMARY_MODEL=deepseek-ai/DeepSeek-R1
HUGGINGFACE_FALLBACK_MODEL=xai-org/grok-1
```

### 3. Install Dependencies

```bash
pnpm install
```

## Usage

### Basic Structured Output

```typescript
import { HuggingFaceProvider } from '@roma/llm';
import { z } from 'zod';

// Create provider
const provider = new HuggingFaceProvider({
  apiKey: process.env.HUGGINGFACE_API_KEY!,
  model: 'deepseek-ai/DeepSeek-R1',
  maxTokens: 4096,
  temperature: 0.7,
});

// Define schema
const schema = z.object({
  appName: z.string(),
  description: z.string(),
  features: z.array(z.string()),
});

// Generate structured output
const result = await provider.completeStructured(
  'Build a todo list SaaS with user auth and cloud sync',
  schema
);

console.log(result);
// { appName: "TodoSync", description: "...", features: [...] }
```

### With Provider Routing (Fallback)

```typescript
import { ProviderRouter, HuggingFaceProvider } from '@roma/llm';

// Create multiple providers
const primaryProvider = new HuggingFaceProvider({
  apiKey: process.env.HUGGINGFACE_API_KEY!,
  model: 'deepseek-ai/DeepSeek-R1',
});

const fallbackProvider = new HuggingFaceProvider({
  apiKey: process.env.HUGGINGFACE_API_KEY!,
  model: 'xai-org/grok-1',
});

// Create router
const router = new ProviderRouter({
  providers: [primaryProvider, fallbackProvider],
  maxAttemptsPerProvider: 2,
});

// Use router (automatic fallback if primary fails)
const result = await router.completeStructured(prompt, schema);
```

### Confidence Scoring

```typescript
import { scoreConfidence, isConfident } from '@roma/llm';

const output = await provider.completeText('Generate a feature list');

// Check confidence
const confidence = scoreConfidence(output);
console.log(confidence);
// {
//   score: 0.95,
//   confident: true,
//   reasons: ['No confidence issues detected']
// }

// Quick check
if (!isConfident(output)) {
  console.log('Output needs clarification');
}
```

### Safety Guardrails

```typescript
import { checkGuardrails, formatGuardrailError } from '@roma/llm';

const prompt = 'Build a healthcare diagnosis SaaS';
const result = checkGuardrails(prompt);

if (!result.allowed) {
  console.error(formatGuardrailError(result));
  // ❌ Cannot generate SaaS for Healthcare/Medical.
  // Reason: ROMA does not support code generation for regulated domains...
}
```

## Model Configuration

### Recommended Models

#### DeepSeek-R1 (Primary)

```typescript
const provider = new HuggingFaceProvider({
  apiKey: process.env.HUGGINGFACE_API_KEY!,
  model: 'deepseek-ai/DeepSeek-R1',
  maxTokens: 4096,
  temperature: 0.7, // Adjust for creativity vs. precision
});
```

**Pros:**
- Strong reasoning capabilities
- Good JSON generation
- Handles complex schemas

**Notes:**
- Outputs `<think>...</think>` reasoning tags (auto-stripped)
- Best for planning and architecture generation

#### Grok-1 (Fallback)

```typescript
const provider = new HuggingFaceProvider({
  apiKey: process.env.HUGGINGFACE_API_KEY!,
  model: 'xai-org/grok-1',
  maxTokens: 4096,
  temperature: 0.6,
});
```

**Pros:**
- Fast inference
- Reliable fallback
- Good structured output

### Custom Models

You can use any HuggingFace model that supports text generation:

```typescript
const provider = new HuggingFaceProvider({
  apiKey: process.env.HUGGINGFACE_API_KEY!,
  model: 'meta-llama/Llama-3-70B-Instruct',
  apiEndpoint: 'https://api-inference.huggingface.co/models/meta-llama/Llama-3-70B-Instruct',
});
```

## Metrics and Monitoring

```typescript
// Get metrics from a provider
const metrics = provider.getMetrics();
console.log(metrics);
// [
//   {
//     provider: 'huggingface',
//     model: 'deepseek-ai/DeepSeek-R1',
//     promptTokens: 150,
//     completionTokens: 450,
//     totalTokens: 600,
//     latencyMs: 2341,
//     timestamp: '2025-11-29T...',
//     success: true
//   }
// ]

// Get summary from router
const summary = router.getMetricsSummary();
console.log(summary);
// {
//   totalCalls: 10,
//   successfulCalls: 9,
//   failedCalls: 1,
//   totalTokens: 45000,
//   averageLatencyMs: 1850,
//   providerBreakdown: {
//     'huggingface:deepseek-ai/DeepSeek-R1': 8,
//     'huggingface:xai-org/grok-1': 2
//   }
// }
```

## Error Handling

```typescript
try {
  const result = await provider.completeStructured(prompt, schema, {
    maxRetries: 3, // Retry up to 3 times
    timeout: 30000, // 30 second timeout
  });
} catch (error) {
  console.error('LLM call failed:', error.message);
  // Handle: rate limits, timeouts, validation errors
}
```

## Supported Domains

### ✅ Allowed (Green-list)

- Productivity tools
- Developer tools
- Entertainment
- Education (non-children)
- E-commerce
- Social platforms
- IoT/Smart home
- Content management
- Marketing/Analytics

### ❌ Blacklisted

- Healthcare/Medical services
- Legal services
- Financial services & banking
- Cryptocurrency/Blockchain
- Gambling/Betting platforms
- Children's content (<13)
- Government-regulated services

## API Reference

### `BaseLlmProvider`

Abstract base class for all LLM providers.

**Methods:**
- `completeStructured<T>(prompt, schema, options): Promise<T>` - Generate structured output
- `completeText(prompt, options): Promise<string>` - Generate text
- `getMetrics(): LlmCallMetrics[]` - Get call history
- `getTotalTokens(): number` - Get total token count
- `resetMetrics(): void` - Clear metrics

### `HuggingFaceProvider`

HuggingFace Inference API implementation.

**Config:**
```typescript
interface HuggingFaceProviderConfig {
  apiKey: string; // HF API token
  model: string; // Model ID (e.g., 'deepseek-ai/DeepSeek-R1')
  apiEndpoint?: string; // Custom endpoint (optional)
  maxTokens?: number; // Default: 4096
  temperature?: number; // Default: 0.7
  timeout?: number; // Default: 30000ms
}
```

### `ProviderRouter`

Multi-provider routing with automatic fallback.

**Config:**
```typescript
interface ProviderRouterConfig {
  providers: BaseLlmProvider[]; // List of providers (tried in order)
  maxAttemptsPerProvider?: number; // Default: 2
}
```

### Confidence Scoring

```typescript
function scoreConfidence(
  output: string,
  options?: ConfidenceOptions
): ConfidenceScore;

function isConfident(output: string, threshold?: number): boolean;

function isStrictlyConfident(output: string): boolean;
```

### Guardrails

```typescript
function checkGuardrails(prompt: string): GuardrailResult;

function formatGuardrailError(result: GuardrailResult): string;
```

## Development

### Build

```bash
pnpm build
```

### Test

```bash
pnpm test
```

### Run Evaluation

```bash
pnpm eval
```

## License

MIT
