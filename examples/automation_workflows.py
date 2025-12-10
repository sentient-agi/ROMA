"""
Automation Workflow Examples - n8n/Zapier-style Systems

This demonstrates building automation workflow engines with ROMA + PTC.
"""

# ============================================================================
# EXAMPLE 1: Python Workflow Automation Engine
# ============================================================================

workflow_engine = """
Build a workflow automation engine (backend):

Core Engine:
- Workflow definition (JSON/YAML)
- Step-by-step execution
- Conditional branching
- Error handling and retries
- State management

Trigger Types:
- Webhook triggers
- Scheduled (cron)
- Event-based (database changes)
- Manual execution

Action Types (Nodes):
- HTTP requests (GET, POST, etc.)
- Database operations (CRUD)
- Email sending
- File operations
- Data transformations
- Delay/wait steps

Features:
- Variable passing between steps
- Data transformation (jmespath, jsonpath)
- Error paths and fallbacks
- Parallel execution support
- Workflow versioning

API:
- Create/update workflows
- Execute workflow
- Get execution status
- Execution history
- Logs and debugging

Integrations:
- Generic HTTP node (works with any API)
- Pre-built connectors:
  * Gmail, Slack, Discord
  * Stripe, PayPal
  * Airtable, Notion
  * GitHub, GitLab
  * AWS S3, Google Drive

Database:
- Workflows (definitions)
- Executions (history)
- Credentials (encrypted)
- Logs
"""

# ROMA + PTC Output:
# - Complete workflow execution engine (500+ lines)
# - Plugin system for connectors
# - Celery/RQ for async execution
# - API endpoints
# Cost: ~$0.06-0.09
# Time: 60 seconds

# ============================================================================
# EXAMPLE 2: Event-Driven Automation Platform
# ============================================================================

event_automation = """
Build an event-driven automation platform:

Event System:
- Event ingestion via webhooks
- Event filtering and routing
- Event transformation
- Event replay

Rules Engine:
- IF/THEN logic
- Conditional triggers
- Time-based conditions
- Threshold-based alerts

Actions:
- Send notifications (email, SMS, Slack)
- HTTP requests to webhooks
- Database updates
- Queue messages
- Trigger other workflows

Use Cases:
- "When Stripe payment succeeds, send welcome email and create user"
- "When form submitted, validate data and notify team on Slack"
- "Every hour, fetch API data and update database"
- "When error occurs, create ticket in Linear"

Storage:
- Event log (append-only)
- Rule definitions
- Execution history
- Retry queue
"""

# ROMA + PTC Output:
# - Event processing engine
# - Rules evaluation system
# - Action executor
# - Webhook receivers
# Cost: ~$0.05-0.08
# Time: 50 seconds

# ============================================================================
# EXAMPLE 3: Data Pipeline Orchestrator
# ============================================================================

data_orchestrator = """
Build a data pipeline orchestrator:

Pipeline Definition:
- DAG (directed acyclic graph) support
- Task dependencies
- Parallel task execution
- Conditional paths

Task Types:
- Extract from source (API, database, files)
- Transform (clean, validate, enrich)
- Load to destination
- Custom Python/SQL tasks

Features:
- Incremental processing
- Checkpointing
- Failure recovery
- Backfill support
- Scheduling (Airflow-like)

Monitoring:
- Task execution tracking
- Performance metrics
- Error alerting
- Data quality checks

API:
- Define pipelines
- Trigger runs
- Monitor status
- View logs
"""

# ROMA + PTC Output:
# - Pipeline execution engine
# - Task scheduler
# - Monitoring system
# - API endpoints
# Cost: ~$0.07-0.10
# Time: 70 seconds

# ============================================================================
# EXAMPLE 4: API Integration Platform
# ============================================================================

integration_platform = """
Build an API integration platform:

Core:
- Universal API client
- Authentication handling (OAuth, API key, JWT)
- Rate limiting and retries
- Response caching

Pre-built Integrations:
- Stripe: Payments, subscriptions, invoices
- Slack: Send messages, create channels
- Gmail: Send emails, read inbox
- Notion: Create pages, update databases
- Airtable: CRUD operations
- GitHub: Repos, issues, PRs

Features:
- Connection management (store credentials)
- Request templates
- Response transformation
- Batch operations
- Webhook forwarding

Developer Tools:
- API playground
- Request/response logging
- Debugging tools
"""

# ROMA + PTC Output:
# - Integration framework
# - OAuth flow handlers
# - API clients for each service
# - Connection management
# Cost: ~$0.08-0.12
# Time: 80 seconds

# ============================================================================
# Specific Automation Examples
# ============================================================================

# Example 1: CRM to Email Automation
crm_automation = """
When new lead in Airtable:
1. Validate email address
2. Enrich with Clearbit data
3. Add to SendGrid list
4. Send welcome email sequence
5. Create Slack notification
"""

# Example 2: Payment to Provisioning
payment_automation = """
When Stripe payment succeeds:
1. Create user account
2. Generate API key
3. Send welcome email
4. Post to Slack #new-customers
5. Add to analytics
"""

# Example 3: Support Ticket Routing
support_automation = """
When form submitted:
1. Validate input
2. Extract keywords
3. Route to correct team
4. Create Linear ticket
5. Send confirmation email
"""

# ============================================================================
# What ROMA + PTC Can Build vs. Can't
# ============================================================================

can_build = """
✅ CAN BUILD:
- Workflow execution engine (backend)
- API connectors and integrations
- Event processing system
- Scheduling and triggers
- Data transformation logic
- Error handling and retries
- REST API for workflow management
- Webhook receivers

⚠️ NEEDS REFINEMENT:
- Visual workflow builder UI
- Drag-and-drop interface
- Real-time execution visualization

❌ CANNOT BUILD (out of scope):
- Complex UI/UX design
- Visual workflow editor (can generate React components, needs polish)
"""

# ============================================================================
# Architecture Comparison
# ============================================================================

comparison = """
n8n/Zapier Architecture:
├── Visual Workflow Builder (frontend) ❌ ROMA can't build UI polish
├── Workflow Engine (backend) ✅ ROMA builds perfectly
├── Connector Framework ✅ ROMA builds perfectly
├── Execution Runtime ✅ ROMA builds perfectly
├── API Layer ✅ ROMA builds perfectly
└── Database Layer ✅ ROMA builds perfectly

Result: Can build 80% of n8n/Zapier functionality (the backend)
The 20% you need to add: Polished visual workflow builder UI
"""
