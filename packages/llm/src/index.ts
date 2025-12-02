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

// LLM-backed builders
export {
  LlmIntakeBuilder,
  type LlmIntakeBuilderConfig,
  type IntakeBuilderOptions,
  type IntakeBuilderResult,
  type ClarificationRequest,
} from './builders/llm-intake-builder.js';

export {
  LlmArchitectureBuilder,
  type LlmArchitectureBuilderConfig,
  type ArchitectureBuilderOptions,
  type ArchitectureBuilderResult,
} from './builders/llm-architecture-builder.js';

export {
  LlmFeatureGraphBuilder,
  type LlmFeatureGraphBuilderConfig,
  type FeatureGraphBuilderOptions,
  type FeatureGraphBuilderResult,
} from './builders/llm-feature-graph-builder.js';

// ROMA integration
export {
  LlmBuilderInterface,
  createLlmBuilderInterface,
  type LlmBuilderInterfaceConfig,
} from './integration/llm-builder-interface.js';

// Evaluation and testing
export {
  EvaluationHarness,
  formatEvalSummary,
  type EvalConfig,
  type PromptEvalResult,
  type EvalSummary,
} from './evaluation/eval-harness.js';

export {
  TEST_PROMPTS,
  getPromptsByDifficulty,
  getPromptsByCategory,
  getPromptById,
  getRandomSample,
  type TestPrompt,
} from './evaluation/test-prompts.js';
