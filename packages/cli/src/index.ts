#!/usr/bin/env node
/**
 * ROMA Builder CLI
 *
 * Main entry point for the ROMA Multi-Agent SaaS Builder CLI
 */

import { readFileSync } from 'fs';
import { join } from 'path';

const packageJson = JSON.parse(readFileSync(join(__dirname, '../package.json'), 'utf-8'));

function printHelp() {
  console.log(`
╔════════════════════════════════════════════════════════════╗
║  ROMA Multi-Agent SaaS Builder v${packageJson.version.padEnd(27)}║
╚════════════════════════════════════════════════════════════╝

A production-ready implementation of ROMA + SaaS Builder v2
+ PTC/MCP for autonomous micro-SaaS generation.

USAGE:
  roma-builder <command> [options]

COMMANDS:
  onthisday        Run the OnThisDay example end-to-end
  build <intake>   Build a SaaS from an intake file
  validate <file>  Validate an intake/architecture/graph file
  help            Show this help message
  version         Show version information

EXAMPLES:
  # Run OnThisDay demo
  roma-builder onthisday

  # Build from intake file
  roma-builder build ./my-app-intake.json

  # Validate an intake file
  roma-builder validate ./intake.json

ENVIRONMENT:
  ROMA_VERBOSE=1         Enable verbose logging
  ROMA_DRY_RUN=1         Run in dry-run mode (no actual execution)
  ROMA_OUTPUT_DIR=<dir>  Set output directory

For more information, visit: https://github.com/sentient-agi/ROMA
`);
}

function printVersion() {
  console.log(`ROMA Builder v${packageJson.version}`);
}

async function main() {
  const args = process.argv.slice(2);
  const command = args[0];

  switch (command) {
    case 'onthisday':
      // Dynamic import to avoid loading unless needed
      const { default: onthisday } = await import('./onthisday.js');
      break;

    case 'help':
    case '--help':
    case '-h':
    case undefined:
      printHelp();
      break;

    case 'version':
    case '--version':
    case '-v':
      printVersion();
      break;

    default:
      console.error(`Unknown command: ${command}\n`);
      printHelp();
      process.exit(1);
  }
}

main().catch((error) => {
  console.error('Fatal error:', error);
  process.exit(1);
});
