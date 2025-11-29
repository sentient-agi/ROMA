/**
 * @roma/llm - LLM Integration Layer
 *
 * Provides natural language to structured SaaS specification capabilities
 */

// Provider interfaces and base classes
export {
  BaseLlmProvider,
  type LlmProviderConfig,
  type LlmCallMetrics,
  type StructuredCompletionOptions,
  type TextCompletionOptions,
} from './providers/base-provider.js';

// HuggingFace provider implementation
export {
  HuggingFaceProvider,
  type HuggingFaceProviderConfig,
} from './providers/huggingface-provider.js';

// Provider routing and fallback
export {
  ProviderRouter,
  type ProviderRouterConfig,
} from './providers/provider-router.js';

// Confidence scoring
export {
  scoreConfidence,
  isConfident,
  isStrictlyConfident,
  type ConfidenceScore,
  type ConfidenceOptions,
} from './confidence.js';

// Safety guardrails
export {
  checkGuardrails,
  formatGuardrailError,
  type GuardrailResult,
} from './guardrails.js';
