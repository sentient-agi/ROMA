# OnThisDay - Example Micro-SaaS

This directory contains a complete example of ROMA's output for building a micro-SaaS application called "OnThisDay".

## Overview

OnThisDay is a SaaS application that displays historical events that happened on the current day. It includes:

- **User Authentication** - JWT-based auth with registration/login
- **Daily Events Feed** - Historical events for the current date
- **Favorites** - Users can save their favorite events
- **Subscription Billing** - Stripe integration with free/pro tiers
- **Admin Dashboard** - Manage users and events

## Files

### 1. `intake.json`
Requirements specification generated from natural language or structured input. Includes:
- Feature definitions
- Security requirements (RBAC, encryption, GDPR compliance)
- Billing configuration (Stripe, subscription tiers)
- Technical constraints (Node.js, Fastify, PostgreSQL)

### 2. `architecture.json`
System architecture design including:
- Service specifications (API server, frontend SPA, cron workers)
- Database schema (users, historical_events, favorites tables)
- API contracts (REST endpoints with request/response schemas)
- Infrastructure (Redis cache, Docker deployment)
- Security & observability configurations

### 3. `feature_graph.json`
Dependency graph of features with execution ordering:
- 8 features organized into 6 execution stages
- Dependencies between features (hard, soft, data)
- Parallelization opportunities
- Critical path analysis

### 4. `scaffolding_auth.json`
Detailed execution specification for the "auth" feature:
- Secret references (JWT_SECRET, DB_PASSWORD)
- Preconditions (database running, tables exist)
- Execution steps (file operations, templates, commands)
- Tests (unit, integration)
- Postconditions (files exist, API responds, tests pass)
- Rollback specification
- Idempotency configuration

## Workflow

```
1. intake.json → Collected requirements
   ↓
2. architecture.json → Generated architecture
   ↓
3. feature_graph.json → Dependency analysis
   ↓
4. scaffolding_*.json → Per-feature execution specs
   ↓
5. Execution via PTC/MCP → Actual code generation
   ↓
6. Verification → Postconditions checked
```

## Running This Example

```bash
# From packages/cli
pnpm run onthisday
```

This will:
1. Load the intake JSON
2. Validate against ArchitectureSchema
3. Process the feature graph
4. Generate scaffolding specs for each feature
5. Simulate execution (without actually running PTC yet)
6. Verify all postconditions
7. Generate execution logs

## Expected Output

```
examples/out/onthisday/
├── backend/
│   ├── src/
│   │   ├── models/
│   │   │   └── user.model.ts
│   │   ├── services/
│   │   │   └── auth/
│   │   │       └── auth.service.ts
│   │   ├── middleware/
│   │   │   └── jwt.middleware.ts
│   │   └── routes/
│   │       └── auth.routes.ts
│   ├── package.json
│   └── .env.example
├── frontend/
│   └── src/
│       └── ...
├── docker-compose.yml
└── README.md
```

## Key Features Demonstrated

- ✅ Comprehensive security requirements (RBAC, encryption, GDPR)
- ✅ Multi-tier billing (free/pro with trial)
- ✅ Complex feature dependencies
- ✅ Idempotent execution with rollback
- ✅ Secret management
- ✅ Postcondition verification
- ✅ Test integration
- ✅ Parallel execution opportunities

## Next Steps

This example can be extended with:
- Real PTC/MCP execution
- LLM-based template generation
- Contract verification
- Multi-environment deployment
- Monitoring and observability
