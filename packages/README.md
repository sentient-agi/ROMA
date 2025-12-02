# ROMA Multi-Agent SaaS Builder (TypeScript)

Production-quality implementation of ROMA + SaaS Builder v2 + PTC/MCP execution harness for autonomous micro-SaaS generation.

## Architecture

This is a monorepo containing:

- **schemas/** - Shared TypeScript interfaces and Zod validators for all contracts
- **roma/** - ROMA orchestrator (Atomizer, Planner, Executor, Aggregator, Verifier)
- **builder/** - SaaS Builder v2 modes (intake, architecture, feature graph, scaffolding)
- **ptc/** - PTC/MCP integration layer for sandboxed code execution
- **examples/** - Reference implementations (OnThisDay, etc.)
- **cli/** - Command-line interface for running the system

## Quick Start

```bash
# Install dependencies
pnpm install

# Run OnThisDay example end-to-end
pnpm roma:onthisday

# Build all packages
pnpm build

# Run tests
pnpm test
```

## Workflow

1. **Intake** → Collect requirements as structured JSON
2. **Architecture** → Generate system design from intake
3. **Feature Graph** → Build dependency graph of features
4. **Scaffolding** → Generate execution specs for each feature
5. **Execution** → Run specs via PTC/MCP in sandbox
6. **Verification** → Validate output against postconditions

## Example: OnThisDay

See `examples/onthisday/` for a complete micro-SaaS example including:
- `intake.json` - Requirements specification
- `architecture.json` - System architecture
- `feature_graph.json` - Feature dependency graph
- `scaffolding_spec.json` - Execution specifications

## Development

Each package is independently buildable and testable:

```bash
cd packages/schemas
pnpm test

cd packages/roma
pnpm build
```

## Integration with Python ROMA

This TypeScript implementation works alongside the existing Python ROMA framework in `src/roma_dspy/`. Both can be used independently or together via MCP.
