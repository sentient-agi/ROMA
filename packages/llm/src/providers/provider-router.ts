/**
 * Provider Router - Handles routing and fallback across multiple LLM providers
 */
import { z } from 'zod';
import type {
  BaseLlmProvider,
  StructuredCompletionOptions,
  TextCompletionOptions,
  LlmCallMetrics,
} from './base-provider.js';

export interface ProviderRouterConfig {
  providers: BaseLlmProvider[];
  maxAttemptsPerProvider?: number;
}

export class ProviderRouter {
  private providers: BaseLlmProvider[];
  private maxAttemptsPerProvider: number;
  private currentProviderIndex: number = 0;

  constructor(config: ProviderRouterConfig) {
    if (config.providers.length === 0) {
      throw new Error('ProviderRouter requires at least one provider');
    }

    this.providers = config.providers;
    this.maxAttemptsPerProvider = config.maxAttemptsPerProvider || 2;
  }

  /**
   * Complete with structured output, trying providers in order with fallback
   */
  async completeStructured<T extends z.ZodTypeAny>(
    prompt: string,
    schema: T,
    options: StructuredCompletionOptions = {}
  ): Promise<z.infer<T>> {
    const errors: Array<{ provider: number; error: Error }> = [];

    for (let i = 0; i < this.providers.length; i++) {
      const provider = this.providers[i];

      try {
        const result = await provider.completeStructured(prompt, schema, {
          ...options,
          maxRetries: this.maxAttemptsPerProvider,
        });

        // Success - reset to primary provider for next call
        this.currentProviderIndex = 0;

        return result;
      } catch (error: any) {
        errors.push({ provider: i, error });

        // If this wasn't the last provider, log and continue to next
        if (i < this.providers.length - 1) {
          console.warn(
            `[ProviderRouter] Provider ${i} failed, trying next: ${error.message}`
          );
        }
      }
    }

    // All providers failed
    const errorSummary = errors
      .map((e) => `Provider ${e.provider}: ${e.error.message}`)
      .join('; ');

    throw new Error(
      `All ${this.providers.length} providers failed. Errors: ${errorSummary}`
    );
  }

  /**
   * Complete with text output, trying providers in order with fallback
   */
  async completeText(
    prompt: string,
    options: TextCompletionOptions = {}
  ): Promise<string> {
    const errors: Array<{ provider: number; error: Error }> = [];

    for (let i = 0; i < this.providers.length; i++) {
      const provider = this.providers[i];

      try {
        const result = await provider.completeText(prompt, options);

        // Success - reset to primary provider for next call
        this.currentProviderIndex = 0;

        return result;
      } catch (error: any) {
        errors.push({ provider: i, error });

        // If this wasn't the last provider, log and continue to next
        if (i < this.providers.length - 1) {
          console.warn(
            `[ProviderRouter] Provider ${i} failed, trying next: ${error.message}`
          );
        }
      }
    }

    // All providers failed
    const errorSummary = errors
      .map((e) => `Provider ${e.provider}: ${e.error.message}`)
      .join('; ');

    throw new Error(
      `All ${this.providers.length} providers failed. Errors: ${errorSummary}`
    );
  }

  /**
   * Get combined metrics from all providers
   */
  getAllMetrics(): LlmCallMetrics[] {
    return this.providers.flatMap((p) => p.getMetrics());
  }

  /**
   * Get total tokens across all providers
   */
  getTotalTokens(): number {
    return this.providers.reduce((sum, p) => sum + p.getTotalTokens(), 0);
  }

  /**
   * Get metrics summary
   */
  getMetricsSummary(): {
    totalCalls: number;
    successfulCalls: number;
    failedCalls: number;
    totalTokens: number;
    averageLatencyMs: number;
    providerBreakdown: Record<string, number>;
  } {
    const allMetrics = this.getAllMetrics();

    const summary = {
      totalCalls: allMetrics.length,
      successfulCalls: allMetrics.filter((m) => m.success).length,
      failedCalls: allMetrics.filter((m) => !m.success).length,
      totalTokens: allMetrics.reduce((sum, m) => sum + m.totalTokens, 0),
      averageLatencyMs:
        allMetrics.length > 0
          ? allMetrics.reduce((sum, m) => sum + m.latencyMs, 0) /
            allMetrics.length
          : 0,
      providerBreakdown: {} as Record<string, number>,
    };

    // Count calls per provider
    allMetrics.forEach((m) => {
      const key = `${m.provider}:${m.model}`;
      summary.providerBreakdown[key] =
        (summary.providerBreakdown[key] || 0) + 1;
    });

    return summary;
  }

  /**
   * Reset metrics for all providers
   */
  resetAllMetrics(): void {
    this.providers.forEach((p) => p.resetMetrics());
  }
}
