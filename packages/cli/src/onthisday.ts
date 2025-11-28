#!/usr/bin/env node
/**
 * OnThisDay Demo - End-to-end ROMA workflow
 *
 * This script demonstrates the complete ROMA + SaaS Builder pipeline
 * using the OnThisDay micro-SaaS example.
 */

import { readFileSync, writeFileSync, mkdirSync } from 'fs';
import { join, dirname } from 'path';
import { fileURLToPath } from 'url';
import { ROMA } from '@roma/core';
import { SaaSBuilder } from '@roma/builder';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

const EXAMPLES_DIR = join(__dirname, '../../examples/onthisday');
const OUTPUT_DIR = join(__dirname, '../../examples/out/onthisday');

async function main() {
  console.log('╔════════════════════════════════════════════════════════════╗');
  console.log('║  ROMA Multi-Agent SaaS Builder - OnThisDay Demo           ║');
  console.log('╚════════════════════════════════════════════════════════════╝\n');

  try {
    // Step 1: Load OnThisDay intake
    console.log('📥 Step 1: Loading intake specification...');
    const intakeJson = readFileSync(join(EXAMPLES_DIR, 'intake.json'), 'utf-8');
    const intake = JSON.parse(intakeJson);
    console.log(`   ✅ Loaded intake for: ${intake.metadata.appName}`);
    console.log(`   Features: ${intake.requirements.features.length}`);
    console.log('');

    // Step 2: Initialize ROMA with Builder interface
    console.log('🤖 Step 2: Initializing ROMA...');
    const builder = new SaaSBuilder();

    const roma = new ROMA({
      verbose: true,
      dryRun: false,
      builderInterface: {
        intake: async (input: any) => {
          console.log('   [Builder] Processing intake...');
          return intake;
        },
        architecture: async (intakeData: any) => {
          console.log('   [Builder] Generating architecture...');
          return await builder.architecture(intakeData);
        },
        featureGraph: async (intakeData: any, architecture: any) => {
          console.log('   [Builder] Building feature graph...');
          return await builder.featureGraph(intakeData, architecture);
        },
        scaffolding: async (featureGraph: any, architecture: any) => {
          console.log('   [Builder] Generating scaffolding specs...');
          return await builder.scaffolding(featureGraph, architecture);
        },
      },
    });
    console.log('   ✅ ROMA initialized\n');

    // Step 3: Run ROMA solve
    console.log('⚡ Step 3: Running ROMA solve...');
    console.log('   Goal: Build OnThisDay micro-SaaS application\n');

    const result = await roma.solve(
      'Build the OnThisDay micro-SaaS application with authentication, daily events feed, favorites, billing, and admin dashboard',
      {
        rawRequirements: intake,
      }
    );

    console.log('\n' + '='.repeat(60));
    console.log('📊 EXECUTION RESULTS');
    console.log('='.repeat(60) + '\n');

    // Step 4: Display results
    if (result.success) {
      console.log('✅ SUCCESS: All tasks completed successfully\n');

      if (result.atomization) {
        console.log('🔍 Atomization:');
        console.log(`   Type: ${result.atomization.isAtomic ? 'Atomic' : 'Composite'}`);
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

        // Save artifacts
        console.log('💾 Saving artifacts...');
        await saveArtifacts(result.aggregation.artifacts);
        console.log(`   ✅ Artifacts saved to: ${OUTPUT_DIR}\n`);

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
    console.log('🎉 Demo completed!');
    console.log('='.repeat(60));

    process.exit(result.success ? 0 : 1);
  } catch (error) {
    console.error('\n❌ Fatal error:', error);
    process.exit(1);
  }
}

async function saveArtifacts(artifacts: Record<string, any>): Promise<void> {
  // Create output directory
  mkdirSync(OUTPUT_DIR, { recursive: true });

  // Save each artifact as JSON
  for (const [key, value] of Object.entries(artifacts)) {
    const filename = `${key}.json`;
    const filepath = join(OUTPUT_DIR, filename);
    writeFileSync(filepath, JSON.stringify(value, null, 2));
  }

  // Create a summary file
  const summary = {
    generatedAt: new Date().toISOString(),
    artifacts: Object.keys(artifacts),
    description: 'ROMA execution artifacts for OnThisDay micro-SaaS',
  };

  writeFileSync(join(OUTPUT_DIR, 'summary.json'), JSON.stringify(summary, null, 2));

  // Create README
  const readme = `# OnThisDay - Generated Artifacts

Generated by ROMA Multi-Agent SaaS Builder on ${new Date().toISOString()}

## Artifacts

${Object.keys(artifacts)
  .map((key) => `- **${key}.json** - ${getArtifactDescription(key)}`)
  .join('\n')}

## Next Steps

1. Review the generated specifications
2. Set up execution environment (Docker, etc.)
3. Run the scaffolding specs via PTC/MCP
4. Deploy the application

## Structure

\`\`\`
onthisday/
├── intake.json          - Requirements specification
├── architecture.json    - System architecture
├── featureGraph.json    - Feature dependency graph
├── scaffoldingSpecs/    - Per-feature execution specs
└── summary.json         - Execution summary
\`\`\`
`;

  writeFileSync(join(OUTPUT_DIR, 'README.md'), readme);
}

function getArtifactDescription(key: string): string {
  const descriptions: Record<string, string> = {
    intake: 'Requirements and feature specifications',
    architecture: 'System architecture and infrastructure design',
    featureGraph: 'Feature dependency graph with execution stages',
    scaffoldingSpecs: 'Detailed execution specifications for each feature',
  };
  return descriptions[key] || 'Generated artifact';
}

// Run if executed directly
if (import.meta.url === `file://${process.argv[1]}`) {
  main().catch((error) => {
    console.error('Unhandled error:', error);
    process.exit(1);
  });
}
