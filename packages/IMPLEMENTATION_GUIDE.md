# ROMA Multi-Agent SaaS Builder - Implementation Guide

This document provides a comprehensive guide to the TypeScript implementation of ROMA + SaaS Builder v2 + PTC/MCP.

## Overview

This monorepo contains a production-ready implementation of:

1. **ROMA Orchestrator** - Recursive meta-agent with Atomizer, Planner, Executor, Aggregator, Verifier
2. **SaaS Builder v2** - Domain-specific SaaS decomposition and scaffolding
3. **PTC/MCP Integration** - Programmatic Tool Calling with Model Context Protocol
4. **Type-Safe Schemas** - Zod-validated TypeScript interfaces for all contracts
5. **End-to-End Example** - Complete OnThisDay micro-SaaS demonstration

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     User Goal / Request                      │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│  ROMA Orchestrator (@roma/core)                              │
│  ┌──────────┬──────────┬──────────┬───────────┬──────────┐  │
│  │Atomizer  │ Planner  │ Executor │Aggregator │ Verifier │  │
│  └──────────┴──────────┴──────────┴───────────┴──────────┘  │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│  SaaS Builder v2 (@roma/builder)                             │
│  ┌─────────┬──────────────┬──────────────┬──────────────┐   │
│  │ Intake  │Architecture  │Feature Graph │ Scaffolding  │   │
│  └─────────┴──────────────┴──────────────┴──────────────┘   │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│  PTC/MCP Layer (@roma/ptc)                                   │
│  ┌──────────┬──────────┬──────────┬──────────┐              │
│  │Executor  │ Sandbox  │  Tools   │ Secrets  │              │
│  └──────────┴──────────┴──────────┴──────────┘              │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│              Generated Application Code                      │
└─────────────────────────────────────────────────────────────┘
```

## Project Structure

```
packages/
├── schemas/          # @roma/schemas - Shared TypeScript interfaces + Zod validators
│   ├── src/
│   │   ├── intake.ts           # IntakeSchema with security, multi-tenancy
│   │   ├── architecture.ts     # ArchitectureSchema with infrastructure
│   │   ├── feature-graph.ts    # FeatureGraphSchema with dependencies
│   │   ├── scaffolding.ts      # ScaffoldingSpec with idempotency, secrets
│   │   ├── roma-workflow.ts    # ROMA task DAG schemas
│   │   └── index.ts            # Exports
│   └── tests/                  # Schema validation tests
│
├── roma/             # @roma/core - ROMA orchestrator
│   ├── src/
│   │   ├── atomizer.ts         # Decides atomic vs composite
│   │   ├── planner.ts          # Builds task DAG
│   │   ├── executor.ts         # Executes tasks
│   │   ├── aggregator.ts       # Combines results
│   │   ├── verifier.ts         # Validates outputs
│   │   ├── roma.ts             # Main ROMA class
│   │   └── index.ts            # Exports
│   └── tests/                  # Unit tests
│
├── builder/          # @roma/builder - SaaS Builder v2
│   ├── src/
│   │   ├── intake.ts           # Intake mode
│   │   ├── architecture.ts     # Architecture mode
│   │   ├── feature-graph.ts    # Feature graph mode
│   │   ├── scaffolding.ts      # Scaffolding mode
│   │   └── index.ts            # SaaSBuilder class
│   └── tests/                  # Unit tests
│
├── ptc/              # @roma/ptc - PTC/MCP integration
│   ├── src/
│   │   ├── interfaces.ts       # Core interfaces (Tool, Sandbox, etc.)
│   │   ├── executor-stub.ts    # Stub implementation
│   │   ├── secret-provider-env.ts  # Environment-based secrets
│   │   └── index.ts            # Exports
│   └── README.md               # PTC integration guide
│
├── examples/         # Example applications
│   ├── onthisday/              # OnThisDay micro-SaaS
│   │   ├── intake.json         # Requirements
│   │   ├── architecture.json   # Architecture
│   │   ├── feature_graph.json  # Feature graph
│   │   ├── scaffolding_auth.json  # Auth scaffolding spec
│   │   └── README.md           # Example documentation
│   └── out/                    # Generated outputs
│
├── cli/              # @roma/cli - Command-line interface
│   ├── src/
│   │   ├── onthisday.ts        # OnThisDay demo script
│   │   └── index.ts            # CLI entry point
│   └── README.md               # CLI usage guide
│
├── package.json      # Workspace configuration
├── tsconfig.json     # Base TypeScript config
└── README.md         # This file
```

## Key Design Decisions

### 1. TypeScript + Zod for Type Safety

All schemas are defined using Zod, providing:
- Runtime validation
- TypeScript type inference
- Error messages
- Easy serialization/deserialization

### 2. Monorepo with pnpm Workspaces

Benefits:
- Shared dependencies
- Cross-package type safety
- Independent versioning
- Easy to test integrations

### 3. Stub-First Development

PTC/MCP layer uses stubs initially:
- Enables rapid prototyping
- Clear interfaces for future implementation
- Easy to swap with real implementations

### 4. Separation of Concerns

- **ROMA**: Orchestration logic only
- **Builder**: Domain-specific SaaS logic
- **PTC**: Execution and tooling
- **Schemas**: Shared contracts

## Workflow Example

Using OnThisDay as an example:

```
1. User provides goal:
   "Build OnThisDay micro-SaaS with auth, events feed, favorites, billing"

