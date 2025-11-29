#!/usr/bin/env node
/**
 * LLM Evaluation CLI - Run evaluation harness on test prompts
 */

import {
  HuggingFaceProvider,
  ProviderRouter,
  EvaluationHarness,
  formatEvalSummary,
  TEST_PROMPTS,
  getPromptsByDifficulty,
  getRandomSample,
} from '@roma/llm';
import { writeFileSync } from 'fs';
import { join } from 'path';

async function main() {
  const args = process.argv.slice(2);

  console.log('╔════════════════════════════════════════════════════════════╗');
  console.log('║  ROMA LLM Evaluation Harness                               ║');
  console.log('╚════════════════════════════════════════════════════════════╝\n');

  // Parse arguments
  const mode = args[0] || 'quick';
  const validModes = ['quick', 'medium', 'full', 'simple', 'complex'];

  if (!validModes.includes(mode)) {
    console.error(`Invalid mode: ${mode}\n`);
    console.log('USAGE:');
    console.log('  pnpm roma:eval [mode]\n');
    console.log('MODES:');
    console.log('  quick    - Test 3 random prompts (fast)');
    console.log('  medium   - Test 5 random prompts');
    console.log('  full     - Test all prompts (slow)');
    console.log('  simple   - Test only simple prompts');
    console.log('  complex  - Test only complex prompts\n');
    console.log('ENVIRONMENT VARIABLES:');
    console.log('  HUGGINGFACE_API_KEY         Required: Your HuggingFace API token');
    console.log('  HUGGINGFACE_PRIMARY_MODEL   Optional: Primary model (default: deepseek-ai/DeepSeek-R1)');
    console.log('  HUGGINGFACE_FALLBACK_MODEL  Optional: Fallback model (default: xai-org/grok-1)');
    console.log('  ROMA_VERBOSE                Optional: Enable verbose logging (1 or true)');
    console.log('  ROMA_SKIP_CLARIFICATION     Optional: Skip clarification turns (1 or true)\n');
    process.exit(1);
  }

  // Check for API key
  const apiKey = process.env.HUGGINGFACE_API_KEY;
  if (!apiKey) {
    console.error('❌ ERROR: HUGGINGFACE_API_KEY environment variable not set');
    console.error('\nGet your API key from: https://huggingface.co/settings/tokens');
    console.error('Then set it: export HUGGINGFACE_API_KEY=hf_xxxxxxxxxxxxx\n');
    process.exit(1);
  }

  const verbose = process.env.ROMA_VERBOSE === '1' || process.env.ROMA_VERBOSE === 'true';
  const skipClarification = process.env.ROMA_SKIP_CLARIFICATION === '1' || process.env.ROMA_SKIP_CLARIFICATION === 'true';

  const primaryModel = process.env.HUGGINGFACE_PRIMARY_MODEL || 'deepseek-ai/DeepSeek-R1';
  const fallbackModel = process.env.HUGGINGFACE_FALLBACK_MODEL || 'xai-org/grok-1';

  // Select prompts based on mode
  let prompts;
  switch (mode) {
    case 'quick':
      prompts = getRandomSample(3);
      break;
    case 'medium':
      prompts = getRandomSample(5);
      break;
    case 'full':
      prompts = TEST_PROMPTS;
      break;
    case 'simple':
      prompts = getPromptsByDifficulty('simple');
      break;
    case 'complex':
      prompts = getPromptsByDifficulty('complex');
      break;
    default:
      prompts = getRandomSample(3);
  }

  console.log('⚙️  Configuration:');
  console.log(`   Mode: ${mode}`);
  console.log(`   Prompts: ${prompts.length}`);
  console.log(`   Primary Model: ${primaryModel}`);
  console.log(`   Fallback Model: ${fallbackModel}`);
  console.log(`   Verbose: ${verbose}`);
  console.log(`   Skip Clarification: ${skipClarification}\n`);

  try {
    // Create LLM providers
    console.log('🔌 Initializing LLM providers...');

    const primaryProvider = new HuggingFaceProvider({
      apiKey,
      model: primaryModel,
      maxTokens: 4096,
      temperature: 0.7,
    });

    const fallbackProvider = new HuggingFaceProvider({
      apiKey,
      model: fallbackModel,
      maxTokens: 4096,
      temperature: 0.7,
    });

    // Create router with fallback
    const router = new ProviderRouter({
      providers: [primaryProvider, primaryProvider, fallbackProvider],
      maxAttemptsPerProvider: 2,
    });

    console.log('✅ Providers initialized\n');

    // Create evaluation harness
    console.log('🧪 Creating evaluation harness...');
    const harness = new EvaluationHarness({
      provider: router,
      prompts,
      verbose,
      skipClarification,
      confidenceThreshold: 0.85,
    });

    console.log('✅ Harness ready\n');

    // Run evaluation
    console.log('🚀 Starting evaluation...\n');
    console.log('='.repeat(60) + '\n');

    const startTime = Date.now();
    const summary = await harness.runEvaluation();
    const duration = Date.now() - startTime;

    // Display summary
    console.log(formatEvalSummary(summary));

    // Save results to file
    const outputPath = join(process.cwd(), 'eval-results.json');
    writeFileSync(outputPath, JSON.stringify(summary, null, 2));
    console.log(`\n📄 Results saved to: ${outputPath}\n`);

    // Display key metrics
    console.log('🎯 KEY METRICS:');
    console.log(`   Success Rate:  ${summary.endToEndValidityRate.toFixed(1)}%`);
    console.log(`   Avg Tokens:    ${Math.round(summary.avgTokensPerPrompt).toLocaleString()}`);
    console.log(`   Avg Latency:   ${Math.round(summary.avgLatencyMs)}ms`);
    console.log(`   Duration:      ${Math.round(duration / 1000)}s\n`);

    // Success/failure
    const successRate = summary.endToEndValidityRate;
    if (successRate >= 90) {
      console.log('✅ EXCELLENT: Success rate >= 90%');
    } else if (successRate >= 75) {
      console.log('✓ GOOD: Success rate >= 75%');
    } else if (successRate >= 50) {
      console.log('⚠️  FAIR: Success rate >= 50%');
    } else {
      console.log('❌ POOR: Success rate < 50%');
    }

    console.log('\n' + '='.repeat(60));
    console.log('🎉 Evaluation completed!');
    console.log('='.repeat(60));

    process.exit(successRate >= 50 ? 0 : 1);
  } catch (error) {
    console.error('\n❌ Fatal error:', error);

    if (error instanceof Error) {
      console.error('\nStack trace:');
      console.error(error.stack);
    }

    process.exit(1);
  }
}

main().catch((error) => {
  console.error('Unhandled error:', error);
  process.exit(1);
});
