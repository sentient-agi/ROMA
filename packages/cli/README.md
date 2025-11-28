# @roma/cli - ROMA Builder CLI

Command-line interface for the ROMA Multi-Agent SaaS Builder.

## Installation

```bash
cd packages/cli
pnpm install
```

## Usage

### Run OnThisDay Demo

The easiest way to see ROMA in action:

```bash
pnpm run onthisday
```

This will:
1. Load the OnThisDay intake specification
2. Initialize ROMA with the SaaS Builder interface
3. Run the complete pipeline (atomization → planning → execution → aggregation → verification)
4. Save all generated artifacts to `examples/out/onthisday/`

### Expected Output

```
╔════════════════════════════════════════════════════════════╗
║  ROMA Multi-Agent SaaS Builder - OnThisDay Demo           ║
╚════════════════════════════════════════════════════════════╝

📥 Step 1: Loading intake specification...
   ✅ Loaded intake for: OnThisDay
   Features: 5

🤖 Step 2: Initializing ROMA...
   ✅ ROMA initialized

⚡ Step 3: Running ROMA solve...
   Goal: Build OnThisDay micro-SaaS application

[ROMA] Starting ROMA solve...
[ROMA] Atomization result: Composite (build_saas_app)
[ROMA] Plan created: 8 tasks, 8 stages
[Executor] Executing stage 1/8...
[Builder] Processing intake...
[Executor] Executing stage 2/8...
[Builder] Generating architecture...
...

============================================================
📊 EXECUTION RESULTS
============================================================

✅ SUCCESS: All tasks completed successfully

🔍 Atomization:
   Type: Composite
   Reasoning: Building a SaaS application requires multiple phases

⏱️  Execution:
   Duration: 1234ms
   Tasks: 8
   Success Rate: 8/8

📦 Artifacts Generated:
   ✓ intake
   ✓ architecture
   ✓ featureGraph
   ✓ scaffoldingSpecs

💾 Saving artifacts...
   ✅ Artifacts saved to: examples/out/onthisday

💡 Recommendations:
   • All tasks completed successfully - ready for deployment
   • Scaffolding specs generated - ready for execution

✓ Verification:
   Status: PASSED ✅
   Checks: 4
```

### Generated Artifacts

After running, check `packages/examples/out/onthisday/`:

```
onthisday/
├── intake.json           - Validated intake specification
├── architecture.json     - Generated system architecture
├── featureGraph.json     - Feature dependency graph
├── scaffoldingSpecs.json - Array of scaffolding specs for each feature
├── summary.json          - Execution summary
└── README.md             - Next steps and documentation
```

## Commands

### `pnpm run onthisday`

Run the complete OnThisDay example end-to-end.

### `pnpm build`

Build the CLI for distribution.

### `pnpm test`

Run tests (when implemented).

## Environment Variables

- `ROMA_VERBOSE=1` - Enable verbose logging
- `ROMA_DRY_RUN=1` - Dry run mode (no actual execution)
- `ROMA_OUTPUT_DIR` - Custom output directory

## Architecture

The CLI orchestrates the following flow:

```
User Input → ROMA → Builder → PTC/MCP → Output

Where:
- ROMA: Orchestrator (Atomizer, Planner, Executor, Aggregator, Verifier)
- Builder: SaaS Builder v2 (intake, architecture, feature graph, scaffolding)
- PTC/MCP: Execution layer (stubbed for now)
```

## Next Steps

1. **Review Generated Artifacts** - Check the output directory
2. **Customize Templates** - Add your own templates to `examples/templates/`
3. **Implement Real PTC** - Replace `PtcExecutorStub` with real execution
4. **Add Custom Builders** - Extend the Builder for your domain
5. **Deploy** - Use the generated specs to scaffold your application

## Troubleshooting

### "Module not found"

Make sure you've run `pnpm install` in the root `packages/` directory.

### "Cannot find examples"

Run from the `packages/cli` directory, or update paths in the script.

### "Execution failed"

Check that all dependencies are installed and schemas are valid.

## Development

To add a new command:

1. Create a new file in `src/` (e.g., `src/my-command.ts`)
2. Add the command to `src/index.ts`
3. Update package.json scripts if needed
4. Test with `tsx src/index.ts my-command`