2. ROMA Atomizer:
   → Determines this is COMPOSITE (requires planning)

3. ROMA Planner:
   → Creates 8-task DAG:
     - collect_intake
     - design_architecture
     - generate_feature_graph
     - generate_scaffolding_specs
     - execute_scaffolding
     - run_integration_tests
     - verify_postconditions
     - aggregate_results

4. ROMA Executor:
   → Executes each task via Builder interface
   → collect_intake: Returns OnThisDay intake.json
   → design_architecture: Generates architecture.json (API server, DB, frontend)
   → generate_feature_graph: Builds dependency graph (8 features, 6 stages)
   → generate_scaffolding_specs: Creates execution specs for each feature
   → execute_scaffolding: (Stubbed - would call PTC/MCP)
   → run_integration_tests: (Stubbed)
   → verify_postconditions: Validates all outputs
   → aggregate_results: Combines all artifacts

5. ROMA Aggregator:
   → Combines results into summary
   → Generates recommendations
   → Calculates metrics

6. ROMA Verifier:
   → Validates all artifacts against schemas
   → Checks postconditions
   → Reports any failures

7. Output:
   → examples/out/onthisday/
     - intake.json
     - architecture.json
     - featureGraph.json
     - scaffoldingSpecs.json
     - summary.json
     - README.md
```

## Running the Demo

```bash
# Install dependencies
cd packages
pnpm install

# Run OnThisDay demo
pnpm roma:onthisday

# Or from cli package
cd cli
pnpm run onthisday
```

## Testing

```bash
# Test schemas
cd packages/schemas
pnpm test

# Test all packages
cd packages
pnpm test
```

## Extending

### Adding a New Feature Type

1. Update `FeatureSpecSchema` in `schemas/src/intake.ts`
2. Add mapping logic in `builder/src/feature-graph.ts`
3. Generate appropriate scaffolding in `builder/src/scaffolding.ts`

### Adding a New Execution Step Type

1. Update step union in `schemas/src/scaffolding.ts`
2. Add execution logic in `ptc/src/executor-stub.ts` (or real executor)
3. Add postcondition type if needed

### Implementing Real PTC Execution

1. Create new class implementing `PtcExecutor` interface
2. Integrate with sandbox (Docker, E2B, etc.)
3. Implement tool execution with retry logic
4. Add secret management (Vault, AWS Secrets Manager, etc.)
5. Implement postcondition verification
6. Add rollback support
7. Replace `PtcExecutorStub` in executor options

## Best Practices

### Schema Design

- Always provide default values where sensible
- Use discriminated unions for step types
- Add descriptions for documentation
- Keep schemas DRY with shared types

### Error Handling

- Validate all inputs with schemas
- Provide clear error messages
- Use severity levels (critical, error, warning, info)
- Implement retry logic with exponential backoff

### Idempotency

- All file operations should be idempotent
- Check state before execution
- Store execution logs
- Support resume from checkpoint

### Security

- Never store secrets in artifacts
- Use secret references, not values
- Validate all external inputs
- Sandbox all code execution

## Next Steps

1. **Implement Real PTC Executor**
   - Docker-based sandbox
   - Real file operations
   - Command execution with retry
   - Template rendering (Jinja2, etc.)

2. **Add LLM Integration**
   - Use LLM for intake generation from natural language
   - Use LLM for architecture decisions
   - Use LLM for template generation

3. **Add Contract Verification**
   - API contract testing
   - Database schema validation
   - Integration testing

4. **Implement Observability**
   - Structured logging
   - Metrics collection
   - Tracing integration
   - Progress tracking

5. **Add More Examples**
   - Different app types (e-commerce, CRM, etc.)
   - Different architectures (serverless, microservices)
   - Different tech stacks

## Troubleshooting

### "Cannot find module '@roma/...'"

Run `pnpm install` from the `packages/` directory.

### "Zod validation failed"

Check the error details for which field failed validation. Ensure your JSON matches the schema.

### "Execution failed"

Check the execution logs for detailed error messages. Most likely a schema validation issue or missing dependency.

## Contributing

1. Follow the existing code structure
2. Add tests for new features
3. Update schemas for new data types
4. Document all public APIs
5. Run `pnpm test` before committing

## License

See LICENSE in the root directory.
