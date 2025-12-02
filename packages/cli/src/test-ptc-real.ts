#!/usr/bin/env node
/**
 * Direct test of PtcExecutorReal - generates files from templates
 */
import { join } from 'path';
import { fileURLToPath } from 'url';
import { dirname } from 'path';
import { PtcExecutorReal } from '@roma/ptc';
import type { ScaffoldingSpec } from '@roma/schemas';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

async function main() {
  console.log('🚀 Testing PtcExecutorReal - File Generation\n');

  // Create output directory
  const outDir = join(__dirname, '../../../apps/test-onthisday');

  // Simple scaffolding spec to copy templates
  const spec: ScaffoldingSpec = {
    metadata: {
      featureId: 'test-feature',
      featureName: 'Test Feature',
      version: '1.0.0',
    },
    steps: [
      {
        type: 'command',
        description: 'Create output directory',
        spec: {
          command: 'mkdir',
          args: ['-p', outDir],
          expectedExitCode: 0,
          continueOnError: false,
        },
      },
      {
        type: 'command',
        description: 'Copy NestJS template',
        spec: {
          command: 'cp',
          args: ['-r', join(__dirname, '../../../templates/nestjs-minimal'), join(outDir, 'api')],
          expectedExitCode: 0,
          continueOnError: false,
        },
      },
      {
        type: 'command',
        description: 'Copy Next.js template',
        spec: {
          command: 'cp',
          args: ['-r', join(__dirname, '../../../templates/nextjs-minimal'), join(outDir, 'web')],
          expectedExitCode: 0,
          continueOnError: false,
        },
      },
    ],
    postconditions: [],
  };

  // Execute with PtcExecutorReal
  const executor = new PtcExecutorReal({
    workingDir: process.cwd(),
    verbose: true,
  });

  console.log('📦 Executing scaffolding spec...\n');
  const result = await executor.execute(spec);

  if (result.success) {
    console.log('\n✅ SUCCESS! Files generated:\n');
    console.log(`  📁 ${outDir}/api/    - NestJS API`);
    console.log(`  📁 ${outDir}/web/    - Next.js Web\n`);
    console.log('🔍 Next steps:');
    console.log(`  cd apps/test-onthisday/api && npm install && npm run build`);
    console.log(`  cd apps/test-onthisday/web && npm install && npm run build\n`);
  } else {
    console.log('\n❌ FAILED:', result.error);
    process.exit(1);
  }
}

main().catch((error) => {
  console.error('Fatal error:', error);
  process.exit(1);
});
