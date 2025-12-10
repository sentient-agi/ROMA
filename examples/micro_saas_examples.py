"""
Micro/Nano SaaS Examples - Built with ROMA + PTC

This file demonstrates specific Micro SaaS products that can be built
with the ROMA + PTC integration.
"""

# ============================================================================
# EXAMPLE 1: Email Validation API (Nano SaaS)
# ============================================================================

nano_saas_1 = """
Build a complete email validation SaaS:

Backend (FastAPI):
- REST API for email validation
- Check MX records, syntax, disposable domains
- Rate limiting per API key
- Usage tracking for billing

Authentication:
- API key generation and management
- User registration/login
- Email verification

Billing:
- Stripe subscription (3 tiers: Free, Pro, Enterprise)
- Usage metering (validations per month)
- Automatic tier upgrades

Database:
- User accounts
- API keys
- Validation logs
- Usage statistics

Features:
- Single email validation endpoint
- Bulk validation (CSV upload)
- Webhook for async results
- Dashboard API for stats
"""

# ROMA + PTC Output:
# - Complete FastAPI backend (200-300 lines)
# - Stripe integration
# - Database models
# - API key auth
# - Rate limiting
# Cost: ~$0.03-0.05
# Time: 30 seconds

# ============================================================================
# EXAMPLE 2: Screenshot-as-a-Service (Micro SaaS)
# ============================================================================

micro_saas_1 = """
Build a screenshot API service:

Core Features:
- Take screenshot of any URL
- Return image or PDF
- Custom viewport sizes
- Wait for JavaScript rendering

API:
- POST /screenshot with URL and options
- GET /screenshot/{id} for async results
- Webhook notification when ready

Tech:
- Playwright/Selenium for screenshots
- S3 for image storage
- Redis for job queue
- Celery workers for processing

User Management:
- API key authentication
- Usage quotas by plan
- Rate limiting

Billing:
- Stripe subscriptions
- Per-screenshot pricing
- Monthly limits

Admin:
- Usage analytics API
- User management endpoints
"""

# ROMA + PTC Output:
# - FastAPI service with Celery workers
# - Playwright integration
# - S3 upload logic
# - Stripe billing
# Cost: ~$0.05-0.07
# Time: 45 seconds

# ============================================================================
# EXAMPLE 3: Form Backend SaaS (Micro SaaS)
# ============================================================================

micro_saas_2 = """
Build a form backend service (like Formspree):

Features:
- Accept form submissions via POST
- Validate data with schemas
- Send email notifications
- Store submissions in database
- Export to CSV/JSON

API:
- Create form endpoints
- Configure validation rules
- Set notification emails
- View submissions

Integrations:
- Email (SendGrid, Mailgun)
- Slack webhooks
- Zapier webhooks
- Google Sheets export

User Management:
- Multi-form support per user
- Team collaboration
- Form analytics

Billing:
- Free tier (100 submissions/month)
- Pro tier (10,000 submissions/month)
- Usage-based overage
"""

# ROMA + PTC Output:
# - Complete backend API
# - Email integration
# - Validation engine
# - Export functionality
# Cost: ~$0.04-0.06
# Time: 40 seconds

# ============================================================================
# EXAMPLE 4: PDF Generation API (Nano SaaS)
# ============================================================================

nano_saas_2 = """
Build PDF generation API:

Core:
- HTML to PDF conversion
- Template system (Jinja2)
- Custom styling
- Header/footer support

API:
- POST /generate with HTML or template
- GET /pdf/{id} for async results
- Template management endpoints

Features:
- Pre-built templates (invoice, receipt, report)
- Custom template upload
- Variable substitution
- Batch generation

Storage:
- S3 for generated PDFs
- Redis for job queue
- PostgreSQL for metadata

Billing:
- Per-PDF pricing
- Monthly subscriptions
- API key based
"""

# ROMA + PTC Output:
# - FastAPI + Celery
# - WeasyPrint/wkhtmltopdf integration
# - Template engine
# - S3 storage
# Cost: ~$0.03-0.05
# Time: 35 seconds

# ============================================================================
# Complete Micro SaaS Stack Template
# ============================================================================

complete_micro_saas = """
Build a complete Micro SaaS foundation:

Backend (FastAPI):
- RESTful API with OpenAPI docs
- JWT authentication
- API key management
- Rate limiting middleware
- CORS configuration

Database (PostgreSQL):
- User accounts
- Organizations/teams
- Subscriptions
- Usage logs
- API keys

Billing (Stripe):
- Subscription management
- Usage-based pricing
- Webhook handlers
- Invoice generation
- Payment methods

Features:
- User registration/login
- Email verification
- Password reset
- Team invitations
- Role-based access (owner/admin/member)

Admin:
- Usage analytics
- User management
- Feature flags
- Audit logs

Infrastructure:
- Docker configuration
- CI/CD with GitHub Actions
- Environment config
- Database migrations (Alembic)
"""

# ROMA + PTC Output:
# - 1,000+ lines of production code
# - Complete authentication system
# - Stripe integration
# - Database models and migrations
# - Docker setup
# Cost: ~$0.08-0.12
# Time: 60-90 seconds

# This becomes your foundation - then add your unique feature on top!

# ============================================================================
# Deployment Capabilities
# ============================================================================

deployment_configs = """
Generate deployment configurations:

Docker:
- Dockerfile
- docker-compose.yml
- .dockerignore

CI/CD:
- GitHub Actions workflows
- GitLab CI pipelines
- Build and test scripts

Cloud:
- Terraform configs (AWS, GCP, Azure)
- CloudFormation templates
- Kubernetes manifests
- Heroku Procfile

Monitoring:
- Logging configuration
- Error tracking (Sentry)
- Health check endpoints
- Metrics collection
"""

# Note: ROMA + PTC generates configs, but actual deployment
# requires manual execution or CI/CD pipeline
