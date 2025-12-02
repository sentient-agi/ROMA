#!/usr/bin/env node
/**
 * Build from Natural Language - ROMA + LLM Integration
 *
 * Accepts natural language SaaS descriptions and generates complete applications
 */

import { ROMA } from '@roma/core';
import { HuggingFaceProvider, ProviderRouter, createLlmBuilderInterface } from '@roma/llm';
import { SaaSBuilder } from '@roma/builder';

async function main() {
  const args = process.argv.slice(2);
  const description = args[0];

  if (!description) {
    console.error(`
╔════════════════════════════════════════════════════════════╗
║  ROMA Natural Language Builder                             ║
╚════════════════════════════════════════════════════════════╝

ERROR: No description provided

USAGE:
  pnpm roma:build "<description>"

EXAMPLES:
  pnpm roma:build "Build a daily history SaaS with auth, billing, and favorites"
  pnpm roma:build "Create a todo list app with user accounts and cloud sync"

ENVIRONMENT VARIABLES:
  HUGGINGFACE_API_KEY         Required: Your HuggingFace API token
  HUGGINGFACE_PRIMARY_MODEL   Optional: Primary model (default: deepseek-ai/DeepSeek-R1)
  HUGGINGFACE_FALLBACK_MODEL  Optional: Fallback model (default: xai-org/grok-1)
  ROMA_VERBOSE                Optional: Enable verbose logging (1 or true)
  ROMA_DRY_RUN                Optional: Dry run mode (1 or true)
  ROMA_SKIP_CLARIFICATION     Optional: Skip clarification turns (1 or true)

SETUP:
  1. Get a HuggingFace API key: https://huggingface.co/settings/tokens
  2. Set HUGGINGFACE_API_KEY environment variable
  3. Run: pnpm roma:build "your SaaS description"

For more information, see packages/llm/README.md
`);
    process.exit(1);
  }

  console.log('╔════════════════════════════════════════════════════════════╗');
  console.log('║  ROMA Multi-Agent SaaS Builder - Natural Language Mode    ║');
  console.log('╚════════════════════════════════════════════════════════════╝\n');

  // Check for required environment variables
  const apiKey = process.env.HUGGINGFACE_API_KEY;
  if (!apiKey) {
    console.error('❌ ERROR: HUGGINGFACE_API_KEY environment variable not set');
    console.error('\nGet your API key from: https://huggingface.co/settings/tokens');
    console.error('Then set it: export HUGGINGFACE_API_KEY=hf_xxxxxxxxxxxxx\n');
    process.exit(1);
  }

  const verbose = process.env.ROMA_VERBOSE === '1' || process.env.ROMA_VERBOSE === 'true';
  const dryRun = process.env.ROMA_DRY_RUN === '1' || process.env.ROMA_DRY_RUN === 'true';
  const skipClarification = process.env.ROMA_SKIP_CLARIFICATION === '1' || process.env.ROMA_SKIP_CLARIFICATION === 'true';

  const primaryModel = process.env.HUGGINGFACE_PRIMARY_MODEL || 'deepseek-ai/DeepSeek-R1';
  const fallbackModel = process.env.HUGGINGFACE_FALLBACK_MODEL || 'xai-org/grok-1';

  try {
    console.log('📝 Input:');
    console.log(`   "${description}"\n`);

    console.log('⚙️  Configuration:');
    console.log(`   Primary Model: ${primaryModel}`);
    console.log(`   Fallback Model: ${fallbackModel}`);
    console.log(`   Verbose: ${verbose}`);
    console.log(`   Dry Run: ${dryRun}`);
    console.log(`   Skip Clarification: ${skipClarification}\n`);

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

    // Create LLM-backed builder interface
    console.log('🤖 Creating LLM builder interface...');
    const llmBuilder = createLlmBuilderInterface({
      provider: router,
      verbose,
      confidenceThreshold: 0.85,
      maxClarificationTurns: 10,
    });

    // Also create standard builder for scaffolding
    const saasBuilder = new SaaSBuilder();

    // Merge builder interfaces
    const builderInterface = {
      intake: llmBuilder.intake,
      architecture: llmBuilder.architecture,
      featureGraph: llmBuilder.featureGraph,
      scaffolding: saasBuilder.scaffolding.bind(saasBuilder),
    };

    console.log('✅ Builder interface ready\n');

    // Initialize ROMA
    console.log('🚀 Initializing ROMA...');
    const roma = new ROMA({
      verbose,
      dryRun,
      builderInterface,
    });
    console.log('✅ ROMA initialized\n');

    // Run ROMA solve with natural language input
    console.log('⚡ Starting ROMA solve...\n');
    console.log('='.repeat(60));
    console.log('\n');

    const result = await roma.solve(description, {
      goal: description,
      skipClarification,
    });

    console.log('\n');
    console.log('='.repeat(60));
    console.log('📊 EXECUTION RESULTS');
    console.log('='.repeat(60) + '\n');

    // Display results
    if (result.success) {
      console.log('✅ SUCCESS: All tasks completed successfully\n');

      if (result.atomization) {
        console.log('🔍 Atomization:');
        console.log(`   Type: ${result.atomization.isAtomic ? 'Atomic' : 'Composite'}`);
        console.log(`   Task Type: ${result.atomization.taskType || 'N/A'}`);
        console.log(`   Reasoning: ${result.atomization.reasoning}\n`);
      }

      if (result.execution) {
        console.log('⏱️  Execution:');
        console.log(`   Duration: ${result.execution.duration}ms`);
        console.log(`   Tasks: ${result.execution.results.length}`);
        console.log(`   Success Rate: ${result.execution.results.filter((r) => r.success).length}/${result.execution.results.length}\n`);
      }

      if (result.aggregation) {
        console.log('📦 Artifacts Generated:');
        const artifactKeys = Object.keys(result.aggregation.artifacts);
        for (const key of artifactKeys) {
          console.log(`   ✓ ${key}`);
        }
        console.log('');

        if (result.aggregation.recommendations && result.aggregation.recommendations.length > 0) {
          console.log('💡 Recommendations:');
          for (const rec of result.aggregation.recommendations) {
            console.log(`   • ${rec}`);
          }
          console.log('');
        }
      }

      if (result.verification) {
        console.log('✓ Verification:');
        console.log(`   Status: ${result.verification.passed ? 'PASSED ✅' : 'FAILED ❌'}`);
        console.log(`   Checks: ${result.verification.checks.length}`);

        const failed = result.verification.checks.filter((c) => !c.passed);
        if (failed.length > 0) {
          console.log(`   Failed: ${failed.length}`);
          for (const check of failed) {
            console.log(`      ❌ ${check.checkId}: ${check.message}`);
          }
        }
        console.log('');
      }

      // Display LLM metrics
      console.log('📈 LLM Metrics:');
      const metrics = router.getMetricsSummary();
      console.log(`   Total Calls: ${metrics.totalCalls}`);
      console.log(`   Successful: ${metrics.successfulCalls}`);
      console.log(`   Failed: ${metrics.failedCalls}`);
      console.log(`   Total Tokens: ${metrics.totalTokens.toLocaleString()}`);
      console.log(`   Avg Latency: ${Math.round(metrics.averageLatencyMs)}ms`);
      console.log('\n   Provider Breakdown:');
      for (const [provider, count] of Object.entries(metrics.providerBreakdown)) {
        console.log(`      ${provider}: ${count} calls`);
      }
      console.log('');

      // Display formatted report
      console.log('='.repeat(60));
      console.log('📄 DETAILED REPORT');
      console.log('='.repeat(60) + '\n');
      console.log(roma.formatResult(result, 'text'));
    } else {
      console.log('❌ FAILURE: Execution failed\n');
      console.log(`Error: ${result.error}\n`);

      if (result.execution) {
        const failed = result.execution.results.filter((r) => !r.success);
        console.log(`Failed tasks (${failed.length}):`);
        for (const task of failed) {
          console.log(`  ❌ ${task.taskId}: ${task.error}`);
        }
      }
    }

    console.log('\n' + '='.repeat(60));
    console.log('🎉 Build completed!');
    console.log('='.repeat(60));

    process.exit(result.success ? 0 : 1);
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
