/**
 * Base LLM Provider Interface
 *
 * Abstraction for structured and text completions across different LLM providers
 */
import { z } from 'zod';

export interface LlmCallMetrics {
  provider: string;
  model: string;
  promptTokens: number;
  completionTokens: number;
  totalTokens: number;
  latencyMs: number;
  timestamp: string;
  success: boolean;
  error?: string;
}

export interface LlmProviderConfig {
  apiKey: string;
  model: string;
  maxTokens?: number;
  temperature?: number;
  timeout?: number;
}

export interface StructuredCompletionOptions {
  maxRetries?: number;
  temperature?: number;
  systemPrompt?: string;
}

export interface TextCompletionOptions {
  maxTokens?: number;
  temperature?: number;
  systemPrompt?: string;
}

export abstract class BaseLlmProvider {
  protected config: LlmProviderConfig;
  protected metrics: LlmCallMetrics[] = [];

  constructor(config: LlmProviderConfig) {
    this.config = config;
  }

  /**
   * Complete with structured output conforming to a Zod schema
   */
  abstract completeStructured<T extends z.ZodTypeAny>(
    prompt: string,
    schema: T,
    options?: StructuredCompletionOptions
  ): Promise<z.infer<T>>;

  /**
   * Complete with text output
   */
  abstract completeText(
    prompt: string,
    options?: TextCompletionOptions
  ): Promise<string>;

  /**
   * Get metrics for all calls made by this provider
   */
  getMetrics(): LlmCallMetrics[] {
    return this.metrics;
  }

  /**
   * Get total tokens used
   */
  getTotalTokens(): number {
    return this.metrics.reduce((sum, m) => sum + m.totalTokens, 0);
  }

  /**
   * Get average latency
   */
  getAverageLatency(): number {
    if (this.metrics.length === 0) return 0;
    const total = this.metrics.reduce((sum, m) => sum + m.latencyMs, 0);
    return total / this.metrics.length;
  }

  /**
   * Reset metrics
   */
  resetMetrics(): void {
    this.metrics = [];
  }

  /**
   * Strip reasoning tags from model output (e.g., <think>...</think>)
   */
  protected stripReasoningTags(text: string): string {
    // Remove <think>...</think> tags
    text = text.replace(/<think>[\s\S]*?<\/think>/gi, '');

    // Remove <thinking>...</thinking> tags
    text = text.replace(/<thinking>[\s\S]*?<\/thinking>/gi, '');

    // Remove any remaining tags
    text = text.replace(/<\/?[^>]+(>|$)/g, '');

    return text.trim();
  }

  /**
   * Extract JSON from text (handles markdown code blocks)
   */
  protected extractJson(text: string): string {
    // Try to find JSON in markdown code block
    const codeBlockMatch = text.match(/```(?:json)?\s*\n?([\s\S]*?)\n?```/);
    if (codeBlockMatch) {
      return codeBlockMatch[1].trim();
    }

    // Try to find JSON object directly
    const jsonMatch = text.match(/\{[\s\S]*\}/);
    if (jsonMatch) {
      return jsonMatch[0];
    }

    return text;
  }
}
