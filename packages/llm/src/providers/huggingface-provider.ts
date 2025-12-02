/**
 * HuggingFace Inference API Provider
 *
 * Supports DeepSeek-R1, Grok-1, and other HF-hosted models
 */
import { z } from 'zod';
import {
  BaseLlmProvider,
  type LlmProviderConfig,
  type StructuredCompletionOptions,
  type TextCompletionOptions,
  type LlmCallMetrics,
} from './base-provider.js';

export interface HuggingFaceProviderConfig extends LlmProviderConfig {
  apiEndpoint?: string; // Optional custom endpoint
}

export class HuggingFaceProvider extends BaseLlmProvider {
  private apiEndpoint: string;

  constructor(config: HuggingFaceProviderConfig) {
    super(config);
    this.apiEndpoint =
      config.apiEndpoint ||
      `https://api-inference.huggingface.co/models/${config.model}`;
  }

  async completeStructured<T extends z.ZodTypeAny>(
    prompt: string,
    schema: T,
    options: StructuredCompletionOptions = {}
  ): Promise<z.infer<T>> {
    const maxRetries = options.maxRetries || 3;
    let lastError: Error | null = null;

    for (let attempt = 1; attempt <= maxRetries; attempt++) {
      try {
        const startTime = Date.now();

        // Build the prompt with schema instructions
        const fullPrompt = this.buildStructuredPrompt(prompt, schema, options);

        // Call HF API
        const response = await this.callHuggingFaceApi(fullPrompt, {
          temperature: options.temperature,
        });

        // Strip reasoning tags
        const cleaned = this.stripReasoningTags(response);

        // Extract JSON
        const jsonText = this.extractJson(cleaned);

        // Parse and validate
        const parsed = JSON.parse(jsonText);
        const validated = schema.parse(parsed);

        // Record metrics
        const latency = Date.now() - startTime;
        this.recordMetrics({
          provider: 'huggingface',
          model: this.config.model,
          promptTokens: this.estimateTokens(fullPrompt),
          completionTokens: this.estimateTokens(response),
          totalTokens:
            this.estimateTokens(fullPrompt) + this.estimateTokens(response),
          latencyMs: latency,
          timestamp: new Date().toISOString(),
          success: true,
        });

        return validated;
      } catch (error: any) {
        lastError = error;

        // Record failed attempt
        this.recordMetrics({
          provider: 'huggingface',
          model: this.config.model,
          promptTokens: 0,
          completionTokens: 0,
          totalTokens: 0,
          latencyMs: 0,
          timestamp: new Date().toISOString(),
          success: false,
          error: error.message,
        });

        if (attempt < maxRetries) {
          // Wait before retry (exponential backoff)
          await this.sleep(1000 * Math.pow(2, attempt - 1));
        }
      }
    }

    throw new Error(
      `Failed to get structured completion after ${maxRetries} attempts: ${lastError?.message}`
    );
  }

  async completeText(
    prompt: string,
    options: TextCompletionOptions = {}
  ): Promise<string> {
    const startTime = Date.now();

    // Build full prompt with system message
    const fullPrompt = options.systemPrompt
      ? `${options.systemPrompt}\n\n${prompt}`
      : prompt;

    // Call API
    const response = await this.callHuggingFaceApi(fullPrompt, {
      temperature: options.temperature,
      maxTokens: options.maxTokens,
    });

    // Strip reasoning tags
    const cleaned = this.stripReasoningTags(response);

    // Record metrics
    const latency = Date.now() - startTime;
    this.recordMetrics({
      provider: 'huggingface',
      model: this.config.model,
      promptTokens: this.estimateTokens(fullPrompt),
      completionTokens: this.estimateTokens(response),
      totalTokens:
        this.estimateTokens(fullPrompt) + this.estimateTokens(response),
      latencyMs: latency,
      timestamp: new Date().toISOString(),
      success: true,
    });

    return cleaned;
  }

  /**
   * Build a prompt that requests structured JSON output
   */
  private buildStructuredPrompt<T extends z.ZodTypeAny>(
    userPrompt: string,
    schema: T,
    options: StructuredCompletionOptions
  ): string {
    const systemPrompt =
      options.systemPrompt ||
      'You are a precise assistant that generates valid JSON matching the provided schema.';

    // Generate schema description from Zod schema
    const schemaDescription = this.describeSchema(schema);

    return `${systemPrompt}

User Request:
${userPrompt}

Required Output Schema:
${schemaDescription}

Instructions:
1. Generate a valid JSON object that strictly conforms to the schema above
2. Do NOT include any explanatory text, only the JSON object
3. Do NOT use placeholders like "TODO", "...", or "???" - provide concrete values
4. Ensure all required fields are populated
5. Return ONLY the JSON object, no markdown formatting

JSON Output:`;
  }

  /**
   * Describe a Zod schema in a human-readable format
   */
  private describeSchema(schema: z.ZodTypeAny): string {
    // For now, use JSON.stringify on the schema shape
    // In production, this would be more sophisticated
    try {
      const shape = (schema as any)._def;
      return `Schema type: ${shape.typeName}\n` + JSON.stringify(shape, null, 2);
    } catch {
      return 'Complex schema - ensure output is valid JSON conforming to the expected structure.';
    }
  }

  /**
   * Call HuggingFace Inference API
   */
  private async callHuggingFaceApi(
    prompt: string,
    options: { temperature?: number; maxTokens?: number } = {}
  ): Promise<string> {
    const timeout = this.config.timeout || 60000; // 60s default

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), timeout);

    try {
      const response = await fetch(this.apiEndpoint, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${this.config.apiKey}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          inputs: prompt,
          parameters: {
            max_new_tokens: options.maxTokens || this.config.maxTokens || 4096,
            temperature: options.temperature ?? this.config.temperature ?? 0.7,
            return_full_text: false,
          },
        }),
        signal: controller.signal,
      });

      clearTimeout(timeoutId);

      if (!response.ok) {
        const errorText = await response.text();
        throw new Error(
          `HuggingFace API error (${response.status}): ${errorText}`
        );
      }

      const data = await response.json() as any;

      // HF returns array of results
      if (Array.isArray(data) && data.length > 0) {
        return data[0].generated_text || data[0].text || '';
      }

      // Single result format
      if (data.generated_text) {
        return data.generated_text;
      }

      throw new Error('Unexpected HuggingFace API response format');
    } catch (error: any) {
      clearTimeout(timeoutId);
      if (error.name === 'AbortError') {
        throw new Error(`HuggingFace API timeout after ${timeout}ms`);
      }
      throw error;
    }
  }

  /**
   * Estimate token count (rough approximation: 1 token ≈ 4 characters)
   */
  private estimateTokens(text: string): number {
    return Math.ceil(text.length / 4);
  }

  /**
   * Record metrics
   */
  private recordMetrics(metrics: LlmCallMetrics): void {
    this.metrics.push(metrics);
  }

  /**
   * Sleep utility
   */
  private sleep(ms: number): Promise<void> {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }
}
